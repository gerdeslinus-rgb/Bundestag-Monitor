"""Prueft die Aenderungen nach der Tankrabatt-Durchsicht vom 26.09.2026.

Kein Netz, kein Modell. Jeder Block steht fuer einen Punkt der Durchsicht:

- Hauptwort statt letztem Wort im Highlight ("pro Liter" statt "Tankrabatt").
- Slide 3 erklaert das Hauptwort ("Energiesteuer" statt "Tankrabatt").
- Sitzbogen am Sitzungstag: namentlich aus der XLSX, sonst Handzeichen.
- "Was fruehere Faelle zeigen" nur mit gepruefter Fundstelle.
- Tausendertrenner als Leerzeichen ("682 000", Wohngeld).
"""
import io
import os
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
os.chdir(WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
import llm
import render
import research
import sitzbogen
import sources
import stimmen

fehler = 0


def pruefe(name, ist, soll):
    global fehler
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist!r}" + ("" if ok else f" (soll {soll!r})"))


print("Hauptwort im Highlight:")
render._SCHLUESSEL[:] = ["Tankrabatt"]
pruefe("Hauptwort vorn", render._block("Tankrabatt: Ab Oktober 17 Cent weniger pro Liter"),
       '<span class="hl">Tankrabatt</span>: Ab Oktober 17 Cent weniger pro Liter')
pruefe("Cover auf Ink", render._cover_headline("Der Tankrabatt kommt"),
       'Der <span class="accent">Tankrabatt</span> kommt')
pruefe("gross/klein egal", render._block("Was ist der TANKRABATT"),
       'Was ist der <span class="hl">TANKRABATT</span>')
pruefe("nur ganzes Wort", render._block("Tankrabattgesetz beschlossen"),
       'Tankrabattgesetz <span class="hl">beschlossen</span>')
pruefe("fehlt: letztes Wort", render._block("Steuerausfall je Quartal"),
       'Steuerausfall je <span class="hl">Quartal</span>')
render._SCHLUESSEL.clear()
pruefe("ohne Hauptwort wie bisher", render._block("Tankrabatt: Ab Oktober weniger pro Liter"),
       'Tankrabatt: Ab Oktober weniger pro <span class="hl">Liter</span>')

print("\nAufbau (formfehler):")
gut = {"titel": "Tankrabatt: 17 Cent weniger", "schluesselwort": "Tankrabatt",
       "begriff": {"titel": "Was ist der Tankrabatt"}}
pruefe("passt", llm.formfehler(dict(gut), {}), "")
schlecht = {**gut, "begriff": {"titel": "Was ist die Energiesteuer"}}
pruefe("Slide 3 erklaert anderes Wort",
       "Erklaere \"Tankrabatt\" selbst" in llm.formfehler(schlecht, {}), True)
pruefe("Hauptwort nicht im Titel",
       "steht nicht woertlich" in llm.formfehler({**gut, "titel": "Sprit wird billiger"}, {}), True)
ohne = {**gut, "vergleich": {"punkte": ["Beim Tankrabatt 2022 ..."]}}
llm.formfehler(ohne, {"fruehere_faelle": []})
pruefe("Vergleich ohne Fundstelle gestrichen", "vergleich" in ohne, False)
mit = {**gut, "vergleich": {"punkte": ["..."]}}
llm.formfehler(mit, {"fruehere_faelle": [{"wert": 85}]})
pruefe("Vergleich mit Fundstelle bleibt", "vergleich" in mit, True)

print("\nFruehere Faelle, strenger Filter:")
roh = [
    {"massnahme": "Tankrabatt 2022", "befund": "rund 85 Prozent weitergegeben",
     "wert": 85, "einheit": "Prozent", "stelle": "ifo Institut",
     "quelle_url": "https://www.ifo.de/x"},
    {"massnahme": "Tankrabatt 2022", "befund": "ohne Adresse", "wert": 70,
     "stelle": "ifo", "quelle_url": "Drucksache 20/1234"},
    {"massnahme": "Tankrabatt 2022", "befund": "ohne Zahl", "wert": "viel",
     "stelle": "ifo", "quelle_url": "https://x"},
    {"massnahme": "Tankrabatt 2022", "befund": "ohne Stelle", "wert": 60,
     "stelle": "", "quelle_url": "https://x"},
]
pruefe("nur der vollstaendige", [f["wert"] for f in research.fruehere_faelle(roh)], [85.0])
pruefe("Zahl gilt als belegt",
       llm.zahl_belegt(llm._schreibweisen(85), "", llm.recherche_zahlen(
           {"fruehere_faelle": research.fruehere_faelle(roh)})), True)

print("\nTausendertrenner als Leerzeichen:")
text = "Wohngeldhaushalte (682 000), Ausgaben 4 689 Millionen Euro, Ende 2025 519 000"
pruefe("682.000", llm.zahl_belegt(llm._schreibweisen(682000), text, set()), True)
pruefe("519000 mit schmalem Leerzeichen", llm.zahl_belegt(llm._schreibweisen(519000), text, set()), True)
pruefe("Jahreszahl bleibt fuer sich", llm.tausender_mit_punkt("Ende 2025 682 000"),
       "Ende 2025 682.000")
pruefe("keine erfundene Zahl", llm.zahl_belegt(llm._schreibweisen(2025682), text, set()), False)

print("\nHandzeichen aus dem Artikel:")
FAELLE = [
    ("Dafür stimmten CDU/CSU und SPD, dagegen die AfD. Bündnis 90/Die Grünen und "
     "Die Linke enthielten sich.",
     {"CDU/CSU": "dafür", "SPD": "dafür", "AfD": "dagegen", "Gruene": "enthalten",
      "Linke": "enthalten"}),
    ("Für den Einigungsvorschlag stimmten die Koalitionsfraktionen CDU/CSU und SPD, "
     "dagegen die Oppositionsfraktionen AfD, Bündnis 90/Die Grünen und Die Linke.",
     {"CDU/CSU": "dafür", "SPD": "dafür", "AfD": "dagegen", "Gruene": "dagegen",
      "Linke": "dagegen"}),
    # Tippfehler in der Quelle ("CDI/CSU") - "Koalitionsfraktionen" traegt.
    ("Dafür stimmten die Koalitionsfraktionen CDI/CSU und SPD. Die "
     "Oppositionsfraktionen AfD, Bündnis 90/Die Grünen und Die Linke enthielten sich.",
     {"CDU/CSU": "dafür", "SPD": "dafür", "AfD": "enthalten", "Gruene": "enthalten",
      "Linke": "enthalten"}),
    ("Für den Gesetzentwurf stimmten CDU/CSU, AfD, SPD und Bündnis 90/Die Grünen, "
     "dagegen stimmte die Fraktion Die Linke.",
     {"CDU/CSU": "dafür", "SPD": "dafür", "AfD": "dafür", "Gruene": "dafür",
      "Linke": "dagegen"}),
]
for satz, soll in FAELLE:
    pruefe(satz[:50], (stimmen.handzeichen(satz) or {}).get("positionen"), soll)
# Nicht jede Fraktion zugeordnet: kein Bogen, statt einen falsch zu faerben.
pruefe("unvollstaendig", stimmen.handzeichen("Dafür stimmten CDU/CSU und SPD, dagegen die AfD."), None)
pruefe("AfD-Position nicht genannt", stimmen.handzeichen(
    "Der Bundestag hat den Gesetzentwurf der AfD mit den Stimmen aller übrigen "
    "Fraktionen abgelehnt."), None)

print("\nSitzbogen bei Handzeichen:")
hz = stimmen.handzeichen(FAELLE[0][0])
bogen = sitzbogen.bogen(hz)
pruefe("Art", bogen["art"], "handzeichen")
pruefe("angenommen", bogen["angenommen"], True)
gefuellt = sum(1 for p in bogen["punkte"] if not p["hohl"])
pruefe("gefuellt = Sitze von CDU/CSU und SPD", gefuellt, 208 + 120)
pruefe("Position in der Legende",
       {f["name"]: f["position"] for f in bogen["legende"]}["Grüne"], "enthalten")

print("\nNamentliche Abstimmung aus der XLSX:")
import openpyxl
buch = openpyxl.Workbook()
blatt = buch.active
blatt.append(["Wahlperiode", "Sitzungnr", "Abstimmnr", "Fraktion/Gruppe", "Name",
              "Vorname", "Titel", "ja", "nein", "Enthaltung", "ungültig",
              "nichtabgegeben", "Bezeichnung", "Bemerkung"])
for fraktion, ja, nein in [("CDU/CSU", 3, 0), ("BÜ90/GR", 0, 2), ("Die Linke", 1, 1)]:
    for _ in range(ja):
        blatt.append([21, 97, 2, fraktion, "X", "Y", None, 1, 0, 0, 0, 0, "", ""])
    for _ in range(nein):
        blatt.append([21, 97, 2, fraktion, "X", "Y", None, 0, 1, 0, 0, 0, "", ""])
puffer = io.BytesIO()
buch.save(puffer)
ergebnis = stimmen.xlsx_ergebnis(puffer.getvalue())
pruefe("Summen", (ergebnis["ja"], ergebnis["nein"], ergebnis["enthalten"]), (4, 3, 0))
pruefe("Gruene unter Protokollnamen", ergebnis["fraktionen"]["BÜNDNIS 90/DIE GRÜNEN"]["nein"], 2)

# Zuordnung: zwei Abstimmungen am selben Tag stehen im Artikel - der Titel
# entscheidet (Tankrabatt vs. Entschliessungsantrag, 25.09.2026).
from datetime import date
_liste, _get, _ergebnis = stimmen._liste, stimmen.requests.get, stimmen.xlsx_ergebnis
stimmen._liste = lambda: [
    {"datum": date(2026, 9, 25), "titel": "Entschließungsantrag der Grünen zur Übergewinnsteuer", "xlsx": "a"},
    {"datum": date(2026, 9, 25), "titel": "Tankrabatt (Art. 11, 12 und 13 Abs. 4 Energiesteuergesetz)", "xlsx": "b"},
    {"datum": date(2026, 9, 24), "titel": "Tankrabatt am Vortag", "xlsx": "c"}]


class _A:
    def __init__(self, url):
        self.content = url

    def raise_for_status(self):
        pass


werte = {"a": (127, 418), "b": (434, 128), "c": (434, 128)}
stimmen.requests.get = lambda url, **k: _A(url)
stimmen.xlsx_ergebnis = lambda inhalt: {"ja": werte[inhalt][0], "nein": werte[inhalt][1],
                                        "enthalten": 0, "gesamt": sum(werte[inhalt]),
                                        "angenommen": True, "fraktionen": {"CDU/CSU": {"ja": 1}}}
try:
    item = {"date": "2026-09-25", "title": "Bundestag beschließt Tankrabatt",
            "text": "votierten 434 Abgeordnete, 128 stimmten dagegen. ... "
                    "Dafür stimmten 127 Abgeordnete, dagegen 418 Abgeordnete."}
    treffer = stimmen.namentlich(item)
    pruefe("Tankrabatt, nicht der Antrag", (treffer or {}).get("ja"), 434)
    item["text"] = "Dafür stimmten 127 Abgeordnete."
    pruefe("Zahl fehlt im Text: keine Zuordnung", stimmen.namentlich(item), None)
finally:
    stimmen._liste, stimmen.requests.get, stimmen.xlsx_ergebnis = _liste, _get, _ergebnis

print("\nZweiter Versuch nach Aufbaufehler:")
sources.ensure_volltext = lambda item: item
einwaende = []
entwuerfe = iter([{"titel": "Tankrabatt: 17 Cent", "schluesselwort": "Tankrabatt",
                   "begriff": {"titel": "Was ist die Energiesteuer"}},
                  {"titel": "Tankrabatt: 17 Cent", "schluesselwort": "Tankrabatt",
                   "begriff": {"titel": "Was ist der Tankrabatt"}}])
llm.compose = lambda item, recherche, einwand="": einwaende.append(einwand) or next(entwuerfe)
llm.belegfehler = lambda *a: None
llm.judge_slides = lambda *a: (True, "")
ergebnis = llm.build_carousels([{"id": "x", "title": "T"}], lambda i: {}, anzahl=1,
                               themen=[{"id": "x", "title": "T"}])
pruefe("zwei Entwuerfe", len(einwaende), 2)
pruefe("Beanstandung nennt das Hauptwort", "Tankrabatt" in einwaende[1], True)
pruefe("Karussell entsteht", len(ergebnis), 1)

print(f"\n{fehler} Fehler" if fehler else "\nalle Faelle bestanden")
sys.exit(1 if fehler else 0)
