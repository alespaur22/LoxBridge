# Profile Engine

LoxBridge od schématu konfigurace `2` nepoužívá XML generátory jako místo,
kde se hádá význam Homey capabilities. Význam zařízení se určí jednou při
`python -m loxbridge.generate` a uloží se do `config/config.generated.yaml`.

## Tok dat

```text
Homey export
   ↓
loxbridge.profiles
   ↓
config.generated.yaml
   ├─ profile
   ├─ synthetic commands
   └─ normalized inputs
   ↓
realtime + XML generators
```

Tím je profil zařízení jeden zdroj pravdy pro runtime i Loxone šablony.

## Aktuální profily

- `light.dimmer`
- `light.tunable_white`
- `light.rgb`
- `light.rgb_tunable_white`
- `light.rgb_white_channel`
- `light.switch`
- `climate.ac`
- `climate.thermostat`
- `sensor.motion`
- `sensor.environment`
- `sensor.generic`
- `switch.socket`
- `switch.generic`
- `water.valve`
- `input.remote`
- `generic`

## Syntetické světelné příkazy

Profile Engine vytváří podle capabilities například:

```text
LED Obývák
  led_obyvak_rgb
  led_obyvak_lumitech

LED Chodba
  led_chodba_dimmer

LED Koupelna
  led_koupelna_rgb
  led_koupelna_white
```

`realtime.mjs` ani XML generátor už nemusí znovu poznávat konkrétní typ světla.

## Normalizované vstupy (aktuálně neaktivní)

Profile Engine má mechanismus, který by uměl z raw Homey capability vytvořit
logický Loxone vstup — transformaci `binary_threshold` (`convertNormalizedInput`
v `realtime.mjs`, threshold výchozně 0.5). `build_normalized_inputs()` v
`loxbridge/profiles.py` ale dnes vždy vrací prázdný seznam a v
`config.generated.yaml` je aktuálně **0 normalizovaných vstupů**.

Případ, který tuhle transformaci původně motivoval — Fibaro RGBW Controller 2,
`measure_voltage.input1..4` → `led_obyvak_input_1..4` jako 0/1 stav — je dnes
řešený jinak: přes eventy (`build_event_inputs()`, viz
[docs/04_event_bridge.md](04_event_bridge.md)), ne přes normalizovaný stav.
Raw `measure_voltage.*` capability je u tohoto driveru v NORMAL XML potlačená
(`suppress_raw_inputs`), takže tam dnes není ani raw, ani normalizovaná
podoba — jen impulsní eventy.

`binary_threshold` kód (Python i `realtime.mjs`) v repozitáři zůstává, takže
jde o mechanismus, který lze znovu zapojit voláním `build_normalized_inputs()`
s reálnou logikou, ne o smazanou funkci.

## Generování vstupů

Běžná šablona:

```bash
python -m loxbridge.addon.udp_xml_generator --mode normal
```

Raw/debug šablona:

```bash
python -m loxbridge.addon.udp_xml_generator \
  --mode raw \
  --output exports/LoxBridge_VirtualInputs_RAW.xml
```

## Po změně profilů

Vždy znovu vygenerovat konfiguraci:

```bash
python -m loxbridge.generate
```

`realtime.mjs` kontroluje verzi schématu a při starém `config.generated.yaml`
raději skončí s jasnou chybou, než aby tiše přestal obsluhovat syntetické
příkazy.
