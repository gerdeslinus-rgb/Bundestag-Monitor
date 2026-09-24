"""Prueft abgeleitete_zahlen gegen den echten Entwurf aus out/debug."""
import os
import sys

# Projektwurzel aus dem eigenen Pfad, nicht aus dem Arbeitsverzeichnis:
# so laeuft der Test auch als "python tests/test_x.py" von ueberall.
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(WURZEL, ".env"))
import llm

# Eingefrorene Fixture statt out/debug: der Zwischenstand wird bei jedem
# Lauf neu geschrieben, und nach einem Themenwechsel verglichen die Tests
# Belegsaetze des einen Themas gegen den Quelltext des anderen.
_FIX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "fixture.json"), encoding="utf-8"))
t, r, slides = (_FIX["faelle"][1]["item"], _FIX["faelle"][1]["recherche"],
                _FIX["faelle"][1]["slides"])
quelltext, belegt = t.get("text", ""), llm.recherche_zahlen(r)

FAELLE = [
    ("70 aus 2026-1955=71, Text sagt 'ueber 70'",
     [{"wert": 70, "aus": [1955, 2026], "rechnung": "differenz"}], True),
    ("exakt 71 statt gerundet",
     [{"wert": 71, "aus": [1955, 2026], "rechnung": "differenz"}], True),
    ("ABLEHNEN: 50 statt 71 (Abweichung zu gross)",
     [{"wert": 50, "aus": [1955, 2026], "rechnung": "differenz"}], False),
    ("ABLEHNEN: 68 ist keine glatte Zahl",
     [{"wert": 68, "aus": [1955, 2026], "rechnung": "differenz"}], False),
    ("ABLEHNEN: Operand 1949 steht nirgends",
     [{"wert": 75, "aus": [1949, 2026], "rechnung": "differenz"}], False),
    ("ABLEHNEN: Rechnung geht nicht auf",
     [{"wert": 40, "aus": [1955, 2026], "rechnung": "summe"}], False),
    ("ABLEHNEN: unbekannte Rechenart",
     [{"wert": 71, "aus": [1955, 2026], "rechnung": "magie"}], False),
    ("ABLEHNEN: Deckel, 7. Eintrag zaehlt nicht mehr",
     [{"wert": 102, "aus": [102], "rechnung": "summe"}] * 6
     + [{"wert": 71, "aus": [1955, 2026], "rechnung": "differenz"}], False),
]

fehler = 0
for name, eintraege, soll in FAELLE:
    # Signalwort ausdruecklich setzen statt aus dem Entwurf zu erben: der
    # Zwischenstand wird bei jedem Lauf neu geschrieben, und ohne "ueber 70"
    # im Text scheitert die Rundungspruefung aus dem falschen Grund.
    probe = dict(slides,
                 chart=dict(slides["chart"],
                            hinweis="Der Betrag gilt seit über 70 Jahren"),
                 abgeleitete_zahlen=eintraege)
    erlaubt = llm.abgeleitete_zahlen(probe, quelltext, belegt)
    ist = bool(erlaubt & llm._schreibweisen(eintraege[-1]["wert"]))
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'}  {name}  -> {ist}")

# Richtungsprobe: dasselbe gerundete 70 mit falschem Signalwort.
print("\n  Richtung des Signalworts:")
for wort, soll in [("ueber", True), ("über", True), ("rund", True),
                   ("knapp", False), ("fast", False), ("", False)]:
    probe = dict(slides,
                 chart=dict(slides["chart"],
                            hinweis=f"Der Betrag gilt seit {wort} 70 Jahren"),
                 abgeleitete_zahlen=[{"wert": 70, "aus": [1955, 2026],
                                      "rechnung": "differenz"}])
    ist = bool(llm.abgeleitete_zahlen(probe, quelltext, belegt))
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'}  'seit {wort or '(nichts)'} 70 Jahren' -> {ist}")


# --- Stellenkuerzen: exakt gerundete Dezimalwerte ohne Signalwort ---------
print("\n  Stellenkuerzen (faktor 5860 / 12509 = 2,13464):")
DEZ = [
    ("2.13 - auf zwei Stellen gerundet", 2.13, True),
    ("2.135 - auf drei Stellen", 2.135, True),
    ("2.1 - auf eine Stelle", 2.1, True),
    ("ABLEHNEN: 2 - sechs Prozent daneben", 2, False),
    ("ABLEHNEN: 2.5 - frei gegriffen", 2.5, False),
    ("ABLEHNEN: 2.14 - falsch gerundet", 2.14, False),
]
for name, wert, soll in DEZ:
    probe = dict(slides,
                 chart=dict(slides["chart"], hinweis="Faktor ohne Signalwort"),
                 abgeleitete_zahlen=[{"wert": wert, "aus": [5860, 12509],
                                      "rechnung": "faktor"}])
    ist = bool(llm.abgeleitete_zahlen(probe, "5860 und 12509", set()))
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'}  {name:<38} -> {ist}")

print(f"\n{'ALLE BESTANDEN' if not fehler else str(fehler) + ' FEHLER'}")
sys.exit(1 if fehler else 0)
