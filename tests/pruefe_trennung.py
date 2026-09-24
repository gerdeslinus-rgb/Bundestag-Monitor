"""Prueft die 3-Zeilen-Regel an echten und typischen Schlagzeilen.

Benutzt dieselbe Mess- und Stufungslogik wie render.py und dieselbe
Cover-Geometrie (928 px Textbreite, 96 px versal Zilla Slab) - sonst misst
man etwas anderes als die Karte.
"""
import os
import sys

# Projektwurzel aus dem eigenen Pfad, nicht aus dem Arbeitsverzeichnis:
# so laeuft der Test auch als "python tests/test_x.py" von ueberall.
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
from pathlib import Path
from playwright.sync_api import sync_playwright

import render

ZIEL = Path(WURZEL) / "out" / "debug" / "trennung.png"

HEADLINES = [
    "Kalte Progression: 102-Euro-Pauschale gilt seit 1955",
    "CO2-Preis stieg auf 55 Euro: AfD will ihn ganz abschaffen",
    "Pendlerpauschale steigt",
    "Werbungskostenpauschbetrag gilt seit 1955",
    "Krankenhausfinanzierung wird neu geregelt",
    "Elektrokleinstfahrzeuge: Haftung soll sich aendern",
    "Widerspruchsloesung bei Organspende soll kommen",
    "Energiewirtschaftsrecht: Netzausbau soll schneller gehen",
    "Mindestlohn steigt 2027 auf 15 Euro",
    "Grundsicherung: Regelsatz soll um 12 Euro steigen",
    # Absichtlich zu lang: muss an die Untergrenze laufen und warnen.
    "Krankenhausstrukturfonds und Pflegepersonaluntergrenzenverordnung "
    "werden zusammengelegt",
]

SEITE = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@700&family=Archivo:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  body {{ margin: 0; padding: 40px; background: #1b2430; width: 1008px; }}
  .h {{
    font-family: "Zilla Slab", Georgia, serif; font-weight: 700;
    font-size: 96px; line-height: 1.03; letter-spacing: -0.025em;
    text-transform: uppercase; color: #fafaf8; margin: 0 0 14px;
    width: 928px;
    hyphens: auto; overflow-wrap: break-word;
    hyphenate-limit-chars: 12 5 5;
  }}
  .m {{ font: 400 22px/1 Archivo, system-ui, sans-serif; color: #8fb4d0;
        margin: 0 0 46px; }}
</style></head><body>{koerper}</body></html>"""


def main() -> int:
    koerper = "".join(f'<div class="h" id="h{i}">{h}</div><p class="m" id="m{i}"></p>'
                      for i, h in enumerate(HEADLINES))
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    quelle = ZIEL.parent / "_trennung.html"
    quelle.write_text(SEITE.format(koerper=koerper), encoding="utf-8")

    fehler = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1088, "height": 1400})
        page.goto(quelle.resolve().as_uri())
        page.wait_for_function("document.fonts.status === 'loaded'")
        page.wait_for_timeout(300)

        print(f"{'Schlagzeile':<58}{'Zeilen':>7}{'->':>4}{'px':>5}{'Zeilen':>8}")
        for i, text in enumerate(HEADLINES):
            el = page.query_selector(f"#h{i}")
            vorher = page.evaluate(render._ZEILEN_JS, el)

            # Dieselbe Stufung wie render._zeilen_deckeln.
            groesse, zeilen = 96.0, vorher
            while (zeilen > render.HEADLINE_ZEILEN_MAX
                   and groesse - render.HEADLINE_STUFE_PX >= render.HEADLINE_MIN_PX):
                groesse -= render.HEADLINE_STUFE_PX
                page.evaluate("([el, px]) => el.style.fontSize = px + 'px'",
                              [el, groesse])
                zeilen = page.evaluate(render._ZEILEN_JS, el)

            marke = "OK  " if zeilen <= render.HEADLINE_ZEILEN_MAX else "ZU LANG"
            fehler += zeilen > render.HEADLINE_ZEILEN_MAX and len(text) <= 60
            print(f"  {marke} {text[:52]:<52}{vorher:>5}{'->':>4}{groesse:>5.0f}{zeilen:>8}")
            page.evaluate(
                "([el, t]) => el.textContent = t",
                [page.query_selector(f"#m{i}"),
                 f"{len(text)} Zeichen · {vorher} Zeilen bei 96 px · "
                 f"gesetzt {groesse:.0f} px · {zeilen} Zeilen"])

        page.screenshot(path=str(ZIEL), full_page=True)
        browser.close()
    quelle.unlink()

    print(f"\n{'ALLE unter 60 Zeichen passen in 3 Zeilen' if not fehler else str(fehler) + ' FEHLER'}")
    print(f"  -> {ZIEL}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
