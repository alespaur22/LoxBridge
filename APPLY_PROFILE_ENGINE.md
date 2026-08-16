# LoxBridge Profile Engine – první refaktor

Tento balík je určený k překopírování přes aktuální repozitář po commitu
`Complete Homey light profiles`.

## 1. Zastavit LoxBridge

```bash
Ctrl + C
```

## 2. Překopírovat soubory balíku přes repozitář

Balík neobsahuje `config/config.yaml`, `config.generated.yaml`, `.venv`,
`node_modules` ani Git metadata.

## 3. Aktivovat správné prostředí

```bash
cd /home/ales/dev/loxbridge
source .venv/bin/activate
```

## 4. Vygenerovat nové schéma konfigurace

Tohle je povinné. Nový realtime očekává Profile Engine schema 2.

```bash
python -m loxbridge.generate
```

## 5. Kontroly

```bash
python -m unittest discover -s tests -v
node --check loxbridge/homey/realtime.mjs
python -m compileall -q loxbridge tests
```

## 6. XML výstupy

Výstupní příkazy jsou semanticky stejné jako před refaktorem (163 příkazů),
takže už vložené Loxone Outputs není nutné kvůli tomuto refaktoru měnit.

Kontrolní generování:

```bash
python -m loxbridge.addon.udp_output_xml_generator
```

## 7. XML vstupy – běžný režim

```bash
python -m loxbridge.addon.udp_xml_generator --mode normal
```

Šablona se jmenuje:

```text
LoxBridge - Homey Inputs
```

U Fibaro RGBW profilů jsou raw `measure_voltage.input1..4` nahrazené
normalizovanými 0/1 vstupy:

```text
LED Obývák - Input 1
LED Obývák - Input 2
LED Obývák - Input 3
LED Obývák - Input 4
```

Stejně pro LED Postel.

Raw/debug varianta zůstává dostupná:

```bash
python -m loxbridge.addon.udp_xml_generator \
  --mode raw \
  --output exports/LoxBridge_VirtualInputs_RAW.xml
```

## 8. Spustit LoxBridge

```bash
python -m loxbridge.main
```

První fyzický test po refaktoru:

1. Ověřit jeden již funkční světelný příkaz (např. LED Obývák RGB/Lumitech).
2. Ověřit LED Koupelna White.
3. Stisknout tlačítko na Input 1 LED Obývák a zkontrolovat, zda se
   `led_obyvak_input_1` přepne `0 → 1 → 0`.

Pokud Input 1 nedosáhne prahu 0.5 V, upraví se pouze profilová transformace,
ne runtime ani XML generátory.
