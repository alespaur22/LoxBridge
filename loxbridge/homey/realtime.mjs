import fs from 'node:fs/promises';
import process from 'node:process';
import { createInterface } from 'node:readline';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';

const SUPPORTED_TYPES = new Set(['boolean', 'number', 'enum']);
const REQUIRED_PROFILE_SCHEMA_VERSION = 2;
const WHITE_WARM_KELVIN = 2700;
const WHITE_COLD_KELVIN = 6500;
const LIGHT_MERGE_DELAY_MS = 120;
const RGBW_WHITE_MASTER_DIM = 0.01;

function writeEvent(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

function writeLog(message) {
  process.stderr.write(`[Homey realtime] ${message}\n`);
}

async function loadConfig(configPath) {
  const source = await fs.readFile(configPath, 'utf8');
  const config = YAML.parse(source);

  if (!config?.homey?.ip) {
    throw new Error('V konfiguraci chybí homey.ip.');
  }

  if (!config?.homey?.token) {
    throw new Error('V konfiguraci chybí homey.token.');
  }

  if (!Array.isArray(config.devices)) {
    throw new Error('V konfiguraci chybí devices.');
  }

  if (
    Number(config?.loxbridge?.schema_version) !==
    REQUIRED_PROFILE_SCHEMA_VERSION
  ) {
    throw new Error(
      'config.generated.yaml používá staré schéma. ' +
      'Spusť znovu: python -m loxbridge.generate',
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
    values: Array.isArray(capabilityConfig.values)
      ? capabilityConfig.values
      : [],
    setable: capabilityConfig.setable === true,
  };
}

function convertValue(
  value,
  capabilityConfig,
) {
  if (capabilityConfig.type !== 'enum') {
    return value;
  }

  const match = capabilityConfig.values.find(
    (enumValue) =>
      enumValue?.id === value,
  );

  if (!match) {
    throw new Error(
      `Enum hodnota "${value}" nemá číselné mapování.`,
    );
  }

  return match.value;
}

function convertCommandValue(
  value,
  capabilityConfig,
) {
  if (capabilityConfig.type === 'boolean') {
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

  if (capabilityConfig.type === 'number') {
    const numberValue = Number(value);

    if (!Number.isFinite(numberValue)) {
      throw new Error(
        `Neplatná číselná hodnota: ${value}`,
      );
    }

    return numberValue;
  }

  if (capabilityConfig.type === 'enum') {
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
      `Enum hodnota "${value}" nemá mapování.`,
    );
  }

  throw new Error(
    `Nepodporovaný typ capability: ${capabilityConfig.type}`,
  );
}

function parseLoxoneRgb(value) {
  const numericValue = Number(value);

  if (!Number.isFinite(numericValue)) {
    throw new Error(
      `Neplatná RGB hodnota: ${value}`,
    );
  }

  const packedValue =
    Math.round(numericValue);

  if (
    packedValue < 0 ||
    Math.abs(
      numericValue - packedValue,
    ) > 0.01
  ) {
    throw new Error(
      `RGB hodnota musí být celé kladné číslo: ${value}`,
    );
  }

  const packedText =
    String(packedValue);

  if (packedText.length > 9) {
    throw new Error(
      `RGB hodnota je příliš dlouhá: ${value}`,
    );
  }

  // Loxone posílá BBBGGGRRR.
  // Vedoucí nuly se mohou při UDP číslu ztratit.
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
        `RGB kanál ${name} je mimo rozsah 0–100: ${channel}`,
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

  const max =
    Math.max(r, g, b);

  const min =
    Math.min(r, g, b);

  const delta =
    max - min;

  let hue = 0;

  if (delta !== 0) {
    if (max === r) {
      hue =
        ((g - b) / delta) % 6;
    } else if (max === g) {
      hue =
        ((b - r) / delta) + 2;
    } else {
      hue =
        ((r - g) / delta) + 4;
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
  const numericValue =
    Number(value);

  if (!Number.isFinite(numericValue)) {
    throw new Error(
      `Neplatná Lumitech hodnota: ${value}`,
    );
  }

  const packedValue =
    Math.round(numericValue);

  if (
    packedValue < 0 ||
    Math.abs(
      numericValue - packedValue,
    ) > 0.01
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
    String(packedValue)
      .padStart(9, '0');

  if (
    normalized.length !== 9 ||
    !normalized.startsWith('20')
  ) {
    throw new Error(
      `Neplatný Lumitech formát: ${value}`,
    );
  }

  const brightness =
    Number(
      normalized.slice(2, 5),
    );

  const kelvin =
    Number(
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

function parsePercent(
  value,
  label,
) {
  const percent =
    Number(value);

  if (
    !Number.isFinite(percent) ||
    percent < 0 ||
    percent > 100
  ) {
    throw new Error(
      `${label} musí být v rozsahu 0–100: ${value}`,
    );
  }

  return percent;
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

function buildNormalizedInputsBySource(
  deviceConfig,
) {
  const result = new Map();

  const inputs =
    deviceConfig.loxbridge?.inputs;

  if (!Array.isArray(inputs)) {
    return result;
  }

  for (const input of inputs) {
    if (
      !input ||
      typeof input !== 'object'
    ) {
      continue;
    }

    const sourceCapability =
      input.source_capability;

    const key = input.key;

    if (
      typeof sourceCapability !== 'string' ||
      !sourceCapability ||
      typeof key !== 'string' ||
      !key
    ) {
      continue;
    }

    const current =
      result.get(sourceCapability) ?? [];

    current.push(input);
    result.set(sourceCapability, current);
  }

  return result;
}

function convertNormalizedInput(
  value,
  inputConfig,
) {
  if (inputConfig.kind === 'binary_threshold') {
    const numberValue = Number(value);

    if (!Number.isFinite(numberValue)) {
      throw new Error(
        `Normalizovaný vstup ${inputConfig.key} ` +
        `nemá číselnou hodnotu: ${value}`,
      );
    }

    const threshold = Number(
      inputConfig.threshold ?? 0.5,
    );

    if (!Number.isFinite(threshold)) {
      throw new Error(
        `Neplatný threshold pro ${inputConfig.key}.`,
      );
    }

    return numberValue >= threshold;
  }

  throw new Error(
    `Nepodporovaný normalizovaný vstup: ` +
    `${inputConfig.kind}`,
  );
}

function emitNormalizedInputEvents({
  device,
  capabilityId,
  sourceValue,
  initial,
  normalizedInputsBySource,
}) {
  const inputs =
    normalizedInputsBySource.get(capabilityId);

  if (!inputs) {
    return;
  }

  for (const inputConfig of inputs) {
    try {
      writeEvent({
        type: 'value',
        initial,
        device_name: device.name,
        device_id: device.id,
        capability_id:
          `normalized:${inputConfig.key}`,
        loxone_key: inputConfig.key,
        value: convertNormalizedInput(
          sourceValue,
          inputConfig,
        ),
      });
    } catch (error) {
      writeEvent({
        type: 'warning',
        message:
          `${device.name} / ${capabilityId} → ` +
          `${inputConfig.key}: ${error.message}`,
      });
    }
  }
}

function buildProfileCommandMap(
  config,
  commandMap,
) {
  const result = new Map();

  const stats = {
    rgb: 0,
    lumitech: 0,
    dimmer: 0,
    white: 0,
    other: 0,
  };

  for (
    const deviceConfig
    of config.devices
  ) {
    const commands =
      deviceConfig.loxbridge?.commands;

    if (!Array.isArray(commands)) {
      continue;
    }

    for (const commandConfig of commands) {
      if (
        !commandConfig ||
        typeof commandConfig !== 'object'
      ) {
        continue;
      }

      const key = commandConfig.key;
      const kind = commandConfig.kind;
      const targetConfigs = commandConfig.targets;

      if (
        typeof key !== 'string' ||
        !key ||
        typeof kind !== 'string' ||
        !kind ||
        !targetConfigs ||
        typeof targetConfigs !== 'object'
      ) {
        continue;
      }

      const resolvedTargets = {};
      let targetDevice = null;
      let valid = true;

      for (
        const [alias, capabilityId]
        of Object.entries(targetConfigs)
      ) {
        if (
          typeof capabilityId !== 'string' ||
          !capabilityId
        ) {
          valid = false;
          break;
        }

        const target =
          getConfiguredCommandTarget(
            deviceConfig,
            capabilityId,
            commandMap,
          );

        if (!target) {
          writeEvent({
            type: 'warning',
            message:
              `${deviceConfig.name} / profil ${kind}: ` +
              `chybí setable capability ${capabilityId}.`,
          });

          valid = false;
          break;
        }

        resolvedTargets[alias] = target;
        targetDevice ??= target.device;
      }

      if (!valid || !targetDevice) {
        continue;
      }

      const profileTarget = {
        device: targetDevice,
        key,
        kind,
        group: commandConfig.group ?? null,
        options:
          commandConfig.options ?? {},
        ...resolvedTargets,
      };

      if (kind === 'rgb_white_white') {
        const configuredMasterDim = Number(
          profileTarget.options?.white_master_dim ??
          RGBW_WHITE_MASTER_DIM,
        );

        profileTarget.whiteMasterDim =
          Number.isFinite(configuredMasterDim)
            ? configuredMasterDim
            : RGBW_WHITE_MASTER_DIM;
      }

      result.set(key, profileTarget);

      if (
        kind === 'rgb' ||
        kind === 'rgb_white_rgb'
      ) {
        stats.rgb += 1;
      } else if (kind === 'lumitech') {
        stats.lumitech += 1;
      } else if (kind === 'dimmer') {
        stats.dimmer += 1;
      } else if (kind === 'rgb_white_white') {
        stats.white += 1;
      } else {
        stats.other += 1;
      }
    }
  }

  return {
    commands: result,
    stats,
  };
}

function getMergedLightState(
  states,
  device,
) {
  let state =
    states.get(
      device.id,
    );

  if (!state) {
    state = {
      device,
      rgb: null,
      lumitech: null,
      lastChangedMode: null,
      rgbTarget: null,
      lumitechTarget: null,
      timer: null,
      pendingResults: [],
      applyQueue:
        Promise.resolve(),
    };

    states.set(
      device.id,
      state,
    );
  }

  return state;
}

function selectMergedLightMode(
  snapshot,
) {
  const rgbHsv =
    snapshot.rgb
      ? rgbToHomeyHsv(
          snapshot.rgb.red,
          snapshot.rgb.green,
          snapshot.rgb.blue,
        )
      : null;

  const rgbActive =
    rgbHsv !== null &&
    rgbHsv.dim > 0;

  const whiteActive =
    snapshot.lumitech !== null &&
    snapshot.lumitech
      .brightness > 0;

  if (
    rgbActive &&
    whiteActive
  ) {
    return {
      mode:
        snapshot
          .lastChangedMode ===
        'lumitech'
          ? 'lumitech'
          : 'rgb',
      rgbHsv,
    };
  }

  if (rgbActive) {
    return {
      mode: 'rgb',
      rgbHsv,
    };
  }

  if (whiteActive) {
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

async function applyMergedLightSnapshot(
  snapshot,
) {
  const selected =
    selectMergedLightMode(
      snapshot,
    );

  if (
    selected.mode === 'rgb'
  ) {
    const target =
      snapshot.rgbTarget;

    if (!target) {
      throw new Error(
        'Chybí RGB target pro světelný profil.',
      );
    }

    if (target.mode) {
      await setTargetValue(
        target.mode,
        'color',
      );
    }

    await setTargetValue(
      target.hue,
      selected.rgbHsv.hue,
    );

    await setTargetValue(
      target.saturation,
      selected.rgbHsv
        .saturation,
    );

    await setTargetValue(
      target.dim,
      selected.rgbHsv.dim,
    );

    await setTargetValue(
      target.onoff,
      true,
    );

    return {
      mode: 'color',
      hue:
        selected.rgbHsv.hue,
      saturation:
        selected.rgbHsv
          .saturation,
      dim:
        selected.rgbHsv.dim,
    };
  }

  if (
    selected.mode ===
    'lumitech'
  ) {
    const target =
      snapshot.lumitechTarget;

    if (!target) {
      throw new Error(
        'Chybí Lumitech target pro světelný profil.',
      );
    }

    const dim =
      snapshot.lumitech
        .brightness / 100;

    const temperature =
      kelvinToHomeyTemperature(
        snapshot.lumitech
          .kelvin,
      );

    if (target.mode) {
      await setTargetValue(
        target.mode,
        'temperature',
      );
    }

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
      mode:
        'temperature',
      brightness:
        snapshot.lumitech
          .brightness,
      kelvin:
        snapshot.lumitech
          .kelvin,
      dim,
      temperature,
    };
  }

  const offTarget =
    snapshot
      .rgbTarget?.onoff ??
    snapshot
      .lumitechTarget?.onoff;

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

function getRgbwState(
  states,
  device,
) {
  let state =
    states.get(
      device.id,
    );

  if (!state) {
    state = {
      device,
      rgb: null,
      white: 0,
      lastChangedMode: null,
      target: null,
      timer: null,
      pendingResults: [],
      applyQueue:
        Promise.resolve(),
    };

    states.set(
      device.id,
      state,
    );
  }

  return state;
}

function selectRgbwMode(
  snapshot,
) {
  const rgbHsv =
    snapshot.rgb
      ? rgbToHomeyHsv(
          snapshot.rgb.red,
          snapshot.rgb.green,
          snapshot.rgb.blue,
        )
      : null;

  const rgbActive =
    rgbHsv !== null &&
    rgbHsv.dim > 0;

  const whiteActive =
    snapshot.white > 0;

  if (
    rgbActive &&
    whiteActive
  ) {
    return {
      mode:
        snapshot
          .lastChangedMode ===
        'white'
          ? 'white'
          : 'rgb',
      rgbHsv,
    };
  }

  if (rgbActive) {
    return {
      mode: 'rgb',
      rgbHsv,
    };
  }

  if (whiteActive) {
    return {
      mode: 'white',
      rgbHsv,
    };
  }

  return {
    mode: 'off',
    rgbHsv,
  };
}

async function applyRgbwSnapshot(
  snapshot,
) {
  const target =
    snapshot.target;

  if (!target) {
    throw new Error(
      'Chybí target pro RGBW profil.',
    );
  }

  const selected =
    selectRgbwMode(
      snapshot,
    );

  if (
    selected.mode === 'rgb'
  ) {
    /*
     * Nejprve vypneme samostatný
     * white kanál.
     */

    await setTargetValue(
      target.whiteDim,
      0,
    );

    await setTargetValue(
      target.hue,
      selected.rgbHsv.hue,
    );

    await setTargetValue(
      target.saturation,
      selected.rgbHsv
        .saturation,
    );

    await setTargetValue(
      target.dim,
      selected.rgbHsv.dim,
    );

    await setTargetValue(
      target.onoff,
      true,
    );

    return {
      mode: 'color',
      hue:
        selected.rgbHsv.hue,
      saturation:
        selected.rgbHsv
          .saturation,
      dim:
        selected.rgbHsv.dim,
    };
  }

  if (
    selected.mode === 'white'
  ) {
    const whiteDim =
      snapshot.white / 100;

    /*
     * Ověřené chování Homey RGBW driveru:
     *
     * dim = 0.01
     * dim.white = požadovaný jas bílé
     * onoff = true
     *
     * onoff.whitemode se NESMÍ použít,
     * protože fyzicky vynutí bílou 100 %.
     */

    const whiteMasterDim =
      Number.isFinite(
        Number(target.whiteMasterDim),
      )
        ? Number(target.whiteMasterDim)
        : RGBW_WHITE_MASTER_DIM;

    await setTargetValue(
      target.dim,
      whiteMasterDim,
    );

    await setTargetValue(
      target.whiteDim,
      whiteDim,
    );

    await setTargetValue(
      target.onoff,
      true,
    );

    return {
      mode: 'white',
      brightness:
        snapshot.white,
      dim:
        whiteDim,
      master_dim:
        whiteMasterDim,
    };
  }

  await setTargetValue(
    target.onoff,
    false,
  );

  return {
    mode: 'off',
  };
}

async function main() {
  const configPath =
    process.argv[2];

  if (!configPath) {
    throw new Error(
      'Chybí cesta ke konfiguraci.',
    );
  }

  const config =
    await loadConfig(
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
      token:
        config.homey.token,
    });

  writeLog(
    'Připojení k Homey bylo úspěšné.',
  );

  writeLog(
    'Načítám zařízení.',
  );

  const devices =
    await homeyApi
      .devices
      .getDevices();

  const devicesById =
    new Map();

  const devicesByName =
    new Map();

  for (
    const device
    of Object.values(devices)
  ) {
    devicesById.set(
      device.id,
      device,
    );

    devicesByName.set(
      device.name
        .toLocaleLowerCase(),
      device,
    );
  }

  const subscriptions = [];
  const commandMap =
    new Map();

  let skipped = 0;
  let missing = 0;

  for (
    const deviceConfig
    of config.devices
  ) {
    let device = null;

    if (
      deviceConfig.homey_id
    ) {
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
          `Zařízení "${deviceConfig.name}" nebylo nalezeno.`,
      });

      missing += 1;
      continue;
    }

    const capabilities =
      deviceConfig
        .capabilities ?? {};

    const normalizedInputsBySource =
      buildNormalizedInputsBySource(
        deviceConfig,
      );

    for (
      const [
        capabilityId,
        rawConfig,
      ]
      of Object.entries(
        capabilities,
      )
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
        capabilityConfig.type !==
          null &&
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
        typeof loxoneKey !==
          'string' ||
        !loxoneKey
      ) {
        missing += 1;
        continue;
      }

      const capability =
        device
          .capabilitiesObj?.[
            capabilityId
          ];

      if (!capability) {
        writeEvent({
          type: 'warning',
          message:
            `Zařízení "${device.name}" nemá capability "${capabilityId}".`,
        });

        missing += 1;
        continue;
      }

      if (
        capabilityConfig
          .setable === true &&
        capability
          .setable === true
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
        const convertedValue =
          convertValue(
            capability.value,
            capabilityConfig,
          );

        writeEvent({
          type: 'value',
          initial: true,
          device_name:
            device.name,
          device_id:
            device.id,
          capability_id:
            capabilityId,
          loxone_key:
            loxoneKey,
          value:
            convertedValue,
        });

        emitNormalizedInputEvents({
          device,
          capabilityId,
          sourceValue: convertedValue,
          initial: true,
          normalizedInputsBySource,
        });

      } catch (error) {
        writeEvent({
          type: 'warning',
          message:
            `${device.name} / ${capabilityId}: ${error.message}`,
        });
      }

      const instance =
        device
          .makeCapabilityInstance(
            capabilityId,
            (newValue) => {
              try {
                const convertedValue =
                  convertValue(
                    newValue,
                    capabilityConfig,
                  );

                writeEvent({
                  type:
                    'value',
                  initial:
                    false,
                  device_name:
                    device.name,
                  device_id:
                    device.id,
                  capability_id:
                    capabilityId,
                  loxone_key:
                    loxoneKey,
                  value:
                    convertedValue,
                });

                emitNormalizedInputEvents({
                  device,
                  capabilityId,
                  sourceValue: convertedValue,
                  initial: false,
                  normalizedInputsBySource,
                });

              } catch (error) {
                writeEvent({
                  type:
                    'warning',
                  message:
                    `${device.name} / ${capabilityId}: ${error.message}`,
                });
              }
            },
          );

      subscriptions.push(
        instance,
      );
    }
  }

  if (
    subscriptions.length === 0
  ) {
    throw new Error(
      'Nevznikl žádný realtime odběr.',
    );
  }

  const profileCommandState =
    buildProfileCommandMap(
      config,
      commandMap,
    );

  const profileCommandMap =
    profileCommandState.commands;

  const profileCommandStats =
    profileCommandState.stats;

  const mergedLightStates =
    new Map();

  const rgbwStates =
    new Map();

  function emitPendingSuccess(
    snapshot,
    homeyValue,
  ) {
    for (
      const pending
      of snapshot.pendingResults
    ) {
      writeEvent({
        type:
          'command_result',
        request_id:
          pending.requestId,
        success: true,
        key:
          pending.key,
        device_name:
          snapshot.device.name,
        device_id:
          snapshot.device.id,
        capability_id:
          pending.capabilityId,
        homey_value:
          homeyValue,
      });
    }
  }

  function emitPendingFailure(
    snapshot,
    error,
  ) {
    for (
      const pending
      of snapshot.pendingResults
    ) {
      writeEvent({
        type:
          'command_result',
        request_id:
          pending.requestId,
        success: false,
        key:
          pending.key,
        device_name:
          snapshot.device.name,
        capability_id:
          pending.capabilityId,
        message:
          error?.message ??
          String(error),
      });
    }
  }

  function scheduleMergedLight(
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
          state.timer = null;

          const snapshot = {
            device:
              state.device,
            rgb:
              state.rgb
                ? {
                    ...state.rgb,
                  }
                : null,
            lumitech:
              state.lumitech
                ? {
                    ...state.lumitech,
                  }
                : null,
            lastChangedMode:
              state
                .lastChangedMode,
            rgbTarget:
              state.rgbTarget,
            lumitechTarget:
              state
                .lumitechTarget,
            pendingResults:
              state
                .pendingResults
                .splice(0),
          };

          state.applyQueue =
            state.applyQueue
              .then(
                async () => {
                  try {
                    const homeyValue =
                      await applyMergedLightSnapshot(
                        snapshot,
                      );

                    emitPendingSuccess(
                      snapshot,
                      homeyValue,
                    );

                  } catch (error) {
                    emitPendingFailure(
                      snapshot,
                      error,
                    );
                  }
                },
              );
        },
        LIGHT_MERGE_DELAY_MS,
      );
  }

  function scheduleRgbw(
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
          state.timer = null;

          const snapshot = {
            device:
              state.device,
            rgb:
              state.rgb
                ? {
                    ...state.rgb,
                  }
                : null,
            white:
              state.white,
            lastChangedMode:
              state
                .lastChangedMode,
            target:
              state.target,
            pendingResults:
              state
                .pendingResults
                .splice(0),
          };

          state.applyQueue =
            state.applyQueue
              .then(
                async () => {
                  try {
                    const homeyValue =
                      await applyRgbwSnapshot(
                        snapshot,
                      );

                    emitPendingSuccess(
                      snapshot,
                      homeyValue,
                    );

                  } catch (error) {
                    emitPendingFailure(
                      snapshot,
                      error,
                    );
                  }
                },
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
      command.request_id ??
      null;

    try {
      const rgb =
        parseLoxoneRgb(
          command.value,
        );

      const hsv =
        rgbToHomeyHsv(
          rgb.red,
          rgb.green,
          rgb.blue,
        );

      const state =
        getMergedLightState(
          mergedLightStates,
          target.device,
        );

      state.rgb = rgb;
      state.rgbTarget =
        target;

      if (hsv.dim > 0) {
        state.lastChangedMode =
          'rgb';
      }

      state
        .pendingResults
        .push({
          requestId,
          key,
          capabilityId:
            'rgb',
        });

      scheduleMergedLight(
        state,
      );

    } catch (error) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id:
          'rgb',
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
      command.request_id ??
      null;

    try {
      const lumitech =
        parseLoxoneLumitech(
          command.value,
        );

      const state =
        getMergedLightState(
          mergedLightStates,
          target.device,
        );

      state.lumitech =
        lumitech;

      state.lumitechTarget =
        target;

      if (
        lumitech.brightness >
        0
      ) {
        state.lastChangedMode =
          'lumitech';
      }

      state
        .pendingResults
        .push({
          requestId,
          key,
          capabilityId:
            'lumitech',
        });

      scheduleMergedLight(
        state,
      );

    } catch (error) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id:
          'lumitech',
        message:
          error?.message ??
          String(error),
      });
    }
  }

  async function handleDimmerCommand(
    command,
    key,
    target,
  ) {
    const requestId =
      command.request_id ??
      null;

    try {
      const brightness =
        parsePercent(
          command.value,
          'Dimmer hodnota',
        );

      const dim =
        brightness / 100;

      if (dim === 0) {
        await setTargetValue(
          target.onoff,
          false,
        );

      } else {
        await setTargetValue(
          target.dim,
          dim,
        );

        await setTargetValue(
          target.onoff,
          true,
        );
      }

      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: true,
        key,
        device_name:
          target.device.name,
        device_id:
          target.device.id,
        capability_id:
          'dimmer',
        homey_value: {
          brightness,
          dim,
          onoff:
            dim > 0,
        },
      });

    } catch (error) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id:
          'dimmer',
        message:
          error?.message ??
          String(error),
      });
    }
  }

  async function handleRgbwRgbCommand(
    command,
    key,
    target,
  ) {
    const requestId =
      command.request_id ??
      null;

    try {
      const rgb =
        parseLoxoneRgb(
          command.value,
        );

      const hsv =
        rgbToHomeyHsv(
          rgb.red,
          rgb.green,
          rgb.blue,
        );

      const state =
        getRgbwState(
          rgbwStates,
          target.device,
        );

      state.rgb = rgb;
      state.target =
        target;

      if (hsv.dim > 0) {
        state.lastChangedMode =
          'rgb';
      }

      state
        .pendingResults
        .push({
          requestId,
          key,
          capabilityId:
            'rgbw_rgb',
        });

      scheduleRgbw(
        state,
      );

    } catch (error) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id:
          'rgbw_rgb',
        message:
          error?.message ??
          String(error),
      });
    }
  }

  async function handleRgbwWhiteCommand(
    command,
    key,
    target,
  ) {
    const requestId =
      command.request_id ??
      null;

    try {
      const white =
        parsePercent(
          command.value,
          'White hodnota',
        );

      const state =
        getRgbwState(
          rgbwStates,
          target.device,
        );

      state.white =
        white;

      state.target =
        target;

      if (white > 0) {
        state.lastChangedMode =
          'white';
      }

      state
        .pendingResults
        .push({
          requestId,
          key,
          capabilityId:
            'rgbw_white',
        });

      scheduleRgbw(
        state,
      );

    } catch (error) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        key,
        device_name:
          target.device.name,
        capability_id:
          'rgbw_white',
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
      command.request_id ??
      null;

    const key =
      command.key;

    if (
      typeof key !== 'string' ||
      !key
    ) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        message:
          'Příkaz neobsahuje platný key.',
      });

      return;
    }

    const profileTarget =
      profileCommandMap.get(
        key,
      );

    if (profileTarget) {
      if (profileTarget.kind === 'rgb') {
        await handleRgbCommand(
          command,
          key,
          profileTarget,
        );
      } else if (
        profileTarget.kind === 'lumitech'
      ) {
        await handleLumitechCommand(
          command,
          key,
          profileTarget,
        );
      } else if (
        profileTarget.kind === 'dimmer'
      ) {
        await handleDimmerCommand(
          command,
          key,
          profileTarget,
        );
      } else if (
        profileTarget.kind === 'rgb_white_rgb'
      ) {
        await handleRgbwRgbCommand(
          command,
          key,
          profileTarget,
        );
      } else if (
        profileTarget.kind === 'rgb_white_white'
      ) {
        await handleRgbwWhiteCommand(
          command,
          key,
          profileTarget,
        );
      } else {
        writeEvent({
          type: 'command_result',
          request_id: requestId,
          success: false,
          key,
          message:
            `Nepodporovaný profilový příkaz: ` +
            `${profileTarget.kind}`,
        });
      }

      return;
    }

    const target =
      commandMap.get(
        key,
      );

    if (!target) {
      writeEvent({
        type:
          'command_result',
        request_id:
          requestId,
        success: false,
        key,
        message:
          `Příkaz "${key}" není setable nebo nebyl nalezen.`,
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
        type:
          'command_result',
        request_id:
          requestId,
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
        type:
          'command_result',
        request_id:
          requestId,
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
      profileCommandMap.size,

    synthetic_rgb_commands:
      profileCommandStats.rgb,

    synthetic_lumitech_commands:
      profileCommandStats.lumitech,

    synthetic_dimmer_commands:
      profileCommandStats.dimmer,

    synthetic_white_commands:
      profileCommandStats.white,

    synthetic_other_commands:
      profileCommandStats.other,

    skipped,
    missing,
  });

  const input =
    createInterface({
      input:
        process.stdin,
      crlfDelay:
        Infinity,
    });

  let commandQueue =
    Promise.resolve();

  input.on(
    'line',
    (line) => {
      const message =
        line.trim();

      if (!message) {
        return;
      }

      commandQueue =
        commandQueue
          .then(
            async () => {
              let command;

              try {
                command =
                  JSON.parse(
                    message,
                  );

              } catch {
                writeEvent({
                  type:
                    'command_result',
                  success:
                    false,
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
                  type:
                    'command_result',
                  request_id:
                    command
                      ?.request_id ??
                    null,
                  success:
                    false,
                  message:
                    'Neznámý typ příkazu.',
                });

                return;
              }

              await handleCommand(
                command,
              );
            },
          )
          .catch(
            (error) => {
              writeEvent({
                type:
                  'command_result',
                success:
                  false,
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
        of mergedLightStates
          .values()
      ) {
        if (state.timer) {
          clearTimeout(
            state.timer,
          );
        }
      }

      for (
        const state
        of rgbwStates.values()
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
          await subscription
            .destroy?.();

        } catch {
          // Ignorujeme chybu při ukončení.
        }
      }

      process.exit(0);
    };

  process.on(
    'SIGINT',
    () =>
      void shutdown(
        'SIGINT',
      ),
  );

  process.on(
    'SIGTERM',
    () =>
      void shutdown(
        'SIGTERM',
      ),
  );

  await new Promise(
    () => {},
  );
}

main().catch(
  (error) => {
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
  },
);