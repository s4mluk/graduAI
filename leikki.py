"""Leikkikenttä GAIA-datalle. Ei tarvitse API-avainta — ilmainen.

Aja:   uv run leikki.py
Muokkaa vapaasti: kokeile omia suodatuksia ja tulostuksia.
"""

from collections import Counter

import tasks

# Lataa kaikki tehtävät (lista sanakirjoja).
data = tasks.load_gaia_sample()

print(f"Tehtäviä yhteensä: {len(data)}\n")

# 1) Montako kutakin vaikeustasoa?
print("Tasojen jakauma:", dict(sorted(Counter(t["level"] for t in data).items())))
print()

# 2) Kaikki kysymykset lyhyesti.
print("Kaikki kysymykset:")
for t in data:
    q = t["question"].replace("\n", " ")
    print(f"  [taso {t['level']}] {q[:90]}")
print()

# 3) Etsi kysymykset joissa mainitaan jokin sana (muokkaa hakusanaa!).
hakusana = "YouTube"
osumat = [t for t in data if hakusana.lower() in t["question"].lower()]
print(f"Kysymykset joissa '{hakusana}' ({len(osumat)} kpl):")
for t in osumat:
    print(f"  - {t['question'][:90]}")
print()

# 4) Katso yksi tehtävä kokonaan (vaihda indeksiä 0 -> mikä tahansa 0..23).
t = data[0]
print("Yksi tehtävä kokonaan:")
print(f"  task_id: {t['task_id']}")
print(f"  taso:    {t['level']}")
print(f"  kysymys: {t['question']}")
print(f"  vastaus: {t['answer']}")
