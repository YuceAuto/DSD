# modules/data/ev_specs.py
EV_RANGE_KM = {
    # WLTP birleşik menzil (km) – istenirse tüketim de eklenebilir
    # -----------------  ELROQ  -----------------
    ('elroq', ''): 422,
    ('enyaq', ''): 535,
    ("elroq", "e prestige 60"): 422,

    # -----------------  ENYAQ  -----------------
    ("enyaq", "e prestige 60"): 423,
    ("enyaq", "coupe e sportline 60"): 431,
    ("enyaq", "coupe e sportline 85x"): 535,
    ("enyaq", "e sportline 60"): 431,
    ("enyaq", "e sportline 85x"): 535,

    # … gerekirse diğer markalar
}
# İçten yanmalı modeller – depo hacmi ve ortalama tüketim
FUEL_SPECS = {
    # (model, trim) : {"tank_l": …, "l_per_100km": …}
    ("fabia",   ""): {"tank_l": 45, "l_per_100km": 5.5},
    ("scala",   ""): {"tank_l": 50, "l_per_100km": 5.9},
    ("kamiq",   ""): {"tank_l": 50, "l_per_100km": 6.1},
    ("karoq",   ""): {"tank_l": 55, "l_per_100km": 6.2},
    ("kodiaq",  ""): {"tank_l": 60, "l_per_100km": 6.5},
    ("octavia", ""): {"tank_l": 50, "l_per_100km": 5.4},
    ("superb",  ""): {"tank_l": 66, "l_per_100km": 5.8},
}
