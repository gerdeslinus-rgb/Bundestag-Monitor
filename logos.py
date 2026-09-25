"""Logos von Parteien, Unternehmen, Verbaenden - nur von Wikimedia Commons.

Abgestimmt am 25.09.2026: Logos kommen AUSSCHLIESSLICH aus Commons (ueber
Wikidata P154), weil dort Lizenz und Urheber je Datei dokumentiert sind.
Keine Website-Favicons, kein Logo-Dienst. Folge: Wer sein Logo nicht frei
lizenziert hat (Eintracht Frankfurt, die meisten Vereinswappen), bekommt
keins - die Karte zeigt dann nur den Namen, ohne Platzhalter.

Ablauf je Name:
1. data/logos/logos.json - Handliste, Name -> Commons-Datei (oder null fuer
   "bewusst keins"), oder {"datei": ..., "kachel": false} fuer Logos mit
   eigener Flaeche (Gruene: Sonnenblume auf Tannengruen) - die bekommen
   keine weisse Kachel, sonst steht ein weisser Rand drumherum.
   Parteien stehen dort fest.
2. Wikidata-Suche nach dem Namen, nur ein Treffer, dessen Bezeichnung oder
   Alias wirklich zum Namen passt, kein Mensch (P31 = Q5). Davon P154.
3. Commons: Lizenz muss frei sein (Public domain, CC0, CC BY, CC BY-SA).

Ergebnis und Fehlschlag landen im Cache (data/logos/cache.json); ein
Fehlschlag wird nach CACHE_TAGE erneut versucht. Jeder Netzfehler endet in
"kein Logo" - der Lauf geht weiter.
"""

import base64
import json
import re
import time
from datetime import date
from pathlib import Path

import requests

ORDNER = Path("data/logos")
HANDLISTE = ORDNER / "logos.json"
CACHE = ORDNER / "cache.json"
CACHE_TAGE = 30

UA = {"User-Agent": "politik-digest/1.0 (gerdeslinus@gmail.com)"}
WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"

FREI = re.compile(r"^(public domain|pd\b.*|cc0.*|cc by(-sa)? [0-9.]+.*)$", re.I)

_RECHTSFORM = re.compile(
    # Lookarounds statt \b: nach "e.V." am Ende steht keine Wortgrenze.
    r"(?<!\w)(gmbh\s*&\s*co\.?\s*kg|ggmbh|gmbh|mbh|ag|se|kgaa|kg|ohg|gbr|e\.\s?v\.|ev|eg|"
    r"aktiengesellschaft|fussball|fußball)(?!\w)\.?", re.I)


def _woerter(text: str) -> set:
    text = _RECHTSFORM.sub(" ", text.lower())
    return set(re.findall(r"[a-zäöüß0-9]{2,}", text))


def _slug(name: str) -> str:
    s = name.lower().translate(str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def _json(pfad: Path) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _get(url: str, **params) -> dict:
    params["format"] = "json"
    for versuch in range(3):
        r = requests.get(url, params=params, headers=UA, timeout=30)
        if r.status_code == 429:
            time.sleep(3 * (versuch + 1))
            continue
        r.raise_for_status()
        return r.json()
    return {}


def _passt(name: str, treffer: dict) -> bool:
    """Die Wikidata-Suche findet zu "BSW" auch einen Bahnhof. Gezaehlt wird
    nur, was wirklich zum Namen passt: alle Woerter der gefundenen
    Bezeichnung stehen im Namen oder umgekehrt."""
    gesucht = _woerter(name)
    gefunden = _woerter((treffer.get("match") or {}).get("text") or treffer.get("label", ""))
    return bool(gesucht and gefunden) and (gefunden <= gesucht or gesucht <= gefunden)


def _suchnamen(name: str) -> list:
    """Erst der Name wie gemeldet, dann ohne Rechtsform und Klammer - die
    Wikidata-Suche findet "Campact e.V." nicht, "Campact" schon."""
    kurz = re.sub(r"\([^)]*\)", " ", name)
    kurz = " ".join(_RECHTSFORM.sub(" ", kurz).split()).strip(" ,-")
    return [name] + ([kurz] if kurz and kurz.lower() != name.lower() else [])


def _datei_zu(name: str) -> str | None:
    """Commons-Dateiname des Logos laut Wikidata, oder None."""
    suche = [t for n in _suchnamen(name)
             for t in _get(WIKIDATA, action="wbsearchentities", search=n,
                           language="de", uselang="de", limit=3).get("search", [])]
    # Genaue Treffer vor Teiltreffern: zu "Campact e.V." findet die Suche
    # auch "Campact DZ 31934" (ohne Logo) - der darf nicht zuerst drankommen.
    genau = lambda t: _woerter((t.get("match") or {}).get("text") or t.get("label", "")) \
        != _woerter(name)
    for treffer in sorted((t for t in suche if _passt(name, t)), key=genau):
        claims = _get(WIKIDATA, action="wbgetclaims", entity=treffer["id"]).get("claims", {})
        if any((c["mainsnak"].get("datavalue") or {}).get("value", {}).get("id") == "Q5"
               for c in claims.get("P31", [])):
            continue
        # Ein Logo mit Enddatum (P582) ist ein altes - das aktuelle zuerst.
        logos = sorted(claims.get("P154", []),
                       key=lambda c: "P582" in (c.get("qualifiers") or {}))
        for c in logos:
            wert = (c["mainsnak"].get("datavalue") or {}).get("value")
            if wert:
                return wert
        return None      # passender Eintrag ohne Logo: nicht weitersuchen
    return None


def _laden(datei: str, von_hand: bool = False) -> dict | None:
    """Datei von Commons holen, nur mit freier Lizenz.

    Automatisch gefunden zaehlt nur eine SVG: das ist fast immer die echte
    Wort-/Bildmarke. Als JPG haengen an Wikidata oft Scans alter Signets
    (S. Fischer: eine Eckmann-Vignette von 1900). Rasterbilder nur aus der
    Handliste."""
    seiten = _get(COMMONS, action="query", titles=f"File:{datei}", prop="imageinfo",
                  iiprop="extmetadata|url|mime", iiurlwidth=256).get("query", {}).get("pages", {})
    info = ((list(seiten.values()) or [{}])[0].get("imageinfo") or [None])[0]
    if not info:
        return None
    meta = info.get("extmetadata") or {}
    lizenz = re.sub(r"<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", "")).strip()
    if not FREI.match(lizenz):
        print(f"    - Logo {datei}: Lizenz '{lizenz}' nicht frei")
        return None
    # Bei Public domain ist keine Nennung noetig; bei CC BY schon. "Unknown
    # author" steht in manchen Dateien doppelt - dann lieber gar keinen.
    autor = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", ""))
    autor = autor.strip().splitlines()[0].strip() if autor.strip() else ""
    if "unknown author" in autor.lower():
        autor = ""
    svg = info.get("mime") == "image/svg+xml"
    if not svg and not von_hand:
        print(f"    - Logo {datei}: kein SVG, nur per Handliste")
        return None
    url = info["url"] if svg else (info.get("thumburl") or info["url"])
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    endung = "svg" if svg else "png"
    ORDNER.mkdir(parents=True, exist_ok=True)
    pfad = ORDNER / f"{_slug(datei.rsplit('.', 1)[0])}.{endung}"
    pfad.write_bytes(r.content)
    return {"datei": datei, "pfad": pfad.name, "lizenz": lizenz,
            "autor": autor[:120], "seite": info.get("descriptionurl", "")}


def logo(name: str) -> dict | None:
    """{data_uri, credit, seite} oder None.

    Nie eine Ausnahme: ein fehlendes Logo ist kein Fehler."""
    name = " ".join((name or "").split())
    if not name:
        return None
    cache = _json(CACHE)
    eintrag = cache.get(name)
    heute = date.today().toordinal()
    try:
        if not eintrag or (eintrag.get("pfad") is None
                           and heute - eintrag.get("stand", 0) > CACHE_TAGE):
            hand = _json(HANDLISTE)
            von_hand = name in hand
            datei = hand[name] if von_hand else _datei_zu(name)
            if isinstance(datei, dict):
                datei = datei.get("datei")
            geladen = _laden(datei, von_hand) if datei else None
            eintrag = {**(geladen or {"pfad": None}), "stand": heute}
            cache[name] = eintrag
            ORDNER.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"    - Logo fuer {name} nicht geholt: {exc}")
        return None

    if not eintrag.get("pfad") or not (ORDNER / eintrag["pfad"]).exists():
        return None
    pfad = ORDNER / eintrag["pfad"]
    mime = "image/svg+xml" if pfad.suffix == ".svg" else "image/png"
    daten = base64.b64encode(pfad.read_bytes()).decode("ascii")
    autor = (f"{eintrag['autor']}, " if eintrag.get("autor")
             and eintrag["lizenz"].lower().startswith("cc by") else "")
    eigen = _json(HANDLISTE).get(name)
    kachel = not (isinstance(eigen, dict) and eigen.get("kachel") is False)
    return {"data_uri": f"data:{mime};base64,{daten}", "kachel": kachel,
            "credit": f"Logo {name}: {autor}{eintrag['lizenz']}, via Wikimedia Commons",
            "seite": eintrag.get("seite", "")}
