# Testipenkin rakenne ja logiikka

Tekninen dokumentaatio siitä *miten* testipenkki toimii ja *miksi* se on
rakennettu näin. Tarkoitettu luettavaksi silloin kun koodiin palataan tauon
jälkeen, ja pohjaksi gradun menetelmäluvulle.

Työnjako muiden dokumenttien kanssa:

| Tiedosto | Sisältö |
|---|---|
| `ARCHITECTURE.md` (tämä) | Rakenne, logiikka, tietorakenteet, kontrollit |
| `NOTES.md` | Päivätyt löydökset ja metodologiset päätökset perusteluineen |
| `README.md` | Asennus ja peruskomennot |
| `CLAUDE.md` | Projektin tavoitteet ja vaiheistus |

---

## 1. Tutkimusasetelma

Kysymys: **paljonko yksi onnistunut tehtävä maksaa eri optimointistrategioilla?**

Asetelma on toistettu mittaus: sama tehtäväjoukko ajetaan läpi jokaisella
strategialla, ja jokaisesta ajosta kirjataan tokenit, kustannus ja onnistuiko
se. Riippumaton muuttuja on strategia, riippuvat muuttujat kustannus ja
onnistuminen. Kaikki muu pyritään vakioimaan (ks. luku 8).

- **Tehtävät:** 24 GAIA-validointitehtävää, ositettu otos 12 × taso 1,
  8 × taso 2, 4 × taso 3. Vain tekstipohjaiset — liitetiedostolliset
  suodatettiin pois, koska agentilla ei ole tiedostojen lukukykyä.
- **Mallit:** Claude Sonnet 4.5 ensisijainen, Haiku 4.5 `model_routing`-strategiassa.
- **Työkalu:** Anthropicin natiivi `web_search`. Palvelinpuolinen, eli haut
  tapahtuvat Anthropicin infrassa emmekä me suorita mitään paikallisesti.

---

## 2. Ajon kulku

```
run.py                    komentoriviargumentit, tehtävien valinta
  │
  ├─ tasks.load_gaia_sample()          tasks/gaia_sample.json → list[dict]
  │
  ├─ for (tehtävä, toisto) in työlista:
  │     │
  │     ├─ agent.run_agent(task, strategy)
  │     │     └─ strategies.STRATEGIES[strategy](task)
  │     │           └─ _run_loop(...)  ─→ Anthropic API  ─→ web_search
  │     │     ← AgentResult (tokenit, kustannus, latenssi)
  │     │
  │     ├─ metrics.evaluate_answer(vastaus, oikea)  → success: bool
  │     └─ kirjoita rivi results/{aikaleima}/run.jsonl  (flush heti)
  │
  └─ yhteenveto terminaaliin

analyze.py                lukee kaikki run.jsonl → Pareto → pareto.png
```

Kaksi suunnitteluperiaatetta näkyy tässä:

**Rivi kerrallaan levylle.** Jokainen tulos kirjoitetaan ja `flush`ataan heti
(`run.py:132`), ei vasta ajon lopussa. Keskeytynyt ajo ei siis hukkaa jo
maksettua työtä.

**Strategia on funktio, ei luokka.** `STRATEGIES` on sanakirja nimestä
funktioon. Uuden strategian lisääminen = yksi funktio + yksi rivi sanakirjaan.
Ei rekisteröintiä, ei perintää, ei tehdasluokkia.

---

## 3. Tietorakenteet

Neljä muotoa, joiden läpi data kulkee.

**Tehtävä** (`tasks/gaia_sample.json`):

```python
{"task_id": "0383a3ee...", "question": "...", "level": 1, "answer": "Rockhopper penguin"}
```

**Strategian paluuarvo** — jokainen strategia palauttaa täsmälleen nämä avaimet:

```python
{"answer": str, "input_tokens": int, "output_tokens": int,
 "cache_read_tokens": int, "cache_write_tokens": int,
 "api_calls": int, "model": str, "cost_eur": float}
```

`cost_eur` lasketaan strategian sisällä, ei kutsujassa. Syy: `model_routing` voi
käyttää kahta mallia yhdessä ajossa, jolloin yksi hinnasto ei riitä.

**`AgentResult`** (`agent.py:10`) — dataclass, joka lisää `task_id`,
`strategy` ja `latency_ms`. Ainoa asia mitä `agent.py` tekee itse on ajastus;
kaikki muu tulee strategialta.

**JSONL-rivi** — `AgentResult` sanakirjana + `repeat` (monesko toisto) +
`success` (bool). Yksi JSON-objekti riviä kohti.

---

## 4. Jaettu agenttisilmukka `_run_loop`

`strategies.py:97`. Kaikki strategiat kutsuvat tätä; strategia päättää vain
*mitä sille syöttää* (malli, system-prompt, työkalut, lisäparametrit).

```python
_run_loop(question, model, system, tools=None, extra_kwargs=None, beta=False)
```

Silmukka tekee kolme asiaa:

**1. `pause_turn`-käsittely.** Kun palvelinpuolinen työkalusilmukka saavuttaa
iteraatiorajansa, API palauttaa `stop_reason == "pause_turn"`. Silloin
assistentin vastaus liitetään viestihistoriaan ja pyyntö lähetetään uudestaan —
palvelin jatkaa siitä mihin jäi. Ilman tätä pitkät hakuketjut katkeaisivat
kesken.

**2. Token-kertymä.** Jokaisen kutsun `usage` summataan. `cache_read_input_tokens`
ja `cache_creation_input_tokens` luetaan `getattr`-oletuksella, koska ne
puuttuvat vastauksesta kun cachea ei käytetä.

**3. Vastauksen poiminta.** Vain `type == "text"` -lohkot yhdistetään.
Hakutuloslohkot jätetään pois, jotta pisteytys näkee vain mallin oman tekstin.

**Työkalut.** `tools=None` → oletuksena `web_search` jaetulla katolla.
`tools=[]` → ei työkaluja lainkaan, ja `tools`-parametri jätetään pois
API-kutsusta kokonaan. Tätä tarvitsee `context_isolation`, jonka
orkestraattorikutsut eivät saa hakea.

**Mitä `api_calls` mittaa.** Vain *meidän* tekemämme kutsut. Palvelimen sisäinen
hakusilmukka voi tehdä useita mallikutsuja yhden `api_calls`-yksikön sisällä —
niiden tokenit näkyvät `usage`ssa, mutta silmukkaa itseään emme näe emmekä ohjaa.
Tämä on mittausmenetelmän keskeinen rajoite (ks. NOTES.md 31.7.).

---

## 5. Strategiat

Kaikki käyttävät samaa `SYSTEM_PROMPT`ia, joka vaatii vastauksen muodossa
`FINAL ANSWER: <vastaus>` — muuten pisteytys ei löydä vastausta.

### baseline

Vertailukohta. Yksi kutsu, täysi konteksti, ei optimointia.

```
kutsuja: 1   mallit: Sonnet   haut: 5
```

### prompt_caching

Kaksi cache-merkintää, joista **vain toinen toimii**:

| Merkintä | Toimii | Miksi |
|---|---|---|
| `cache_control` system-promptissa | ei | ~100 tokenia < Sonnet 4.5:n 1024 tokenin minimi |
| top-level `cache_control` | kyllä | palvelinsilmukka kasvattaa viestiprefiksin yli minimin |

Minimin alittava prefiksi jätetään cachaamatta **hiljaisesti** — ei virhettä, ei
varoitusta. Havaitut cache-osumat tulevat siis kokonaan top-level-parametrista.
System-prompt-merkintä on jätetty koodiin, koska se on oppikirjatapa soveltaa
cachingia ja sen tehottomuus tässä asetelmassa on itsessään tulos.

```
kutsuja: 1   mallit: Sonnet   haut: 5
```

### model_routing

Haiku vastaa ensin ja raportoi itsevarmuutensa rivillä `CONFIDENCE: high|low`.
Jos `high`, Haikun halpa vastaus kelpaa. Muuten eskaloidaan Sonnetille
**puhtaalta pöydältä** — Sonnet ei näe Haikun yritystä.

Kaksi puolustettavaa yksityiskohtaa:

- **Jäsennyksen oletus on `low`** (`_parse_confidence`, rivi 189). Jos
  `CONFIDENCE`-rivi puuttuu tai on epäselvä, eskaloidaan. Virhe kaatuu
  laadun eikä halpuuden puolelle.
- **`CONFIDENCE`-rivi poistetaan** ennen pisteytystä (`_strip_confidence`),
  jottei se päädy arvioitavaan vastaukseen.

Kustannus summataan mallien yli erikseen kummankin hinnastolla.

```
kutsuja: 1 tai 2   mallit: Haiku (+ Sonnet)   haut: 5 per malli
```

### context_compression

Anthropicin natiivi context editing: `clear_tool_uses_20250919` tyhjentää vanhat
työkalutulokset kun konteksti kasvaa. Ainoa strategia joka käyttää beta-endpointia
(`client.beta.messages.create` + beta-lippu `context-management-2025-06-27`).

Varaus: yhden kutsun tehtävissä ei ole mitään tyhjennettävää, joten vaikutus on
pieni. Se on odotettu tulos, ei bugi.

```
kutsuja: 1   mallit: Sonnet   haut: 5
```

### context_isolation

Ainoa strategia jossa **me** teemme useita kutsuja per tehtävä.

```
1. Suunnittelu   orkestraattori pilkkoo kysymyksen ≤3 osakysymykseen   (ei hakua)
2. Subagentit    kukin ratkaisee omansa eristetyssä kontekstissa        (haku)
3. Synteesi      orkestraattori kokoaa osavastaukset                    (ei hakua)
```

**Eristys tarkoittaa konkreettisesti tätä:** subagentin `messages`-lista
sisältää yhden viestin, joka on pelkkä sen oma osakysymys. Ei alkuperäistä
kysymystä, ei muiden subagenttien vastauksia, ei orkestraattorin suunnitelmaa.
Siksi `DECOMPOSE_SYSTEM` vaatii että jokainen osakysymys on itsenäisesti
ymmärrettävä ("name entities in full") — muuten subagentti saisi kysymyksen
jonka konteksti puuttuu.

**Hakubudjetti jaetaan, ei monisteta:** `ceil(5/N)` per subagentti.

| Osatehtäviä | Hakuja/subagentti | Yhteensä |
|---|---|---|
| 1 | 5 | 5 |
| 2 | 3 | 6 |
| 3 | 2 | 6 |

Jos jokainen saisi oman viidenkön, kolmen subagentin ajo saisi 15 hakua siinä
missä baseline sai 5 — silloin mitattaisiin hakubudjettia eikä eristystä.
Kolmen osatehtävän katto pitää kokonaismäärän 5–6:ssa riippumatta N:stä eikä
kukaan jää yhden haun varaan.

**Jäsennyksen varautuminen:** `_parse_subtasks` sietää numeroinnin ja luetelmaviivat
vaikka prompt kieltää ne, ja jos tulos on tyhjä, alkuperäistä kysymystä käytetään
yhtenä osatehtävänä. Silloin strategia degeneroituu baselineksi + kaksi
ylimääräistä kutsua — kalliimpi mutta ei rikki.

```
kutsuja: 2 + N (N ≤ 3)   mallit: Sonnet   haut: 5–6 yhteensä
```

---

## 6. Kustannuslaskenta

`metrics.compute_cost_eur`. Suoraviivainen: tokenit × hinta / miljoona, sitten
dollarit euroiksi kertoimella.

Hinnat (`config.py`, USD / miljoona tokenia):

| Malli | input | output | cache write | cache read |
|---|---|---|---|---|
| Sonnet 4.5 | 3.00 | 15.00 | 3.75 | 0.30 |
| Haiku 4.5 | 1.00 | 5.00 | 1.25 | 0.10 |

Cache-kertoimet ovat Anthropicin: kirjoitus 1.25×, luku 0.1× perushinnasta.

`EUR_PER_USD = 0.92`. **Tämä on kiinteä luku, ei live-kurssi.** Se vaikuttaa
kaikkiin euromääriin samassa suhteessa, joten strategioiden *keskinäinen*
vertailu ei muutu vaikka kurssi liikkuisi — mutta absoluuttiset luvut pitää
mainita gradussa tällä varauksella.

---

## 7. Onnistumisen arviointi

`metrics.question_scorer` on GAIAn oman pisteytysfunktion uudelleentoteutus.
Kaksivaiheinen:

**1. Vastauksen poiminta** (`extract_final_answer`): otetaan teksti *viimeisen*
`FINAL ANSWER:` -merkinnän jälkeen. Viimeisen eikä ensimmäisen, koska malli voi
mainita muodon aiemmin. Jos merkintää ei ole, koko teksti menee arvioitavaksi ja
käytännössä epäonnistuu — tarkoituksella, koska muotovaatimuksen rikkominen on
epäonnistuminen.

**2. Kvasi-eksakti vertailu**, joka haarautuu oikean vastauksen tyypin mukaan:

| Oikea vastaus | Vertailu |
|---|---|
| Numero | Poistetaan `$ % ,`, verrataan floattina |
| Lista (`,` tai `;`) | Pilkotaan, verrataan alkioittain, pituuden on täsmättävä |
| Merkkijono | Poistetaan välilyönnit ja välimerkit, pienaakkostetaan |

Vertailu on ankara: `"penguins"` ≠ `"Rockhopper penguin"`. Se on tarkoitus —
GAIAn pisteytys on eksakti, ja löysempi vertailu tekisi tuloksista
vertailukelvottomia julkaistujen GAIA-tulosten kanssa.

---

## 8. Mikä on vakioitu ja miksi

Nämä ovat asetelman kontrollit. Jos jokin näistä eroaisi strategioiden välillä,
kustannusero heijastaisi sitä eikä strategiaa.

| Vakioitu | Arvo | Miksi |
|---|---|---|
| Tehtäväjoukko | samat 24, sama järjestys | ilmeinen |
| System-prompt | sama `SYSTEM_PROMPT` | eri ohjeistus → eri vastauspituus → eri kustannus |
| Hakukatto | 5 per tehtävä | ks. NOTES.md 31.7. ja 19.8. |
| `max_tokens` | 4096 | katkaisuraja vaikuttaa vastauksen pituuteen |
| Pisteytys | sama `question_scorer` | ilmeinen |
| Malli | Sonnet 4.5, paitsi routing | routingin koko idea on mallin vaihto |

Poikkeukset ovat tarkoituksellisia ja kuuluvat strategian määritelmään:
`model_routing` vaihtaa mallia, `context_isolation` käyttää lisäksi kahta
orkestraattoripromptia.

---

## 9. Ajologiikka

**Checkpointing.** `load_progress` lukee olemassa olevan `run.jsonl`:n ja kerää
joukon `(task_id, strategy, repeat)`. Työlistalta jätetään pois kaikki mikä on
jo tehty. `--resume <kansio>` jatkaa siis keskeytynyttä ajoa maksamatta
uudestaan siitä mikä valmistui.

**Kustannuskatto.** `--max-cost-eur` (oletus 5) tarkistetaan **ennen** jokaista
tehtävää. Käytännön seuraus: katto voi ylittyä yhden tehtävän kustannuksella,
koska kesken olevaa ajoa ei keskeytetä. Oikea turvaverkko on Anthropic-konsolin
kuukausikatto.

**Virheensieto.** Yhden tehtävän poikkeus napataan ja ajo jatkuu (`run.py:122`).
Rivi jää kirjaamatta, joten checkpointing yrittää sitä uudestaan seuraavalla
ajolla.

---

## 10. Analyysi

`analyze.py` lukee kaikki `results/*/run.jsonl` ja laskee strategioittain
keskimääräisen kustannuksen, onnistumisprosentin ja **kustannuksen onnistumista
kohti** — se on varsinainen tutkimuskysymyksen mittari.

`scored_only()` suodattaa rivit joilta `success`-kenttä puuttuu. Ne ovat ennen
Phase 5:tä ajettuja eikä niitä voi tulkita epäonnistumisiksi, koska niitä ei
koskaan pisteytetty.

**Pareto-rintama:** strategia on rintamalla jos mikään toinen ei ole
*yhtä aikaa* vähintään yhtä halpa ja vähintään yhtä tarkka (ja aidosti parempi
toisessa). Rintaman ulkopuoliset ovat dominoituja: on olemassa strategia joka
päihittää ne molemmilla mittareilla.

---

## 11. Tunnetut rajoitteet

Nämä kuuluvat gradun arviointilukuun.

1. **Web-haku on voimakkaasti epädeterministinen.** Eri haku joka ajolla → suuri
   vaihtelu tokeneissa, kustannuksessa ja vastauksessa. Yksi ajo per strategia ei
   riitä johtopäätökseen; tarvitaan `--repeats` ja keskiarvoistus.

2. **Palvelimen sisäistä silmukkaa ei näe eikä ohjaa.** Mittarit summaavat sen
   kulutuksen, mutta emme voi asettaa sinne cache-breakpointeja emmekä tietää
   montako mallikutsua siellä tapahtui.

3. **`temperature` on asettamatta** (oletus 1.0). Toinen, poistettavissa oleva
   varianssin lähde. Hakukohina dominoi, mutta tämä kannattaa mainita.

4. **Haikun itsearvioitu itsevarmuus ei ole kalibroitu.** Pilotissa Haiku oli
   itsevarma mutta väärässä eikä eskaloinut. `model_routing`in halpuus voi siis
   olla osin näennäistä — se säästää eskaloimatta jättämällä.

5. **Otos on pieni** (24 tehtävää) ja painottuu tasoon 1 (12/24). Tason 3
   tehtäviä on vain 4, joten strategioiden erot vaikeissa tehtävissä jäävät
   heikosti mitatuiksi — juuri siellä missä `context_isolation`in pitäisi
   hyödyttää eniten.

6. **Kustannus ei ole sama kuin laatu.** Pilotissa kalliimpi ajo antoi paremman
   vastauksen. Siksi `success` on välttämätön eikä pelkkä kustannusvertailu
   riitä.
