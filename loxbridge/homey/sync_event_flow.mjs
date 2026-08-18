import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

import { HomeyAPI } from 'homey-api';
import YAML from 'yaml';


const CONFIG_PATH =
  'config/config.generated.yaml';

const MANAGED_FLOW_NAME =
  'LoxBridge EVENTS';

const HTTP_ACTION_CARD_ID =
  'homey:manager:logic:http';

const DEFAULT_EVENT_URL =
  'http://192.168.68.70:7010/event';

const UUID_NAMESPACE =
  '6d87829e-213c-4cf8-897a-2b028d6f2983';

const EVENT_KEY_RE =
  /^[a-z0-9_]+$/;


function parseArguments() {
  const args = process.argv.slice(2);

  let apply = false;
  let eventUrl = DEFAULT_EVENT_URL;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];

    if (arg === '--apply') {
      apply = true;
      continue;
    }

    if (arg === '--url') {
      const value = args[index + 1];

      if (!value) {
        throw new Error(
          'Za --url chybí adresa.',
        );
      }

      eventUrl = value;
      index += 1;
      continue;
    }

    throw new Error(
      `Neznámý argument: ${arg}`,
    );
  }

  return {
    apply,
    eventUrl,
  };
}


async function loadConfig(configPath) {
  const text = await fs.readFile(
    configPath,
    'utf8',
  );

  const config = YAML.parse(text);

  if (
    !config ||
    typeof config !== 'object'
  ) {
    throw new Error(
      'Konfigurace není platný YAML objekt.',
    );
  }

  if (
    !config.homey?.ip ||
    !config.homey?.token
  ) {
    throw new Error(
      'V konfiguraci chybí homey.ip nebo homey.token.',
    );
  }

  return config;
}


function collectEvents(config) {
  const events = [];

  if (!Array.isArray(config.devices)) {
    throw new Error(
      'Konfigurace neobsahuje devices.',
    );
  }

  for (const device of config.devices) {
    if (
      !device ||
      typeof device !== 'object'
    ) {
      continue;
    }

    const deviceEvents =
      device.loxbridge?.events;

    if (!Array.isArray(deviceEvents)) {
      continue;
    }

    for (const event of deviceEvents) {
      if (
        !event ||
        typeof event !== 'object'
      ) {
        continue;
      }

      events.push({
        ...event,
        deviceName:
          String(
            device.name ??
            'Neznámé zařízení',
          ),
      });
    }
  }

  return events;
}


function validateEvents(events) {
  const keys = new Set();

  for (const event of events) {
    if (
      typeof event.key !== 'string' ||
      !EVENT_KEY_RE.test(event.key)
    ) {
      throw new Error(
        `Neplatný event key: ${event.key}`,
      );
    }

    if (keys.has(event.key)) {
      throw new Error(
        `Duplicitní event key: ${event.key}`,
      );
    }

    keys.add(event.key);

    if (
      typeof event.trigger?.card_id !==
        'string' ||
      !event.trigger.card_id
    ) {
      throw new Error(
        `Event ${event.key} nemá trigger.card_id.`,
      );
    }

    if (
      !event.trigger.args ||
      typeof event.trigger.args !==
        'object'
    ) {
      throw new Error(
        `Event ${event.key} nemá trigger.args.`,
      );
    }
  }
}


function uuidToBytes(uuid) {
  const hex =
    uuid.replaceAll('-', '');

  if (!/^[0-9a-f]{32}$/i.test(hex)) {
    throw new Error(
      `Neplatné UUID: ${uuid}`,
    );
  }

  return Buffer.from(
    hex,
    'hex',
  );
}


function bytesToUuid(bytes) {
  const hex =
    Buffer.from(bytes).toString('hex');

  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join('-');
}


function uuidV5(name, namespace) {
  const namespaceBytes =
    uuidToBytes(namespace);

  const hash = crypto
    .createHash('sha1')
    .update(namespaceBytes)
    .update(name)
    .digest();

  const bytes =
    Buffer.from(
      hash.subarray(0, 16),
    );

  bytes[6] =
    (bytes[6] & 0x0f) | 0x50;

  bytes[8] =
    (bytes[8] & 0x3f) | 0x80;

  return bytesToUuid(bytes);
}


function collectKnownCardIds(cards) {
  const ids = new Set();

  for (
    const [objectKey, card]
    of Object.entries(cards ?? {})
  ) {
    if (objectKey) {
      ids.add(objectKey);
    }

    if (
      card &&
      typeof card.id === 'string'
    ) {
      ids.add(card.id);
    }
  }

  return ids;
}


function groupEventsByDevice(events) {
  const groups = new Map();

  for (const event of events) {
    if (!groups.has(event.deviceName)) {
      groups.set(
        event.deviceName,
        [],
      );
    }

    groups.get(
      event.deviceName,
    ).push(event);
  }

  return groups;
}


function buildCards(
  events,
  eventUrl,
) {
  const cards = {};

  const groups =
    groupEventsByDevice(events);

  let columnIndex = 0;

  for (
    const [, deviceEvents]
    of groups.entries()
  ) {
    const triggerX =
      100 + columnIndex * 1150;

    const actionX =
      triggerX + 550;

    deviceEvents.forEach(
      (event, eventIndex) => {
        const y =
          100 + eventIndex * 90;

        const triggerUuid =
          uuidV5(
            `${event.key}:trigger`,
            UUID_NAMESPACE,
          );

        const actionUuid =
          uuidV5(
            `${event.key}:action`,
            UUID_NAMESPACE,
          );

        cards[triggerUuid] = {
          type: 'trigger',
          id: event.trigger.card_id,
          args: event.trigger.args,
          x: triggerX,
          y,
          outputSuccess: [
            actionUuid,
          ],
        };

        cards[actionUuid] = {
          type: 'action',
          id: HTTP_ACTION_CARD_ID,
          args: {
            method: 'post',
            url: eventUrl,
            headers:
              'Content-Type: application/json',
            body: JSON.stringify({
              key: event.key,
            }),
          },
          x: actionX,
          y,
        };
      },
    );

    columnIndex += 1;
  }

  return cards;
}


function flowName(flow) {
  return String(
    flow?.name ?? '',
  ).trim();
}


async function main() {
  const {
    apply,
    eventUrl,
  } = parseArguments();

  const root =
    process.cwd();

  const configPath =
    path.resolve(
      root,
      CONFIG_PATH,
    );

  console.log(
    'LoxBridge Homey Event Flow Sync',
  );
  console.log(
    '===============================',
  );

  console.log(
    `Config:    ${CONFIG_PATH}`,
  );
  console.log(
    `Flow:      ${MANAGED_FLOW_NAME}`,
  );
  console.log(
    `Event URL: ${eventUrl}`,
  );
  console.log(
    `Režim:     ${
      apply
        ? 'APPLY'
        : 'DRY RUN'
    }`,
  );

  console.log();

  const config =
    await loadConfig(
      configPath,
    );

  const events =
    collectEvents(config);

  validateEvents(events);

  console.log(
    `Nalezeno eventů: ${events.length}`,
  );
  console.log();

  const grouped =
    groupEventsByDevice(events);

  for (
    const [deviceName, deviceEvents]
    of grouped.entries()
  ) {
    console.log(
      `${deviceName}:`,
    );

    for (const event of deviceEvents) {
      console.log(
        `  ${event.key}`,
      );
    }

    console.log();
  }

  const cards =
    buildCards(
      events,
      eventUrl,
    );

  console.log(
    'Advanced Flow plán:',
  );
  console.log(
    `  triggerů:    ${events.length}`,
  );
  console.log(
    `  HTTP akcí:   ${events.length}`,
  );
  console.log(
    `  karet celkem: ${
      Object.keys(cards).length
    }`,
  );

  console.log();
  console.log(
    `Připojuji se k Homey ${config.homey.ip}...`,
  );

  const homey =
    await HomeyAPI.createLocalAPI({
      address:
        `http://${config.homey.ip}`,
      token: config.homey.token,
    });

  console.log(
    'Připojení k Homey: OK',
  );

  console.log();
  console.log(
    'Ověřuji dostupné Homey Flow karty...',
  );

  const [
    triggerCards,
    actionCards,
  ] = await Promise.all([
    homey.flow.getFlowCardTriggers(),
    homey.flow.getFlowCardActions(),
  ]);

  const triggerCardIds =
    collectKnownCardIds(
      triggerCards,
    );

  const actionCardIds =
    collectKnownCardIds(
      actionCards,
    );

  for (const event of events) {
    if (
      !triggerCardIds.has(
        event.trigger.card_id,
      )
    ) {
      throw new Error(
        `Homey nezná trigger kartu: ${event.trigger.card_id}`,
      );
    }
  }

  console.log(
    `Trigger karty: OK (${events.length})`,
  );

  if (
    !actionCardIds.has(
      HTTP_ACTION_CARD_ID,
    )
  ) {
    throw new Error(
      `Homey nezná HTTP action kartu: ${HTTP_ACTION_CARD_ID}`,
    );
  }

  console.log(
    'HTTP action karta: OK',
  );

  console.log();
  console.log(
    'Načítám existující Advanced Flows...',
  );

  const advancedFlows =
    await homey.flow.getAdvancedFlows();

  const flows =
    Object.values(
      advancedFlows ?? {},
    );

  const managedFlows =
    flows.filter(
      flow =>
        flowName(flow) ===
        MANAGED_FLOW_NAME,
    );

  if (managedFlows.length > 1) {
    throw new Error(
      `Existuje více Flowů s názvem "${MANAGED_FLOW_NAME}".`,
    );
  }

  const managedFlow =
    managedFlows[0] ?? null;

  const otherLoxBridgeFlows =
    flows.filter(flow => {
      const name =
        flowName(flow);

      return (
        name
          .toLocaleLowerCase()
          .startsWith('loxbridge') &&
        name !== MANAGED_FLOW_NAME
      );
    });

  if (managedFlow) {
    console.log(
      `Managed Flow nalezen: ${managedFlow.id}`,
    );
    console.log(
      `Aktuální stav: ${
        managedFlow.enabled
          ? 'ENABLED'
          : 'DISABLED'
      }`,
    );
  } else {
    console.log(
      'Managed Flow zatím neexistuje.',
    );
  }

  if (
    otherLoxBridgeFlows.length
  ) {
    console.log();
    console.log(
      'POZOR: další LoxBridge Flowy v Homey:',
    );

    for (
      const flow
      of otherLoxBridgeFlows
    ) {
      console.log(
        `  - ${flowName(flow)} (${flow.id})`,
      );
    }

    console.log(
      'Tyto Flowy synchronizátor NEZMĚNÍ.',
    );
  }

  /*
   * Bezpečnost:
   *
   * - existující managed Flow zachová svůj enabled stav
   * - úplně nový managed Flow vznikne vypnutý
   */
  const desiredFlow = {
    name: MANAGED_FLOW_NAME,
    enabled:
      managedFlow
        ? Boolean(
            managedFlow.enabled
          )
        : false,
    cards,
  };

  if (!apply) {
    console.log();
    console.log(
      'DRY RUN — Homey nebyl změněn.',
    );

    if (managedFlow) {
      console.log(
        `Při --apply bude aktualizován existující Flow ${managedFlow.id}.`,
      );
    } else {
      console.log(
        'Při --apply bude vytvořen nový vypnutý managed Flow.',
      );
    }

    return;
  }

  console.log();

  if (managedFlow) {
    console.log(
      `Aktualizuji "${MANAGED_FLOW_NAME}"...`,
    );

    await homey.flow.updateAdvancedFlow({
      id: managedFlow.id,
      advancedflow: desiredFlow,
    });

    console.log(
      `Advanced Flow aktualizován: ${managedFlow.id}`,
    );
  } else {
    console.log(
      `Vytvářím "${MANAGED_FLOW_NAME}"...`,
    );

    const created =
      await homey.flow.createAdvancedFlow({
        advancedflow:
          desiredFlow,
      });

    console.log(
      `Advanced Flow vytvořen: ${created.id}`,
    );
  }

  console.log();
  console.log(
    'Synchronizace dokončena.',
  );
}


main().catch(error => {
  console.error();
  console.error(
    'CHYBA:',
    error?.message ?? error,
  );

  process.exitCode = 1;
});
