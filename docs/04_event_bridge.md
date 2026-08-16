# Event Bridge

LoxBridge rozlišuje dva typy Homey vstupů:

- **state** – trvalá hodnota capability (teplota, pohyb, on/off, ...),
- **event** – jednorázová událost Homey Flow triggeru (1x, 2x, 3x, hold, release, scene, ...).

Eventy se nepřekládají na umělý stav 0/1. Homey Flow pošle HTTP POST na lokální LoxBridge:

```text
POST http://<loxbridge>:7010/event
Content-Type: application/json

{"key":"led_obyvak_input_1_press_2x"}
```

LoxBridge ověří:

1. zdrojová IP odpovídá `homey.ip`,
2. `key` existuje v Profile Engine manifestu.

Potom odešle jediný UDP paket do Loxone:

```text
led_obyvak_input_1_press_2x=1
```

V NORMAL XML je event vytvořen jako `Analog="false"`, takže paket funguje jako impuls.

## Fibaro RGBW Controller 2

Driver `homey:app:com.fibaro:FGRGBWM-442` používá v režimu Scene Flow trigger `FGRGBWM-442:scene`.

Flow karta používá argument `input` s hodnotami `1` až `4` a argument `scene` s hodnotami:

- `Key Pressed 1 time`
- `Key Pressed 2 times`
- `Key Pressed 3 times`
- `Key Held Down`
- `Key Released`

Profile Engine proto vytváří pro každý Input 1..4:

- `Press 1x`
- `Press 2x`
- `Press 3x`
- `Hold`
- `Release`

Například:

```text
led_obyvak_input_1_press_1x
led_obyvak_input_1_press_2x
led_obyvak_input_1_press_3x
led_obyvak_input_1_hold
led_obyvak_input_1_release
```

Původní `measure_voltage.input1..4` zůstávají dostupné v RAW XML, ale v NORMAL XML jsou skryté.

## HTTP listener

Výchozí endpoint:

```text
0.0.0.0:7010/event
```

Phase 2 používá současně whitelist event klíčů a kontrolu zdrojové IP Homey. Samostatné event secret/authentication je plánováno před stabilní v1.0.
