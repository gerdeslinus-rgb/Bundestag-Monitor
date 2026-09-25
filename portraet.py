"""Portraets fuer Personen-Karussells (Nebentaetigkeiten): freigestellt, in Farbe.

Zwei Teile:

* `portraet(name)` - zur Laufzeit. Liest das fertige PNG aus data/portraets/
  und liefert es als data-URI plus Bildnachweis. Kein Netz, kein Modell:
  fehlt die Datei, gibt es kein Portraet und das Cover bleibt typografisch.

* `python portraet.py [name-filter]` - einmalig, von Hand. Laedt das in
  data/portraets.json gewaehlte Commons-Bild und stellt es frei. Braucht
  rembg mit dem Modell "birefnet-portrait", das bewusst NICHT in
  requirements.txt steht: der Tageslauf soll kein 900-MB-Modell laden, nur
  um ein Bild zu verwenden, das sich innerhalb der Wahlperiode nicht aendert.

Die Auswahl je Person steht in data/portraets.json (Commons-Datei, Lizenz,
Autor). Kriterien: moeglichst neu, eine Person, kein Mikrofon vor dem
Gesicht, Oberkoerper sichtbar. Ein anderes Bild: Eintrag aendern, Skript fuer
diese Person neu laufen lassen.
"""

import base64
import json
import re
from pathlib import Path

AUSWAHL = Path("data/portraets.json")
ORDNER = Path("data/portraets")
UA = {"User-Agent": "politik-digest/1.0 (gerdeslinus@gmail.com)"}

# Auf der Karte ist das Bild hoechstens 1350 px hoch. Mehr kostet nur Platz
# im Repository.
MAX_HOEHE = 1400


def slug(name: str) -> str:
    s = name.lower().translate(str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _auswahl() -> dict:
    try:
        return json.loads(AUSWAHL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def portraet(name: str) -> dict | None:
    """{data_uri, credit, seite} oder None."""
    eintrag = _auswahl().get(name)
    pfad = ORDNER / f"{slug(name)}.png"
    if not eintrag or not pfad.exists():
        return None
    daten = base64.b64encode(pfad.read_bytes()).decode("ascii")
    return {"data_uri": f"data:image/png;base64,{daten}",
            "credit": f"Foto {name}: {eintrag['autor']}, {eintrag['lizenz']}, "
                      f"via Wikimedia Commons",
            "seite": eintrag["seite"]}


def _freistellen(filter_: str = "") -> None:
    import io
    import time

    import requests
    from PIL import Image
    from rembg import new_session, remove

    session = new_session("birefnet-portrait")
    ORDNER.mkdir(parents=True, exist_ok=True)
    for name, e in _auswahl().items():
        if filter_ and filter_.lower() not in name.lower():
            continue
        # Commons liefert nur feste Thumbnail-Groessen - 1600 gibt HTTP 400.
        url = re.sub(r"/\d+px-", "/1280px-", e["thumb"])
        for _ in range(4):
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(5)
        r.raise_for_status()
        bild = Image.open(io.BytesIO(r.content)).convert("RGB")
        frei = remove(bild, session=session, post_process_mask=True)
        # Auf die Person zuschneiden, unten buendig: der Oberkoerper laeuft
        # auf der Karte aus dem unteren Rand, darunter darf nichts stehen.
        box = frei.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
        if box:
            l, o, rr, u = box
            rand = int(0.02 * frei.width)
            frei = frei.crop((max(l - rand, 0), max(o - rand, 0),
                              min(rr + rand, frei.width), u))
        if frei.height > MAX_HOEHE:
            frei = frei.resize((round(frei.width * MAX_HOEHE / frei.height), MAX_HOEHE),
                               Image.LANCZOS)
        ziel = ORDNER / f"{slug(name)}.png"
        frei.save(ziel, optimize=True)
        print(f"  + {ziel} {frei.size}")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    _freistellen(sys.argv[1] if len(sys.argv) > 1 else "")
