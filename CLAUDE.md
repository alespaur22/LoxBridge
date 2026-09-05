# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LoxBridge is a realtime bridge between a Homey Pro smart-home hub and a Loxone Miniserver. It mirrors Homey device capability values to Loxone (via UDP virtual inputs) and lets Loxone send commands back to Homey (via UDP virtual outputs / a Node helper process). It is a personal home-automation project, not a published package — most user-facing text, comments, and error messages are in Czech.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # PyYAML
npm install                       # homey-api, yaml
```

Runtime needs a real `config/config.yaml` (git-ignored, not present in a fresh checkout) with `homey.ip`, `homey.token`, `loxone.ip`, `loxone.port`. There is no committed example to copy from — `config/config.example.yaml` exists but is empty.

## Commands

Run the bridge (long-running realtime process):
```bash
python -m loxbridge.main
```

Regenerate the Profile Engine config after any device/profile change — **always required** before running the bridge or XML generators when devices/capabilities changed:
```bash
python -m loxbridge.generate
```

Generate Loxone virtual-input XML (state values + button events):
```bash
python -m loxbridge.addon.udp_xml_generator --mode normal
python -m loxbridge.addon.udp_xml_generator --mode raw --output exports/LoxBridge_VirtualInputs_RAW.xml
```

Generate Loxone virtual-output XML (commands Loxone can send to Homey):
```bash
python -m loxbridge.addon.udp_output_xml_generator
```

Incremental "delta" generation/confirmation (only new inputs/outputs since the last confirmed baseline in `config/loxone_imported_state.json`) — used to avoid re-touching an already-wired Loxone project on every regen:
```bash
python -m loxbridge.addon.delta_generator
python -m loxbridge.addon.delta_confirm --apply
```

Export the current Homey device list (required before `python -m loxbridge.generate` can see new devices):
```bash
node loxbridge/homey/export_devices.mjs
```

Tests (unittest, no pytest):
```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_profiles -v          # single module
python -m unittest tests.test_profiles.ProfileEngineTests.test_rgb_tunable_white_profile -v  # single test
```

Sanity checks before/after touching the Node realtime helper or Python packages:
```bash
node --check loxbridge/homey/realtime.mjs
python -m compileall -q loxbridge tests
```

No linter/formatter is configured for either language.

## Architecture

### Two-stage pipeline: generate, then run

LoxBridge does **not** infer device semantics at runtime. Everything is decided once, offline, by the **Profile Engine** (`loxbridge/profiles.py`, driven by `loxbridge/generate.py`), and the result is written to `config/config.generated.yaml`. The realtime bridge and all XML generators only ever read that generated file — they never re-derive meaning from raw Homey capabilities.

```
node loxbridge/homey/export_devices.mjs   → exports/homey_devices.json (raw Homey export)
python -m loxbridge.generate              → config/config.generated.yaml (profile + synthetic commands + events)
python -m loxbridge.main                  → runs the bridge using config.generated.yaml
python -m loxbridge.addon.udp_xml_generator / udp_output_xml_generator → Loxone XML using config.generated.yaml
```

`config/config.yaml` (hand-maintained, has `homey`/`loxone` connection settings and is the *source* for regeneration) is never overwritten by `loxbridge.generate` — only `config.generated.yaml` is. `Bridge.runtime_config_path()` (`loxbridge/bridge/bridge.py`) prefers `config.generated.yaml` and falls back to `config.yaml` if it doesn't exist.

`config/config.generated.yaml` carries a `loxbridge.schema_version` (`PROFILE_SCHEMA_VERSION` in `loxbridge/profiles.py`, currently `5`). `loxbridge/homey/realtime.mjs` hard-fails at startup if the schema version doesn't match (`REQUIRED_PROFILE_SCHEMA_VERSION`), so a Python-side profile change and the Node runtime are always kept in lock-step. **Bump this constant in both files together** when the shape of `commands`/`inputs`/`events` in the manifest changes.

### Profile Engine (`loxbridge/profiles.py`)

For each exported Homey device, `build_device_manifest()` determines, once:
- **`profile`** — a device archetype like `light.rgb_tunable_white`, `climate.ac`, `sensor.motion`, `switch.socket`, etc. (`detect_primary_profile`).
- **`commands`** — synthetic composite Loxone commands (`build_commands`), e.g. a single `_rgb` or `_lumitech` key that internally targets several Homey capabilities (`onoff`, `dim`, `light_hue`, ...). These are what `realtime.mjs` looks up in `buildProfileCommandMap()` to know how to fan a single Loxone UDP command out to multiple `setCapabilityValue` calls.
- **`inputs`** — normalized state transforms (currently only `binary_threshold`, e.g. turning a raw `measure_voltage` into a clean 0/1).
- **`events`** — one-shot Homey Flow trigger events (button presses, "scene" triggers) that are *not* modeled as state. Per-driver adapters exist for specific hardware (Fibaro RGBW Controller 2, Shelly RGBW Gen2/Plus, Aeotec Pico Duo) that translate a Homey Flow "trigger card" into `device_input_N_press_1x` / `_press_2x` / `_hold` / `_release` style keys.

Adding support for a new light/device type or a new button-capable driver means editing `detect_primary_profile` / `build_commands` / `build_event_inputs` in this one file — the realtime bridge and both XML generators pick it up automatically once `config.generated.yaml` is regenerated.

### State vs. event: two different transport paths

- **State** (temperature, on/off, dim level, ...) flows continuously: Homey capability change → `realtime.mjs` subscription callback → stdout JSON line → `Bridge.process_event()` (Python) → UDP packet to Loxone (`loxbridge/loxone/udp.py`).
- **Event** (a single button press) is not a persistent value. Homey Flow POSTs `{"key": "..."}` to a local HTTP listener (`loxbridge/homey/event_listener.py`, port `7010`, path `/event`). The listener checks the source IP against `homey.ip` and the key against the set of event keys declared in `config.generated.yaml` (`Bridge.collect_event_keys`), then sends one UDP impulse to Loxone. See `docs/04_event_bridge.md` for the Fibaro RGBW example end-to-end.

### Bridge process (`loxbridge/bridge/bridge.py`)

`Bridge.run()` is the Python supervisor: it spawns `loxbridge/homey/realtime.mjs` as a child Node process, talking to it over stdin/stdout as newline-delimited JSON:
- Python → Node: `{"type": "command", "key": ..., "value": ..., "request_id": ...}` (from a Loxone UDP virtual output, received in `loxbridge/loxone/udp_listener.py` on port `7002`).
- Node → Python: `{"type": "value"|"command_result"|"ready"|"warning"|"fatal", ...}`.

It also runs the Homey→Loxone event HTTP listener (port `7010`) and the Loxone→Homey UDP command listener (port `7002`) as background threads, and auto-restarts the Node helper (`RESTART_DELAY = 3.0s`) if it exits unexpectedly.

The Node side (`realtime.mjs`) additionally does light-weight command *merging* for composite light profiles: RGB and white-channel/temperature commands for the same device are coalesced with a short debounce (`LIGHT_MERGE_DELAY_MS = 120`) so that Loxone sending hue+saturation+dim as separate near-simultaneous UDP packets doesn't cause visible flicker or redundant Homey API calls (`selectMergedLightMode`, `selectRgbwMode`, `getMergedLightState`, `getRgbwState`).

### XML generation and delta workflow (`loxbridge/addon/`)

- `udp_xml_generator.py` / `udp_output_xml_generator.py` are the **current** generators; they read `config.generated.yaml` and emit Loxone `.xml` templates for import into Loxone Config.
- `delta_generator.py` / `delta_confirm.py` / `delta_state.py` / `delta.py` layer a "baseline" workflow on top: `config/loxone_imported_state.json` tracks what's already been imported into the live Loxone project, so re-running the generators after adding one device doesn't force re-importing everything — only the delta is emitted, and `delta_confirm.py --apply` commits the newly-imported items to the baseline.
- `addon_generator.py` (`TemplateGenerator`) and `xml_generator.py` (`XmlGenerator`) implement an older `.LxAddon`-packaging code path (`loxbridge/addon/generate.py`) that imports `loxbridge.homey.parser` and `loxbridge.models.device`, neither of which exists in the repo anymore — treat this path as legacy/dead and prefer the `udp_xml_generator`/`udp_output_xml_generator` + Profile Engine flow above for anything new.
- `translations.py` maps Homey capability IDs to Czech display titles used in generated Loxone element names.

### Ad-hoc Homey scripts (`loxbridge/homey/*.py`, not part of the bridge)

`list_devices.py`, `show_device.py`, `inspect_device.py`, `watch_capability.py`, `watch_motion.py`, `send_motion_to_loxone.py` are standalone debugging/exploration utilities, largely superseded by the Profile Engine + bridge but still useful for poking at a single device's raw Homey capabilities. Several read `HOMEY_IP`/`HOMEY_TOKEN` from the environment rather than `config.yaml`.


# LoxBridge — Project Context

## Co to je
Univerzální překladač mezi Homey a Loxone. NENÍ to další systém chytré domácnosti
a NEDĚLÁ rozhodovací logiku (topení, scény, automatizace) — to patří do Loxone Config.
Loxbridge pouze:
- zpřístupňuje zařízení z Homey v Loxone (skoro jako nativní)
- provádí technické transformace protokolu (škálování, enum mapping, RGB↔HSB apod.)

Vrstvy:

    LOXONE (mozek domu, regulace, scény)
       ↕ virtuální I/O (UDP)
    LOXBRIDGE (překlad, mapování, normalizace, routing)
       ↕ lokální Homey API
    HOMEY (knihovna ovladačů zařízení — Zigbee/Z-Wave/Wi-Fi/cloud)

## Co Loxbridge NEDĚLÁ
- Nerozhoduje kdy topit/chladit/svítit — to je Loxone Config
- Není vlastní automatizační engine
- Výjimka: technické transformace (Loxone RGB → hue+sat+dim) JSOU jeho úkol

## Aktuální stav (ověřit proti kódu při každé větší práci!)
Hotovo:
- Homey ↔ Loxone realtime obousměrná komunikace (UDP + HTTP listener)
- Běh jako systemd service na Raspberry Pi (auto-restart, přežije reboot)
- Export Homey zařízení → config.yaml → generator → config.generated.yaml
- Profile Engine — normalizace capabilities, detekce typu zařízení (climate.ac,
  light.dimmer, RGB/RGBW, switch...), syntetické entity (RGB z hue+sat+dim)
- Event handling pro tlačítka (press_1x/2x/3x, hold, release) — Fibaro, Shelly
- Generátory Loxone XML (Virtual Inputs + Virtual Outputs)
- Automatický reconnect (Python supervisor restartuje realtime helper)

Chybí / TODO:
- GUI (dashboard, device mapping editor, diagnostika, logy) — zatím vše přes CLI/YAML
- Univerzální pokrytí všech typů Homey zařízení (zatím vybrané profily)
- Mock/test zařízení bez fyzického hardwaru (nice-to-have, ne priorita)

## Architektonický princip (drž se ho!)
Runtime a XML generátory NESMÍ znát konkrétní Homey driver (žádné
`if Fibaro / if Shelly / if Aqara` v hlavní logice). Speciální adaptery jen
tam, kde zařízení dělá opravdu nestandardní věc (viz event adapters).
Profile Engine je oddělovací vrstva — cíl je generický capability model →
profil, ne pevně zakódované drivery.

## Cíl "Loxbridge 1.0" (než se řeší GUI)
1. Všechna reálně používaná zařízení fungují správně
2. Základní typy normalizované přes Profile Engine
3. Obousměrná komunikace stabilní
4. Eventová tlačítka fungují
5. Přežije restart Homey/RPi/Loxone a znovu se spojí
6. Konfigurace se generuje reprodukovatelně
7. Loxone XML se generuje automaticky
8. Běžné zařízení nevyžaduje ruční patch Pythonu

Teprve POTOM GUI (Loxbridge 2.0).

## Reference
Plný kontext, diagramy a historie rozhodnutí: viz PLAN.md v rootu.
