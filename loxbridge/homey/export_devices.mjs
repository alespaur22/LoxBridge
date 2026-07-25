import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PROJECT_ROOT = path.resolve(__dirname, '../..');
const CONFIG_PATH = path.join(PROJECT_ROOT, 'config', 'config.yaml');
const EXPORT_DIRECTORY = path.join(PROJECT_ROOT, 'exports');
const EXPORT_PATH = path.join(EXPORT_DIRECTORY, 'homey_devices.json');


async function loadConfig() {
  const source = await fs.readFile(CONFIG_PATH, 'utf8');
  const config = YAML.parse(source);

  if (!config?.homey?.ip) {
    throw new Error('V config/config.yaml chybí homey.ip.');
  }

  if (!config?.homey?.token) {
    throw new Error('V config/config.yaml chybí homey.token.');
  }

  return config;
}


function makeSerializable(value) {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map(makeSerializable);
  }

  if (typeof value === 'object') {
    const result = {};

    for (const [key, childValue] of Object.entries(value)) {
      if (typeof childValue !== 'function') {
        result[key] = makeSerializable(childValue);
      }
    }

    return result;
  }

  return String(value);
}


function exportCapability(capabilityId, capabilityObject) {
  return {
    id: capabilityId,
    title:
      capabilityObject?.title ??
      capabilityObject?.titleFormatted ??
      capabilityId,
    value: makeSerializable(capabilityObject?.value ?? null),
    type: capabilityObject?.type ?? null,
    getable: capabilityObject?.getable ?? null,
    setable: capabilityObject?.setable ?? null,
    units: capabilityObject?.units ?? null,
    min: capabilityObject?.min ?? null,
    max: capabilityObject?.max ?? null,
    step: capabilityObject?.step ?? null,
    values: makeSerializable(capabilityObject?.values ?? null),
    last_updated: capabilityObject?.lastUpdated ?? null,
  };
}


async function loadZones(homeyApi) {
  try {
    const zones = await homeyApi.zones.getZones();
    return zones;
  } catch (error) {
    console.warn(
      `Varování: Nepodařilo se načíst zóny: ${error.message}`,
    );

    return {};
  }
}


async function main() {
  const config = await loadConfig();
  const address = `http://${config.homey.ip}`;

  console.log('Export zařízení z Homey');
  console.log('=======================');
  console.log(`Homey:  ${address}`);
  console.log(`Výstup: ${EXPORT_PATH}`);
  console.log('Připojuji se...');

  const homeyApi = await HomeyAPI.createLocalAPI({
    address,
    token: config.homey.token,
  });

  console.log('Připojení bylo úspěšné.');
  console.log('Načítám zařízení a zóny...');

  const [devices, zones] = await Promise.all([
    homeyApi.devices.getDevices(),
    loadZones(homeyApi),
  ]);

  const exportedDevices = [];

  for (const device of Object.values(devices)) {
    const capabilityIds = Array.isArray(device.capabilities)
      ? device.capabilities
      : Object.keys(device.capabilitiesObj ?? {});

    const capabilities = capabilityIds.map((capabilityId) =>
      exportCapability(
        capabilityId,
        device.capabilitiesObj?.[capabilityId],
      ),
    );

    const zone = device.zone
      ? zones[device.zone]
      : null;

    exportedDevices.push({
      id: device.id,
      name: device.name,
      zone_id: device.zone ?? null,
      zone_name: zone?.name ?? null,
      class: device.class ?? null,
      driver_id: device.driverId ?? null,
      virtual_class: device.virtualClass ?? null,
      available: device.available ?? null,
      capabilities,
    });
  }

  exportedDevices.sort((first, second) => {
    const firstZone = first.zone_name ?? '';
    const secondZone = second.zone_name ?? '';

    const zoneComparison = firstZone.localeCompare(
      secondZone,
      'cs',
    );

    if (zoneComparison !== 0) {
      return zoneComparison;
    }

    return first.name.localeCompare(second.name, 'cs');
  });

  const exportData = {
    exported_at: new Date().toISOString(),
    homey_ip: config.homey.ip,
    device_count: exportedDevices.length,
    devices: exportedDevices,
  };

  await fs.mkdir(EXPORT_DIRECTORY, {
    recursive: true,
  });

  await fs.writeFile(
    EXPORT_PATH,
    `${JSON.stringify(exportData, null, 2)}\n`,
    'utf8',
  );

  console.log('');
  console.log(`Hotovo. Nalezeno zařízení: ${exportedDevices.length}`);
  console.log('');

  for (const device of exportedDevices) {
    const zoneName = device.zone_name ?? 'Bez zóny';

    console.log(`${zoneName} / ${device.name}`);
    console.log(`  Třída: ${device.class ?? '-'}`);
    console.log(`  ID: ${device.id}`);

    for (const capability of device.capabilities) {
      console.log(
        `  - ${capability.id} = ` +
        `${JSON.stringify(capability.value)} ` +
        `(setable: ${capability.setable})`,
      );
    }

    console.log('');
  }

  console.log(`JSON uložen do: ${EXPORT_PATH}`);
}


main().catch((error) => {
  console.error('');
  console.error('EXPORT SELHAL');
  console.error(error?.stack ?? error);
  process.exit(1);
});
