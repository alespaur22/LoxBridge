import fs from 'node:fs/promises';
import process from 'node:process';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';


function writeEvent(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}


function writeLog(message) {
  process.stderr.write(`[Homey realtime] ${message}\n`);
}


function validateConfig(config) {
  if (!config || typeof config !== 'object') {
    throw new Error('Konfigurace neobsahuje platný YAML objekt.');
  }

  if (!config.homey?.ip) {
    throw new Error('V konfiguraci chybí homey.ip.');
  }

  if (!config.homey?.token) {
    throw new Error('V konfiguraci chybí homey.token.');
  }

  if (!Array.isArray(config.devices) || config.devices.length === 0) {
    throw new Error('V konfiguraci chybí seznam devices.');
  }
}


async function loadConfig(configPath) {
  const source = await fs.readFile(configPath, 'utf8');
  const config = YAML.parse(source);

  validateConfig(config);

  return config;
}


async function main() {
  const configPath = process.argv[2];

  if (!configPath) {
    throw new Error(
      'Chybí cesta ke konfiguraci. Použití: node realtime.mjs config/config.yaml',
    );
  }

  const config = await loadConfig(configPath);
  const address = `http://${config.homey.ip}`;

  writeLog(`Připojuji se k ${address}`);

  const homeyApi = await HomeyAPI.createLocalAPI({
    address,
    token: config.homey.token,
  });

  writeLog('Připojení k Homey bylo úspěšné.');
  writeLog('Načítám zařízení.');

  const devices = await homeyApi.devices.getDevices();
  const devicesByName = new Map();

  for (const device of Object.values(devices)) {
    devicesByName.set(device.name.toLocaleLowerCase(), device);
  }

  const subscriptions = [];

  for (const deviceConfig of config.devices) {
    const configuredName = deviceConfig.name;
    const device = devicesByName.get(
      configuredName.toLocaleLowerCase(),
    );

    if (!device) {
      writeEvent({
        type: 'warning',
        message: `Zařízení "${configuredName}" nebylo nalezeno.`,
      });

      continue;
    }

    const configuredCapabilities = deviceConfig.capabilities ?? {};

    for (const [capabilityId, loxoneKey] of Object.entries(
      configuredCapabilities,
    )) {
      const capability = device.capabilitiesObj?.[capabilityId];

      if (!capability) {
        writeEvent({
          type: 'warning',
          message:
            `Zařízení "${device.name}" nemá capability ` +
            `"${capabilityId}".`,
        });

        continue;
      }

      writeEvent({
        type: 'value',
        initial: true,
        device_name: device.name,
        device_id: device.id,
        capability_id: capabilityId,
        loxone_key: loxoneKey,
        value: capability.value,
      });

      const instance = device.makeCapabilityInstance(
        capabilityId,
        (newValue) => {
          writeEvent({
            type: 'value',
            initial: false,
            device_name: device.name,
            device_id: device.id,
            capability_id: capabilityId,
            loxone_key: loxoneKey,
            value: newValue,
          });
        },
      );

      subscriptions.push(instance);
    }
  }

  if (subscriptions.length === 0) {
    throw new Error(
      'Nevznikl žádný realtime odběr. ' +
      'Zkontroluj názvy zařízení a capability v config.yaml.',
    );
  }

  writeEvent({
    type: 'ready',
    subscriptions: subscriptions.length,
  });

  const shutdown = async (signal) => {
    writeLog(`Ukončuji spojení: ${signal}`);

    for (const subscription of subscriptions) {
      try {
        await subscription.destroy?.();
      } catch {
        // Chybu při ukončení není nutné řešit.
      }
    }

    process.exit(0);
  };

  process.on('SIGINT', () => {
    void shutdown('SIGINT');
  });

  process.on('SIGTERM', () => {
    void shutdown('SIGTERM');
  });

  await new Promise(() => {});
}


main().catch((error) => {
  writeEvent({
    type: 'fatal',
    message: error?.message ?? String(error),
  });

  writeLog(error?.stack ?? String(error));
  process.exit(1);
});
