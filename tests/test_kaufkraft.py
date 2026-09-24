"""Kaufkraft: gerechnet mit 2 % p.a., Operanden aus dem Quelltext."""
import os
import sys

# Projektwurzel aus dem eigenen Pfad, nicht aus dem Arbeitsverzeichnis:
# so laeuft der Test auch als "python tests/test_x.py" von ueberall.
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(os.path.join(WURZEL, ".env"))
import config
import llm
import research

fehler = 0
HEUTE = datetime.now().year
TEXT = ("So sei der Werbungskostenpauschbetrag bei den sonstigen Einkuenften "
        "wie Renten in Hoehe von 102 Euro seit 1955 nicht mehr angepasst "
        "worden. Die Grenze von 1.000 Euro gilt seit 2011.")

print(f"Rechnung: {config.KAUFKRAFT_INFLATION:.0%} p.a., heute = {HEUTE}")
erwartet = 102 * 1.02 ** (HEUTE - 1955)
print(f"  102 Euro von 1955 ueber {HEUTE - 1955} Jahre = {erwartet:.2f} "
      f"-> gerundet {research._rund(erwartet):g}\n")

print("research._kaufkraft:")
FAELLE = [
    ("Betrag und Jahr im Text", {"betrag": 102, "jahr": 1955}, True),
    ("zweiter Betrag im Text", {"betrag": 1000, "jahr": 2011}, True),
    ("Betrag NICHT im Text", {"betrag": 250, "jahr": 1955}, False),
    ("Jahr NICHT im Text", {"betrag": 102, "jahr": 1949}, False),
    ("Jahr in der Zukunft", {"betrag": 102, "jahr": HEUTE + 1}, False),
    ("Jahr zu jung (< 10 Jahre)", {"betrag": 102, "jahr": HEUTE - 3}, False),
    ("Jahr vor 1900", {"betrag": 102, "jahr": 1810}, False),
    ("Betrag negativ", {"betrag": -102, "jahr": 1955}, False),
    ("betrag fehlt", {"jahr": 1955}, False),
    ("unlesbar", {"betrag": "hundertzwei", "jahr": 1955}, False),
    ("gar kein Dict", "102 Euro von 1955", False),
    ("None", None, False),
]
for name, roh, soll in FAELLE:
    erg = research._kaufkraft(roh, TEXT)
    ok = bool(erg) == soll
    fehler += not ok
    zusatz = f" -> {erg['heute_etwa']:g} {erg['einheit']}, {erg['annahme']}" if erg else ""
    print(f"  {'OK  ' if ok else 'FEHL'} {name:<26}{zusatz}")

print("\n_rund - zwei geltende Ziffern:")
for roh, soll in [(416.3, 420.0), (1187.0, 1200.0), (98.4, 98.0),
                  (12345.0, 12000.0), (7.3, 7.3)]:
    ist = research._rund(roh)
    ok = abs(ist - soll) < 1e-9
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {roh:>9g} -> {ist:g} (erwartet {soll:g})")

print("\nllm.recherche_zahlen - nur der berechnete Wert gilt:")
kk = research._kaufkraft({"betrag": 102, "jahr": 1955}, TEXT)
belegt = llm.recherche_zahlen({"vorher_nachher": [], "kaufkraft": kk})
wert = f"{kk['heute_etwa']:g}"
for probe, soll in [(wert, True), ("1350", False), ("416", False)]:
    ist = probe in belegt
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {probe:>6} belegt: {ist}")

print("\nverify_slides mit drittem Balken:")
# Eingefrorene Fixture statt out/debug: der Zwischenstand wird bei jedem
# Lauf neu geschrieben, und nach einem Themenwechsel verglichen die Tests
# Belegsaetze des einen Themas gegen den Quelltext des anderen.
_FIX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "fixture.json"), encoding="utf-8"))
t, r, s = (_FIX["faelle"][1]["item"], _FIX["faelle"][1]["recherche"],
           _FIX["faelle"][1]["slides"])
echt = research._kaufkraft({"betrag": 102, "jahr": 1955}, t.get("text", ""))

def mit_balken(w):
    chart = dict(s["chart"])
    chart["balken"] = list(chart["balken"]) + [
        {"label": "1955 in heutiger Kaufkraft", "wert": w}]
    chart["hervorheben"] = 2
    chart["hinweis"] = "Kaufkraft, Annahme: 2 % Inflation pro Jahr"
    return dict(s, chart=chart)

PROBEN = [
    ("berechneter Wert", echt["heute_etwa"], dict(r, kaufkraft=echt), True),
    ("ohne Kaufkraft-Feld", echt["heute_etwa"], dict(r, kaufkraft={}), False),
    ("Modell erfindet Wert", 999, dict(r, kaufkraft=echt), False),
]
for name, w, rech, soll in PROBEN:
    ist = llm.verify_slides(mit_balken(w), t, rech)
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {name:<22} Balken {w:g} -> {ist}")

print(f"\n{'ALLE BESTANDEN' if not fehler else str(fehler) + ' FEHLER'}")
sys.exit(1 if fehler else 0)
