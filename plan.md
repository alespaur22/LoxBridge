Když to vezmu úplně od začátku, **Loxbridge má být univerzální překladač mezi Homey a Loxone**. Ne další systém chytré domácnosti vedle nich a ne místo, kde budeme programovat vytápění, světelné scény nebo automatizace. Jeho úkolem je zařídit, aby zařízení dostupné v Homey vypadalo pro Loxone skoro jako nativní zařízení — rychle, obousměrně a pokud možno bez ručního bastlení desítek virtuálních vstupů.

A důležité je, že dnes už jsme značnou část toho jádra skutečně postavili.

# 1. Co je Loxbridge

Představ si tři vrstvy:

```text
┌─────────────────────┐
│       LOXONE        │
│                     │
│ regulace, logika,   │
│ místnosti, scény... │
└─────────┬───────────┘
          │
          │ virtuální I/O
          │
          ▼
┌─────────────────────┐
│     LOXBRIDGE       │
│                     │
│ překlad              │
│ mapování             │
│ normalizace          │
│ routing              │
└─────────┬───────────┘
          │
          │ lokální Homey API
          ▼
┌─────────────────────┐
│       HOMEY         │
│                     │
│ Zigbee / Z-Wave /   │
│ Wi-Fi / cloud apps  │
│ zařízení            │
└─────────────────────┘
```

Homey je pro nás **obrovská knihovna ovladačů zařízení**.

Loxone je **mozek domu**.

Loxbridge je **adaptér mezi nimi**.

Tohle rozdělení bych chtěl zachovat i do budoucna.

---

# 2. Co už dnes Loxbridge reálně umí

Dnešní Loxbridge už není experiment typu „pošli jednu teplotu do Loxone“.

V jednom z posledních ověřených běhů startoval s:

**57 zařízeními, 281 realtime capabilities, 13 zatím nepodporovanými capabilities a 26 eventy.** Současně běžel UDP listener pro příkazy `Loxone → Homey` a HTTP listener pro eventy z Homey. 

Navíc běží na Raspberry Pi jako **systemd service**. To znamená, že:

```text
VS Code může být zavřený
SSH může být odpojené
terminál může být zavřený
        ↓
Loxbridge dál běží
```

a po restartu RPi se má spustit automaticky.

To už je správný základ pro zařízení, které má být součást infrastruktury domu, ne vývojový script.

---

# 3. Jak funguje směr Homey → Loxone

Tohle je například:

> Homey teploměr změní teplotu z 24,1 na 24,2 °C.

Loxbridge má pomocnou Node část `realtime.mjs`, která se **lokálně připojí přímo k Homey**, načte zařízení a pracuje s jejich capabilities. Homey zařízení se dohledávají primárně podle ID, případně podle jména.  

Pak například přijde:

```text
Homey:
Teploměr Obývák
measure_temperature = 24.2
```

Loxbridge ví, že tato capability má Loxone key například:

```text
teplomer_obyvak_measure_temperature
```

a pošle do Loxone:

```text
teplomer_obyvak_measure_temperature=24.2
```

V logu to dnes vidíme jako:

```text
Odesláno do Loxone: ...
... [realtime]
```

Takto dnes chodí teploty, vlhkosti, příkony, napětí, stavy světel, setpointy klimatizace atd. Reálné logy ukazují například realtime změny jasu, hue, saturation nebo hodnot ze senzorů. 

A při startu Loxbridge pošle i **počáteční stav**, takže nemusí čekat, až se každé zařízení poprvé změní.

---

# 4. Co je vlastně „capability“

To je základ Homey architektury.

Jedno zařízení není jedna hodnota.

Například Panasonic klima může mít:

```text
onoff
target_temperature
measure_temperature
measure_temperature_inside
measure_temperature_outside
operation_mode
fan_speed
eco_mode
measure_power
meter_power
...
```

Loxbridge už obsahuje normalizační mapu, která říká například:

```text
Homey onoff
→ Loxbridge power
→ boolean
→ obousměrné

Homey dim
→ Loxbridge brightness
→ number
→ obousměrné

measure_temperature_inside
→ inside_temperature
→ °C
→ pouze Homey → Loxone

target_temperature
→ target_temperature
→ °C
→ obousměrné

operation_mode
→ enum
→ obousměrné
```

Směry `INPUT`, `OUTPUT` a `BIDIRECTIONAL` jsou už přímo součástí dnešního datového modelu.  A například klimatizační capabilities už tam mají definovaný směr a datový typ. 

Tohle je důležité pro budoucí GUI.

GUI nebude všechno vymýšlet od nuly. Velkou část už bude Loxbridge **vědět sám**.

---

# 5. Jak funguje Loxone → Homey

Opačný směr je třeba:

> Loxone chce změnit Panasonic z 24 °C na 26 °C.

Loxone má virtuální výstup, který pošle lokálním UDP:

```text
ac_obyvak_target_temperature=26
```

do Loxbridge.

Generátor virtuálních výstupů už dnes existuje. Vytváří Loxone `VirtualOut` směřující přes `/dev/udp/<IP Loxbridge>/<port>` a podle typu capability generuje například:

```text
boolean:
key=1
key=0

analog:
key=<v>
```

 

Loxbridge má mapu:

```text
ac_obyvak_target_temperature
        ↓
Homey device:
AC Obývák
        ↓
capability:
target_temperature
```

a zavolá Homey:

```text
setCapabilityValue(target_temperature, 26)
```

Homey to pošle Panasonicu.

A pak je důležitá druhá část:

```text
Panasonic / Homey
        ↓
target_temperature = 26
        ↓
realtime update
        ↓
Loxbridge
        ↓
Loxone
```

Takže máme **feedback**.

Proto jsme dnes viděli:

```text
Loxone → LoxBridge: ac_obyvak_target_temperature=26
...
AC Obývák: target_temperature=26
...
Homey příkaz potvrzen
```

Tohle je už skutečně obousměrná integrace.

---

# 6. Loxbridge tedy nedělá klasický polling

Základní stavové capabilities jsou dnes řešené **realtime odběrem změn Homey**.

To je jeden z důvodů, proč jsme nechtěli stavět most jen na MQTT nebo na periodickém:

```text
každých 5 sekund:
zeptám se Homey na všechno
```

Realtime část se připojuje lokálním Homey API a vytváří subscriptions pro nakonfigurované capabilities. 

Navíc má Python supervisor automatický reconnect. Pokud realtime helper spadne, Loxbridge čeká krátkou dobu a znovu ho nastartuje. 

Pozor ale na jednu věc:

**Loxbridge může být realtime, ale zdroj zařízení nemusí být realtime.**

Dnešní Panasonic Homey app například sama zřejmě některé údaje dotahuje z Panasonic cloudu zhruba po minutě.

Takže:

```text
Panasonic cloud
       ↓ pomalé
Homey
       ↓ realtime
Loxbridge
       ↓ okamžitě
Loxone
```

Loxbridge neumí odstranit zpoždění, které vzniklo už před Homey.

---

# 7. Tlačítka jsou jiný problém než stav

Tady jsme už také udělali docela důležitý kus práce.

Hodnota:

```text
temperature = 24.2
```

má stav.

Ale například:

```text
double click
hold
release
```

není stav. Je to **událost**.

Proto Loxbridge rozlišuje:

```text
STATE
→ realtime capability

EVENT
→ krátký impuls
```

U Fibaro RGBW Controlleru 2 jsme zjistili, že tlačítkové vstupy nejsou spolehlivě reprezentované jako změny `measure_voltage`. Homey je publikuje přes Flow trigger. Proto Profile Engine pro tento driver generuje eventy jako:

```text
press_1x
press_2x
press_3x
hold
release
```



Podobnou specializaci máme i pro Shelly RGBW. 

Proto dnes Loxbridge vedle realtime kanálu používá také:

```text
Homey Flow
    ↓
HTTP
    ↓
Loxbridge :7010/event
    ↓
pulse
    ↓
Loxone
```

Při posledním ověřeném startu bylo takových povolených eventů **26**. 

---

# 8. Profile Engine je velmi důležitý

To je podle mě základ budoucího produktu.

Na úplném začátku jsme měli problém:

> Homey má stovky různých capabilities a každý výrobce se trochu liší. Jak to dostat do Loxone tak, aby z toho nebyl bordel?

Proto vznikla mezivrstva:

## Profile Engine

Ten se podívá na zařízení:

```text
driver
class
capabilities
setable / read-only
datové typy
```

a snaží se poznat:

> Co to vlastně je?

Například:

```text
climate.ac
climate.thermostat
light.dimmer
RGB / RGBW
switch.socket
switch.generic
input.remote
...
```

V jednom z posledních generování bylo například automaticky rozpoznáno **5× `climate.ac` a 5× `climate.thermostat`**. 

Profil pak neříká jen:

> pošli capability A.

Umí z několika Homey capabilities vytvořit jednu **syntetickou Loxone entitu**.

Například světlo:

```text
Homey:
onoff
dim
light_hue
light_saturation

            ↓ Profile Engine

Loxone:
RGB command
```

U RGBW už máme například syntetické příkazy pro RGB část a samostatný white channel. 

To je přesně rozdíl mezi:

**„proxy Homey API“**

a

**„integrací zařízení do Loxone“**.

---

# 9. Raw data vs. normalizovaná data

Dnes máme vlastně dvě úrovně.

Raw vrstva může být:

```text
homey.<device-id>.light_hue
homey.<device-id>.dim
...
```

nebo pozdější čitelnější key:

```text
led_obyvak_light_hue
led_obyvak_dim
```

Ale pro praktickou integraci nechceme, aby ses v Loxone hrabal v každé surové capability.

Chceme:

```text
LED Obývák
    ├ RGB
    ├ White
    ├ Power
    └ Input 1 events
```

Profile Engine už umí definovat:

```text
commands
inputs
events
suppress_raw_inputs
```



Takže GUI má později hlavně umožnit tuhle vrstvu **vidět a upravit**.

---

# 10. Jak dnes vzniká konfigurace

Dnes je proces vývojářský.

Homey se nejprve vyexportuje:

```text
Homey
 ↓
exports/homey_devices.json
```

Pak máme ruční:

```text
config/config.yaml
```

a generátor:

```bash
python -m loxbridge.generate
```

z toho vytvoří:

```text
config/config.generated.yaml
```

V jednom z posledních běhů obsahoval export **62 Homey zařízení**, do výsledné konfigurace šlo 57 a generátor zpracovával 294 capabilities. 

Důležité je:

```text
config.yaml
        ↓
Profile Engine + Homey export
        ↓
config.generated.yaml
        ↓
runtime
```

`config.generated.yaml` je tedy **strojově vytvořený manifest toho, co má Loxbridge skutečně provozovat**.

Runtime už umí odmítnout staré/neplatné schéma, takže se pomalu dostáváme i k verzování konfigurace. 

---

# 11. Loxone XML se už také generuje

Tohle je docela zásadní, protože právě to měl původně dělat budoucí GUI.

Máme generátor:

```text
config.generated.yaml
       ↓
Loxone Virtual Inputs XML
```

a:

```text
config.generated.yaml
       ↓
Loxone Virtual Outputs XML
```

Generátor vstupů už vytváří `VirtualInUdp` a rozlišuje raw, normalizované a eventové vstupy. 

Generátor výstupů umí:

```text
boolean
number
enum

synthetic RGB
Lumitech
Dimmer
White
...
```



Takže už dnes nemusíme ručně vytvářet stovky virtuálních příkazů jeden po druhém.

---

# 12. Kde jsme tedy dnes

Kdybych měl dát současný stav do jedné věty:

> **Máme funkční obousměrné runtime jádro a poměrně pokročilý generátor integrace, ale zatím je to nástroj pro vývojáře, ne pohodlný produkt pro konfiguraci domu.**

Přibližně bych to viděl takto:

| Oblast                                   | Stav                                        |
| ---------------------------------------- | ------------------------------------------- |
| Homey lokální spojení                    | ✅                                           |
| Homey → Loxone realtime                  | ✅                                           |
| Loxone → Homey                           | ✅                                           |
| potvrzení příkazů                        | ✅                                           |
| automatický reconnect                    | ✅                                           |
| běh jako systemd služba                  | ✅                                           |
| export Homey zařízení                    | ✅                                           |
| normalizace capabilities                 | ✅                                           |
| Profile Engine                           | ✅                                           |
| syntetické RGB/Dimmer atd.               | ✅                                           |
| tlačítkové eventy                        | ✅ pro vybrané drivery                       |
| XML generátor Loxone vstupů              | ✅                                           |
| XML generátor Loxone výstupů             | ✅                                           |
| klimatizace                              | ✅ technicky, ladíme Loxone regulační logiku |
| univerzální pokrytí všech Homey zařízení | 🟡                                          |
| GUI                                      | ❌                                           |
| pohodlné přidávání zařízení              | ❌                                           |
| GUI mapping capabilities                 | ❌                                           |
| diagnostický dashboard                   | ❌                                           |

---

# 13. Co Loxbridge naopak dělat NEMÁ

Tohle je teď po dnešním řešení klimatizace důležité.

Například:

```text
Kdy topit?
Kdy chladit?
Jaká je komfortní teplota?
Je noc?
Je otevřené okno?
Má se vypnout klima?
```

by primárně **neměl rozhodovat Loxbridge**.

To patří do:

```text
Loxone Config
```

Loxbridge má dostat:

```text
AC Obývák:
ON
HEAT
target 27
fan AUTO
```

a zajistit:

> Panasonic udělá přesně toto.

Stejně světla:

Loxbridge nemá rozhodovat:

> je tma, rozsviť obývák.

Má jen překládat:

```text
Loxone RGB = ...
↓
Homey Zigbee/Fibaro/Shelly = ...
```

Výjimkou jsou **technické transformace**, protože ty patří do bridge.

Například:

```text
Loxone RGB
       ↓
hue + saturation + dim
```

nebo:

```text
Homey enum "Cool"
       ↓
Loxone číslo 3
```

To není automatizace. To je překlad protokolu.

---

# 14. Kam chceme projekt dostat

Finální Loxbridge si představuju jako malou **lokální integrační appliance**.

Na Raspberry Pi poběží:

```text
Loxbridge runtime
+
webové GUI
```

A ty otevřeš třeba z Macu:

```text
http://loxbridge.local
```

a všechno nastavíš přes web.

Žádný:

```bash
nano config.yaml
python -m ...
vim ...
```

pro běžnou instalaci.

---

# 15. Jak by mělo vypadat GUI

Domovská stránka by měla být spíš dashboard než konfigurátor:

```text
LOXBRIDGE

Homey      ● Online
Loxone     ● Online

Devices             57
Active mappings     281
Events              26

Last Homey update   před 0.2 s
Last Loxone command před 3 s

Service             Running
```

A například chyby:

```text
⚠ LED XYZ
capability "foo" unsupported

⚠ AC Bedroom
Homey device unavailable
```

Neměl bys kvůli základní diagnostice chodit do:

```bash
journalctl -u loxbridge
```

---

# 16. Přidání nového Homey zařízení

Tohle je hlavní workflow.

Řekněme, že do Homey přidáš nový Zigbee senzor.

V GUI dáš:

```text
Devices
→ Refresh Homey
```

Loxbridge si přes Homey API stáhne zařízení.

Uvidíš například:

```text
Aqara Temperature Sensor

Zone: Ložnice
Class: sensor

Capabilities:
✓ measure_temperature
✓ measure_humidity
✓ measure_battery
```

Pak:

```text
[ Add to Loxbridge ]
```

Profile Engine řekne:

```text
Doporučený profil:
sensor.temperature_humidity
```

Ty ho přijmeš.

Hotovo.

---

# 17. Detail zařízení

Například Panasonic:

```text
AC Obývák
Profile: Climate / AC
Homey ID: e4a4...
Status: Online
```

A pod tím tabulka typu:

| Homey capability           | Loxbridge entity   | směr | typ  | Loxone                               |
| -------------------------- | ------------------ | ---- | ---- | ------------------------------------ |
| onoff                      | Power              | ↔    | bool | ac_obyvak_onoff                      |
| target_temperature         | Target temperature | ↔    | °C   | ac_obyvak_target_temperature         |
| measure_temperature_inside | Inside temperature | →    | °C   | ac_obyvak_measure_temperature_inside |
| operation_mode             | Mode               | ↔    | enum | ac_obyvak_operation_mode             |
| fan_speed                  | Fan                | ↔    | enum | ac_obyvak_fan_speed                  |
| measure_power              | Power consumption  | →    | W    | ac_obyvak_measure_power              |

A tady se dostáváme k tomu **mapování jednotlivých entit**, o kterém jsme se bavili.

---

# 18. Co bude možné u entity nastavit

Tady bych GUI rozdělil na jednoduchý a Advanced režim.

Normálně:

```text
Enabled:          ✓
Direction:        Homey ↔ Loxone
Name:             Target Temperature
Loxone key:       ac_obyvak_target_temperature
Type:             Number
Unit:             °C
```

Advanced by zpřístupnil například transformace:

```text
Input range
Output range

Scale
Offset
Invert

Round
Min
Max

Enum mapping
Deadband

Event / pulse
```

Například nějaký výrobce používá:

```text
brightness = 0...1
```

ale ty chceš v Loxone:

```text
0...100 %
```

GUI nastaví:

```text
0 → 0
1 → 100
```

Podobně enum:

```text
Homey:
Off
Heat
Cool
Dry
Fan

Loxone:
0
2
3
4
5
```

Tohle má být configurable bez zásahu do Pythonu.

---

# 19. Směry mapování

U každé entity budou čtyři smysluplné typy:

```text
Homey → Loxone

Loxone → Homey

Homey ↔ Loxone

Event → Loxone pulse
```

Takže například:

```text
measure_temperature
= Homey → Loxone

target_temperature
= obousměrné

button double-click
= event pulse
```

To odpovídá už dnešnímu internímu modelu direction/value type, takže GUI by pouze zpřístupňovalo něco, co v backendu už máme. 

---

# 20. Profily / šablony

Nechci, abys při každém světle nastavoval:

```text
onoff
dim
hue
saturation
temperature
...
```

Proto profily.

Například:

```text
Switch
Dimmer
RGB
RGBW
Tunable White
Temperature Sensor
Presence Sensor
Socket
Thermostat
Air Conditioner
Remote/Button
Water Valve
```

Profil udělá 90 % práce automaticky.

Pak ty jen něco případně přemapuješ.

To je přesně směr, kterým už dnešní Profile Engine jde.

---

# 21. Velmi důležitá věc: automatické rozpoznání ≠ pevně zakódovaný driver

Dlouhodobě nechci skončit s:

```python
if Fibaro:
   ...

if Shelly:
   ...

if Ikea:
   ...

if Aqara:
   ...
```

všude v programu.

Ideální je:

```text
Homey capability model
        ↓
generický profil
```

Například:

> zařízení má `onoff + dim`

→ pravděpodobně Dimmer.

> má `onoff + dim + hue + saturation`

→ RGB light.

Speciální driver adapter budeme potřebovat jen tam, kde Homey zařízení dělá něco opravdu nestandardního — jako dnes eventy Fibaro/Shelly.

Profile Engine už je připravený právě jako oddělovací vrstva; komentář v jeho kódu výslovně říká, že runtime ani XML generátory nemusí znát konkrétní Homey driver. 

To je velmi správná architektura.

---

# 22. Co se stane po kliknutí „Apply“

Cílově by GUI mělo udělat celý dnešní terminálový workflow samo:

```text
uživatel upraví mapping
        ↓
SAVE
        ↓
uložit user config
        ↓
Profile Engine
        ↓
vygenerovat config.generated.yaml
        ↓
validace
        ↓
vygenerovat Loxone XML
        ↓
restart/reload runtime
```

A GUI řekne:

```text
Configuration valid ✓

57 devices
283 mappings
26 events

Runtime restarted ✓
```

Když konfigurace není validní:

```text
NEAPLIKOVAT
```

a běžící konfigurace zůstane funkční.

Tohle je důležité pro spolehlivost.

---

# 23. Co s Loxone XML

Ideální cílová UX:

```text
Loxone
→ Integration
→ Export
```

a dostaneš:

**Virtual Inputs.xml**

**Virtual Outputs.xml**

Ty naimportuješ do Loxone Config.

Generátory už dnes prakticky máme, takže GUI pouze přidá tlačítko nad existující funkci.

Později můžeme řešit, jestli dokážeme generování a vložení do `.Loxone` projektu automatizovat ještě dál. Ale to bych zatím nepovažoval za nutnost.

---

# 24. Diagnostika zařízení

Tady bych chtěl, aby GUI bylo opravdu užitečné pro technika.

Otevřeš:

```text
AC Obývák
→ Live
```

a vidíš:

```text
Homey                           Loxone

onoff            false         0
target temp      24            24
inside temp      21            21
mode             Cool          3
fan              Auto          0
```

Pod tím:

```text
Last change:
21:47:13 target_temperature
Loxone → Homey
24 → 26

21:47:17
Homey confirmed
26
```

A tlačítko:

```text
[Test]
```

Například:

```text
Set target_temperature = 25
```

To nám obrovsky usnadní přesně takové ladění, jaké jsme dnes dělali s Panasonicem.

---

# 25. Log by měl být součást GUI

Dnes:

```bash
sudo journalctl -u loxbridge
```

je pro vývoj OK.

Finálně chci:

```text
Diagnostics → Logs
```

s filtrem:

```text
All
Errors
Homey → Loxone
Loxone → Homey
Events
Device: AC Obývák
```

A místo kilometrového logu:

```text
21:42:03  ← Loxone
AC Obývák / target_temperature = 26

21:42:06  → Homey
command accepted

21:42:09  ← Homey
target_temperature = 26

✓ confirmed 6.1 s
```

To z Loxbridge udělá opravdu použitelný integrační nástroj.

---

# 26. Testování zařízení, které fyzicky nemáme

To jsme nakousli a podle mě to patří až za GUI.

Homey API samozřejmě ukáže jen zařízení, která konkrétní Homey skutečně má.

Ale mohli bychom si uložit **device descriptor**:

```text
driver
class
capabilities
types
enum values
setable
...
```

Například někdo nám pošle export:

```text
Sonoff XYZ
```

My ho nahrajeme:

```text
Developer
→ Mock device
→ Import Homey descriptor
```

a Loxbridge bude umět na jeho modelu vyzkoušet:

```text
profil
generování XML
mapping
syntetické entity
```

bez fyzického zařízení.

To bych ale označil jako **pozdější vývojářskou funkci**, ne jako nezbytnou věc pro první ostrou verzi GUI.

---

# 27. Jak bych dnes definoval cílové vrstvy Loxbridge

Tohle je podle mě nejdůležitější obrázek celého projektu:

```text
┌───────────────────────────────────────────┐
│                   GUI                     │
│ Devices / Mapping / Diagnostics / Export  │
└────────────────────┬──────────────────────┘
                     │
┌────────────────────▼──────────────────────┐
│             USER CONFIGURATION            │
│ která zařízení, názvy, overrides, mapping │
└────────────────────┬──────────────────────┘
                     │
┌────────────────────▼──────────────────────┐
│               PROFILE ENGINE              │
│ detekce typu zařízení                     │
│ normalizace                               │
│ syntetické entity                         │
│ event adapters                            │
└────────────────────┬──────────────────────┘
                     │
┌────────────────────▼──────────────────────┐
│             RUNTIME MANIFEST              │
│           config.generated.yaml           │
└──────────────┬───────────────────┬────────┘
               │                   │
        ┌──────▼──────┐     ┌──────▼──────┐
        │ Homey side  │     │ Loxone side │
        │ realtime    │     │ UDP I/O      │
        │ commands    │     │ events       │
        └──────┬──────┘     └──────┬──────┘
               │                   │
               └────────┬──────────┘
                        │
                 ┌──────▼──────┐
                 │   ROUTER    │
                 │ key ↔ entity│
                 └─────────────┘
```

A vedle toho:

```text
runtime manifest
       ↓
XML generators
       ↓
Loxone Config import
```

---

# 28. Co bych považoval za „Loxbridge 1.0“

Ne GUI se všemi vychytávkami.

Za **1.0 pro tvůj dům** bych považoval stav, kdy:

1. všechna zařízení, která skutečně chceš používat, fungují správně,
2. základní typy jsou normalizované přes Profile Engine,
3. Loxone → Homey a Homey → Loxone jsou stabilní,
4. eventová tlačítka fungují,
5. systém přežije restart Homey/RPi/Loxone a znovu se spojí,
6. konfigurace se generuje reprodukovatelně,
7. Loxone XML se generuje automaticky,
8. není potřeba ručně patchovat Python při každém běžném zařízení.

**A teprve potom GUI.**

To je pořád moje preference. GUI bych nestavěl nad pohyblivým backendem.

Backend už je ale dnes výrazně blíž tomuto bodu, než byl před pár dny.

---

# 29. A potom „Loxbridge 2.0“ = produkt

Tam bych přesunul konfiguraci z terminálu do browseru:

```text
Homey connection
Loxone connection

Device discovery
Profile assignment
Entity mapping
Transforms
Events

Live values
Diagnostics
Logs

Generate / export Loxone XML
Apply configuration
Backup / restore
```

A potom už můžeš přijít k jiné instalaci a udělat:

```text
nové RPi
↓
Loxbridge
↓
zadám Homey IP/token
↓
najde zařízení
↓
vyberu 15 zařízení
↓
přiřadí profily
↓
doladím mapping
↓
Export to Loxone
```

To je podle mě **skutečný konečný smysl projektu**.

---

## Nejkratší shrnutí

Dnes Loxbridge už umí:

```text
HOMEY
 ⇅
realtime / commands / events
 ⇅
LOXBRIDGE
 ⇅
UDP virtuální I/O
 ⇅
LOXONE
```

a nad tím už máme:

```text
capability normalizaci
Profile Engine
syntetické entity
event adapters
config generator
Loxone XML generators
```

To, co dnes chybí, není základ komunikace. **Chybí hlavně pohodlná konfigurační a diagnostická vrstva.**

A finálně chci, aby ses vůbec nezabýval otázkou:

> „Jak se jmenuje capability `light_saturation` a co mám napsat do YAML?“

Místo toho otevřeš:

> **LED Obývák → RGB → Loxone ↔ Homey → Enabled**

a Loxbridge zbytek sestaví sám.

Tohle je podle mě pořád velmi dobrá vize — a po dohledání současných souborů bych řekl, že největší architektonické základy už jsme skutečně položili.
