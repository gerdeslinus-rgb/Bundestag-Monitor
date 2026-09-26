# Quellen: Zugang, Eigenheiten, Verarbeitung

Einstiegspunkt fuer jede Arbeit an `sources.py`. Alles hier ist am 24.09.2026
live gegen die Quellen geprueft worden - Zahlen und Feldnamen stammen aus
echten Antworten, nicht aus Dokumentation. Quellen aendern sich: vor einer
groesseren Umstellung die betroffene Stelle kurz nachmessen und diese Datei
nachziehen.

Wie der Tag aufgebaut ist (seit 25.09.2026): Karussell 1 ist ein
beschlossenes Gesetz aus DIP oder dem Textarchiv (Abschnitt 7, seit
26.09.2026 - beide in einer Kandidatenliste), Karussell 2 kommt aus einer zufaellig gezogenen
Kategorie - Destatis, Lobbyregister, Parteispenden, Nebentaetigkeiten
(`config.WEITERE_KATEGORIEN`, Bau in `weitere.py`, Slide-Vorlagen in
VORLAGEN.md). Liefert DIP nichts, kommen beide aus zwei verschiedenen
Kategorien. Was eine Quelle fuer ein Karussell mitbringen muss:
einen Quelltext, in dem der Beleg-Satz woertlich steht (`llm.verify_slides`),
moeglichst Zahlen fuer die Chart-Slide, und - fuer die normale LLM-Strecke -
etwas ENTSCHIEDENES (siehe `SELECT_PROMPT` in `llm.py`). Letzteres ist bei
Statistik- und Registerquellen die eigentliche Huerde, siehe unten.

---

## 1. DIP - Bundestag (Hauptquelle)

**Zugang:** REST `https://search.dip.bundestag.de/api/v1`, Key in `.env`
(`DIP_API_KEY`). Bundespuls nennt einen oeffentlichen Key mit Laufzeit bis
Mai 2027 - wir nutzen den eigenen.

**Was wir holen:** `vorgang` mit `f.vorgangstyp=Gesetzgebung`, 21 Tage zurueck,
nur `beratungsstand` in `DIP_BESCHLOSSEN`. Volltext spaeter ueber
`vorgangsposition` -> `drucksache-text` (Auswahl nach Typ, nicht nach Datum,
siehe `DIP_DRUCKSACHE_REIHENFOLGE`).

**Abstimmungen im DIP:** Eine Beschlussfassung in `vorgangsposition` hat
hoechstens diese Felder:

    {"abstimmungsart": "Namentliche Abstimmung",
     "beschlusstenor": "Ablehnung der Vorlage",
     "abstimm_ergebnis_bemerkung": "58:462:80",   # Ja:Nein:Enthaltung
     "dokumentnummer": "21/7019", "seite": "11148B"}

Also nur Gesamtzahlen, **keine Fraktionen, keine Einzelstimmen**. Die
Fraktionszahlen zieht `abstimmung.py` aus dem Plenarprotokoll-Text; die
Einzelstimmen gibt es nur in der Bundestag-XLSX (Abschnitt 3).

**Fallstricke:**
- Ohne Vorgangstyp-Filter sind drei Viertel der Vorgaenge Schriftliche
  Fragen und Kleine Anfragen.
- Plenarprotokoll-Texte sind riesig (800.000+ Zeichen) - Timeout 120 s.
- `vorgang` liefert hoechstens 100 Treffer je Seite; `fetch_dip` blaettert
  per `cursor`. Ueber 90 Tage waren es 157 Vorgaenge - ohne Blaettern fielen
  Gesetze still weg.
- `drucksache?f.vorgang=<id>` ignoriert den Filter und liefert die neuesten
  Drucksachen ueberhaupt. Die Drucksachen eines Vorgangs kommen ueber
  `vorgangsposition?f.vorgang=<id>` (`sources.dip_drucksachen`).
- Nach der Sommerpause lagen im 21-Tage-Fenster nur zehn beschlossene Gesetze,
  keines mit nennenswerter Lobbyarbeit. Das Lobby-Karussell schaut deshalb
  90 Tage zurueck (`LOBBY_GESETZE_TAGE`).
- Die zuletzt eingegangene Drucksache ist oft ein abgelehnter
  Aenderungsantrag, nicht der beschlossene Text.

---

## 2. Destatis (Statistisches Bundesamt)

**Zugang:** RSS `https://www.destatis.de/SiteGlobals/Functions/RSSFeed/DE/RSSNewsfeed/Aktuell.xml`,
kein Key. `sources.fetch_destatis` (Teaser), `sources.destatis_anreichern`
(Volltext + Grafikdaten, nur fuer die ausgewaehlten Meldungen).

**Menge:** Der Feed haelt nur die **letzten 10** Pressemitteilungen, das
sind 3-4 Tage (2-3 pro Werktag). Bei taeglichem Lauf reicht das; faellt der
Lauf ein paar Tage aus, gehen Meldungen verloren.

**Inhalt:** Jede Meldung hat eine harte Zahl im ersten Satz und fast immer
einen Vorjahresvergleich. Beispiel (PM 337, Verkehrsunfaelle): 1.233 Tote im
1. Halbjahr, -9 % zum Vorjahr, dazu Rangfolge der Bundeslaender und
Aufschluesselung nach Verkehrsmittel. Der RSS-Teaser ist nur 200-600 Zeichen,
die Seite 4.000+.

**Die eigentliche Fundgrube - Chart-CSV:** Rund 6 von 10 Meldungen haben eine
eingebettete Grafik, deren Daten als CSV an der Seite haengen:

    <p class="chartImage ..." data-chart-csvurl="/DE/Presse/.../_Daten/20260924-verkehrsunfaelle-getoetete-monat.csv?__blob=value&v=1">

    "Monat";2024;2025;2026
    "Jan";175;183;151
    ...

Das sind die amtlichen Zahlen, fertig als Zeitreihe - die Chart-Slide koennte
sie direkt uebernehmen, statt das Modell Zahlen aus dem Fliesstext ziehen zu
lassen. Vorsicht: Semikolon-getrennt, leere Zellen fuer noch nicht erhobene
Monate, Monatsnamen abgekuerzt ("Mrz").

**Volltext-Extraktion:** `_fetch_full_text` funktioniert, nimmt aber
Seitenrahmen mit ("Seite teilen", "Laedt...", Kontaktblock). Sauber ist der
Bereich zwischen `Pressemitteilung Nr. ` und `Kontakt fuer weitere Auskuenfte`.

**GENESIS-Datenbank:** `https://genesis.destatis.de/genesisWS/rest/2020/`.
Tabellen **suchen** geht als Gast (POST, Header `username: GAST`,
`password: GAST`). Tabellen **herunterladen** (`data/tablefile`) antwortet
als Gast mit 401 Code 15 - dafuer braucht es ein kostenloses Konto. Die
Pressemitteilung nennt die Tabellennummer ("Tabellen 46241"). Fuer den
Tageslauf nicht noetig, die Chart-CSV reicht.

**Passung zur Pipeline:** Eine Statistik ist nicht "entschieden" - der
SELECT_PROMPT haette sie verworfen. Destatis hat deshalb eine eigene Auswahl
(`llm.destatis_auswahl`: Haiku markiert je Meldung Alltagsbezug ja/nein, die
juengste markierte gewinnt) und laeuft danach durch die normale Strecke
(Recherche, Entwurf, Belegpruefung, Faktencheck). Erster Test 25.09.2026:
Haeuserpreisindex gewaehlt, Kirschenernte und Erzeugerpreise verworfen,
Karussell bestand beide Pruefungen.

Themenauswahl: nicht jede Meldung taugt (Kirschenernte, Pkw-Exporte). Gute
Kandidaten beruehren Alltag oder oeffentliche Debatte: Preise, Mieten,
Unfaelle, Einkommen, Bevoelkerung.

---

## 3. Namentliche Abstimmungen - Bundestag XLSX

**Zugang:** Liste als HTML-Fragment, kein Key:

    https://www.bundestag.de/ajax/filterlist/de/parlament/plenum/abstimmung/liste/462112-462112?limit=30&offset=0&noFilterSet=true

Jede Zeile hat Datum, Titel, ein PDF und eine XLSX. Dateinamen
`YYYYMMDD_N.pdf` / `YYYYMMDD_N-xls.xlsx` (manchmal `_xls.xlsx`), N = laufende
Nummer am Tag.

**Aktualitaet:** Am selben Tag. Die Abstimmung vom 24.09.2026 stand am
24.09. online. abgeordnetenwatch hatte zu dem Zeitpunkt als neueste
Abstimmung den 10.07.2026 - deshalb ist `fetch_aow` entfernt.

**XLSX-Spalten:** `Wahlperiode, Sitzungnr, Abstimmnr, Fraktion/Gruppe, Name,
Vorname, Titel, ja, nein, Enthaltung, ungueltig, nichtabgegeben, Bezeichnung,
Bemerkung` - eine Zeile pro MdB (630), die Stimmspalten sind 0/1.
Fraktionskuerzel: `CDU/CSU, SPD, AfD, BUe90/GR, Die Linke, Fraktionslos`.
Namen enthalten Zeichen ausserhalb Latin-1 (z. B. "ć") - Ausgabe immer UTF-8,
sonst bricht ein `print` unter Windows ab. Lesen braucht `openpyxl`
(seit 26.09.2026 in `requirements.txt`).

**Genutzt seit 26.09.2026** (`stimmen.py`): Sitzbogen fuer Textarchiv-
Karussells am Sitzungstag. Zuordnung Artikel -> XLSX: gleiches Datum, und
Ja- und Nein-Zahl der XLSX stehen woertlich im Artikel; bei mehreren
Treffern (Tankrabatt 434:128 und Entschliessungsantrag 127:418 im selben
Artikel) entscheidet die Titelnaehe. Ohne namentliche Abstimmung liest
`stimmen.handzeichen()` die Fraktionspositionen aus dem Redaktionssatz
("Dafuer stimmten ..., dagegen ... enthielt sich") - nur wenn JEDE Fraktion
zugeordnet ist, sonst gibt es keinen Bogen. Stand 24./25.09.2026: 3 von 9
Beschluessen namentlich, 5 per Handzeichen lesbar, 1 ohne Bogen ("mit den
Stimmen aller uebrigen Fraktionen abgelehnt" - die AfD-Position zum eigenen
Entwurf steht dort nicht).

**Menge:** 51 namentliche Abstimmungen in der 21. WP bis 24.09.2026, an 27
Tagen - im Schnitt drei pro Monat, gebuendelt (10.07.2026: acht an einem Tag).
Keine taegliche Quelle, sondern ein Ereignis.

**Verknuepfung mit DIP - deterministisch:** Das Tripel Ja:Nein:Enthaltung aus
der XLSX ist identisch mit `abstimm_ergebnis_bemerkung` im DIP. Am 10.07.2026
passten alle vier Pruefungen exakt (58:462:80 -> Drs. 21/7019, 135:456:0 ->
21/7020, 57:456:75 -> 21/7021, 267:326:6 -> 21/7022). Datum + Tripel ergibt
den Vorgang ohne Titelvergleich. Das ist sicherer als der Titelabgleich in
`abstimmung.py` (Ueberlappung 0.6).

**Was sich daraus machen laesst:**
- Fraktionsaufschluesselung fuer DIP-Karussells (heute aus dem Protokoll -
  die XLSX waere die einfachere, amtliche Alternative).
- Abweichler: Fraktion mit >= 2 Stimmen gegen die eigene Mehrheit. Beispiel
  GKV-Finanzreform 10.07.2026: SPD 111 Ja / 4 Enthaltung / 3 Nein, CDU/CSU
  207 Ja / 1 Nein - mit Namen. `fetch_einzelstimmen` tat das ueber
  abgeordnetenwatch (wochenlang hinterher) und ist entfernt; wenn Abweichler
  wieder ein Thema werden, dann aus dieser XLSX.
- Sitzbogen (`sitzbogen.py`) aus echten Einzelstimmen.

**Vorsicht bei Namen:** Einzelne Abweichler namentlich auf eine Karte zu
setzen, ist eine redaktionelle Entscheidung, keine technische.

---

## 4. Lobbyregister

**Zwei Zugaenge, die sich ergaenzen:**

| | `www.lobbyregister.bundestag.de/sucheJson` | API v2 `api.lobbyregister.bundestag.de/rest/v2/registerentries` |
|---|---|---|
| Key | keiner | oeffentlich auf der Open-Data-Seite: Header `Authorization: ApiKey 5bHB2zrUuHR6YdPoZygQhWfg2CBrjUOi` (individueller Dauerkey per Mail an lobbyregister@bundestag.de) |
| Ohne Suchbegriff | liefert **alle ~7.000 Eintraege in einer Antwort** - daher die ~50 s in `fetch_lobbyregister` | 50 pro Seite |
| Mit `q=21/6278` | alle 61 Treffer in 0,5 s, aber nur Zaehler (`regulatoryProjectsCount`) | volle Details inkl. Regelungsvorhaben - aber nur die ersten 50 |
| Paginierung | - | `cursor` laut Doku; im Test lieferte Seite 2 **immer 0 Treffer** |

`sortierung=AKTUALITAET` in `fetch_lobbyregister` wird ignoriert - die
Antwort meldet `sortOrder: REGISTRATION_DESC`.

**Weniger als 7.000 holen - serverseitige Filter:** `sucheJson` versteht
dieselben Filter wie die Web-Suche, in der Form `filter[<name>][<wert>]=true`
(Bereiche: `filter[<name>][<von>-<bis>]=true`). Einfache Namen wie
`revolvingdooractive=true` werden still ignoriert - dann kommen wieder alle
7.000. Ob ein Filter gegriffen hat, steht in `searchParameters.facets` bzw.
`numberRanges` der Antwort. Gemessen:

| Filter | Treffer | Groesse |
|---|---|---|
| (keiner) | 6.987 | 17 MB, 3 s |
| `filter[revolvingdooractive][true]` | 110 | 330 KB |
| `filter[revolvingdoorareas][FEDERAL_GOVERNMENT]` | 12 | 36 KB |
| `filter[revolvingdoorareas][FEDERAL_GOVERNMENT\|MINISTER]` | 4 | 10 KB |
| `filter[revolvingdoorareas][HOUSE_OF_REPRESENTATIVES\|MEMBER]` | 164 | 490 KB |
| `filter[financialexpenses][5000000-999999999]` | 14 | 88 KB |
| `filter[fieldsofinterest][FOI_DEFENSE\|FOI_DEFENSE_ARMAMENTS]` | 379 | 1,2 MB |
| `filter[annotations][CODEX_VIOLATION]` | 1 | 5 KB |
| `filter[regulatoryprojecttypes][BT_PRINTING_NUMBER]` | 1.777 | 5 MB |

Alle Filternamen stehen als `value` der Checkboxen im HTML von
`/suche` (dort URL-kodiert). `sort` und `pageSize` wirken auf `sucheJson`
nicht. Nach Datum filtern geht nicht - fuer "neu seit" die Felder
`accountDetails.firstPublicationDate` / `registerEntryDetails.validFromDate`
selbst auswerten.

**Codes unterscheiden sich zwischen Suche und API:** Die Suche liefert
`ACT_ORGANIZATION`, die API v2 fuer denselben Eintrag `ACT_ORGANIZATION_V2`
("Sonstiges Unternehmen"). Ohne Abgleich landeten 44 von 104 Organisationen
unter "Sonstige" (`weitere._art` schneidet `_V2` ab).

**Namen haben Leerzeichen am Rand** ("Hitschler ") - vor Anzeige normalisieren.

**Suchliste vs. Detail:** `sucheJson` liefert nur Zaehler (Anzahl
Regelungsvorhaben, Stellungnahmen, Vertraege). Personen, Regelungsvorhaben
mit Drucksachen, Stellungnahmen (mit Volltext, PDF, Versanddatum und
Empfaenger-Ministerium), Oeffentliche Zuwendungen, Auftraggeber gibt es nur
im Einzeleintrag: API `GET /registerentries/{R-Nummer}` (aktuell) bzw.
`/{R-Nummer}/{version}` (frueherer Stand). Jede Version ist abrufbar - ein
Vergleich zweier Versionen zeigt, wer neu dazugekommen ist.

**Statistik:** `GET /rest/v2/statistics/registerentries` - Gesamtzahlen
(6.315 aktive Akteure, 30.272 Personen, davon 971 mit frueherer Funktion in
Regierung/Bundestag/Verwaltung, 435 mit versaeumter Jahresaktualisierung).

**Einzeleintraege sind kein Thema:** 30-70 Aenderungen pro Tag, grosse
Spitzen vor dem 30.06. (Jahresmeldung der Finanzen). Der SELECT_PROMPT
schliesst "Lobbyregister-Eintraege" ausdruecklich aus.

**Was funktioniert - Lobby zu einem Gesetz:** Jedes Regelungsvorhaben traegt
die Drucksachen, auf die es sich bezieht:

    "printedMatters": [{"printingNumber": "21/6278", "issuer": "BT",
      "projectUrl": "https://dip.bundestag.de/vorgang/.../334923",
      "leadingMinistries": [{"shortTitle": "BMWE"}, ...]}]

`projectUrl` endet auf die **DIP-Vorgangs-ID** - direkt verknuepfbar mit
unseren DIP-Items. Suche per Drucksachennummer (die Vorgangs-ID selbst ist
nicht im Suchindex, `q=334923` ergibt 0). Beispiel Gebaeudemodernisierungs-
gesetz: 61 Eintraege, darunter BDEW, E.ON, Bundesverband Solarwirtschaft,
Zentralverband Baugewerbe; 21 Unternehmen, 13 Wirtschaftsverbaende.

Das ist eine Anreicherung fuer DIP-Karussells ("61 Organisationen haben zu
diesem Gesetz Lobbyarbeit gemeldet"), keine eigenstaendige Quelle.

**Was die Organisationen wollten - gemessen am 25.09.2026:** Jedes
Regelungsvorhaben im Einzeleintrag hat ein Feld `description` - die eigenen
Worte der Organisation, was sie erreichen will ("Weiterentwicklung der
bundesrechtlichen Rahmenbedingungen fuer klimaneutrale Waermelieferung ...").
Dazu `statements.statements[]`: hochgeladene Stellungnahmen mit
`regulatoryProjectNumber`, `pdfUrl` und dem **Volltext** in `text.text`
(z. B. dena und KiB zum GModG, BDEW, E.ON). Der Text kommt aus dem PDF:
Zeilenumbrueche mitten im Satz, Silbentrennung am Zeilenende - vor
Verwendung glaetten (`weitere._ohne_umbruch`). Zuordnung zum Gesetz ueber
die Vorhabennummer. Daraus baut `llm.lobby_positionen` je Organisation einen
Satz; Auszug je Stellungnahme `LOBBY_AUSZUG` Zeichen, derselbe fuer Modell
und Faktencheck. Achtung Urheberrecht: das Register weist darauf hin, dass
Stellungnahmen geschuetzte Werke sein koennen - zusammenfassen, nicht
zitieren.

**Selbstbeschreibung:** `activitiesAndInterests.activityDescription` ist ein
Absatz in eigenen Worten ("Campact ist eine Kampagnen-Organisation, mit der
ueber 4,5 Millionen Menschen ..."). Grundlage fuer "Wer ist der Spender?"
zusammen mit dem Wikipedia-Anfang (`sources.wikipedia_kurz`, nur bei
passendem Artikeltitel).

**Falle - Betraege:** `financialExpensesEuro` ist der **gesamte**
Jahresaufwand der Organisation fuer Interessenvertretung, nicht der Aufwand
fuer dieses Gesetz. "BDEW gab 9,9 Mio. fuer das GModG aus" waere falsch.
Ausserdem Spannen (`from`/`to`), selbst deklariert, Vorjahr.

**Inhaltliche Blickwinkel - gemessen am 24.09.2026:**

1. *Lobby zu einem Gesetz* (siehe oben) - stark, weil an ein aktuelles
   Gesetz gebunden. Taeglich verfuegbar, solange DIP Gesetze liefert.
2. *Drehtuer* - ehemalige Regierungsmitglieder, die jetzt als
   Interessenvertreter eingetragen sind. Das Feld
   `recentGovernmentFunction` je Person nennt Funktion, Ministerium und
   Enddatum. Beispiele: Annegret Kramp-Karrenbauer (Ministerin bis 12/2021)
   bei drei Organisationen, Bettina Stark-Watzinger (Ministerin bis 11/2024)
   bei Focused Energy (Kernfusion), Daniela Kluckert (PStS bis 11/2024) bei
   einer Lobbyberatung, Mario Brandenburg (PStS bis 11/2024) bei SAP.
   Fallstricke:
   - `ended: false` sind oft **Amtstraeger kraft Amtes**, keine Drehtuer
     (z. B. MdB im Kuratorium der Deutschen Bundesstiftung Umwelt).
   - Selbstauskunft, Fehler kommen vor: thyssenkrupp fuehrt eine Person als
     "Bundeskanzler/-in".
   - Der Bestand ist klein (Bundesregierung: 12 Eintraege) und aendert sich
     selten. Neu hinzukommende Personen sind laut Versionsvergleich meist
     Referenten und Sachbearbeiter - Privatpersonen, kein Thema.
3. *Wer gibt am meisten aus* - Rangliste nach `financialExpenses`, auch je
   Themenfeld (`fieldsofinterest`). Spitze Geschaeftsjahr 2025: GDV 15,8 Mio.,
   Verbraucherzentrale Bundesverband 12,4 Mio., VDA 10,3 Mio., BDEW 9,9 Mio.,
   BDI 9,6 Mio. Diagrammfertig. Aendert sich nur einmal im Jahr (Meldung bis
   30.06.). **Doppelte Eintraege** kommen vor (BDI zweimal) - nach
   `registerNumber` entdoppeln.
4. *Schwach:* Neuregistrierungen (~50/Monat, Neue melden fast immer 0 Euro,
   weil noch kein Geschaeftsjahr abgeschlossen ist); Spenden aus
   Drittstaaten (Filter trifft vor allem Hilfswerke, `totalDonationsEuro` ist
   die Gesamtsumme, nicht der Drittstaaten-Anteil); Kodex-Verstoesse (1).

---

## 5. Parteispenden (§ 25 PartG, ueber 35.000 Euro)

**Zugang:** HTML-Tabelle je Jahr, kein Key:
`https://www.bundestag.de/parlament/praesidium/parteienfinanzierung/fundstellen50000/<jahr>`.
Der Parser in `fetch_parteispenden` funktioniert (2025: 170 Zeilen, 2026:
72).

**Nicht auf die Bundespuls-CSV umstellen:** Sie ist mindestens einen Tag
hinterher (die DVAG-Spende vom 23.09.2026 fehlte dort am 24.09.).

**Spalten:** Partei, Betrag ("50.000 Euro"), Spender inkl. Anschrift,
Eingang der Spende, Eingang der Anzeige (+ "Drs. 21/4050" sobald
gesammelt veroeffentlicht).

**Menge:** 2026 rund 7 pro Monat, 2025 mit Wahlkampfspitze im Januar (71).
Das 30-Stunden-Fenster (`LOOKBACK_HOURS`) ist deshalb fast immer leer.

**Fallstricke:**
- **Spender-Feld enthaelt Privatadressen** ("Prof. Dr. ... Am Sonnenberg 9
  23627 Gross Groenau"). Der Bundestag veroeffentlicht sie, wir sollten sie
  nicht auf eine Karte oder in eine Caption setzen. Bei Organisationen ist
  die Adresse harmlos, bei Privatpersonen nicht.
- Weiche Trennzeichen (`\xad`) mitten in Namen ("Metall- \xad Industrie").
- Datumsfeld manchmal mit mehreren Teilzahlungen ("18./20./24.10. 2025")
  - das Regex im Parser ueberspringt diese Zeilen still.
- Partei-Schreibweise uneinheitlich ("Buendnis 90/ Die Gruenen").

**Was sich daraus machen laesst:** Eine Einzelspende ist selten ein Thema.
Eine Aggregation schon: Monat/Jahr nach Partei, groesste Spender, Vergleich
zum Vorjahr - deterministisch, ohne Modell, wie der Profil-Modus.

---

## 6. Nebentaetigkeiten (abgeordnetenwatch /sidejobs)

**Zugang:** `https://www.abgeordnetenwatch.de/api/v2/sidejobs`, kein Key,
CC0. Die Rohdaten sind die veroeffentlichungspflichtigen Angaben des
Bundestages.

**Felder:** `label` (Taetigkeit), `mandates[0].label` ("Name (Bundestag 2025 -
2029)"), `sidejob_organization.label`, `income` (Euro, exakt, wenn gemeldet),
`income_level` (Stufe 1-10), `interval` (meist leer = einmalig/jaehrlich),
`category` (Code, z. B. 29647 = entgeltliche Taetigkeit, 29230 = Ehrenamt in
Organisation, 29231 = Beteiligung, 29232 = Reisekosten), `data_change_date`,
`created` (Unix-Zeit).

**Menge:** Schubweise. Von 200 neuesten: 88 am 17.09., 71 am 16.09.,
sonst einstellig. Deshalb `REGISTER_LOOKBACK_DAYS = 14`. Etwa die Haelfte mit
Betrag.

**Warum nur rund die Haelfte einen Betrag hat** (2.000 neueste Eintraege
ausgezaehlt): Die meisten Kategorien sind von Natur aus unbezahlt.

| Kategorie | mit Betrag | ohne | Amtliche Bezeichnung (laut abgeordnetenwatch-Doku) |
|---|---|---|---|
| 29647 | 403 | 52 | Entgeltliche Taetigkeiten neben dem Mandat |
| 29232 | 50 | 0 | Spenden/Zuwendungen fuer politische Taetigkeit |
| 29229 | 256 | 279 | Funktionen in Koerperschaften und Anstalten des oeffentlichen Rechts |
| 29228 | 57 | 148 | Funktionen in Unternehmen |
| 29230 | 19 | 342 | Funktionen in Vereinen, Verbaenden und Stiftungen |
| 29231 | 9 | 46 | Beteiligung an Kapital- oder Personengesellschaften |
| 29233 | - | - | Vereinbarungen ueber kuenftige Taetigkeiten oder Vermoegensvorteile |
| 29234 | 0 | 338 | Berufliche Taetigkeit vor der Mitgliedschaft im Bundestag |

Die Liste steht auch in `config.NEBEN_KATEGORIEN` (mit Kurzlabels fuer die
Balken). `income_level` 0-10 sind Stufen von "1 bis 1.000 Euro" bis "ab
250.000 Euro".

Die Angaben ohne Betrag bei entgeltlichen Taetigkeiten sind meist Anwaelte
und Steuerberater, die ihre Mandanten in `additional_information` nur
anonym auflisten ("Mandant 1, Automobil, 2025"). Nach den Verhaltensregeln
des Bundestages werden Einkuenfte ausserdem erst ab einer Schwelle je
Taetigkeit angegeben (nach unserem Kenntnisstand 1.000 Euro im Monat bzw.
3.000 Euro im Jahr - vor einer Karte, die damit argumentiert, im AbgG
nachpruefen).

**Beispiele (Sept. 2026):** 70.766 Euro Unternehmenseinkuenfte, 47.500 Euro
von einem Fussball-Bundesligisten, Anwalts- und Autorenhonorare.

**Zeitraum eines Betrags - `interval`** (laut API-Doku `/api/entitaeten/sidejob`):
`0` = einmalig, `1` = monatlich, `2` = jaehrlich. Ohne Intervall steht der
Zeitraum oft in `job_title_extra` ("Einkommen im Jahr 2025" = Jahressumme).
Von 1.065 Meldungen mit Betrag (WP seit 2025): 292 monatlich, 130 jaehrlich,
643 ohne Intervall. Auf der Karte steht jeder Betrag mit Zeitraum ("11.227 €
/ Monat"); verglichen (Durchschnitt, Rang, Balkenlaenge) wird aufs Jahr
gerechnet, Monatsbetrag x 12 (`sources.neben_jahreswert`). Ohne das stand
Linnemann (CDU-Generalsekretaer, 11.227 Euro im Monat) auf Platz 51 statt 5.

**Ganzer Bundestag auf einmal:** `GET /sidejobs?mandates[entity.parliament_period]=161&range_start=0&range_end=1000`
filtert serverseitig auf die Wahlperiode (25.09.2026: 4.621 Meldungen, fuenf
Seiten). `range_end` ist die Seitengroesse, nicht das Ende. Eine Meldung
nennt ALLE Mandate der Person, auch fruehere Wahlperioden - beim Verdichten
nur das Mandat mit "(Bundestag 2025 - 2029)" im Label zaehlen, sonst stehen
1.205 "Abgeordnete" in der Liste. Ergebnis 25.09.2026: 615 Abgeordnete mit
mindestens einer Meldung, 266 mit Betrag; Ø 7,3 Meldungen je Sitz.
`sources.neben_statistik`, eine Woche Cache. Vorige Wahlperiode: 132.

**Je Person abfragen:** Name -> `GET /politicians?label=<Name>` -> ID ->
`GET /candidacies-mandates?politician=<ID>&parliament_period=161&type=mandate`
(161 = Bundestag 2025-2029; leer = kein aktuelles Mandat) -> Mandats-ID ->
`GET /sidejobs?mandates=<Mandats-ID>&range_end=200`.

**Rate-Limit:** abgeordnetenwatch antwortet schon bei zuegigen
Einzelabfragen mit **HTTP 429** und leerem Body (dann scheitert `.json()`).
Nicht parallel abfragen, Pausen einbauen, bei 429 mit wachsender Wartezeit
wiederholen. Personen-/Mandats-IDs aendern sich innerhalb der Wahlperiode
nicht - einmal aufloesen und speichern statt jeden Lauf neu.

**Minister:** Bundesminister duerfen im Amt nach unserem Kenntnisstand kein
bezahltes Nebenamt ausueben. Ihre Eintraege sind deshalb meist Taetigkeiten
vor dem Mandat oder Ehrenaemter (Merz: 5 Eintraege, 0 mit Betrag; Klingbeil:
8, 0 mit Betrag).

**Fallstricke:** Alle Angaben personenbezogen - dieselbe Vorsicht wie bei
Abweichlern. Mehrfacheintraege derselben Person/Organisation fuer
verschiedene Zeitraeume: der Zeitraum steht in `job_title_extra`
("Einkommen im Jahr 2025"), nicht in `interval`. Nicht addieren; auf dem
Balken steht das Jahr dabei ("Eintracht Frankfurt 2025").

---

## 7. Textarchiv des Bundestages (Beschluesse vom Sitzungstag)

**Warum:** DIP hinkt. Der Tankrabatt wurde am Freitag, 25.09.2026, um 09:25
im Textarchiv gemeldet ("Bundestag beschliesst Tankrabatt ..."). Im DIP stand
der Vorgang am Samstag noch auf "Beschlussempfehlung liegt vor" - und hiess
"Gesetz zur Umsetzung der Richtlinien (EU) 2025/1 ... Versicherungsunternehmen",
weil der Finanzausschuss den Tankrabatt als Artikel 11-13 an das VSAAG
gehaengt hatte. Die Artikel der Parlamentsredaktion nennen das eigentliche
Thema und stehen noch am Sitzungstag online.

**Zugang (kein Key, nicht dokumentiert - aus der Archivseite abgelesen):**

    Liste:   https://www.bundestag.de/ajax/filterlist/de/dokumente/textarchiv/454772-454772?limit=20&offset=0&noFilterSet=true
    Artikel: https://www.bundestag.de/blueprint/servlet/ajax/content/de/<id>-<id>/asJsonSliderResult
    Seite:   https://www.bundestag.de/dokumente/textarchiv/<id>  (leitet auf die volle Adresse um)

Die Liste liefert je Seite 20 Artikel-IDs (`data-for-id="slider_<id>"`),
neueste zuerst, 6739 Artikel am 26.09.2026. Das Artikel-JSON hat
`teaser-title`, `href` und `text-description` - nur den ersten Absatz (rund
500 Zeichen), kein Datum. Das Datum steht im ersten Satz ("am Freitag,
25. September 2026"). Den ganzen Text hat nur die Artikelseite.

Der RSS-Feed "Aktuelle Themen" (`/static/appdata/includes/rss/aktuellethemen.rss`)
hat denselben Inhalt samt Volltext, haelt aber nur 15 Eintraege - in einer
Sitzungswoche rund anderthalb Tage. Deshalb die Liste.

**Was wir holen:** Artikel der letzten 4 Tage (`TEXTARCHIV_TAGE`, damit der
Montagslauf Donnerstag und Freitag noch sieht). Am 26.09.2026 waren das 140
Artikel in 46 Sekunden, davon 9 Beschluesse zu Gesetzen.

**Beschluss oder nicht** (`sources.ta_beschluss`, ohne Modell): Ueberschrift
und erster Absatz muessen ein Beschlussverb enthalten (beschlossen,
angenommen, abgelehnt, zugestimmt, verabschiedet ...) UND ein Gesetz nennen
(ganzes Wort: "...gesetz", "...gesetzes", "Gesetzentwurf", "Verordnung",
Vermittlungsergebnis, Abkommen, Bundeswehr). Raus sind erste Lesungen,
"Abgesetzt:", Aktuelle Stunden, Befragungen - und abgelehnte Antraege der
Opposition, die es jede Woche dutzendfach gibt (Entscheidung 26.09.2026).
Ein abgelehnter Gesetzentwurf zaehlt dagegen, wie bei DIP.

**Volltext:** Die Artikelseite enthaelt Navigation, verwandte Artikel und die
Rednerliste. Gelesen wird vom Absatz, der wie der Anriss beginnt, bis zum
Absatz mit dem Redaktionskuerzel am Ende ("(hle/vom/25.09.2026)"). Fehlt das
Kuerzel, bleibt es beim Anriss. `ensure_volltext()` laesst Textarchiv-Items
in Ruhe - sonst holte es fuer kurze Artikel die ganze Seite.

**Verknuepfung mit DIP:** Die Drucksachennummern im Artikel ("21/6561") fuehren
ueber `drucksache?f.dokumentnummer=21/6561&f.zuordnung=BT` zum
`vorgangsbezug`. Gibt es einen Gesetzgebungsvorgang, bekommt das Item DESSEN
ID (`_hash("dipvorgang" + id)`) - dieselbe wie bei `fetch_dip()`. Damit steht
ein Gesetz nur einmal in der Auswahl (`mit_textarchiv`: das Textarchiv-Item
gewinnt), und nach dem Post kommt es nicht Tage spaeter ueber DIP zurueck.
`dip_vorgang_id` wird bewusst NICHT gesetzt: daran haengt `ensure_volltext()`
den Drucksachentext, der den Artikel ersetzen wuerde.

**Fallstricke:**
- Inline-Tags: `_clean()` macht aus `<strong>2026</strong>,` "2026 ," - ein
  korrekt zitierter Beleg-Satz faende sich dann nicht wieder. `_ta_glatt()`
  entfernt Tags ohne Leerzeichen, dazu `&shy;` (Tank&shy;rabatt) und den
  Linkhinweis "(Dokument, oeffnet ein neues Fenster)".
- Ein Artikel kann mehrere Beschluesse buendeln ("Abschliessende Beratungen
  ohne Aussprache", Tankrabatt plus Versicherungsrecht). Verknuepft wird
  ueber die erste Drucksache, die zu einem Gesetz fuehrt.
- Die Adressen koennen sich ohne Ankuendigung aendern. Dann liefert der
  Fetcher eine leere Liste, und der Lauf faehrt mit DIP allein weiter.

**Nicht genommen:** hib-Meldungen (Ausschuesse - "Finanzausschuss beschliesst
Tankrabatt" kam am Mittwoch, VOR der Abstimmung im Plenum) und
Plenarprotokolle (erscheinen erst am naechsten Morgen, der vom Freitag lag
am Samstag noch nicht vor).

---

## Entfernte Quellen - und warum

Damit sie nicht aus Versehen zurueckkommen.

| Quelle | Entfernt | Grund |
|---|---|---|
| `fetch_tagesordnung` (Bundestag conferences.xml) | 24.09.2026 | Kuendigt Debatten an, entscheidet nichts. Verdraengte beschlossene Gesetze. |
| `fetch_bundespuls` (bundespuls.de RSS) | 24.09.2026 | Reiner Aggregator von DIP, Lobbyregister, abgeordnetenwatch, Parteispenden - kein eigenes Material. Vorgangs-Feed zur Haelfte Kleine Anfragen, Abstimmungs-Feed hinkt wie abgeordnetenwatch. API-Doku unter `bundespuls.de/openapi.json`, `/llms.txt`, falls es je wieder interessiert. |
| `fetch_aow` (abgeordnetenwatch /polls) | 24.09.2026 | Wochen hinterher (neueste Abstimmung 10.07., waehrend der Bundestag am 24.09. schon die XLSX hatte). Mit 30-h-Fenster praktisch immer leer. Hatte ausserdem einen Bug: las `poll["url"]`, das Feld heisst `abgeordnetenwatch_url`. |
| Bundesbank-RSS | 24.09.2026 | Anleihe-Auktionen ohne Text, jede Meldung doppelt (deutsch/englisch). |
| Bundesregierung-RSS | 24.09.2026 | Pressemitteilungs-Feed (1151244) ueberwiegend Protokoll (Telefonate, Glueckwuensche). Der bessere Artikel-Feed (1151246) wurde geprueft und bewusst nicht genommen: alte Artikel tauchen mit neuem Datum wieder auf, "Kabinett beschlossen" ist meist nur ein Gesetzentwurf, und `_fetch_full_text` liefert dort Cookie-Banner statt Text (Artikel steht in den `div.bpa-richtext` nach dem ersten). |

| `fetch_einzelstimmen` (abgeordnetenwatch /votes) | 25.09.2026 | Uneinige Fraktionen bei namentlichen Abstimmungen - dieselbe Verzoegerung wie `fetch_aow`. Die Bundestag-XLSX (Abschnitt 3) hat dieselben Daten am selben Tag. |
| `fetch_ausschuesse` (Bundestag Ausschuss-XML) | 25.09.2026 | Besetzungswechsel in Ausschuessen: Personalien ohne Alltagsbezug, verrauschte Aenderungsdaten, rund 65 s Laufzeit. |

---

## Entscheidungen

Getroffen (24./25.09.2026):
- Tagesaufbau: 1 DIP + 1 zufaellige weitere Kategorie; ohne DIP zwei weitere.
- Destatis: juengste Meldung mit Alltagsbezug.
- Lobbyregister: "Wer hat zu diesem Gesetz lobbyiert" fuer die Gesetze mit
  den meisten Eintraegen; sonst Drehtuer, sonst Ausgaben-Rangliste.
  Ehemalige Minister duerfen namentlich genannt werden.
- Parteispenden: aktuelle Grossspende (ab 100.000 Euro, 14 Tage) mit
  Spenderhintergrund, sonst Jahresbilanz nach Partei. Privatpersonen nur mit
  Name und Betrag, nie mit Anschrift.
- Nebentaetigkeiten: 15 Abgeordnete der Reihe nach (`POLITIKER_BACKLOG`).

- Negative Werte: Balken von einer Nulllinie aus; Gruen/Rot bei
  `wertung: "hoch_gut"` (auch Haeuserpreise) oder `"hoch_schlecht"` (Verbraucherpreise, Mieten), nur
  fuer Messwerte, nie fuer Gesetzesregeln (DESIGN-SYSTEM.md §1, §4).
- Parteien: in Kopfzeilen und Diagrammen das Logo, im Fliesstext der Name.
- Portraets fuer Nebentaetigkeiten: in Farbe, freigestellt mit Oberkoerper,
  je Person ein fest gewaehltes Commons-Bild (`data/portraets.json`,
  ausgewaehlt 25.09.2026 nach Regeln: neu, eine Person, kein Mikrofon vor
  dem Gesicht; freigestellt mit `portraet.py`). Cover 1g.
- Logos nur von Wikimedia Commons (keine Websites, kein Logo-Dienst).
  Eintracht Frankfurt und die meisten Vereinswappen sind dort nicht frei -
  die bekommen keins.
- Nebentaetigkeiten nur mit Befund (Betrag oder deutliche Aenderung), mit
  Vergleich zum Durchschnitt aller Abgeordneten.

Offen:
1. Abweichler aus der Bundestag-XLSX als eigene Kategorie - ja oder nein.
2. Reserve-Personen (Kloeckner, Esken, Brandner, Hasselmann, Pellmann) haben
   noch kein Portraet - ihr Cover bleibt typografisch.
