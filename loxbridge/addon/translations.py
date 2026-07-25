"""
Překlady Homey capabilities na čitelné názvy pro Loxone.
"""

CAPABILITY_TITLES = {
    "onoff": "Zapnuto",

    "measure_temperature": "Aktuální teplota",
    "measure_temperature_inside": "Vnitřní teplota",
    "measure_temperature_outside": "Venkovní teplota",
    "target_temperature": "Požadovaná teplota",

    "operation_mode": "Režim",
    "fan_speed": "Rychlost ventilátoru",

    "measure_power": "Aktuální příkon",
    "meter_power": "Spotřebovaná energie",

    "measure_humidity": "Vlhkost",
    "measure_luminance": "Osvětlení",

    "alarm_motion": "Pohyb",
    "alarm_contact": "Kontakt",
    "alarm_tamper": "Sabotáž",

    "dim": "Jas",
    "battery": "Baterie",

    "air_swing_lr": "Směr lamel vlevo–vpravo",
    "air_swing_ud": "Směr lamel nahoru–dolů",

    "nanoe_mode": "Nanoe",
    "eco_mode": "Eco režim",
}


def get_capability_title(capability_id: str, homey_title: str | None = None) -> str:
    """
    Vrátí český název capability.

    Priorita:
    1. Ruční překlad podle capability ID.
    2. Název dodaný Homey.
    3. Capability ID převedené na čitelný text.
    """
    if capability_id in CAPABILITY_TITLES:
        return CAPABILITY_TITLES[capability_id]

    if homey_title:
        return homey_title.strip()

    return capability_id.replace("_", " ").strip().capitalize()
