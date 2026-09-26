"""Prueft, wann ein Entwurf einen zweiten Versuch bekommt.

Kein Netz, kein Modell: Entwurf, Pruefungen und Faktencheck sind durch
Attrappen ersetzt, getestet wird nur die Schleife in build_carousels.

Anlass (26.09.2026): der Tankrabatt fiel durch, weil das Modell in einem
einzigen Satz "ueber die Laufzeit etwa 32 bis 36 Euro" hochgerechnet hatte.
Eine unbelegte Zahl bekommt seitdem einen zweiten Versuch mit genau dieser
Beanstandung. Ein Beleg-Satz, der nicht im Quelltext steht, weiterhin nicht.
"""
import os
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
os.chdir(WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
import llm
import sources

fehler = 0


def pruefe(name, ist, soll):
    global fehler
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist!r}" + ("" if ok else f" (soll {soll!r})"))


sources.ensure_volltext = lambda item: item
ITEM = {"id": "x", "title": "Bundestag beschließt Tankrabatt", "text": "..."}


def lauf(pruefungen, faktencheck=(True, "")):
    """Ein Thema durch die Schleife. `pruefungen` sind die Ergebnisse von
    belegfehler() fuer Versuch 1, 2, ... - zurueck kommen die Einwaende, die
    compose() gesehen hat, und ob ein Karussell herauskam."""
    einwaende, reihe = [], list(pruefungen)
    llm.compose = lambda item, recherche, einwand="": (
        einwaende.append(einwand) or {"titel": "Tankrabatt"})
    llm.belegfehler = lambda slides, item, recherche: reihe.pop(0)
    llm.judge_slides = lambda slides, item, recherche: faktencheck
    ergebnis = llm.build_carousels([ITEM], lambda item: {}, anzahl=1,
                                   themen=[dict(ITEM)])
    return einwaende, len(ergebnis)


print("Unbelegte Zahl, dann sauber:")
einwaende, n = lauf([("zahl", "32"), None])
pruefe("zwei Entwuerfe", len(einwaende), 2)
pruefe("zweiter kennt die Zahl", "Die Zahl 32" in einwaende[1], True)
pruefe("Karussell entsteht", n, 1)

print("\nUnbelegte Zahl zweimal:")
einwaende, n = lauf([("zahl", "32"), ("zahl", "36")])
pruefe("zwei Entwuerfe, nicht drei", len(einwaende), 2)
pruefe("kein Karussell", n, 0)

print("\nBeleg-Satz nicht im Quelltext:")
einwaende, n = lauf([("beleg", "Ein erfundener Satz.")])
pruefe("kein zweiter Entwurf", len(einwaende), 1)
pruefe("kein Karussell", n, 0)

print("\nZahl im ersten, Faktencheck im zweiten Versuch:")
einwaende, n = lauf([("zahl", "32"), None], faktencheck=(False, "Satz X"))
pruefe("nicht noch ein dritter", len(einwaende), 2)
pruefe("kein Karussell", n, 0)

print(f"\n{fehler} Fehler" if fehler else "\nalle Faelle bestanden")
sys.exit(1 if fehler else 0)
