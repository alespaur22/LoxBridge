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

## Normalizované vstupy

Profile Engine může z raw Homey capability vytvořit logický Loxone vstup.
První podporovaná transformace je `binary_threshold`.

U testovaného Fibaro RGBW driveru jsou například:

```text
measure_voltage.input1 → led_obyvak_input_1
measure_voltage.input2 → led_obyvak_input_2
```

V režimu `normal` je raw analogový vstup v XML nahrazen normalizovaným stavem
0/1. Runtime stále může posílat raw hodnotu, takže diagnostika zůstává možná.

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
