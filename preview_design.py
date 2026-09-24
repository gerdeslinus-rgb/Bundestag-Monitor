"""Rendert ein Beispiel-Karussell mit erfundenen Daten - zum Pruefen des Designs.

Laeuft ohne Modell, ohne Netz, ohne Quellen: nur render.py und das Template.

    python preview_design.py

Gerendert wird jede Variante, die das Design-System kennt - sonst prueft man
immer nur den einen Fall, der gerade gebaut wurde:

    lang/    5 Slides, Balkendiagramm, Folgen-Muster 4a
    bogen/   dasselbe Karussell mit namentlicher Abstimmung: Sitzbogen
    4b/      Anspruch (gilt fuer dich / gilt nicht)
    4c/      Checkliste ("Nichts.")
    4d/      zwei Faelle nebeneinander (Subgrid)
    kurz/    4 Slides, Profil-Karussell ohne Begriffskarte und ohne Folgen
    1a-1f/   die sechs Cover-Architekturen, je erzwungen statt gezogen

Im Lauf wird die Cover-Architektur gezogen (cover.py). Hier wird sie gesetzt:
eine Vorschau, die wuerfelt, zeigt bei jedem Aufruf etwas anderes und taugt
nicht zum Vergleich.

Dazu out/design_preview/uebersicht.png als Kontaktbogen ueber alles.
"""

import base64
import mimetypes
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Ohne .env liefe die Vorschau immer ohne Pexels-Key und damit immer mit
# typografischem Cover - also gerade ohne den Fall, den man sehen will.
load_dotenv()

import bilder
import cover
import render

ZIEL = Path("out/design_preview")

BEISPIEL = {
    "item": {
        "source": "Bundesregierung",
        "title": "Kabinett beschließt höheren Pendlerfreibetrag ab 2027",
        "url": "https://www.bundesregierung.de/breg-de/aktuelles/pendlerpauschale-2027",
        "date": "13.09.2026",
    },
    "slides": {
        "titel": "Pendlerpauschale steigt",
        "hook": "Ab 2027 zahlst du bis zu 127 Euro weniger Steuern.",
        "cover_frage": "Was ist eine Pendlerpauschale?",
        "chart": {
            "titel": "Pauschale je Kilometer",
            "einheit": "Cent",
            "hervorheben": 2,
            "balken": [
                {"label": "2024", "wert": 30},
                {"label": "2026", "wert": 38},
                {"label": "ab 2027", "wert": 45},
            ],
            "hinweis": "Gilt ab dem ersten Kilometer, nicht erst ab dem 21.",
        },
        "context": [
            "Die Pendlerpauschale senkt dein zu versteuerndes Einkommen, "
            "nicht die Steuer direkt.",
            "Bisher galten 38 Cent erst ab dem 21. Kilometer, davor 30 Cent.",
            "Der Bundesrat muss dem Gesetz noch zustimmen.",
        ],
        "begriff": {
            "titel": "Was ist eine Pendlerpauschale",
            "saetze": [
                "Die Pendlerpauschale ist ein Betrag, den du von deinem "
                "Einkommen abziehen darfst, bevor die Steuer berechnet wird.",
                "Sie gilt je Kilometer zwischen Wohnung und Arbeit, an jedem "
                "Arbeitstag, egal womit du fährst.",
            ],
            "beispiel": "Bei 25 Kilometern und 220 Arbeitstagen sind das "
                        "5.500 Kilometer, für die du 45 Cent abziehst.",
            "warum": [
                "Die Spritpreise sind seit der letzten Anhebung gestiegen.",
                "Wer auf dem Land wohnt, fährt weiter zur Arbeit als in der "
                "Stadt und zahlt dafür mehr.",
            ],
        },
        "sowhat": {
            "art": "rechnung",
            "text": "Bei 25 Kilometern einfachem Arbeitsweg sparst du rund "
                    "127 Euro im Jahr.",
            "schritte": [
                "25 km x 220 Arbeitstage = 5.500 km",
                "5.500 km x 7 Cent mehr = 385 Euro mehr Freibetrag",
                "385 Euro x 33 % Grenzsteuersatz = 127 Euro",
            ],
        },
        "folgen": {
            "muster": "4a",
            "kopf_neu": "ab 2027",
            "zeilen": [
                {"label": "Je Kilometer", "bisher": "38 Cent", "neu": "45 Cent"},
                {"label": "Ab Kilometer", "bisher": "21", "neu": "1"},
            ],
            "pills": [{"label": "Gilt ab", "wert": "01.01.27"}],
        },
    },
}

# Namentliche Abstimmung in der Form, die abstimmung.aus_protokoll() liefert.
# 335 Ja von 610 abgegebenen Stimmen, also 306 noetig.
ABSTIMMUNG = {
    "gegenstand": "Gesetz zur Anhebung der Entfernungspauschale",
    "gesamt": 610, "ja": 335, "nein": 265, "enthalten": 10,
    "angenommen": True,
    "fraktionen": {
        "CDU/CSU": {"ja": 200, "nein": 3, "enthalten": 2},
        "SPD": {"ja": 118, "nein": 0, "enthalten": 1},
        "BÜNDNIS 90/DIE GRÜNEN": {"ja": 5, "nein": 74, "enthalten": 3},
        "Die Linke": {"ja": 2, "nein": 56, "enthalten": 2},
        "AfD": {"ja": 10, "nein": 130, "enthalten": 2},
        "SSW": {"ja": 0, "nein": 1, "enthalten": 0},
    },
}

# Die drei anderen Muster der Folgen-Slide. Slide 4 faellt am ehesten auf,
# wenn das Muster nicht zur Aussage passt - deshalb steht jedes einmal im
# Kontaktbogen.
FOLGEN_VARIANTEN = {
    "4b": {
        "muster": "4b",
        "ja": [
            "Du fährst mit dem eigenen Auto oder dem Rad zur Arbeit.",
            "Dein Arbeitsweg ist länger als 10 Kilometer.",
            "Du gibst eine Steuererklärung ab.",
        ],
        "nein": [
            "Dein Arbeitgeber zahlt dir das Ticket ohnehin.",
            "Du arbeitest ausschließlich zu Hause.",
        ],
    },
    "4c": {
        "muster": "4c",
        "payoff": "Nichts.",
        "erklaerung": "Das Finanzamt rechnet den neuen Satz automatisch, "
                      "sobald du deine Steuererklärung für 2027 abgibst.",
        "schritte": [
            "Du willst den Vorteil sofort: dann beantrage einen Freibetrag "
            "auf der Lohnsteuerkarte.",
            "Du hast mehrere Arbeitsstätten: dann trage jede Strecke einzeln ein.",
        ],
    },
    "4d": {
        "muster": "4d",
        "faelle": [
            {"label": "25 km, Auto", "symbol": "auto",
             "kennzahlen": [{"label": "Mehr Freibetrag", "wert": "385 €"},
                            {"label": "Weniger Steuern", "wert": "127 €"}]},
            {"label": "8 km, Rad", "symbol": "person",
             "kennzahlen": [{"label": "Mehr Freibetrag", "wert": "123 €"},
                            {"label": "Weniger Steuern", "wert": "41 €"}]},
        ],
    },
}


def _kontaktbogen(bilder: list, ziel: Path) -> None:
    """Legt alle Slides verkleinert nebeneinander - ein Blick, ein Urteil."""
    reihen = []
    for titel, pfade in bilder:
        kacheln = "".join(
            f'<figure><img src="{p.resolve().as_uri()}"><figcaption>'
            f'{p.parent.name}/{p.name}</figcaption></figure>' for p in pfade)
        reihen.append(f"<h2>{titel}</h2><div class='reihe'>{kacheln}</div>")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ margin: 0; padding: 40px; background: #1b1b1b; color: #ddd;
              font: 15px/1.4 system-ui, sans-serif; width: 1660px; }}
      h2 {{ font-size: 17px; font-weight: 600; margin: 30px 0 14px; }}
      .reihe {{ display: flex; gap: 18px; }}
      figure {{ margin: 0; }}
      img {{ width: 300px; display: block; }}
      figcaption {{ font-size: 12px; opacity: 0.6; margin-top: 6px; }}
    </style></head><body>{''.join(reihen)}</body></html>"""

    seite = ziel.parent / "_kontaktbogen.html"
    seite.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1660, "height": 1200})
        page.goto(seite.resolve().as_uri())
        page.wait_for_timeout(400)
        page.screenshot(path=str(ziel), full_page=True)
        browser.close()
    seite.unlink()


def _lokales_bild(pfad: Path) -> dict:
    """Beliebiges Bild von der Platte im Format, das render.py erwartet."""
    typ = mimetypes.guess_type(pfad.name)[0] or "image/jpeg"
    daten = base64.b64encode(pfad.read_bytes()).decode()
    return {"data_uri": f"data:{typ};base64,{daten}",
            "fotograf": "Beispielfoto", "seite": "https://www.pexels.com",
            "thema": "vorschau"}


# Abwurfflaeche fuer die Fotovarianten, solange kein echtes Bild da ist. Ohne
# das koennte die Vorschau 1d, 1e und 1f gar nicht zeigen: ohne Pexels-Key
# faellt die Ziehung sonst auf die fotolosen Varianten zurueck.
PLATZHALTER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350"'
    ' viewBox="0 0 1080 1350" preserveAspectRatio="none">'
    '<rect width="1080" height="1350" fill="#B9BDC0"/>'
    '<path d="M0 0 L1080 1350 M1080 0 L0 1350" stroke="#FAFAF8"'
    ' stroke-width="6" fill="none"/></svg>')


def _platzhalter() -> dict:
    # Base64 statt roher SVG-Quelltext im data:-URI: die Anfuehrungszeichen und
    # spitzen Klammern darin muessten sonst einzeln maskiert werden, und ein
    # Zeichen zu wenig heisst nicht "haesslich", sondern "Bild laedt nicht".
    daten = base64.b64encode(PLATZHALTER.encode()).decode()
    return {"data_uri": f"data:image/svg+xml;base64,{daten}",
            "fotograf": "Platzhalter", "seite": "https://www.pexels.com",
            "thema": "vorschau"}


def _bilder_festlegen(bild: dict) -> None:
    """Haengt die Bildsuche ab: kein Netz, kein Key, immer dasselbe Bild.

    render.py fragt in zwei Schritten (erst das Thema, dann das Foto in der
    Ausrichtung, die die gezogene Variante braucht) - beide Schritte werden
    hier ersetzt, sonst haengt die Vorschau doch wieder an Pexels.
    """
    bilder.thema = lambda item, slides: {"thema": "vorschau",
                                         "suche": "vorschau"}
    bilder.hole = lambda thema, ausrichtung="landscape": bild
    bilder.finde = lambda item, slides, *a, **k: bild


def main() -> None:
    # Ohne Pexels-Key laesst sich der Bildrahmen sonst nicht beurteilen:
    #   python preview_design.py pfad/zum/foto.jpg
    if len(sys.argv) > 1:
        pfad = Path(sys.argv[1])
        _bilder_festlegen(_lokales_bild(pfad))
        print(f"  = Vorschau mit festem Foto: {pfad}")
    else:
        _bilder_festlegen(_platzhalter())

    if ZIEL.exists():
        shutil.rmtree(ZIEL)
    ZIEL.mkdir(parents=True)

    varianten = [("lang", "5 Slides, Balken, Muster 4a", BEISPIEL)]

    # Dasselbe Karussell mit namentlicher Abstimmung: Slide 2 wird zum
    # Sitzbogen, der Fuss nennt die Wahlperiode.
    varianten.append((
        "bogen", "mit namentlicher Abstimmung (Sitzbogen)",
        {"item": {**BEISPIEL["item"], "abstimmung": ABSTIMMUNG},
         "slides": BEISPIEL["slides"]}))

    for name, folgen in FOLGEN_VARIANTEN.items():
        varianten.append((
            name, f"Folgen-Muster {name}",
            {"item": BEISPIEL["item"],
             "slides": {**BEISPIEL["slides"], "folgen": folgen}}))

    # Profil-Karussells haben weder Begriffskarte noch Folgen-Slide - der
    # Farbwechsel muss auch mit vier Slides aufgehen.
    varianten.append((
        "kurz", "4 Slides (Profil, ohne Begriff und Folgen)",
        {"item": BEISPIEL["item"],
         "slides": {k: v for k, v in BEISPIEL["slides"].items()
                    if k not in ("sowhat", "begriff", "folgen")}}))

    # Die sechs Cover-Architekturen. Erzwungen, nicht gezogen: eine Vorschau,
    # die wuerfelt, zeigt bei jedem Aufruf etwas anderes. Bei 1c und 1e steht
    # das Cover auf hellem Grund, das Deck dahinter wechselt entsprechend mit.
    for kennung in cover.VARIANTEN:
        varianten.append((
            kennung, f"Cover {kennung} ({cover.VARIANTEN[kennung]})",
            {"item": BEISPIEL["item"], "slides": BEISPIEL["slides"],
             "cover": kennung}))

    original = render.OUT
    gerendert = []
    try:
        render.OUT = ZIEL
        for name, titel, karussell in varianten:
            pfade = render.build_carousel(karussell, name)
            # build_carousel legt nach OUT/karussell_<n>/ ab - handlicher
            # umbenennen, damit der Kontaktbogen lesbare Namen zeigt.
            (ZIEL / f"karussell_{name}").rename(ZIEL / name)
            seiten = [ZIEL / name / p.name for p in pfade]
            # Bei den Cover-Gruppen interessiert im Kontaktbogen nur Slide 1
            # plus Slide 2 - dort sieht man, ob der Grundwechsel aufgeht.
            gerendert.append((titel, seiten[:2] if "cover" in karussell
                              else seiten))
    finally:
        render.OUT = original

    _kontaktbogen(gerendert, ZIEL / "uebersicht.png")

    print(f"  = Vorschau in {ZIEL}/ - Kontaktbogen: {ZIEL}/uebersicht.png")


if __name__ == "__main__":
    main()
