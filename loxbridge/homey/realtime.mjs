import fs from 'node:fs/promises';
import process from 'node:process';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';


const SUPPORTED_TYPES = new Set([
  'boolean',
  'number',
  'enum',
]);


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

  writeEvent({
    type: 'ready',
    subscriptions:
      subscriptions.length,
    skipped,
    missing,
  });

  const shutdown =
    async (signal) => {
      writeLog(
        `Ukončuji spojení: ${signal}`,
      );

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