# LoxBridge Profile Engine – Phase 2 / Event Bridge v2

Tento balík je inkrementální aktualizace nad Phase 1.
Nahrazuje předchozí Phase 2 balík, který nebylo potřeba instalovat.

## Co mění

- Fibaro FGRGBWM-442 Input 1..4 už nejsou falešné binární hodnoty z `measure_voltage.*`.
- Profile Engine je modeluje jako skutečné Homey scene eventy.
- Pro každý vstup podporuje Press 1x / Press 2x / Press 3x / Hold / Release.
- Trigger argumenty odpovídají přímo hodnotám Flow karty Homey (`input=1..4`, `scene=Key Pressed ...`).
- Přidán lokální HTTP listener `:7010/event` pro Homey Flow eventy.
- NORMAL XML generuje digitální impulsní vstupy (`Analog=false`).
- RAW XML dál obsahuje původní `measure_voltage.input1..4`.

## Očekávaný stav na současném exportu

- 57 profilovaných zařízení
- 40 event vstupů (2x Fibaro × 4 vstupy × 5 eventů)
- 8 raw Fibaro voltage vstupů skrytých v NORMAL režimu
- 313 vstupů v NORMAL XML
- 13 unit testů

## Příklad

`LED Obývák / Input 1 / dvojstisk`:

```text
Homey trigger:
Switch is pressed
Input = 1
Scene = Key Pressed 2 times

LoxBridge event key:
led_obyvak_input_1_press_2x

Loxone UDP:
led_obyvak_input_1_press_2x=1
```
