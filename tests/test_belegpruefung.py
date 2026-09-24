"""Gesamturteil: echte Saetze und Faelschungen durch die fertige Pruefung."""
import os
import sys

# Projektwurzel aus dem eigenen Pfad, nicht aus dem Arbeitsverzeichnis:
# so laeuft der Test auch als "python tests/test_x.py" von ueberall.
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import os
import re
from dotenv import load_dotenv
load_dotenv(os.path.join(WURZEL, ".env"))
import config
import llm

# Eingefrorene Fixture statt out/debug: der Zwischenstand wird bei jedem
# Lauf neu geschrieben, und nach einem Themenwechsel verglichen die Tests
# Belegsaetze des einen Themas gegen den Quelltext des anderen.
_FIX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "fixture.json"), encoding="utf-8"))
v = [f["item"] for f in _FIX["faelle"]]
e = [f["slides"] for f in _FIX["faelle"]]


def urteil(satz, idx):
    """Wie verify_slides entscheidet: Quote UND Zahlenpruefung."""
    quelle = llm._normalise(v[idx].get("text", ""))
    roh = v[idx].get("text", "")
    norm = llm._normalise(satz)
    quote = llm.belegquote(norm, quelle)
    erfunden = llm.evidenz_zahl_erfunden(satz, roh)
    return quote >= config.EVIDENCE_THRESHOLD and not erfunden, quote, erfunden


print("ECHTE BELEGSAETZE (sollen alle durch):")
schlecht = 0
for idx in (0, 1):
    for s in re.split(r"(?<=[.!?])\s+", e[idx]["fakten_evidence"].strip()):
        if not llm._normalise(s):
            continue
        ok, quote, erf = urteil(s, idx)
        schlecht += not ok
        grund = f" ZAHL {erf}" if erf else ""
        print(f"  {'OK  ' if ok else 'FEHL'} {quote:.2f}{grund} | {s[:60]}")

FAELSCHUNGEN = [
    ("Quellvokabular, Aussage erfunden", 0,
     "Der Ausschuss fuer Umwelt, Klimaschutz, Naturschutz und nukleare "
     "Sicherheit hat den Antrag der AfD-Fraktion mit grosser Mehrheit "
     "abgelehnt und die Bundesregierung aufgefordert, den CO2-Preis bis 2030 "
     "auf 120 Euro pro Tonne anzuheben."),
    ("echter Satz, Zahl ausgetauscht", 1,
     "So sei der Werbungskostenpauschbetrag bei den sonstigen Einkuenften wie "
     "Renten in Hoehe von 250 Euro seit 1975 nicht mehr angepasst worden."),
    ("echter Satz, nur EINE Ziffer geaendert", 1,
     "So sei der Werbungskostenpauschbetrag bei den sonstigen Einkuenften wie "
     "Renten in Hoehe von 102 Euro seit 1956 nicht mehr angepasst worden."),
    ("Aussage umgedreht", 1,
     "Nach 20-minuetiger Aussprache soll der Entwurf nicht dem Finanzausschuss "
     "ueberwiesen, sondern unmittelbar in zweiter Lesung beschlossen werden."),
    ("falsche Quelle", 0,
     "Der Bundesrat hat dem Gesetz zur Senkung der Stromsteuer zugestimmt, "
     "die Entlastung tritt zum 1. Januar 2027 in Kraft."),
    ("Paraphrase statt Zitat", 0,
     "Die AfD-Fraktion moechte saemtliche Klimaschutzvorschriften streichen "
     "lassen, weil sie die Wirtschaft aus ihrer Sicht unnoetig belastet."),
]

print("\nFAELSCHUNGEN (sollen alle durchfallen):")
for name, idx, satz in FAELSCHUNGEN:
    ok, quote, erf = urteil(satz, idx)
    schlecht += ok
    grund = f" -> Zahl {erf} nicht in Quelle" if erf else ""
    print(f"  {'FEHL' if ok else 'OK  '} {quote:.2f}{grund} | {name}")

print(f"\n{'ALLES WIE GEWOLLT' if not schlecht else str(schlecht) + ' PROBLEME'}")
sys.exit(1 if schlecht else 0)
