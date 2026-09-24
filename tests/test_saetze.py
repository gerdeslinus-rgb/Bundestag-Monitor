"""Prueft saetze() und den anteiligen Mindestblock."""
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
import config
import llm

fehler = 0

print("saetze() - Zerlegung:")
FAELLE = [
    ("Der Bundestag beraet am Mittwoch, 23. September 2026, erstmals ueber "
     "den Entwurf. Danach folgt die Aussprache.", 2),
    ("Die Frist endet am 1. Januar 2027.", 1),
    ("Nach Art. 50 Abs. 4 gilt das nicht. Der Rest bleibt.", 2),
    ("Er nennt Drs. 21/8065 als Grundlage. Das ist der Entwurf.", 2),
    ("Ein Satz. Noch einer. Und ein dritter.", 3),
    ("Die Kosten liegen bei 5 Mio. Euro jaehrlich.", 1),
]
for text, soll in FAELLE:
    ist = llm.saetze(text)
    ok = len(ist) == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {len(ist)} statt {soll} erwartet | {text[:52]}")
    if not ok:
        for s in ist:
            print(f"         -> {s!r}")

print("\nmindestblock() - anteilig bei kurzen Saetzen:")
for laenge, soll in [(300, 16), (48, 16), (45, 15), (35, 11), (20, 6), (9, 6)]:
    ist = llm.mindestblock("x" * laenge)
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} Satz {laenge:>3} Zeichen -> Mindestblock {ist} (erwartet {soll})")

print("\nEchte Belegsaetze nach der neuen Zerlegung:")
# Eingefrorene Fixture statt out/debug: der Zwischenstand wird bei jedem
# Lauf neu geschrieben, und nach einem Themenwechsel verglichen die Tests
# Belegsaetze des einen Themas gegen den Quelltext des anderen.
_FIX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "fixture.json"), encoding="utf-8"))
v = [f["item"] for f in _FIX["faelle"]]
e = [f["slides"] for f in _FIX["faelle"]]
for idx in (0, 1):
    q = llm._normalise(v[idx].get("text", ""))
    roh = v[idx].get("text", "")
    for s in llm.saetze(e[idx]["fakten_evidence"]):
        n = llm._normalise(s)
        if not n:
            continue
        quote = llm.belegquote(n, q)
        erf = llm.evidenz_zahl_erfunden(s, roh)
        ok = quote >= config.EVIDENCE_THRESHOLD and not erf
        fehler += not ok
        print(f"  {'OK  ' if ok else 'FEHL'} {quote:.2f}  len={len(n):>4} "
              f"block={llm.mindestblock(n):>2} | {s[:52]}")

print(f"\n{'ALLE BESTANDEN' if not fehler else str(fehler) + ' FEHLER'}")
sys.exit(1 if fehler else 0)
