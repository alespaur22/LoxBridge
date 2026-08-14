import fs from 'node:fs/promises';
import process from 'node:process';
import { createInterface } from 'node:readline';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';


const SUPPORTED_TYPES = new Set([
  'boolean',
  'number',
  'enum',
]);


const WHITE_WARM_KELVIN = 2700;
const WHITE_COLD_KELVIN = 6500;
const LIGHT_MERGE_DELAY_MS = 120;


function writeEvent(event) {
  process.stdout.write(
    `${JSON.stringify(event)}\n`,
  );
}


function writeLog(message) {
  process.stderr.write(
    `[Homey realtime] ${message}\n`,
  );
}


async function loadConfig(configPath) {
  const source = await fs.readFile(
    configPath,
    'utf8',
  );

  const config = YAML.parse(source);

  if (!config?.homey?.ip) {
    throw new Error(
      'V konfiguraci chybí homey.ip.',
    );
  }

  if (!config?.homey?.token) {
    throw new Error(
      'V konfiguraci chybí homey.token.',
    );
  }

  if (!Array.isArray(config.devices)) {
    throw new Error(
      'V konfiguraci chybí devices.',
    );
  }

  return config;
}


function parseCapability(
  capabilityId,
  capabilityConfig,
) {
  if (typeof capabilityConfig === 'string') {
    return {
      key: capabilityConfig,
      type: null,
      values: [],
      setable: false,
    };
  }

  if (
    !capabilityConfig ||
    typeof capabilityConfig !== 'object'
  ) {
    return null;
  }

  return {
    key: capabilityConfig.key,
    type: capabilityConfig.type ?? null,
    values: Array.isArray(
      capabilityConfig.values,
    )
      ? capabilityConfig.values
      : [],
    setable:
      capabilityConfig.setable === true,
  };
}


function convertValue(
  value,
  capabilityConfig,
) {
  if (
    capabilityConfig.type !== 'enum'
  ) {
    return value;
  }

  const match =
    capabilityConfig.values.find(
      (enumValue) =>
        enumValue?.id === value,
    );

  if (!match) {
    throw new Error(
      `Enum hodnota "${value}" ` +
      'nemá číselné mapování.',
    );
  }

  return match.value;
}


function convertCommandValue(
  value,
  capabilityConfig,
) {
  if (
    capabilityConfig.type === 'boolean'
  ) {
    if (value === true || value === 1) {
      return true;
    }

    if (value === false || value === 0) {
      return false;
    }

    if (typeof value === 'string') {
      const normalized =
        value.trim().toLowerCase();

      if (
        ['1', 'true', 'on'].includes(
          normalized,
        )
      ) {
        return true;
      }

      if (
        ['0', 'false', 'off'].includes(
          normalized,
        )
      ) {
        return false;
      }
    }

    throw new Error(
      `Neplatná boolean hodnota: ${value}`,
    );
  }

  if (
    capabilityConfig.type === 'number'
  ) {
    const numberValue = Number(value);

    if (!Number.isFinite(numberValue)) {
      throw new Error(
        `Neplatná číselná hodnota: ${value}`,
      );
    }

    return numberValue;
  }

  if (
    capabilityConfig.type === 'enum'
  ) {
    const numericValue = Number(value);

    if (Number.isFinite(numericValue)) {
      const match =
        capabilityConfig.values.find(
          (enumValue) =>
            enumValue?.value ===
            numericValue,
        );

      if (match) {
        return match.id;
      }
    }

    const directMatch =
      capabilityConfig.values.find(
        (enumValue) =>
          enumValue?.id === value,
      );

    if (directMatch) {
      return directMatch.id;
    }

    throw new Error(
      `Enum hodnota "${value}" ` +
      'nemá mapování.',
    );
  }

  throw new Error(
    `Nepodporovaný typ capability: ` +
    `${capabilityConfig.type}`,
  );
}


function parseLoxoneRgb(value) {
  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    throw new Error(
      `Neplatná RGB hodnota: ${value}`,
    );
  }

  const packedValue = Math.round(numericValue);

  if (
    packedValue < 0 ||
    Math.abs(numericValue - packedValue) > 0.01
  ) {
    throw new Error(
      `RGB hodnota musí být celé kladné číslo: ${value}`,
    );
  }

  const packedText = String(packedValue);

  if (packedText.length > 9) {
    throw new Error(
      `RGB hodnota je příliš dlouhá: ${value}`,
    );
  }

  const normalized =
    packedText.padStart(9, '0');

  const blue = Number(
    normalized.slice(0, 3),
  );

  const green = Number(
    normalized.slice(3, 6),
  );

  const red = Number(
    normalized.slice(6, 9),
  );

  for (
    const [name, channel]
    of [
      ['R', red],
      ['G', green],
      ['B', blue],
    ]
  ) {
    if (
      !Number.isInteger(channel) ||
      channel < 0 ||
      channel > 100
    ) {
      throw new Error(
        `RGB kanál ${name} je mimo ` +
        `rozsah 0–100: ${channel}`,
      );
    }
  }

  return {
    red,
    green,
    blue,
  };
}


function rgbToHomeyHsv(
  red,
  green,
  blue,
) {
  const r = red / 100;
  const g = green / 100;
  const b = blue / 100;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;

  let hue = 0;

  if (delta !== 0) {
    if (max === r) {
      hue = ((g - b) / delta) % 6;
    } else if (max === g) {
      hue = ((b - r) / delta) + 2;
    } else {
      hue = ((r - g) / delta) + 4;
    }

    hue /= 6;

    if (hue < 0) {
      hue += 1;
    }
  }

  const saturation =
    max === 0
      ? 0
      : delta / max;

  return {
    hue,
    saturation,
    dim: max,
  };
}


function parseLoxoneLumitech(value) {
  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    throw new Error(
      `Neplatná Lumitech hodnota: ${value}`,
    );
  }

  const packedValue = Math.round(numericValue);

  if (
    packedValue < 0 ||
    Math.abs(numericValue - packedValue) > 0.01
  ) {
    throw new Error(
      `Lumitech hodnota musí být celé číslo: ${value}`,
    );
  }

  if (packedValue === 0) {
    return {
      brightness: 0,
      kelvin: null,
    };
  }

  const normalized =
    String(packedValue).padStart(9, '0');

  if (
    normalized.length !== 9 ||
    !normalized.startsWith('20')
  ) {
    throw new Error(
      `Neplatný Lumitech formát: ${value}`,
    );
  }

  const brightness = Number(
    normalized.slice(2, 5),
  );

  const kelvin = Number(
    normalized.slice(5, 9),
  );

  if (
    brightness < 0 ||
    brightness > 100
  ) {
    throw new Error(
      `Lumitech jas je mimo rozsah 0–100: ${brightness}`,
    );
  }

  if (
    !Number.isFinite(kelvin) ||
    kelvin <= 0
  ) {
    throw new Error(
      `Neplatná teplota bílé: ${kelvin}`,
    );
  }

  return {
    brightness,
    kelvin,
  };
}


function kelvinToHomeyTemperature(
  kelvin,
) {
  const clampedKelvin =
    Math.min(
      WHITE_COLD_KELVIN,
      Math.max(
        WHITE_WARM_KELVIN,
        kelvin,
      ),
    );

  return (
    WHITE_COLD_KELVIN -
    clampedKelvin
  ) / (
    WHITE_COLD_KELVIN -
    WHITE_WARM_KELVIN
  );
}


async function setTargetValue(
  target,
  value,
) {
  const homeyValue =
    convertCommandValue(
      value,
      target.capabilityConfig,
    );

  await target.device
    .setCapabilityValue(
      target.capabilityId,
      homeyValue,
    );

  return homeyValue;
}


function getConfiguredCommandTarget(
  deviceConfig,
  capabilityId,
  commandMap,
) {
  const rawConfig =
    deviceConfig.capabilities?.[
      capabilityId
    ];

  const capabilityConfig =
    parseCapability(
      capabilityId,
      rawConfig,
    );

  if (
    !capabilityConfig?.key ||
    capabilityConfig.setable !== true
  ) {
    return null;
  }

  return commandMap.get(
    capabilityConfig.key,
  ) ?? null;
}


function buildRgbCommandMap(
  config,
  commandMap,
) {
  const rgbCommandMap = new Map();

  for (
    const deviceConfig
    of config.devices
  ) {
    const onoff =
      getConfiguredCommandTarget(
        deviceConfig,
        'onoff',
        commandMap,
      );

    const dim =
      getConfiguredCommandTarget(
        deviceConfig,
        'dim',
        commandMap,
      );

    const hue =
      getConfiguredCommandTarget(
        deviceConfig,
        'light_hue',
        commandMap,
      );

    const saturation =
      getConfiguredCommandTarget(
        deviceConfig,
        'light_saturation',
        commandMap,
      );

    const mode =
      getConfiguredCommandTarget(
        deviceConfig,
        'light_mode',
        commandMap,
      );

    if (
      !onoff ||
      !dim ||
      !hue ||
      !saturation ||
      !mode
    ) {
      continue;
    }

    const rawOnOff =
      deviceConfig.capabilities?.onoff;

    const onoffConfig =
      parseCapability(
        'onoff',
        rawOnOff,
      );

    const onoffKey =
      onoffConfig?.key;

    if (
      typeof onoffKey !== 'string' ||
      !onoffKey.endsWith('_onoff')
    ) {
      continue;
    }

    const baseKey =
      onoffKey.slice(
        0,
        -'_onoff'.length,
      );

    rgbCommandMap.set(
      `${baseKey}_rgb`,
      {
        device: onoff.device,
        onoff,
        dim,
        hue,
        saturation,
        mode,
      },
    );
  }

  return rgbCommandMap;
}


function buildLumitechCommandMap(
  config,
  commandMap,
) {
  const lumitechCommandMap =
    new Map();

  for (
    const deviceConfig
    of config.devices
  ) {
    const onoff =
      getConfiguredCommandTarget(
        deviceConfig,
        'onoff',
        commandMap,
      );

    const dim =
      getConfiguredCommandTarget(
        deviceConfig,
        'dim',
        commandMap,
      );

    const temperature =
      getConfiguredCommandTarget(
        deviceConfig,
        'light_temperature',
        commandMap,
      );

    const mode =
      getConfiguredCommandTarget(
        deviceConfig,
        'light_mode',
        commandMap,
      );

    if (
      !onoff ||
      !dim ||
      !temperature ||
      !mode
    ) {
      continue;
    }

    const rawOnOff =
      deviceConfig.capabilities?.onoff;

    const onoffConfig =
      parseCapability(
        'onoff',
        rawOnOff,
      );

    const onoffKey =
      onoffConfig?.key;

    if (
      typeof onoffKey !== 'string' ||
      !onoffKey.endsWith('_onoff')
    ) {
      continue;
    }

    const baseKey =
      onoffKey.slice(
        0,
        -'_onoff'.length,
      );

    lumitechCommandMap.set(
      `${baseKey}_lumitech`,
      {
        device: onoff.device,
        onoff,
        dim,
        temperature,
        mode,
      },
    );
  }

  return lumitechCommandMap;
}


function getLightProfileState(
  states,
  device,
) {
  let state = states.get(
    device.id,
  );

  if (!state) {
    state = {
      device,
      rgb: null,
      lumitech: null,
      last_changed_mode: null,
      rgb_target: null,
      lumitech_target: null,
      timer: null,
      pending_results: [],
      apply_queue: Promise.resolve(),
    };

    states.set(
      device.id,
      state,
    );
  }

  return state;
}


function selectLightProfileMode(
  rgb,
  lumitech,
  lastChangedMode,
) {
  const rgbHsv =
    rgb
      ? rgbToHomeyHsv(
          rgb.red,
          rgb.green,
          rgb.blue,
        )
      : null;

  const rgbActive =
    rgbHsv !== null &&
    rgbHsv.dim > 0;

  const lumitechActive =
    lumitech !== null &&
    lumitech.brightness > 0;

  if (
    rgbActive &&
    lumitechActive
  ) {
    if (
      lastChangedMode === 'lumitech'
    ) {
      return {
        mode: 'lumitech',
        rgbHsv,
      };
    }

    return {
      mode: 'rgb',
      rgbHsv,
    };
  }

  if (rgbActive) {
    return {
      mode: 'rgb',
      rgbHsv,
    };
  }

  if (lumitechActive) {
    return {
      mode: 'lumitech',
      rgbHsv,
    };
  }

  return {
    mode: 'off',
    rgbHsv,
  };
}


async function applyLightProfileSnapshot(
  snapshot,
) {
  const selected =
    selectLightProfileMode(
      snapshot.rgb,
      snapshot.lumitech,
      snapshot.last_changed_mode,
    );

  if (selected.mode === 'rgb') {
    const target =
      snapshot.rgb_target;

    if (!target) {
      throw new Error(
        'Chybí RGB target pro světelný profil.',
      );
    }

    const hsv =
      selected.rgbHsv;

    await setTargetValue(
      target.mode,
      'color',
    );

    await setTargetValue(
      target.hue,
      hsv.hue,
    );

    await setTargetValue(
      target.saturation,
      hsv.saturation,
    );

    await setTargetValue(
      target.dim,
      hsv.dim,
    );

    await setTargetValue(
      target.onoff,
      true,
    );

    return {
      mode: 'color',
      hue: hsv.hue,
      saturation: hsv.saturation,
      dim: hsv.dim,
    };
  }

  if (
    selected.mode === 'lumitech'
  ) {
    const target =
      snapshot.lumitech_target;

    if (!target) {
      throw new Error(
        'Chybí Lumitech target pro světelný profil.',
      );
    }

    const lumitech =
      snapshot.lumitech;

    const dim =
      lumitech.brightness / 100;

    const temperature =
      kelvinToHomeyTemperature(
        lumitech.kelvin,
      );

    await setTargetValue(
      target.mode,
      'temperature',
    );

    await setTargetValue(
      target.temperature,
      temperature,
    );

    await setTargetValue(
      target.dim,
      dim,
    );

    await setTargetValue(
      target.onoff,
      true,
    );

    return {
      mode: 'temperature',
      brightness:
        lumitech.brightness,
      kelvin:
        lumitech.kelvin,
      dim,
      temperature,
    };
  }

  const offTarget =
    snapshot.rgb_target?.onoff ??
    snapshot.lumitech_target?.onoff;

  if (!offTarget) {
    throw new Error(
      'Chybí onoff target pro světelný profil.',
    );
  }

  await setTargetValue(
    offTarget,
    false,
  );

  return {
    mode: 'off',
  };
}


async function main() {
  const configPath = process.argv[2];

  if (!configPath) {
    throw new Error(
      'Chybí cesta ke konfiguraci.',
    );
  }

  const config = await loadConfig(
    configPath,
  );

  const address =
    `http://${config.homey.ip}`;

  writeLog(
    `Konfigurace: ${configPath}`,
  );

  writeLog(
    `Připojuji se k ${address}`,
  );

  const homeyApi =
    await HomeyAPI.createLocalAPI({
      address,
      token: config.homey.token,
    });

  writeLog(
    'Připojení k Homey bylo úspěšné.',
  );

  writeLog(
    'Načítám zařízení.',
  );

  const devices =
    await homeyApi.devices.getDevices();

  const devicesById = new Map();
  const devicesByName = new Map();

  for (
    const device
    of Object.values(devices)
  ) {
    devicesById.set(
      device.id,
      device,
    );

    devicesByName.set(
      device.name.toLocaleLowerCase(),
      device,
    );
  }

  const subscriptions = [];
  const commandMap = new Map();

  let skipped = 0;
  let missing = 0;

  for (
    const deviceConfig
    of config.devices
  ) {
    let device = null;

    if (deviceConfig.homey_id) {
      device =
        devicesById.get(
          deviceConfig.homey_id,
        ) ?? null;
    }

    if (
      !device &&
      deviceConfig.name
    ) {
      device =
        devicesByName.get(
          deviceConfig.name
            .toLocaleLowerCase(),
        ) ?? null;
    }

    if (!device) {
      writeEvent({
        type: 'warning',
        message:
          `Zařízení "${deviceConfig.name}" ` +
          'nebylo nalezeno.',
      });

      missing += 1;
      continue;
    }

    const capabilities =
      deviceConfig.capabilities ?? {};

    for (
      const [
        capabilityId,
        rawConfig,
      ]
      of Object.entries(capabilities)
    ) {
      const capabilityConfig =
        parseCapability(
          capabilityId,
          rawConfig,
        );

      if (!capabilityConfig) {
        missing += 1;
        continue;
      }

      if (
        capabilityConfig.type !== null &&
        !SUPPORTED_TYPES.has(
          capabilityConfig.type,
        )
      ) {
        skipped += 1;
        continue;
      }

      const loxoneKey =
        capabilityConfig.key;

      if (
        typeof loxoneKey !== 'string' ||
        !loxoneKey
      ) {
        missing += 1;
        continue;
      }

      const capability =
        device.capabilitiesObj?.[
          capabilityId
        ];

      if (!capability) {
        writeEvent({
          type: 'warning',
          message:
            `Zařízení "${device.name}" ` +
            `nemá capability "${capabilityId}".`,
        });

        missing += 1;
        continue;
      }

      if (
        capabilityConfig.setable === true &&
        capability.setable === true
      ) {
        commandMap.set(
          loxoneKey,
          {
            device,
            capabilityId,
            capabilityConfig,
          },
        );
      }

      try {
        const initialValue =
          convertValue(
            capability.value,
            capabilityConfig,
          );

        writeEvent({
          type: 'value',
          initial: true,
          device_name: device.name,
          device_id: device.id,
          capability_id: capabilityId,
          loxone_key: loxoneKey,
          value: initialValue,
        });

      } catch (error) {
        writeEvent({
          type: 'warning',
          message:
            `${device.name} / ${capabilityId}: ` +
            `${error.message}`,
        });
      }

      const instance =
        device.makeCapabilityInstance(
          capabilityId,
          (newValue) => {
            try {
              const convertedValue =
                convertValue(
                  newValue,
                  capabilityConfig,
                );

              writeEvent({
                type: 'value',
                initial: false,
                device_name: device.name,
                device_id: device.id,
                capability_id: capabilityId,
                loxone_key: loxoneKey,
                value: convertedValue,
              });

            } catch (error) {
              writeEvent({
                type: 'warning',
                message:
                  `${device.name} / ` +
                  `${capabilityId}: ` +
                  `${error.message}`,
              });
            }
          },
        );

      subscriptions.push(
        instance,
      );
    }
  }

  if (subscriptions.length === 0) {
    throw new Error(
      'Nevznikl žádný realtime odběr.',
    );
  }

  const rgbCommandMap =
    buildRgbCommandMap(
      config,
      commandMap,
    );


  const lumitechCommandMap =
    buildLumitechCommandMap(
      config,
      commandMap,
    );


  const lightProfileStates =
    new Map();


  function flushLightProfile(
    state,
  ) {
    const snapshot = {
      device: state.device,
      rgb: state.rgb,
      lumitech: state.lumitech,
      last_changed_mode:
        state.last_changed_mode,
      rgb_target:
        state.rgb_target,
      lumitech_target:
        state.lumitech_target,
      pending_results:
        state.pending_results.splice(0),
    };

    state.timer = null;

    state.apply_queue =
      state.apply_queue.then(
        async () => {
          try {
            const homeyValue =
              await applyLightProfileSnapshot(
                snapshot,
              );

            for (
              const pending
              of snapshot.pending_results
            ) {
              writeEvent({
                type: 'command_result',
                request_id:
                  pending.request_id,
                success: true,
                key:
                  pending.key,
                device_name:
                  snapshot.device.name,
                device_id:
                  snapshot.device.id,
                capability_id:
                  pending.capability_id,
                homey_value:
                  homeyValue,
              });
            }

          } catch (error) {
            for (
              const pending
              of snapshot.pending_results
            ) {
              writeEvent({
                type: 'command_result',
                request_id:
                  pending.request_id,
                success: false,
                key:
                  pending.key,
                device_name:
                  snapshot.device.name,
                capability_id:
                  pending.capability_id,
                message:
                  error?.message ??
                  String(error),
              });
            }
          }
        },
      );
  }


  function scheduleLightProfile(
    state,
  ) {
    if (state.timer) {
      clearTimeout(
        state.timer,
      );
    }

    state.timer =
      setTimeout(
        () => {
          flushLightProfile(
            state,
          );
        },
        LIGHT_MERGE_DELAY_MS,
      );
  }


  async function handleRgbCommand(
    command,
    key,
    target,
  ) {
    const requestId =
      command.request_id ?? null;

    try {
      const rgb =
        parseLoxoneRgb(
          command.value,
        );

      const state =
        getLightProfileState(
          lightProfileStates,
          target.device,
        );

      state.rgb = rgb;
      state.rgb_target = target;
      state.last_changed_mode = 'rgb';

      state.pending_results.push({
        request_id: requestId,
        key,
        capability_id: 'rgb',
      });

      scheduleLightProfile(
        state,
      );

    } catch (error) {
      writeEvent({
        type: 'command_result',
        request_id: requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id: 'rgb',
        message:
          error?.message ??
          String(error),
      });
    }
  }


  async function handleLumitechCommand(
    command,
    key,
    target,
  ) {
    const requestId =
      command.request_id ?? null;

    try {
      const lumitech =
        parseLoxoneLumitech(
          command.value,
        );

      const state =
        getLightProfileState(
          lightProfileStates,
          target.device,
        );

      state.lumitech = lumitech;
      state.lumitech_target = target;
      state.last_changed_mode =
        'lumitech';

      state.pending_results.push({
        request_id: requestId,
        key,
        capability_id: 'lumitech',
      });

      scheduleLightProfile(
        state,
      );

    } catch (error) {
      writeEvent({
        type: 'command_result',
        request_id: requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id: 'lumitech',
        message:
          error?.message ??
          String(error),
      });
    }
  }


  async function handleCommand(
    command,
  ) {
    const requestId =
      command.request_id ?? null;

    const key = command.key;

    if (
      typeof key !== 'string' ||
      !key
    ) {
      writeEvent({
        type: 'command_result',
        request_id: requestId,
        success: false,
        message:
          'Příkaz neobsahuje platný key.',
      });

      return;
    }

    const rgbTarget =
      rgbCommandMap.get(key);

    if (rgbTarget) {
      await handleRgbCommand(
        command,
        key,
        rgbTarget,
      );

      return;
    }

    const lumitechTarget =
      lumitechCommandMap.get(key);

    if (lumitechTarget) {
      await handleLumitechCommand(
        command,
        key,
        lumitechTarget,
      );

      return;
    }


    const target =
      commandMap.get(key);

    if (!target) {
      writeEvent({
        type: 'command_result',
        request_id: requestId,
        success: false,
        key,
        message:
          `Příkaz "${key}" není setable ` +
          'nebo nebyl nalezen.',
      });

      return;
    }

    try {
      const homeyValue =
        await setTargetValue(
          target,
          command.value,
        );

      writeEvent({
        type: 'command_result',
        request_id: requestId,
        success: true,
        key,
        device_name:
          target.device.name,
        device_id:
          target.device.id,
        capability_id:
          target.capabilityId,
        homey_value:
          homeyValue,
      });

    } catch (error) {
      writeEvent({
        type: 'command_result',
        request_id: requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id:
          target.capabilityId,
        message:
          error?.message ??
          String(error),
      });
    }
  }


  writeEvent({
    type: 'ready',
    subscriptions:
      subscriptions.length,
    commands:
      commandMap.size +
      rgbCommandMap.size +
      lumitechCommandMap.size,
    synthetic_rgb_commands:
      rgbCommandMap.size,
    synthetic_lumitech_commands:
      lumitechCommandMap.size,
    skipped,
    missing,
  });


  const input =
    createInterface({
      input: process.stdin,
      crlfDelay: Infinity,
    });

  let commandQueue =
    Promise.resolve();

  input.on(
    'line',
    (line) => {
      const message = line.trim();

      if (!message) {
        return;
      }

      commandQueue =
        commandQueue.then(
          async () => {
            let command;

            try {
              command =
                JSON.parse(message);
            } catch {
              writeEvent({
                type: 'command_result',
                success: false,
                message:
                  'Neplatný JSON příkaz.',
              });

              return;
            }

            if (
              command?.type !==
              'command'
            ) {
              writeEvent({
                type: 'command_result',
                request_id:
                  command?.request_id ??
                  null,
                success: false,
                message:
                  'Neznámý typ příkazu.',
              });

              return;
            }

            await handleCommand(
              command,
            );
          },
        ).catch(
          (error) => {
            writeEvent({
              type: 'command_result',
              success: false,
              message:
                error?.message ??
                String(error),
            });
          },
        );
    },
  );


  const shutdown =
    async (signal) => {
      writeLog(
        `Ukončuji spojení: ${signal}`,
      );

      input.close();

      for (
        const state
        of lightProfileStates.values()
      ) {
        if (state.timer) {
          clearTimeout(
            state.timer,
          );
        }
      }

      for (
        const subscription
        of subscriptions
      ) {
        try {
          await subscription.destroy?.();
        } catch {
          // Chybu při ukončení ignorujeme.
        }
      }

      process.exit(0);
    };


  process.on(
    'SIGINT',
    () => {
      void shutdown('SIGINT');
    },
  );

  process.on(
    'SIGTERM',
    () => {
      void shutdown('SIGTERM');
    },
  );

  await new Promise(() => {});
}


main().catch((error) => {
  writeEvent({
    type: 'fatal',
    message:
      error?.message ??
      String(error),
  });

  writeLog(
    error?.stack ??
    String(error),
  );

  process.exit(1);
});