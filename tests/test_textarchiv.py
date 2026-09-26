"""Prueft das Textarchiv des Bundestages als Quelle - die Stellen, an denen
es still falsch laeuft: welcher Artikel als Beschluss zaehlt, wo der
Artikeltext anfaengt und aufhoert, und dass dasselbe Gesetz aus DIP und
Textarchiv nur einmal in die Auswahl geht.

Kein Netz, kein Modell. Die Faelle stammen aus der Sitzungswoche vom
23. bis 25.09.2026 - der Woche, in der der Tankrabatt als Anhang eines
Versicherungsgesetzes beschlossen wurde und im DIP nicht zu finden war.
"""
import os
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
os.chdir(WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
import llm
import render
import sources

fehler = 0


def pruefe(name, ist, soll):
    global fehler
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist!r}" + ("" if ok else f" (soll {soll!r})"))


print("Beschluss oder nicht (Ueberschrift + erster Absatz):")
FAELLE = [
    ("Bundestag beschließt Tankrabatt und ändert das Versicherungsrecht",
     "Der Bundestag hat am Freitag, 25. September 2026, nach halbstündiger "
     "Aussprache den Tankrabatt für den Zeitraum vom 1. Oktober bis 31. Dezember "
     "2026 beschlossen. Damit sinkt die Energiesteuer auf Benzin und Diesel um "
     "14,04 Cent pro Liter. Für die entsprechende Änderung des "
     "Energiesteuergesetzes votierten 434 Abgeordnete.", True),
    ("Modernisierung des Bundespolizeigesetzes in dritter Beratung beschlossen",
     "Zu Beginn der Plenarsitzung am Freitag, 25. September 2026, hat der "
     "Bundestag ohne Aussprache in dritter Beratung den Gesetzentwurf der "
     "Bundesregierung angenommen.", True),
    ("Bundestag modernisiert das Designrecht",
     "Der Bundestag hat am Donnerstag, 24. September 2026, den Gesetzentwurf der "
     "Bundesregierung zur Modernisierung des Designrechts angenommen.", True),
    # Abgelehnter Gesetzentwurf: auch eine Entscheidung, wie bei DIP.
    ("Keine Ächtung von Boykottmaßnahmen durch Nichtregierungsorganisationen",
     "Der Bundestag hat am Donnerstag, 24. September 2026, nach 20-minütiger "
     "Aussprache den Gesetzentwurf der AfD-Fraktion (21/4933) mit den Stimmen "
     "aller übrigen Fraktionen abgelehnt.", True),
    # Abgelehnter ANTRAG: gibt es dutzendfach - kein Thema. "Gesetze und
    # Verordnungen" im Zitat darf ihn nicht zum Gesetz machen.
    ("Bundestag lehnt Vorlage zur Senkung der Energiekosten ab",
     "Der Bundestag hat am Donnerstag, 24. September 2026, die Forderung der "
     "AfD-Fraktion nach Beendigung aller deutschen Klimaschutzmaßnahmen "
     "abgewiesen. Ihr Antrag (21/5322) war mit der Mehrheit abgelehnt worden. "
     "Darin hatte die Fraktion darauf gedrungen, alle Gesetze und "
     "Verordnungen aufzuheben.", False),
    ("Anträge zur Wohnungspolitik abgelehnt",
     "Der Bundestag hat am Mittwoch, 23. September 2026, zwei Anträge der "
     "Linken abgelehnt.", False),
    # Erste Lesung: debattiert, ueberwiesen - nichts entschieden.
    ("Einführung einer Frühstartrente für Sechs- bis Achtzehnjährige beraten",
     "Der Bundestag hat am Freitag, 25. September 2026, in erster Lesung den "
     "Gesetzentwurf der Bundesregierung zur Einführung einer Frühstartrente "
     "debattiert und an den Finanzausschuss überwiesen.", False),
    # Erste Lesung, in der nebenbei ein Antrag abgelehnt wird: bleibt draussen.
    ("Gesetzentwurf zur Reform des Nachrichtendienstrechts beraten",
     "Der Bundestag hat am Donnerstag, 24. September 2026, in erster Lesung "
     "den Gesetzentwurf beraten. Einen Antrag der AfD lehnte er ab.", False),
    ("Abgesetzt: Maßnahmen zur Bekämpfung von linksextremer Gewalt",
     "Der Bundestag hat die Beratung zweier AfD-Anträge von der Tagesordnung "
     "abgesetzt. Ein Gesetz wurde nicht beschlossen.", False),
]
for titel, teaser, soll in FAELLE:
    pruefe(titel[:60], sources.ta_beschluss(titel, teaser), soll)

print("\nText aus dem HTML:")
pruefe("Datum ohne Leerzeichen vor dem Komma",
       sources._ta_glatt("am <strong>Freitag, 25. September 2026</strong>, nach"),
       "am Freitag, 25. September 2026, nach")
pruefe("bedingter Trennstrich weg", sources._ta_glatt("Tank&shy;rabatt"), "Tankrabatt")
pruefe("Linkhinweis weg",
       sources._ta_glatt("(21/6561<span>(Dokument, öffnet ein neues Fenster)</span>)"),
       "(21/6561)")
pruefe("Datum aus dem Anriss",
       sources._ta_datum("Der Bundestag hat am Freitag, 25. September 2026, ..."),
       sources.date(2026, 9, 25))
pruefe("kein Datum", sources._ta_datum("Ohne Datum"), None)
pruefe("Drucksachen",
       sources._TA_DRUCKSACHE.findall("VSAAG, 21/6561, 21/8162) ... (21/8195) 2026/27"),
       ["21/6561", "21/8162", "21/8195"])

print("\nArtikelgrenzen auf der Seite:")
SEITE = """<html><head><meta name="description" content="Der Bundestag hat am Freitag
beschlossen"></head><body><nav><p>Menue</p></nav>
<p>Verwandter Artikel: Der Bundestag hat am Mittwoch etwas anderes getan.</p>
<p>Der Bundestag hat am <strong>Freitag, 25. September 2026</strong>, den Tankrabatt beschlossen.</p>
<h3>Abstimmung</h3>
<p>Dafür stimmten 434 Abgeordnete. (hle/vom/25.09.2026)</p>
<p>Reden zu diesem Tagesordnungspunkt</p><p>Ortleb, Josephine</p>
</body></html>"""


class _Antwort:
    text = SEITE

    def raise_for_status(self):
        pass


_get = sources.requests.get
sources.requests.get = lambda *a, **k: _Antwort()
try:
    anriss = "Der Bundestag hat am Freitag, 25. September 2026, den Tankrabatt beschlossen."
    pruefe("vom Anriss bis zum Kuerzel",
           sources._ta_volltext("https://x", anriss),
           "Der Bundestag hat am Freitag, 25. September 2026, den Tankrabatt "
           "beschlossen. Abstimmung Dafür stimmten 434 Abgeordnete. (hle/vom/25.09.2026)")
    # Ohne Kuerzel keine sichere Grenze: dann lieber nur der Anriss als die
    # Rednerliste im Quelltext.
    _Antwort.text = SEITE.replace(" (hle/vom/25.09.2026)", "")
    pruefe("ohne Kuerzel der Anriss", sources._ta_volltext("https://x", anriss), anriss)
finally:
    sources.requests.get = _get

print("\nEin Gesetz, eine Stelle in der Auswahl:")
dip = [{"id": "a", "title": "Gesetz zur Umsetzung der Richtlinien (EU) 2025/1 ..."},
       {"id": "b", "title": "Drittes Gesetz zur Änderung des Seelotsgesetzes"}]
archiv = [{"id": "a", "title": "Bundestag beschließt Tankrabatt"}]
pruefe("Textarchiv ersetzt DIP bei gleicher ID",
       [it["title"][:20] for it in sources.mit_textarchiv(archiv, dip)],
       ["Bundestag beschließt", "Drittes Gesetz zur Ä"])

print("\nEntschieden-Kennzeichnung und Bildtext:")
item = {"source": "Bundestag, Textarchiv vom 25.09.2026"}
pruefe("zaehlt als entschieden", llm._entschieden(item), True)
pruefe("Verfahrensstand bekannt",
       llm.verfahrensstand(item).startswith("Der Quelltext ist der Bericht"), True)
pruefe("Bildtext-Quelle", render._caption_quelle(item["source"]), "Deutscher Bundestag")

print(f"\n{fehler} Fehler" if fehler else "\nalle Faelle bestanden")
sys.exit(1 if fehler else 0)
