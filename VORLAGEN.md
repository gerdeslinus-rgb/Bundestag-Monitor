# Vorlagen: das zweite Karussell des Tages

Slide fuer Slide, wie `weitere.py` die vier Kategorien baut. Abgestimmt am
25.09.2026, ueberarbeitet am selben Tag nach der ersten Probe. Das Layout (Cover-Architekturen, Farben, Groessen) kommt
unveraendert aus DESIGN-SYSTEM.md - hier steht nur, WAS auf den Slides steht
und WOHER es kommt.

**Daten** heisst: vom Code aus der amtlichen Quelle gebaut, kein Modell.
**Modell** heisst: von Claude geschrieben und gegen die Quelle geprueft.
**Fest** heisst: redigierter Satz im Code - Aenderungen dort, nicht im Modell.

Jedes Karussell geht vor dem Versand durch den Faktencheck
(`llm.judge_slides`). Datenkarussells haben keine Slide 4 ("Was heisst das
fuer dich?") - ausser Destatis, das die normale Strecke nimmt.

Die Cover-Architektur wird wie immer gezogen (§6.1). Die Vorlagen geben nur
vor, was fuer welche Architektur taugt: `cover_frage` macht 1b moeglich,
`cover_figur` die Zahl fuer 1a, `keine_figur` schliesst 1a aus. Ausnahme:
Personen-Karussells mit Portraet bekommen immer 1g (Portraet auf Farbfeld).

**Logos** (seit 25.09.2026): Parteien, Unternehmen, Verbaende und Vereine
tragen ihr Logo, wo es auf Wikimedia Commons frei lizenziert liegt
(`logos.py`: Handliste `data/logos/logos.json`, sonst Wikidata P154, nur
SVG). Kein Logo - nur der Name, kein Platzhalter. Nachweis in der Caption.

**So-what-Regel** (Abstimmung 25.09.2026): Eine Liste von Namen oder
Kategorien ist kein Befund. Jede Vorlage braucht eine Zahl, einen Vergleich
oder eine Aussage der Beteiligten - sonst gibt die Kategorie `None`.

---

## Tagesablauf

1. Karussell 1: ein beschlossenes Gesetz aus DIP (unveraendert).
2. Karussell 2: eine Kategorie, zufaellig gezogen. Liefert sie nichts, die
   naechste. Liefert DIP nichts, werden zwei Kategorien gebaut.

---

## A. Destatis - die juengste Meldung mit Alltagsbezug

Auswahl: Haiku markiert je Pressemitteilung ja/nein (Alltag: Preise, Mieten,
Loehne, Wohnen, Verkehr, Gesundheit, Familie ...). Die juengste markierte
gewinnt, zwei weitere sind Reserve.

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover | Schlagzeile + Haken | Modell |
| 2 Chart | bis 4 Balken; Zahlen aus der Destatis-Grafik-CSV, sonst aus dem Text; gruen/rot: Haeuserpreise steigend gruen, Verbraucherpreise und Mieten steigend rot | Modell, Zahlen belegt |
| 3 Begriff | "Was ist der Haeuserpreisindex" o. ae.; darunter "Genauer hingeschaut": 2 Punkte mehr Zusammenhang aus der Meldung (Metropolen gegen Land, Gruppen, laengerer Vergleich) statt "Warum ueberhaupt aendern?" | Modell (`llm.STATISTIK_REGEL`) |
| 4 Folgen | eines der Muster 4a-4d | Modell |
| 5 CTA | unveraendert | Fest |

## B. Lobbyregister

### B1. Wer hat zu diesem Gesetz lobbyiert (Standard)

Auswahl: alle beschlossenen Gesetze der letzten 90 Tage, gezaehlt nach
Lobbyregister-Eintraegen, die auf ihre Drucksachen verweisen. Das Gesetz mit
den meisten gewinnt (mindestens 10, jeder Eintrag einzeln geprueft). Jedes
Gesetz nur einmal, nie dasselbe wie Karussell 1.

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover | "Wer beim {Gesetz} mitredete" / "{n} Organisationen haben laut Lobbyregister Lobbyarbeit zu diesem Gesetz gemeldet." / Frage: "Wer hat beim {Gesetz} mitgeredet?" | Daten; Gesetzesname vom Modell, gegen DIP-Text geprueft |
| 2 Chart | "Wer lobbyiert hat, nach Art": Unternehmen, Wirtschaftsverbaende, Berufsverbaende, Vereine/NGOs, Beratung/Kanzleien, Wissenschaft - drei groesste + Sonstige | Daten |
| 3 "Wer was wollte" | ZWEI LAGER, die sich gegenueberstehen (z. B. "Wollen Beitragszahler entlasten" gegen "Wollen hoehere Preise und Verguetungen"), je bis zu zwei Organisationen mit Logo, Name und EIN Satz ("Fordert ...", "Kritisiert ...", max 110 Zeichen, ohne Paragrafen). Sieht das Modell keinen Gegensatz: "Was sie wollten" als einfache Liste mit drei Organisationen. Hinweis: Grenzen des Registers + federfuehrendes Ministerium | Modell aus Regelungsvorhaben-Beschreibung + Stellungnahme-Auszug (bis 8 Kandidaten); Saetze mechanisch belegt, dann Faktencheck gegen denselben Auszug |
| 4 "Was das Gesetz aendert" | Begriffskarte wie DIP Slide 3: zwei Saetze, ein Beispiel (Zahlen nur aus dem Text), darunter "Warum ueberhaupt aendern?" mit zwei Gruenden. Faellt die Belegpruefung durch: Pfeilliste "Worum es ging" | Modell aus dem DIP-Text (`llm.gesetz_karte`), jeder Satz belegt |

Weniger als zwei belegte Positionen: kein Karussell, das naechste Gesetz ist
dran.

Fest: "Im Lobbyregister steht nur, wer Kontakt zu Bundestag oder
Bundesregierung meldet. Nicht jede Einflussnahme ist dort erfasst."

Nie auf der Karte: Betraege je Gesetz. Das Register kennt nur das
Gesamtbudget einer Organisation.

### B2. Drehtuer (wenn B1 nichts findet)

Ehemalige Bundesminister/-innen und Parlamentarische Staatssekretaer/-innen
(Amt beendet), die heute im Lobbyregister stehen. Jede Person einmal.

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover | "Von der Regierungsbank ins Lobbyregister" / "{Name} ist im Lobbyregister fuer {Organisation} eingetragen." / Frage: "Wo ist {Name} heute im Lobbyregister eingetragen?" | Daten |
| 2 Chart | "Im Register mit frueherem Amt": Bundesminister/-innen, Parl. Staatssekretaer/-innen, Bundestagsabgeordnete, Bundesverwaltung - die Gruppe der Person hervorgehoben | Daten (Register-Statistik) |
| 3 "Vom Amt zur Interessenvertretung" | → "{Name} war bis {MM/JJJJ} in der Bundesregierung: {Amt}, {Ressort}." → "Heute ... eingetragen." → Art und Themen der Organisation → Zahl der Regelungsvorhaben → Fest | Daten |

Fest: "Die Angaben im Lobbyregister machen die Eingetragenen selbst."

### B3. Ausgaben-Rangliste (wenn B1 und B2 nichts finden)

Insgesamt, danach je Themenfeld (Gesundheit, Energie, Verteidigung, Umwelt,
Verkehr, Medien und Digitales) - jede Variante einmal je Geschaeftsjahr.

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover | "Die groessten Lobby-Budgets[: Feld]" / "Was Organisationen {Jahr} fuer Lobbyarbeit ausgegeben haben, nach eigener Angabe." | Daten |
| 2 Chart | "Lobbyausgaben {Jahr}", Top 4 in Mio. Euro (Obergrenze der Spanne) | Daten |
| 3 "So liest du die Zahlen" | → Spitzenreiter mit Betrag und Vollzeitstellen → Zahl der Organisationen ueber 1 Mio. → Fest | Daten |

Fest: "Die Betraege melden die Organisationen selbst, als Spanne. Gezeigt ist
die Obergrenze."

## C. Parteispenden

Regel: Gibt es eine Einzelspende ab 100.000 Euro, eingegangen in den letzten
14 Tagen, wird C2 gebaut (die juengste). Sonst C1, hoechstens einmal im Monat.

### C1. Jahresbilanz nach Partei

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover | "{x,x} Mio. €" / "Grossspenden an Parteien {Jahr}" / "{n} Spenden ueber 35.000 Euro seit Januar." | Daten |
| 2 Chart | "Grossspenden {Jahr} nach Partei": fuenf groesste Parteien mit Logo, auf den Euro genau; die uebrigen mit Namen und Summe im Hinweis | Daten |
| 3 "Was dahintersteckt" | Saeulenreihe: Summe der Grossspenden jeweils 1. Januar bis heute, Vorvorjahr / Vorjahr / dieses Jahr. Darunter → groesste Einzelspende (Spendername nur bei Organisationen) und wievielmal so hoch wie der Durchschnitt → Veraenderung zum selben Zeitraum im Vorjahr (und Vorvorjahr), im Wahljahr mit Hinweis auf den Januar → Partei mit den meisten Spenden | Daten |

Kein fester Satz mehr (seit der Saeulenreihe, 25.09.2026 - die Slide war
zu voll).

### C2. Aktuelle Grossspende

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover | "{Betrag} €" / "Grossspende an {die Partei}" / "Von {Spender}, eingegangen am {Datum}." | Daten |
| 2 Chart | "Diese Spende im Vergleich": diese Spende, uebrige Grossspenden an die Partei im Jahr (mit Parteilogo), Durchschnitt aller Grossspenden im Jahr | Daten |
| 3 "Wer ist {Spender}?" - Begriffskarte wie bei DIP, Logo im Badge | → zwei Saetze, was die Organisation ist und macht → fett: fruehere Grossspenden seit {Jahr-2}, Summe, Parteien → "Die Spende einordnen": Rang im Jahr, Vielfaches des Durchschnitts → Fest | Modell (2 Saetze, aus Lobbyregister-Selbstbeschreibung + Wikipedia, belegt) + Daten |

Findet sich zur Organisation nichts (kein Lobbyregister, kein Wikipedia-
Artikel) oder faellt die Belegpruefung durch: Pfeilliste "Wer ist der
Spender?" nur aus Daten. Privatperson: Pfeilliste "Die Spende".

Fest (Privatperson): "Der Spender ist eine Privatperson. Name und Betrag
veroeffentlicht der Bundestag, weil die Spende ueber 35.000 Euro liegt."
Fest (immer): "Spenden ueber 35.000 Euro muessen Parteien sofort dem
Bundestag melden (§ 25 Parteiengesetz)."

Nie: Anschriften (das Bundestagsfeld enthaelt sie, der Code trennt sie ab),
Vermutungen ueber Motive.

## D. Nebentaetigkeiten - eine Person aus dem Backlog

Reihenfolge: `config.POLITIKER_BACKLOG`, niemand zweimal, bevor alle dran
waren; wer in den letzten 14 Tagen neue Meldungen hat, zuerst. Reserve
(`POLITIKER_RESERVE`) rueckt nach.

**Betraege immer mit Zeitraum** ("/ Monat", "/ Jahr", "einmalig", aus
`interval` bzw. "Einkommen im Jahr ..."). Jeder Vergleich - Balkenlaenge,
Ø Bundestag, Rang - rechnet Monatsbetraege x 12; der Hinweis sagt es.

**Nur mit Befund** (25.09.2026): mindestens eine Meldung mit Betrag, ODER
die Zahl verschiedener Taetigkeiten hat sich gegenueber der Wahlperiode
2021-2025 um mindestens 4 und mindestens die Haelfte veraendert. Sonst ist
die naechste Person dran (Spahn: kein Betrag, 8 -> 7 - uebersprungen).

| Slide | Inhalt | Wer |
|---|---|---|
| 1 Cover 1g | Portraet (freigestellt, in Farbe, auf Farbfeld rechts) / "{Name} neben dem Mandat" / Haken: "{Betrag} Euro von {Organisation}: der hoechste Einzelbetrag, den {Nachname} gemeldet hat." bzw. die Aenderung | Daten, Portraet aus data/portraets |
| 2 Chart | Mit mind. 2 Betraegen: "Hoechste gemeldete Betraege", bis 4, je Meldung mit Jahr und Logo, nie addiert. Mit einem Betrag: dieser gegen den Durchschnitt aller Abgeordneten. Ohne Betrag: verschiedene Taetigkeiten 2021-2025 gegen seit 2025 | Daten |
| 3 "Im Vergleich zum Bundestag" | Tabelle "Ø Bundestag" gegen {Nachname}: Meldungen, hoechster Einzelbetrag, alle Betraege zusammen (Betragszeilen nur, wenn die Person Betraege gemeldet hat, die Summe erst ab zwei Betraegen; nie der Anteil der Meldungen mit Betrag). Pills: Platz beim hoechsten Einzelbetrag ("11 von 630"), ggf. Aenderung zur vorigen Wahlperiode. Hinweis: Ø-Definition + Fest | Daten (`sources.neben_statistik`, alle 630 gezaehlt) |

Fest: "Abgeordnete muessen Taetigkeiten neben dem Mandat und Einkuenfte daraus
beim Bundestag melden. Eine Meldung ist kein Vorwurf."
