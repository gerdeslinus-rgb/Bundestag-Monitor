"""Zentrale Konfiguration. Hier stellst du alles ein, ohne Code anzufassen."""

# --- Ausgabe ---------------------------------------------------------------
# Ein Karussell = Hook, Chart, Context, So what, Newsletter (5 Slides).
# Pro Lauf werden CAROUSELS_PER_RUN Stueck gebaut und beide nach Telegram
# geschickt - du waehlst eines aus. Die Rollen sind fest verteilt: eines aus
# DIP (ein beschlossenes Gesetz), eines aus einer WEITERE_KATEGORIEN, zufaellig
# gezogen. Liefert DIP nichts, kommen beide aus zwei verschiedenen Kategorien.
CAROUSELS_PER_RUN = 2
# Ersatzthemen je Quelle, falls eines die Pruefung nicht besteht. Ohne
# Reserve kostet ein einziger Durchfaller der Quelle ihren ganzen Slot: der
# Lauf faellt dann auf eine schwaechere Quelle durch, obwohl noch brauchbare
# Vorgaenge bereitliegen. Ein Ersatz wird NUR bei Ausfall bezahlt - nichts
# kostet, was nicht gebraucht wird.
THEMEN_RESERVE = 2
MAX_ITEMS = 40             # Wie viele Kandidaten maximal ins Themen-Ranking gehen
LOOKBACK_HOURS = 30        # Wie weit zurueck Quellen gelesen werden
TIMEZONE = "Europe/Berlin"
# So lange wartet der Lauf auf deinen Knopfdruck. GitHub startet den Cron oft
# Stunden zu spaet; mit 25 Minuten lief das Fenster ab, bevor du die Karten
# ueberhaupt gesehen hast. Obergrenze ist der Job-Deckel in daily.yml
# (timeout-minutes), der muss darueber liegen.
FREIGABE_MINUTEN = 300

# --- Modelle ---------------------------------------------------------------
# Billiges Modell sortiert vor, teures Modell schreibt nur die Finalisten.
MODEL_RANK = "claude-haiku-4-5-20251001"
MODEL_DRAFT = "claude-sonnet-5"
MODEL_RESEARCH = "claude-sonnet-5"   # Recherche-Call mit Websuche
MODEL_JUDGE = "claude-sonnet-5"      # Faktencheck der So-what-Slide

# --- Verifikation ----------------------------------------------------------
# Wie stark der Beleg-Satz mit dem Quelltext uebereinstimmen muss (0.0 - 1.0).
# 0.82 faengt Halluzinationen, erlaubt aber Whitespace- und Umlaut-Abweichungen.
EVIDENCE_THRESHOLD = 0.82

# Gewertet wird die Summe aller woertlichen Uebereinstimmungen, aber nur
# Bloecke ab dieser Laenge zaehlen mit. Der Wert ist die eigentliche Huerde:
# ohne ihn summieren sich die Fuellwoerter einer freien Paraphrase auf 0.98,
# bei 16 Zeichen bleibt dieselbe Paraphrase bei 0.22. Hoeher setzen macht die
# Pruefung strenger, aber auch empfindlich gegen kurze Belegsaetze.
EVIDENCE_MIN_BLOCK = 16

# --- Volltext ----------------------------------------------------------
# RSS-Teaser sind manchmal zu kurz fuer die Beleg-Pruefung in llm.py.
# Unterhalb dieser Laenge wird der Artikeltext von der Original-Seite
# nachgeladen (hoeflich, mit Timeout, Fehler stoppen den Lauf nicht).
FULLTEXT_MIN_CHARS = 400
FULLTEXT_MAX_CHARS = 24000

# Fuer die AUSGEWAEHLTEN Themen gilt eine hoehere Huerde als beim Einsammeln.
# Grund: die Beleg-Pruefung in llm.verify_slides() matcht den Beleg-Satz gegen
# genau diesen Text. Ein Destatis-Teaser von 636 Zeichen liegt zwar ueber
# FULLTEXT_MIN_CHARS, bricht aber mitten im Satz ab - das Modell schreibt dann
# korrekt ueber die Meldung und faellt trotzdem durch, weil der Beleg im
# Teaser gar nicht vorkommen kann. Nachgeladen wird erst nach der Auswahl,
# also fuer 2 Themen statt fuer 136 - das kostet zwei Seitenaufrufe, keine
# Verlangsamung des Einsammelns.
VOLLTEXT_ZIEL_CHARS = 1500

# Wie viel Quelltext Schreiber UND Faktenpruefer sehen. Bewusst EINE Zahl:
# vorher bekam compose() 4000 Zeichen und judge_slides() nur 3000. Alles in
# diesem Spalt konnte das Modell voellig korrekt verwenden, ohne dass der
# Pruefer es je zu Gesicht bekam - er musste es fuer erfunden halten. Solange
# beide dieselbe Konstante benutzen, kann diese Luecke nicht zurueckkehren.
# 16000 statt frueher 4000, seit DIP-Ausschussberichte dazugekommen sind.
# Gemessen an der Beschlussempfehlung zum antragslosen Kindergeld (21/6979,
# 35.453 Zeichen): im 4000er-Fenster lagen 10 von rund 104 Zahlen des
# Dokuments, und der Anfang ist Drucksachenkopf und "A. Problem". Das Modell
# sollte also eine zahlengetriebene Grafik bauen und sah ein Neuntel des
# Textes - kein Wunder, dass es zu einer erfundenen Zahl griff. Input-Tokens
# sind der billigste Posten im Lauf; das Fenster zu verbreitern kostet
# ungefaehr einen Cent je Aufruf.
PRUEFTEXT_MAX_CHARS = 16000

# Register werden schubweise veroeffentlicht, nicht taeglich: die Nebentaetig-
# keiten bei abgeordnetenwatch kamen zuletzt am 08.-11.09., davor war sechs
# Wochen nichts. Mit LOOKBACK_HOURS = 30 ist die Abfrage an den meisten Tagen
# leer - und damit auch der Profil-Modus, der genau darauf aufbaut. Deshalb
# fuer diese Quellen ein eigenes, deutlich groesseres Fenster.
REGISTER_LOOKBACK_DAYS = 14

# --- Quellen ---------------------------------------------------------------
# Eigenheiten jeder Quelle, gemessen und mit Beispielen: QUELLEN.md.
# Pruefe die Adressen einmal mit `python check_sources.py`, Feeds aendern sich.

# Statistisches Bundesamt: die letzten zehn Pressemitteilungen.
DESTATIS_FEED = "https://www.destatis.de/SiteGlobals/Functions/RSSFeed/DE/RSSNewsfeed/Aktuell.xml"

# Bundestag DIP API (Drucksachen, Vorgaenge, Plenarprotokolle)
DIP_ENABLED = True
DIP_BASE = "https://search.dip.bundestag.de/api/v1"

# Gelesen wird der VORGANG, nicht die einzelne Drucksache. Der Vorgang traegt
# ein redaktionelles "abstract", den Beratungsstand und das Sachgebiet - die
# Drucksachen-Abfrage lieferte dagegen nur Titel, und als Quelltext stand dann
# derselbe Titel noch einmal da. Damit konnte ein DIP-Item die Belegpruefung
# in llm.verify_slides() gar nicht bestehen.
DIP_VORGANGSTYP = "Gesetzgebung"

# Serverseitig filtern spart das Aussortieren im Modell: in einer Woche waren
# 433 von 800 Vorgaengen Schriftliche Fragen und 175 Kleine Anfragen - also
# drei Viertel genau das, was SELECT_PROMPT als "ungeeignet" auflistet.

# Nur entschiedene Vorgaenge. "Abgelehnt" gehoert dazu: dass der Bundestag
# etwas NICHT beschlossen hat, ist genauso eine Nachricht wie das Gegenteil.
#
# Nach dem Bundesrat steht ein Gesetz NICHT mehr auf "Verabschiedet", sondern
# auf einem der beiden Bundesrat-Staende - bis es verkuendet ist. Fehlen die
# hier, faellt jedes Gesetz genau dann heraus, wenn es fertig ist: am
# 25.09.2026 waren das zehn, darunter das antragslose Kindergeld.
DIP_BESCHLOSSEN = {
    "Verkündet", "Verabschiedet", "Angenommen", "Abgelehnt", "Abgeschlossen",
    "Bundesrat hat zugestimmt",
    "Bundesrat hat Vermittlungsausschuss nicht angerufen",
}

# Quellen, deren Items eine bereits gefallene Entscheidung beschreiben.
# Die Themenauswahl bekommt das ausdruecklich vorgelegt, statt es aus der
# Quellenbezeichnung erraten zu muessen: ohne diesen Hinweis hat das Modell
# zweimal hintereinander zwei Antraege gewaehlt, ueber die erst noch
# abgestimmt wird - waehrend neun verabschiedete Gesetze danebenlagen.
#
# "Bundestag, Vorgang ..." ist sicher: fetch_dip() laesst nur Vorgaenge aus
# DIP_BESCHLOSSEN durch. Eine namentliche Abstimmung hat stattgefunden, ein
# Tagesordnungspunkt dagegen steht erst an. "Bundestag, Textarchiv" ebenso:
# fetch_textarchiv() nimmt nur Artikel ueber gefallene Beschluesse.
ENTSCHIEDEN_QUELLEN = (
    "Bundestag, Vorgang ",
    "Bundestag, Textarchiv",
    "namentliche Abstimmung",
)

# --- Textarchiv des Bundestages (QUELLEN.md, Abschnitt 7) --------------------
# Die Parlamentsredaktion berichtet noch am Sitzungstag, was beschlossen
# wurde - DIP traegt den Beratungsstand erst einen Tag oder mehr spaeter
# nach. Und die Artikel nennen das eigentliche Thema: der Tankrabatt vom
# 25.09.2026 hing als Artikel 11-13 an einem Versicherungsgesetz und hiess im
# DIP entsprechend. Beide Adressen sind nicht dokumentiert - sie stammen aus
# der Archivseite selbst. Aendert der Bundestag sie, liefert der Fetcher
# nichts, und der Lauf faehrt mit DIP allein weiter.
TEXTARCHIV_ENABLED = True
TEXTARCHIV_BASIS = "https://www.bundestag.de"
# Neueste zuerst, 20 je Seite; liefert nur die Artikel-IDs.
TEXTARCHIV_LISTE = TEXTARCHIV_BASIS + "/ajax/filterlist/de/dokumente/textarchiv/454772-454772"
# Je Artikel: Ueberschrift, Pfad und der erste Absatz.
TEXTARCHIV_ARTIKEL = (TEXTARCHIV_BASIS
                      + "/blueprint/servlet/ajax/content/de/{id}-{id}/asJsonSliderResult")
# Vier Tage: der Montagslauf sieht noch Donnerstag und Freitag.
TEXTARCHIV_TAGE = 4
# In einer Sitzungswoche erscheinen rund 30 Artikel am Tag.
TEXTARCHIV_MAX_SEITEN = 8

# Gesetze werden in Sitzungswochen beschlossen, nicht gleichmaessig ueber den
# Monat verteilt - ein 30-Stunden-Fenster waere an den meisten Tagen leer.
# Dass dadurch aeltere Beschluesse mitkommen, ist unkritisch: seen.json sorgt
# dafuer, dass jeder Vorgang nur einmal auftaucht.
GESETZE_LOOKBACK_DAYS = 21

# Wie stark der Ankuendigungssatz einer namentlichen Abstimmung mit dem Titel
# des Vorgangs uebereinstimmen muss, damit sie zugeordnet wird. Lieber streng:
# ein falsch zugeordnetes Abstimmungsergebnis behauptet das Gegenteil dessen,
# was passiert ist. Im Zweifel zeigt das Karussell einfach keine Stimmen.
ABSTIMMUNG_ENABLED = True
ABSTIMMUNG_MIN_UEBERLAPPUNG = 0.6
# Namentliche Abstimmungen mit XLSX je Abstimmung, am selben Tag online
# (QUELLEN.md Abschnitt 3, gelesen von stimmen.py).
ABSTIMMUNGSLISTE = ("https://www.bundestag.de/ajax/filterlist/de/parlament/"
                    "plenum/abstimmung/liste/462112-462112")

# Welche Drucksache eines Vorgangs den Quelltext liefert - in dieser
# Reihenfolge. Nicht einfach "die neueste": ein Vorgang enthaelt auch
# Aenderungsantraege einzelner Fraktionen, die gerade NICHT beschlossen
# wurden. Einmal beobachtet: fuer das E-Scooter-Haftungsgesetz war die
# letzte Drucksache ein abgelehnter Aenderungsantrag einer Fraktion - ein
# Karussell daraus haette das Gegenteil des Beschlossenen behauptet.
#
#   Beschlussempfehlung und Bericht - was der Ausschuss geaendert hat und
#       was am Ende angenommen wurde, mit Begruendung. Der beste Quelltext.
#   Gesetzesbeschluss - der amtliche Wortlaut, aber oft nur wenige Zeilen.
#   Gesetzentwurf - ausfuehrlich samt Begruendung, allerdings der Stand VOR
#       den Ausschussaenderungen.
DIP_DRUCKSACHE_REIHENFOLGE = [
    "Beschlussempfehlung und Bericht",
    "Beschlussempfehlung",
    "Gesetzesbeschluss",
    "Gesetzentwurf",
]

# Lobbyregister: Suche des Web-Frontends (kein Key) und API v2 (oeffentlicher
# Key von der Open-Data-Seite; ein eigener Dauerkey per Mail an
# lobbyregister@bundestag.de, dann als LOBBYREGISTER_API_KEY in die .env).
LOBBYREGISTER_URL = "https://www.lobbyregister.bundestag.de/sucheJson"
LOBBYREGISTER_API = "https://api.lobbyregister.bundestag.de/rest/v2"
LOBBYREGISTER_API_KEY = "5bHB2zrUuHR6YdPoZygQhWfg2CBrjUOi"

# Parteispenden ueber 35.000 Euro nach § 25 PartG (HTML-Tabelle je Jahr).
PARTEISPENDEN_URL = "https://www.bundestag.de/parlament/praesidium/parteienfinanzierung/fundstellen50000"

# Nebentaetigkeiten: Quelle sind die veroeffentlichungspflichtigen Angaben
# des Bundestages, abgefragt ueber abgeordnetenwatch (/sidejobs, CC0).
NEBENTAETIGKEITEN_URL = "https://www.abgeordnetenwatch.de/recherchen/nebentaetigkeiten"

# --- Weitere Kategorien (das zweite Karussell) -----------------------------
# Jeden Tag wird eine davon zufaellig gezogen. Liefert sie nichts Brauchbares,
# kommt die naechste dran. Aufbau der Slides je Kategorie: weitere.py.
WEITERE_KATEGORIEN = ["destatis", "lobbyregister", "parteispenden",
                      "nebentaetigkeiten"]

# Lobbyregister: "Wer hat zu diesem Gesetz lobbyiert" braucht mindestens so
# viele Organisationen, sonst ist es keine Geschichte - dann Drehtuer oder
# Ausgaben-Rangliste. Gezaehlt werden nur Eintraege, deren Regelungsvorhaben
# nachweislich auf den Vorgang verweisen (einzeln in der API geprueft).
LOBBY_MIN_ORGANISATIONEN = 10
# Die grossen Gesetze ziehen die meiste Lobbyarbeit an, werden aber nicht jede
# Woche beschlossen: im 21-Tage-Fenster von DIP lag am 25.09.2026 kein Gesetz
# mit mehr als 13 Eintraegen, das Gebaeudemodernisierungsgesetz (61) vom Juli
# war schon draussen. 60 Tage brachten nach der Sommerpause dieselben zehn
# Gesetze, 90 Tage 31. Jedes Gesetz kommt trotzdem nur einmal dran (seen.json).
LOBBY_GESETZE_TAGE = 90
# Drehtuer: nur ehemalige Regierungsmitglieder, keine Mitarbeitenden. Wer das
# Amt noch innehat, sitzt meist kraft Amtes in einem Stiftungsgremium - das
# ist keine Drehtuer.
DREHTUER_FUNKTIONEN = {"MINISTER", "PARLIAMENTARY_STATE_SECRETARY"}
# Ausgaben-Rangliste: erst insgesamt, dann je Themenfeld. Jede Variante
# einmal je Geschaeftsjahr.
LOBBY_RANG_THEMEN = [
    (None, ""),
    ("FOI_HEALTH", "Gesundheit"),
    ("FOI_ENERGY", "Energie"),
    ("FOI_DEFENSE", "Verteidigung"),
    ("FOI_ENVIRONMENT", "Umwelt"),
    ("FOI_TRANSPORTATION", "Verkehr"),
    ("FOI_MEDIA", "Medien und Digitales"),
]

# Parteispenden: eine einzelne Spende ab diesem Betrag, eingegangen in den
# letzten SPENDE_TAGE Tagen, bekommt ein eigenes Karussell. Sonst die
# Jahresbilanz nach Partei (hoechstens einmal im Monat).
SPENDE_GROSS = 100_000
SPENDE_TAGE = 14
# Jahresbilanz: so viele Parteien als Balken, der Rest steht im Hinweis.
SPENDEN_JAHR_BALKEN = 5

# Lobby zu einem Gesetz: so viele Organisationen mit ihrer Position auf der
# Slide "Was sie wollten". Weniger als LOBBY_POSITIONEN_MIN belegte
# Positionen - dann ist es kein Karussell, das naechste Gesetz ist dran.
LOBBY_POSITIONEN = 3
LOBBY_POSITIONEN_MIN = 2
# Mit zwei Lagern: so viele Kandidaten gehen ans Modell, und hoechstens so
# viele Organisationen stehen je Lager auf der Slide.
LOBBY_KANDIDATEN = 8
LOBBY_JE_LAGER = 2
# Auszug je Stellungnahme fuer Modell UND Faktencheck (derselbe Text).
LOBBY_AUSZUG = 2800

# Nebentaetigkeiten: diese Abgeordneten der Reihe nach, keiner zweimal, bevor
# alle dran waren. Wer in den letzten REGISTER_LOOKBACK_DAYS Tagen neue
# Meldungen hat, kommt zuerst. Die Reserve rueckt nach, wenn jemand kein
# aktuelles Mandat mehr hat oder zu wenig gemeldet ist.
POLITIKER_BACKLOG = [
    "Friedrich Merz", "Jens Spahn", "Armin Laschet", "Norbert Röttgen",
    "Carsten Linnemann", "Lars Klingbeil", "Bärbel Bas", "Matthias Miersch",
    "Alice Weidel", "Tino Chrupalla", "Beatrix von Storch", "Omid Nouripour",
    "Ricarda Lang", "Gregor Gysi", "Heidi Reichinnek",
]
# Ein Personen-Karussell braucht einen Befund (Abstimmung 25.09.2026): einen
# gemeldeten Betrag, ODER eine deutliche Aenderung der Zahl verschiedener
# Taetigkeiten gegenueber der vorigen Wahlperiode - mindestens so viele und
# mindestens um die Haelfte. Sonst ist es eine Liste ohne Aussage.
NEBEN_AENDERUNG_MIN = 4
NEBEN_AENDERUNG_ANTEIL = 0.5
# Vorige Wahlperiode bei abgeordnetenwatch (Bundestag 2021 - 2025).
NEBEN_PERIODE_VORHER = 132
# Vergleichsbasis "Ø Bundestag": alle Sitze, auch wer nichts gemeldet hat.
ABGEORDNETE = 630

POLITIKER_RESERVE = ["Julia Klöckner", "Saskia Esken", "Stephan Brandner",
                     "Britta Haßelmann", "Sören Pellmann"]

# Kategorien der Nebentaetigkeiten, wie die Bundestagsverwaltung sie fuehrt
# (Codes laut abgeordnetenwatch-Doku). Links die amtliche Bezeichnung, rechts
# die kurze fuer den Balken.
NEBEN_KATEGORIEN = {
    "29647": ("Entgeltliche Tätigkeiten neben dem Mandat", "Bezahlte Tätigkeiten"),
    "29228": ("Funktionen in Unternehmen", "Funktionen in Unternehmen"),
    "29229": ("Funktionen in Körperschaften und Anstalten des öffentlichen Rechts",
              "Öffentliche Einrichtungen"),
    "29230": ("Funktionen in Vereinen, Verbänden und Stiftungen",
              "Vereine und Stiftungen"),
    "29231": ("Beteiligung an Kapital- oder Personengesellschaften", "Beteiligungen"),
    "29232": ("Spenden/Zuwendungen für politische Tätigkeit", "Spenden, Zuwendungen"),
    "29233": ("Vereinbarungen über künftige Tätigkeiten oder Vermögensvorteile",
              "Vereinbarungen"),
    "29234": ("Berufliche Tätigkeit vor der Mitgliedschaft im Deutschen Bundestag",
              "Beruf vor dem Mandat"),
}

# --- Recherche (Websuche fuer Context- und So-what-Slide) ------------------
# Das Modell darf ueber unsere amtlichen Quellen hinaus recherchieren, aber
# nur auf dieser Allowlist. Haelt Meinungsseiten und Muell raus - und ist die
# zweite Verteidigungslinie gegen Prompt-Injection aus fremden Webseiten
# (die erste ist die unveraenderte Belegpflicht in llm.verify_slides).
#
# Arbeitsteilung: Die harten Fakten (Beschluss, Zahlen, Abstimmung) kommen
# aus unseren amtlichen Quellen und werden woertlich geprueft. Die Recherche
# liefert nur ERKLAERENDEN Hintergrund ("Was ist ein Freibetrag?") - dafuer
# gibt es keinen woertlichen Beleg-Satz und deshalb keine Beleg-Pruefung,
# sondern den KI-Faktencheck in llm.judge_slides(). Jede recherchierte Zahl
# traegt ihre Fundstelle mit und landet in der Telegram-Pruefliste.
#
# Ebenfalls wichtig: Steht hier eine Domain, die den Anthropic-Crawler
# aussperrt, antwortet die API mit 400 und der GANZE Lauf scheitert. Die
# grossen Nachrichtenseiten (tagesschau.de, zeit.de, sueddeutsche.de,
# faz.net, spiegel.de, deutschlandfunk.de, br.de, wdr.de, ndr.de) sind
# genau deshalb NICHT in der Liste - alle getestet, alle gesperrt.
# --- Aufwand pro Aufruf -----------------------------------------------------
# Sonnet 5 denkt von sich aus mit (adaptive thinking, effort "high"), wenn man
# nichts angibt - das ist der groesste Zeit- und Output-Token-Posten im Lauf.
# Fuers Schreiben ist das richtig, fuer die mechanischen Schritte nicht:
# judge_slides() beantwortet eine Ja/Nein-Frage und gibt {"ok": ...} zurueck.
EFFORT_JUDGE = "low"
# Budget fuer den Schreibschritt. Das Modell denkt erst nach und schreibt dann
# das komplette JSON - reicht das Budget nicht, bricht die Antwort mitten im
# JSON ab und das Thema faellt still aus dem Lauf ("unvollstaendiges JSON").
# Mit den Feldern begriff und folgen ist der Entwurf laenger geworden; 12000
# hat dafuer nicht mehr gereicht.
DRAFT_MAX_TOKENS = 24000
# Lobby-Positionen, Gesetzeskarte, Spenderportraet: kurze JSON-Antworten,
# aber das Modell denkt vorher nach. Mit 1.200 kam bei acht Kandidaten gar
# kein Textblock zurueck ("keine Textantwort", 25.09.2026).
DATEN_MAX_TOKENS = 8000

JUDGE_MAX_TOKENS = 2000

RESEARCH_ENABLED = True
# Kostentreiber: jede Suche haengt ihre Treffer an den Kontext, und jeder
# Tool-Durchgang schickt den ganzen Kontext erneut. Gemessen: 5 erlaubte
# Suchen -> ~65.000 Input-Tokens -> rund 0,20 $ pro Recherche.
#
# Stand 16.09.2026: 3 statt 5 - zusammen mit zwei anderen Aenderungen, die
# den Suchbedarf ueberhaupt erst senken:
#
#  - Die Recherche sah bisher nur 3.000 Zeichen des Quelltextes. Beim
#    Ausschussbericht zum antragslosen Kindergeld (24.000 Zeichen) lagen
#    "B. Loesung", "D. Haushaltsausgaben" und "E. Erfuellungsaufwand"
#    ausserhalb dieses Fensters - also genau die Abschnitte mit den Kosten
#    und Zahlen. Das Modell suchte im Netz nach Angaben, die im Dokument
#    standen, das es gerade in der Hand hatte.
#  - Der Prompt sagt jetzt ausdruecklich, dass nur gesucht werden soll, was
#    im Quelltext fehlt - und dass gar keine Suche richtig ist, wenn er
#    schon alles hergibt.
#
# Die Obergrenze ist damit eher Sicherheitsnetz als Arbeitsanweisung.
RESEARCH_QUELLTEXT_CHARS = 10000
RESEARCH_MAX_SEARCHES = 3

# Kaufkraft-Vergleich: was ein historischer Betrag heute ungefaehr wert waere.
# Pauschale Annahme, keine Messung - und genau so steht sie auch auf der
# Karte. Der Versuch, den Wert zu recherchieren, ist einmal gelaufen und hat
# nur das Suchbudget verbrannt, ohne ein Ergebnis zu liefern.
#
# 2 Prozent sind das Ziel der EZB und liegen nahe am langfristigen deutschen
# Mittel. Fuer einzelne Jahrzehnte trifft das nicht zu - die Zahl ist eine
# Groessenordnung und darf nie als amtlicher Wert beschriftet werden.
KAUFKRAFT_INFLATION = 0.02

# Recherche ist Nachschlagen und Zusammenfassen, kein schweres Nachdenken -
# anders als das Schreiben, das auf "high" bleibt.
EFFORT_RESEARCH = "medium"        # max_uses pro Thema
RESEARCH_DOMAINS = [
    "bundestag.de", "bundesregierung.de", "destatis.de", "bundesbank.de",
    "bundesrat.de", "bundesfinanzministerium.de", "bmas.de", "bmwk.de",
    "gesetze-im-internet.de", "bundesanzeiger.de", "abgeordnetenwatch.de",
    "handelsblatt.com",
]

# --- Karussell -------------------------------------------------------------
# Balkendiagramm: zu wenige Balken sind langweilig, zu viele unlesbar.
CHART_MIN_BARS = 2
CHART_MAX_BARS = 4

# Laufende Wahlperiode. Steht laut Design-System im Fuss jeder Abstimmungs-
# Slide: eine Sitzverteilung ohne Wahlperiode ist nicht nachpruefbar.
WAHLPERIODE = 21

# --- Sitzverteilung --------------------------------------------------------
# Der 21. Bundestag, in echter Kammerreihenfolge von links nach rechts. Summe
# 630 - das ist die Zahl, die der Sitzbogen zeichnet. Die FDP hat kein Mandat
# und darf hier nicht auftauchen; wer das Roster anfasst, aendert damit jede
# Abstimmungs-Slide, also bitte gegen die amtliche Sitzverteilung pruefen.
#
# Stand 25.09.2026 laut Abstimmungsliste des Bundestages (XLSX der
# namentlichen Abstimmung zum Tankrabatt): AfD 150, dazu 3 Fraktionslose -
# Stefan Seidler (SSW) sowie Sieghard Knodel und Jan Wenzel Schmidt (beide
# frueher AfD). Vorher standen hier 152 AfD-Sitze, der Bogen zeigte damit zwei
# leere AfD-Punkte zu viel. Fraktionslose sitzen rechts aussen neben der AfD.
#
# Die Farben sind die einzige Stelle im Deck, an der Parteifarben erlaubt
# sind (Design-System §1). Nie fuer Text, Karten oder Flaechen verwenden.
BUNDESTAG_SITZE = [
    {"key": "Linke",   "name": "Linke",    "sitze": 64,  "farbe": "#BE3075"},
    {"key": "SSW",     "name": "SSW",      "sitze": 1,   "farbe": "#003C8F"},
    {"key": "Gruene",  "name": "Grüne",    "sitze": 85,  "farbe": "#409A3C"},
    {"key": "SPD",     "name": "SPD",      "sitze": 120, "farbe": "#E3000F"},
    {"key": "CDU/CSU", "name": "CDU/CSU",  "sitze": 208, "farbe": "#151B20"},
    {"key": "AfD",     "name": "AfD",      "sitze": 150, "farbe": "#009EE0"},
    {"key": "Fraktionslos", "name": "Fraktionslos", "sitze": 2, "farbe": "#8A9199"},
]

# Schreibweisen aus den Plenarprotokollen (siehe abstimmung.FRAKTIONEN) auf die
# Roster-Schluessel. Seit 26.09.2026 haben auch die Fraktionslosen Sitze im
# Roster; der SSW-Abgeordnete steht in Listen und Protokoll ebenfalls unter
# "Fraktionslos" und wird in stimmen.py per Name zugeordnet.
FRAKTION_ALIAS = {
    "CDU/CSU": "CDU/CSU",
    "SPD": "SPD",
    "AfD": "AfD",
    "BÜNDNIS 90/DIE GRÜNEN": "Gruene",
    "BÜNDNIS 90/ DIE GRÜNEN": "Gruene",
    "Die Linke": "Linke",
    "DIE LINKE": "Linke",
    "Linke": "Linke",
    "Gruene": "Gruene",
    "SSW": "SSW",
    "Fraktionslos": "Fraktionslos",
    "Fraktionslose": "Fraktionslos",
}

# Mindestlaenge des Quelltexts, damit ein Thema ueberhaupt in die (teure)
# Recherche geht - siehe llm.quelltext_tragfaehig(). Teaser-Schnipsel aus
# Aggregator-Feeds scheitern sonst erst nach der Recherche an der Belegpflicht.
# Bewusst niedrig: die eigentliche Unterscheidung macht die Satzzaehlung,
# nicht die Laenge. Kurze, aber echte Pressemitteilungen sollen durchkommen.
MIN_QUELLTEXT_CHARS = 200

# --- Bild auf der Cover-Slide ----------------------------------------------
# Stockfoto von Pexels, nur auf Slide 1, nur wenn ein Thema unten wirklich
# trifft. Braucht PEXELS_API_KEY in der .env (kostenlos, 200 Abfragen/Stunde).
# Ohne Key oder ohne Treffer bleibt das Cover rein typografisch - das ist der
# Normalfall, kein Fehler.
BILDER_ENABLED = True
BILDER_TIMEOUT = 20
BILDER_MIN_BREITE = 1200     # schmaler skaliert auf 928 px Kartenbreite sichtbar

# Die Suchphrase wird NICHT aus der Meldung gebaut, sondern steht hier fest.
# So kann die Suche nur Motive liefern, die du einmal freigegeben hast.
# Reihenfolge = Rangfolge: das erste passende Thema gewinnt, deshalb stehen
# die spezifischen oben und das allgemeine Parlamentsmotiv unten.
# Absichtlich Orte und Gegenstaende statt Personen - siehe bilder.py.
BILDER_THEMEN = [
    # Gesucht wird mit STAEMMEN, nicht mit ganzen Woertern: deutsche
    # Ueberschriften bauen Komposita, und "miete" findet die "Mietpreis-
    # bremse" nicht. Alles in Umschrift, ohne Umlaute - bilder.py bringt den
    # Text in dieselbe Form.
    #
    # "nicht" ist die Gegenprobe zu einem Stamm, der in einem anderen Wort
    # steckt. Lieber kein Bild als das falsche: ein Spielplatz neben einer
    # Meldung ueber Kinderarmut ist schlimmer als eine rein typografische
    # Karte.
    {"thema": "steuern",
     "woerter": ["steuer", "freibetrag", "pauschale", "abgabe", "soli",
                 "umsatzsteuer", "einkommensteuer"],
     "nicht": ["steuerung", "gesteuert", "steuerrad"],
     "suche": "Steuerbescheid Schreibtisch Kugelschreiber"},
    {"thema": "rente",
     "woerter": ["rente", "rentner", "pension", "altersvorsorge", "ruhestand",
                 "erwerbsminderung"],
     "nicht": ["rentabel", "rentabilitaet"],
     "suche": "aeltere Haende Spardose Ruhestand"},
    {"thema": "arbeit",
     "woerter": ["lohn", "gehalt", "arbeitsmarkt", "beschaeftig", "arbeitslos",
                 "tarif", "buergergeld", "kurzarbeit", "beitragsbemessung",
                 "arbeitnehmer", "arbeitgeber"],
     "nicht": ["belohn", "lohnt", "lohnend"],
     "suche": "Baustelle Werkstatt Arbeitskleidung"},
    {"thema": "wohnen",
     "woerter": ["miet", "wohn", "immobilie", "neubau", "wohnungsbau",
                 "bauland", "bauantrag", "bauministeri", "grundstueck"],
     # "vermiet" und "vermieter": das E-Scooter-Haftungsgesetz handelt vom
     # Vermieter der Roller, und "miet" traf mitten in dieses Wort. Das
     # Cover bekam daraufhin ein Foto von Wohnbloecken.
     "nicht": ["gewohnheit", "gewohnt", "mietwagen", "vermiet", "vermieter"],
     "suche": "Wohnblock Fassade Deutschland"},
    # Eigenes Thema statt eines Stichworts bei "verkehr": dessen Suchbegriff
    # ist ein Regionalzug, und ein Zugfoto ueber einer E-Scooter-Meldung ist
    # nur unauffaelliger falsch als das Wohnblock-Foto davor.
    {"thema": "mikromobilitaet",
     "woerter": ["e-scooter", "escooter", "e-tretroller", "tretroller",
                 "elektrokleinstfahrzeug", "elektrokleinst", "leihroller",
                 "mikromobil"],
     "suche": "E-Scooter Gehweg Strasse Stadt"},
    {"thema": "energie",
     "woerter": ["strom", "energie", "gaspreis", "gasnetz", "erdgas",
                 "gasspeicher", "heiz", "netzentgelt", "waermepumpe",
                 "kilowattstunde"],
     "nicht": ["stroemung"],
     "suche": "Stromzaehler Hochspannungsmast"},
    # Eigenes Thema, nicht nur Stichworte im Verkehr: eine Meldung ueber
    # Ladesaeulen bekam sonst einen Regionalzug.
    {"thema": "elektromobilitaet",
     "woerter": ["ladesaeule", "ladeinfrastruktur", "e-auto", "elektroauto",
                 "ladepunkt", "elektromobil"],
     "suche": "Ladesaeule Elektroauto Parkplatz"},
    {"thema": "verkehr",
     "woerter": ["pendler", "bahn", "nahverkehr", "maut", "verkehr",
                 "deutschlandticket", "kilometer", "tempolimit",
                 "fuehrerschein"],
     "nicht": ["bahnbrechend", "laufbahn"],
     "suche": "Regionalzug Bahnsteig Deutschland"},
    {"thema": "gesundheit",
     "woerter": ["kranken", "pflege", "gesundheit", "klinik", "arznei",
                 "apotheke", "krankenkasse", "zuzahlung"],
     "suche": "Krankenhausflur leer"},
    {"thema": "familie",
     "woerter": ["kindergeld", "elterngeld", "familie", "kita", "kinder",
                 "unterhaltsvorschuss", "mutterschutz"],
     "nicht": ["kinderarmut", "kindeswohl", "missbrauch"],
     "suche": "Spielplatz Schaukel leer"},
    {"thema": "bildung",
     "woerter": ["schul", "bafoeg", "studium", "studier", "ausbildung",
                 "hochschul", "lehrer", "azubi"],
     "nicht": ["schulden", "verschuld"],
     "suche": "leerer Klassenraum Tafel"},
    {"thema": "haushalt",
     "woerter": ["haushalt", "schulden", "etat", "milliarden", "inflation",
                 "preise", "sondervermoegen"],
     "nicht": ["haushaltsgeraet"],
     "suche": "Euro Muenzen Geldscheine"},
    {"thema": "landwirtschaft",
     "woerter": ["landwirt", "bauern", "agrar", "ernte", "lebensmittel",
                 "tierhaltung"],
     "suche": "Getreidefeld Traktor"},
    {"thema": "klima",
     "woerter": ["klima", "co2", "emission", "umwelt", "waerme", "solar",
                 "windkraft"],
     "suche": "Windraeder Feld Deutschland"},
    {"thema": "digital",
     "woerter": ["digital", "daten", "internet", "cyber", "breitband",
                 "kuenstliche intelligenz"],
     "suche": "Serverraum Netzwerkkabel"},
    # Allgemeiner Rueckfall fuer reine Verfahrensmeldungen. Zaehlt halb,
    # damit jedes echte Sachthema ihn schlaegt.
    {"thema": "parlament",
     "rueckfall": True,
     "woerter": ["bundestag", "bundesrat", "gesetz", "kabinett", "abstimmung",
                 "ausschuss", "verordnung", "drucksache"],
     "suche": "Reichstagsgebaeude Berlin Architektur"},
]

# Letzte Slide, rein statisch - kein Modell, keine Belegpflicht.
# Keine Gedankenstriche: das Design-System laesst als Satzzeichen nur
# Doppelpunkt, Komma und Punkt zu.
CTA_HEADLINE = "Einordnung statt\nSchlagzeile."
CTA_BODY = "Jeden zweiten Tag ein Beschluss, der dich betrifft: mit Quelle und Rechenweg."
CTA_ACTION = "Newsletter abonnieren. Link in Bio"

# --- Vorfilter (laeuft ohne Modell, spart 80-90 % der Kosten) ---------------
# Nur Items, die mindestens einen Begriff enthalten, gehen ins Modell.
KEYWORDS = [
    "gesetz", "beschluss", "kabinett", "bundestag", "bundesrat", "verordnung",
    "haushalt", "urteil", "reform", "statistik", "prozent", "milliarden",
    "millionen", "koalition", "abstimmung", "entwurf", "richtlinie", "quote",
    "spende", "lobbyregister", "tagesordnung", "plenarprotokoll",
    "abweichler", "nebentaetigkeit", "nebeneinkuenfte", "ausschuss",
]

# Items mit diesen Begriffen werden verworfen (Termine, Grussworte, PR).
BLOCKLIST = [
    "grusswort", "grußwort", "terminhinweis", "einladung zur", "bildergalerie",
    "podcast", "stellenausschreibung", "nachruf",
]
