# Muistiinpanot / Notes

Löydöksiä ja päätöksiä, jotka eivät näy suoraan koodista. Tarkoitettu gradun
johdanto- ja arviointilukuun.

## 2026-07-31 — Serverin sisäinen silmukka ja mittareiden rajat

**Löydös:** Prompt caching aktivoituu, vaikka meidän tekemiämme API-kutsuja on
vain yksi per tehtävä (`api_calls = 1`). Syy: Anthropicin natiivi `web_search`
ajaa palvelimella oman monivaiheisen mallisilmukkansa. Meidän `usage`-mittarimme
laskevat yhteen tuon sisäisen kulutuksen, mutta emme näe emmekä voi ohjata, mitä
silmukan sisällä tapahtuu (emme voi asettaa cache-breakpointeja sinne).

**Todiste** (tehtävä `0383a3ee`, sama kysymys, sama malli Sonnet 4.5):

| Strategia | input | cache_read | cache_write | kustannus | vastaus |
|---|---|---|---|---|---|
| baseline | 8116 | 0 | 0 | €0.0242 | "Penguin" (väärä) |
| prompt_caching | 17 | 8581 | 10149 | €0.0417 | "Rockhopper penguin" (oikea) |

**Kaksi pointtia graduun:**

1. "Yksi API-kutsu per tehtävä" EI tarkoita "ei caching-mahdollisuutta" — caching
   voi hyödyntää serverin sisäistä silmukkaa. Aiempi työhypoteesi (caching ei
   pure yhden kutsun tapauksessa) osoittautui vääräksi.
2. Mittarit eivät paljasta, mitä serverin sisäisessä silmukassa tapahtuu, mutta
   caching pystyy silti hyödyntämään sitä. Tämä on mittausmenetelmän rajoite,
   joka kannattaa käsitellä arviointiluvussa.

**Metodologinen seuraus:** web-haku on voimakkaasti epädeterministinen (eri haku
joka ajolla → suuri vaihtelu tokeneissa, kustannuksessa ja vastauksessa). Yksi
ajo per strategia EI riitä johtopäätökseen — täytyy käyttää `--repeats` ja
keskiarvoistaa. Yllä oleva kustannusero (€0.0417 vs €0.0242) on sekoittunut
hakukohinaan, ei puhdas caching-vaikutus. Huomaa myös, että kalliimpi ajo antoi
*paremman* vastauksen: pelkkä kustannus ei kerro kumpi strategia on parempi,
siksi `success`-pisteytys (Phase 5) on välttämätön.

## 2026-07-31 — Metodologinen päätös: web_search `max_uses = 5`

Kaikki strategiat käyttävät `web_search`-työkalussa `max_uses = 5` (asetettu
`strategies.py`:n `WEB_SEARCH_TOOL`-vakioon, joka on jaettu kaikille).

**Perustelu:**
1. **Tuotantorealismi** — oikeat käyttöönotot rajaavat työkalukutsut.
2. **Budjettikontrolli** — rajaamaton baseline antoi yhden tehtävän imeä 246k
   tokenia (€0.70). Katto leikkaa tämän hännän lähteestä.
3. **Vertailukelpoisuus** — katon on oltava identtinen kaikilla strategioilla,
   muuten kustannusero heijastaa hakusyvyyttä, ei strategiaa.

Tämä on tietoinen suunnitteluvalinta, ei oletusarvo. Kaikki alla olevat
pilottitulokset on ajettu tällä asetuksella.

## 2026-08-19 — Cachattavan prefiksin minimipituus: system-prompt ei cachaudu

**Löydös:** `prompt_caching`-strategian `cache_control`-merkintä system-promptissa
ei luo cache-entryä lainkaan. Anthropicin cachattavan prefiksin minimipituus on
Sonnet 4.5:llä **1024 tokenia** ja Haiku 4.5:llä **4096**; meidän `SYSTEM_PROMPT`
on ~100 tokenia. Minimin alittava prefiksi jätetään cachaamatta **hiljaisesti** —
ei virhettä, ei varoitusta, `cache_creation_input_tokens` vain pysyy nollassa
siltä breakpointilta.

**Seuraus tulkintaan:** kaikki 31.7. havaitut cache-osumat (8581 read / 10149
write) tulevat *top-level* `cache_control`-parametrista, eivät system-promptista.
Top-level auto-cache osuu viestiprefiksiin, joka kasvaa serverin sisäisessä
web_search-silmukassa yli minimin. Eli:

| Mekanismi | Toimiiko | Miksi |
|---|---|---|
| `cache_control` system-promptissa | ei | ~100 tokenia < 1024 minimi |
| top-level `cache_control` | kyllä | serverin silmukka kasvattaa prefiksin yli minimin |

**Miksi tämä on tärkeä graduun:** aiempi kuvaus mekanismista oli väärä, ja väärä
kuvaus mekanismista on vakavampi virhe kuin väärä mittaus — mittauksen voi toistaa,
mutta väite siitä *miksi* jokin toimii kantaa läpi koko analyysin. Cachingin
hyöty tässä testipenkissä ei tule siitä, mitä me merkitsemme cachattavaksi, vaan
siitä mitä serverin sisäinen silmukka sattuu tuottamaan. Tämä vahvistaa 31.7.
kirjattua mittausmenetelmän rajoitetta: emme ohjaa sitä, mistä hyöty syntyy.

**Vaihtoehto jos caching halutaan aidosti mitattavaksi:** system-promptin pitäisi
olla >1024 tokenia (esim. few-shot-esimerkkejä tai laajempi ohjeistus). Se olisi
kuitenkin eri koeasetelma — nykyisillä tuloksilla mitataan caching-hyötyä
*lyhyellä* system-promptilla, mikä on itsessään realistinen tapaus.

## Strategiat (Phase 4) — kuvaukset ja pilottitulokset

Viisi strategiaa, kaikki Sonnet 4.5:llä paitsi routing, joka käyttää myös
Haiku 4.5:tä:

- **baseline** — täysi konteksti, natiivi web-haku, ei optimointia. Vertailukohta.
- **prompt_caching** — top-level `cache_control` (viestiprefiksin auto-cache).
  Natiivi ominaisuus. Huom: koodissa on myös `cache_control` system-promptissa,
  mutta se ei tee mitään — ks. alla oleva minimipituusrajoitus.
- **model_routing** — Haiku vastaa ensin ja raportoi itsevarmuutensa; jos
  "high", pidetään Haikun halpa vastaus; muuten eskaloidaan Sonnetille. Kustannus
  summataan molempien mallien yli.
- **context_compression** — natiivi context editing (`clear_tool_uses`) tyhjentää
  vanhat työkalutulokset kun konteksti kasvaa. Varaus: yhden kutsun tehtävissä ei
  ole mitään tyhjennettävää.
- **context_isolation** — orkestraattori pilkkoo kysymyksen enintään kolmeen
  itsenäiseen osakysymykseen; kukin subagentti näkee vain oman osatehtävänsä,
  ei alkuperäistä kysymystä eikä muiden työtä. Orkestraattori kokoaa
  osavastaukset. Ainoa strategia jossa `api_calls > 1` on meidän hallinnassamme:
  2 orkestraattorikutsua (suunnittelu + synteesi, ei hakua) + 1 per subagentti.

**Hakubudjetin jako (19.8.).** Subagentit *jakavat* saman viiden haun budjetin
(`ceil(5/N)` per subagentti) sen sijaan että kukin saisi oman viidenkön. Muuten
kolmen subagentin ajo saisi 15 hakua siinä missä baseline sai 5, ja
kustannusero heijastaisi hakubudjettia eikä kontekstin eristystä — sama
perustelu kuin `max_uses = 5` -päätöksessä yllä. Osatehtävien katto on 3, jolloin
kokonaishakumäärä on 5–6 riippumatta N:stä (1→5, 2→3+3, 3→2+2+2) eikä yksikään
subagentti jää yhden haun varaan.

**Pilotti** (2 tehtävää, 1 toisto, `max_uses=5`):

| Strategia | `0383a3ee` (want "Rockhopper penguin") | `b415aba4` (want "diamond") | Yht. | Oikein |
|---|---|---|---|---|
| baseline | €0.0243 ❌ | €0.1254 ✅ | €0.150 | 1/2 |
| prompt_caching | €0.0229 ❌ | €0.1043 ✅ | €0.127 | 1/2 |
| model_routing | €0.0094 ❌ | €0.0663 ✅ | €0.076 | 1/2 |
| context_compression | €0.0248 ❌ | €0.1243 ✅ | €0.149 | 1/2 |

**Havainnot (suuntaa-antavia):**
- **model_routing halvin** — ~50 % baselinea halvempi samalla tarkkuudella. Haiku
  hoiti molemmat tehtävät itsevarmasti ilman eskalaatiota Sonnetille.
- **Haiku-kalibrointi on jatkokysymys** — tehtävässä 1 Haiku oli itsevarma mutta
  väärässä ("penguin") eikä eskaloinut. Itsearvioitu itsevarmuus ei ole hyvin
  kalibroitu → reitityksen laatu vaatii tutkimista.
- **prompt_caching** hieman baselinea halvempi token-raskaassa tehtävässä
  (€0.104 vs €0.125).
- **context_compression ≈ baseline** — ei vaikutusta yhden kutsun tehtävissä,
  kuten ennustettiin.
- Kaikki strategiat väärässä tehtävässä 1 ("Penguin" vs "Rockhopper penguin") —
  vaikea tehtävä, jossa tarkka laji jää hakutulosten alle.

**⚠️ Nämä ovat n=1 -pilottipisteitä.** Web-haun suuri epädeterminismi tarkoittaa,
ettei näistä voi tehdä johtopäätöksiä strategioiden paremmuudesta. Lopullinen
vertailu vaatii `--repeats` (3–5) koko 24 tehtävän joukolla — se on rahoitettava
ajo, josta keskustellaan Viran-tapaamisessa 1.8.
