import fs from 'node:fs/promises';
import process from 'node:process';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';


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

  return config;
}


async function main() {
  const configPath = process.argv[2];
  const deviceRef = process.argv[3];
  const capabilityId = process.argv[4];
  const rawValue = process.argv[5];

  if (
    !configPath ||
    !deviceRef ||
    !capabilityId ||
    rawValue === undefined
  ) {
    throw new Error(
      'Použití: node set_capability.mjs ' +
      '<config.yaml> <device-id-or-name> ' +
      '<capability> <value>',
    );
  }

  const config =
    await loadConfig(configPath);

  const homeyApi =
    await HomeyAPI.createLocalAPI({
      address:
        `http://${config.homey.ip}`,
      token:
        config.homey.token,
    });

  const devices =
    await homeyApi.devices.getDevices();

  const device =
    devices[deviceRef] ??
    Object.values(devices).find(
      (item) =>
        item.id === deviceRef ||
        item.name === deviceRef,
    );

  if (!device) {
    throw new Error(
      `Zařízení "${deviceRef}" nebylo nalezeno.`,
    );
  }

  const capability =
    device.capabilitiesObj?.[
      capabilityId
    ];

  if (!capability) {
    throw new Error(
      `Zařízení "${device.name}" nemá capability ` +
      `"${capabilityId}".`,
    );
  }

  if (capability.setable !== true) {
    throw new Error(
      `Capability "${capabilityId}" není setable.`,
    );
  }

  let value = rawValue;

  if (capability.type === 'boolean') {
    value =
      rawValue === '1' ||
      rawValue.toLowerCase() === 'true';
  }

  else if (
    capability.type === 'number'
  ) {
    value = Number(rawValue);

    if (Number.isNaN(value)) {
      throw new Error(
        `Hodnota "${rawValue}" není číslo.`,
      );
    }
  }

  await device.setCapabilityValue(
    capabilityId,
    value,
  );

  console.log(
    `Nastaveno: ${device.name} / ` +
    `${capabilityId} = ${JSON.stringify(value)}`,
  );
}


main().catch((error) => {
  console.error(
    error?.stack ??
    String(error),
  );

  process.exit(1);
});