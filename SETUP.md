# Setup: Politik-Tagesueberblick

Von null bis laufender Pipeline. Reihenfolge einhalten, nichts ueberspringen.
Gesamtaufwand etwa 4 bis 5 Stunden, verteilt auf mehrere Tage.

---

## Phase 0: Zwei Wochen von Hand (unverzichtbar)

**Bevor du irgendetwas installierst.**

Jeden Morgen 30 Minuten:

1. Bundesregierung, Destatis und Bundestag durchsehen
2. Die 5 wichtigsten Entscheidungen oder Zahlen notieren
3. Karten in Canva bauen, posten

**Warum das nicht optional ist:**
- Du lernst, welche Quellen wirklich brauchbare Meldungen liefern
- Du entwickelst das Format, bevor du es in Code giesst
- Du merkst nach 3 Tagen, ob du das ueberhaupt machen willst

Nach zwei Wochen weisst du, welche Feeds du in `config.py` brauchst.

**Erst danach weiterlesen.**

---

## Phase 1: Konten und Schluessel (60 Min)

Alles kostenlos ausser dem Anthropic-Guthaben.

### 1.1 Telegram-Bot

1. In Telegram `@BotFather` anschreiben, `/newbot` senden
2. Namen vergeben, du bekommst einen **Token** wie `123456:ABC-DEF...`
3. Deinen neuen Bot anschreiben, irgendwas senden ("hi")
4. Im Browser oeffnen: `https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates`
5. Im JSON `"chat":{"id":123456789` suchen, das ist deine **Chat-ID**

### 1.2 Anthropic API

1. Konto auf console.anthropic.com anlegen
2. Guthaben aufladen, 5 Euro reichen fuer Monate
3. API-Key erzeugen, sofort kopieren (wird nur einmal gezeigt)

### 1.3 Bundestag DIP (optional, aber gut)

API-Key formlos per E-Mail anfragen bei `parlamentsdokumentation@bundestag.de`.
Laufzeit zunaechst zehn Jahre. Ohne Key laufen nur die RSS-Feeds, das reicht
fuer den Anfang.

### 1.4 Pexels (optional, fuer das Titelbild)

Kostenloses Konto auf `pexels.com/api`, Key sofort im Dashboard. 200 Abfragen
pro Stunde, das reicht um ein Vielfaches. Ohne Key bleibt das Cover rein
typografisch - das ist kein Fehlerfall, sondern der Normalzustand.

Das Bild kommt **nur** auf Slide 1 und nur, wenn ein Thema aus
`config.BILDER_THEMEN` im Titel vorkommt. Gesucht wird mit der dort
hinterlegten festen Suchphrase, nie mit dem Meldungstext. Wenn du ein Motiv
nicht sehen willst, aendere die Phrase - oder setze `BILDER_ENABLED = False`.

Die Pexels-Lizenz erlaubt auch kommerzielle Nutzung. Die API-Richtlinien
verlangen dafuer, dass der Fotograf genannt wird und Pexels erkennbar bleibt.
Das Cover traegt nach `DESIGN-SYSTEM.md` nichts ausser Haken und Stuetzzeile,
deshalb stehen Name und Link zum Foto zusammen in der Caption. Nicht
entfernen.

### 1.5 GitHub

Konto anlegen, falls nicht vorhanden. Ein **oeffentliches** Repo nutzen:
unbegrenzte Actions-Minuten, und die offene Pipeline ist bei einem
Politikformat ein Vertrauensargument.


### 1.5 Instagram und Meta (fuer den automatischen Upload)

Ohne diese Schritte laeuft alles bis zur Freigabefrage - nur das Posten
scheitert. Du kannst sie also nachholen.

1. **Instagram-Konto auf Professional umstellen** (Business oder Creator).
   Eine Facebook-Seite ist nicht noetig: `instagram.py` nutzt die "Instagram
   API with Instagram Login" auf `graph.instagram.com`. Ein privates Konto
   kann die Publishing-API nicht nutzen, egal welche Rechte die App hat.
2. **Meta-App anlegen** auf `developers.facebook.com` (Typ "Business"),
   Produkt "Instagram" hinzufuegen, Weg "API setup with Instagram login",
   Berechtigungen `instagram_business_basic` und
   `instagram_business_content_publish`.
3. **Langlebiges Zugriffstoken** erzeugen und die **Instagram-User-ID**
   notieren. Beides brauchst du gleich als Secret.

**Das Token laeuft nach etwa 60 Tagen ab.** Danach schlaegt der Upload fehl -
du bekommst eine Telegram-Meldung, aber keine Vorwarnung. Trag dir eine
Erinnerung ein.

**API-Version:** In `instagram.py` steht oben `API = ".../v21.0"`. Meta stellt
alte Versionen nach etwa zwei Jahren ab. Laeuft der Upload ploetzlich in einen
Fehler, der nach einem Rechteproblem aussieht, ist meist diese Zeile faellig.

---

## Phase 2: Lokal zum Laufen bringen (45 Min)

```bash
cd politik-digest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Umgebungsvariablen setzen:

```bash
cp .env.example .env
# .env ausfuellen, dann:
export $(grep -v '^#' .env | xargs)
```

**Erst die Quellen pruefen:**

```bash
python check_sources.py
```

Behoerden-Feeds aendern ihre URLs gelegentlich. Was hier `FEHL` oder `LEER`
zeigt, suchst du auf der jeweiligen Website neu und traegst es in `config.py`
ein. Rechne damit, dass ein bis zwei URLs angepasst werden muessen.

**Dann der erste Lauf:**

```bash
python run.py
```

Nach ein bis zwei Minuten kommen die Karten auf Telegram. Wenn nicht, steht
der Fehler im Terminal.

**Jetzt anpassen:**
- `render.py`: `HANDLE` auf deinen Instagram-Namen setzen
- `templates/card.html`: Farben und Schriften nach deinem Geschmack
- `config.py`: `KEYWORDS` schaerfen, `MAX_ITEMS` einstellen

---

## Phase 3: Automatisieren (30 Min)

1. Repo auf GitHub pushen (`.env` ist in `.gitignore`, pruefe das)
2. **Settings → Secrets and variables → Actions → New repository secret**
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DIP_API_KEY` (falls vorhanden)
   - `PEXELS_API_KEY` (falls du Titelbilder willst)
   - `IG_USER_ID` und `IG_ACCESS_TOKEN` (aus Schritt 1.5)
3. **Settings → Secrets and variables → Actions → Variables → New variable**
   - `PAGES_BASE_URL`, die Basis deiner Pages-Adresse ohne Schraegstrich am
     Ende, Form: `https://deinname.github.io/politik-digest`
4. **Settings → Pages → Source: Deploy from branch → main / docs**
   Von dort holt Instagram die Bilder ab (siehe unten).
5. **Settings → Actions → General → Workflow permissions**
   auf "Read and write permissions" stellen - der Lauf pusht die Karten
   selbst, nicht nur den Stand in `data/`.
6. Tab **Actions** → "Taeglicher Digest" → **Run workflow** zum Testen

Laeuft dann werktags automatisch. Uhrzeit steht in `.github/workflows/daily.yml`.

**Achtung:** GitHub-Actions-Cron ist nicht puenktlich, 15 bis 30 Minuten
Verzoegerung sind normal. Wenn du um 8 Uhr freigeben willst, stell auf 06:40 UTC.

**Warum die Karten oeffentlich liegen muessen:** Die Instagram-API nimmt keine
Dateien entgegen. Sie bekommt URLs und holt die Bilder selbst ab. Deshalb
schiebt der Lauf das freigegebene Karussell vor dem Posten nach `docs/`, wo
GitHub Pages es ausliefert. Gepusht wird **nur das freigegebene** - was du
verwirfst, landet nicht im oeffentlichen Verlauf, und der bleibt fuer immer.

Der Datumsordner darin ist kein Schmuck: die API merkt sich die URL, nicht das
Bild. Wuerde der Lauf von morgen dieselben Dateinamen ueberschreiben, zeigte
der Post von heute ploetzlich die Karten von morgen.

---

## Phase 4: Rechtliches, bevor der erste Post rausgeht (60 Min)

### 4.1 Impressum

`impressum.html` ausfuellen und auf GitHub Pages veroeffentlichen:

1. Datei ins Repo legen (oder ein eigenes Repo `impressum`)
2. **Settings → Pages → Source: Deploy from branch → main / root**
3. URL notieren, Form: `https://deinname.github.io/repo/impressum.html`

In der Instagram-Bio verlinken, sichtbar unterhalb der Beschreibung, mit dem
Wort **"Impressum"**. Nicht "Info", nicht "Kontakt", nicht ueber Linktree.

Pflichtangaben: Name, ladungsfaehige Anschrift (kein Postfach), E-Mail,
und der Verantwortliche nach § 18 Abs. 2 MStV.

Wenn du deine Privatadresse nicht zeigen willst: c/o-Geschaeftsadresse mieten,
etwa 10 bis 20 Euro im Monat.

### 4.2 Gewerbe

Sobald Einnahmen fliessen oder du aktiv Kooperationen suchst: Gewerbeanmeldung.
Kleinunternehmerregelung pruefen.

### 4.3 Redaktionelle Kontrolle dokumentieren

Der Freigabeschritt ist nicht Formsache. Er ist der Grund, warum du unter
Art. 50 Abs. 4 KI-Verordnung von der Kennzeichnungspflicht ausgenommen bist,
und er erfuellt die journalistische Sorgfaltspflicht nach § 19 MStV.

**Konkret heisst das:** Bei jeder Meldung den Quelllink oeffnen, bevor du sie
freigibst. Die Telegram-Nachricht liefert dir die Links genau dafuer.

Seit der Upload automatisch laeuft, ist dieser Schritt der einzige Ort, an dem
noch ein Mensch entscheidet - und er traegt damit die ganze Last der beiden
Vorschriften. Deshalb ist er so gebaut, dass Untaetigkeit nie zu einem Post
fuehrt: Du drueckst "Option 1", "Option 2" oder "Keine". Antwortest du gar
nicht, laeuft das Fenster ab und es wird nichts veroeffentlicht. Ein Knopf
"alles freigeben" existiert nicht, und ein Zeitablauf gilt nie als Zustimmung.

Wenn du unsicher bist, ob eine Zahl stimmt: "Keine" druecken. Der Lauf kostet
ein paar Cent, eine unwahre Tatsachenbehauptung kostet vierstellig.

---

## Taeglicher Ablauf danach

| Zeit | Was |
|---|---|
| 07:40 | Pipeline laeuft, beide Karussells kommen auf Telegram |
| 08:00 | Du prufst die Quellen, 5 bis 10 Minuten |
| 08:10 | Du drueckst "Option 1", "Option 2" oder "Keine" |
| 08:12 | Der Lauf legt die Karten ab und postet - oder eben nicht |

**Das Zeitfenster ist begrenzt.** Der Actions-Job wartet `FREIGABE_MINUTEN`
(config.py, 5 Stunden) auf deinen Knopfdruck; die Frage nennt die Uhrzeit, bis
zu der sie gilt. Danach verschwinden die Knoepfe, und es wurde nur nichts
gepostet. So lang, weil GitHub den Cron oft Stunden zu spaet startet. Im
oeffentlichen Repo kostet die Wartezeit keine Actions-Minuten. Es gilt immer
nur die neueste Frage: ein Knopf unter einer alten Nachricht meldet
"abgelaufen" und bewirkt nichts.

---

## Wenn etwas kaputtgeht

| Symptom | Ursache | Fix |
|---|---|---|
| Keine Telegram-Nachricht | Bot nie angeschrieben | Bot in Telegram anschreiben, Chat-ID neu holen |
| "Keine Items nach Vorfilter" | Feeds tot oder Keywords zu eng | `python check_sources.py` |
| Karten ohne richtige Schrift | Google Fonts nicht geladen | Wartezeit in `render.py` erhoehen |
| Alles faellt durch die Pruefung | Quelltexte zu kurz (nur Anreisser) | Volltext nachladen oder `EVIDENCE_THRESHOLD` senken |
| Workflow schlaegt beim Push fehl | Workflow-Rechte fehlen | Settings → Actions → Read and write |
| Knopfdruck bewirkt nichts | Zeitfenster abgelaufen, Job beendet | Workflow neu starten, oder Cron auf deine Zeit stellen |
| "Bild nicht ladbar" beim Upload | Pages liefert noch nicht aus | `PAGES_BASE_URL` pruefen, Pages-Quelle auf `main / docs` |
| Upload scheitert nach ~60 Tagen | Instagram-Token abgelaufen | Neues langlebiges Token erzeugen, Secret ersetzen |
| Upload-Fehler "Unsupported request" | Meta-API-Version abgestellt | `API` in `instagram.py` hochziehen |

---

## Kosten

| Posten | Monat |
|---|---|
| GitHub Actions (oeffentliches Repo) | 0 EUR |
| Anthropic API bei 6 Meldungen taeglich | 1 bis 3 EUR |
| GitHub Pages Impressum und Karten | 0 EUR |
| Instagram Graph API | 0 EUR |
| c/o-Adresse (optional) | 10 bis 20 EUR |

---

## Was du niemals automatisieren solltest

Den Freigabeschritt. Eine falsche Zahl zu einem namentlich genannten
Politiker ist eine unwahre Tatsachenbehauptung, und die kostet in Deutschland
schnell vierstellig. Die Verifikationsstufe im Code faengt viel ab, aber sie
ersetzt dich nicht.

Der Upload ist inzwischen automatisiert, die **Auswahl** nicht - und das ist
der Unterschied, auf den es ankommt. Was der Code dir abnimmt, ist Handarbeit:
Bilder ablegen, hochladen, Bildtext setzen. Was er dir nicht abnimmt, ist die
Entscheidung, ob eine Meldung stimmt und rausgehen soll.

Die Versuchung, daraus ein "postet automatisch, wenn die Pruefung besteht" zu
machen, ist gross - beide Pruefungen im Code sind ja gut. Sie pruefen aber nur,
ob die Karte zur Quelle passt, nicht ob die Quelle richtig verstanden wurde.
Genau dafuer oeffnest du den Link.
