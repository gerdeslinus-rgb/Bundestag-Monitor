# Politik-Tagesueberblick

Taeglicher, quellenbelegter Kurzueberblick zur deutschen Politik fuer Instagram.

**Ablauf:** Amtliche Quellen -> deterministischer Vorfilter -> Modell schreibt ->
Code prueft die Belege -> zwei fertige Karussells kommen per Telegram ->
**du waehlst eines aus** -> es geht auf Instagram.

Es wird nichts ohne deine Entscheidung veroeffentlicht. Das ist Absicht: der
Freigabeschritt erfuellt die redaktionelle Kontrolle nach Art. 50 Abs. 4 KI-VO
und die Sorgfaltspflicht nach § 19 MStV.

Automatisiert ist nur die Handarbeit danach - Bilder ablegen, hochladen,
Bildtext setzen. Die Auswahl selbst bleibt ein Knopfdruck von dir: Telegram
fragt "Option 1, Option 2 oder keine", und **ohne Antwort passiert nichts**.
Der Ausfall der Freigabe fuehrt nie zu einem Post, sondern immer nur zu keinem.

## Start

Siehe **SETUP.md**. Phase 0 (zwei Wochen von Hand) nicht ueberspringen.

## Dateien

| Datei | Zweck |
|---|---|
| `config.py` | Alle Einstellungen: Quellen, Keywords, Modelle |
| `check_sources.py` | Prueft einmalig, ob die Feeds erreichbar sind |
| `sources.py` | Holt Bundestag-DIP und -Textarchiv, Destatis, dedupliziert, vorfiltert |
| `QUELLEN.md` | Jede Quelle: Zugang, Eigenheiten, Fallstricke, offene Fragen |
| `weitere.py` | Das zweite Karussell: Destatis, Lobbyregister, Parteispenden, Nebentaetigkeiten |
| `VORLAGEN.md` | Slide-Vorlagen dieser vier Kategorien, mit allen festen Saetzen |
| `llm.py` | Ranking, Entwurf, Beleg-Verifikation |
| `render.py` | Baut die 1080x1350-Karten |
| `DESIGN-SYSTEM.md` | Die Spec, die `templates/card.html` umsetzt |
| `sitzbogen.py` | Sitzbogen (630 Punkte) fuer namentliche Abstimmungen |
| `preview_design.py` | Rendert jede Slide-Variante ohne Modell und ohne Netz |
| `debug_lauf.py` | Der Tageslauf in einzelnen Stufen, zur Fehlersuche |
| `tests/` | Prueft die Belegmaschinerie, ohne Modell und ohne Netz |
| `notify.py` | Schickt alles per Telegram und holt deine Freigabe |
| `ablage.py` | Legt die freigegebenen Karten fuer Instagram oeffentlich ab |
| `instagram.py` | Laedt das freigegebene Karussell hoch |
| `run.py` | Startet den Tageslauf |
| `impressum.html` | Vorlage fuer GitHub Pages |

## Pruefen

    python tests/alle.py

Laeuft in Sekunden, kostet nichts und braucht kein Netz. Geprueft wird die
Maschinerie hinter der Belegpflicht: Umlaut-Reparatur, Belegquote,
Satzzerlegung, nachgerechnete Zahlen, Kaufkraft.

Das sind die Stellen, an denen ein Fehler nicht auffaellt, sondern still
eine falsche Karte erzeugt - eine zu gierige Umlaut-Regel macht aus
"Steuer" ein "Steür", und die Belegquote laesst einen echten Quellsatz mit
einer ausgetauschten Ziffer mit 0.99 durch, wenn die Zahlenpruefung daneben
fehlt. Wer an `llm.py` etwas aendert, sollte das hier vorher und nachher
laufen lassen.

    python tests/pruefe_trennung.py

Separat, weil es Playwright und die Webschriften braucht: rendert typische
Schlagzeilen in Cover-Groesse und prueft, dass keine ueber drei Zeilen geht.
