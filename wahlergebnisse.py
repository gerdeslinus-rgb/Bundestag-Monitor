"""Nachschlagefunktion fuer Bundestagswahl-2025-Ergebnisse (Bundeswahlleiterin
Open Data, Lizenz dl-de/by-2.0).

Bewusst KEINE collect()-Quelle: Wahlergebnisse aendern sich nicht taeglich,
sie sind Kontext fuer Portraits/Hintergrund, keine Tagesmeldung. Einbindung
z. B. wenn du eine Portrait-Karte zu einem Wahlkreis oder einer/einem
Abgeordneten baust:

    from wahlergebnisse import wahlkreis_ergebnis
    erg = wahlkreis_ergebnis(1)              # per Nummer
    erg = wahlkreis_ergebnis("Flensburg")    # per (Teil-)Name
"""

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

CACHE_DIR = Path("data/wahlergebnisse")
# Endgueltige Ergebnisse aendern sich praktisch nie mehr - lange cachen,
# um die Bundeswahlleiterin nicht bei jedem Aufruf neu zu belasten.
CACHE_MAX_AGE_DAYS = 30
# Die MdB-Liste aendert sich dagegen laufend (Nachruecker, Ruecktritte) -
# kuerzer cachen als die Wahlergebnisse selbst.
MDB_CACHE_MAX_AGE_DAYS = 7

WKR_NAMEN_URL = ("https://www.bundeswahlleiterin.de/dam/jcr/"
                  "17e066f6-a0af-42df-a5d2-365dc87769ab/btw25_wahlkreisnamen_utf8.csv")
KERG2_URL = ("https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/"
             "opendata/btw25/csv/kerg2.csv")
ERGEBNIS_SEITE = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse.html"
MDB_INDEX_URL = "https://www.bundestag.de/xml/v2/mdb/index.xml"

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "politik-digest/1.0 (+kontakt@example.de)"),
}


def _cached(url: str, filename: str, max_age_days: int = CACHE_MAX_AGE_DAYS) -> str:
    """Laedt eine Datei und cached sie lokal unter data/wahlergebnisse/."""
    path = CACHE_DIR / filename
    if path.exists():
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age < timedelta(days=max_age_days):
            return path.read_text(encoding="utf-8")

    resp = requests.get(url, headers=UA, timeout=60)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _load_wahlkreisnamen() -> dict:
    text = _cached(WKR_NAMEN_URL, "wahlkreisnamen.csv")
    rows = [r for r in text.splitlines() if r and not r.startswith("#")]
    reader = csv.DictReader(rows, delimiter=";")
    return {r["WKR_NR"]: r for r in reader}


def _load_mdb_index() -> dict:
    """Aktuelle Mitglieder des Bundestages je Wahlkreis (bundestag.de, kein
    Key noetig). Liefert echte Namen - im Gegensatz zu kerg2.csv, das nur
    Parteien fuehrt. Deckt aber nur ab, wer tatsaechlich einen Sitz hat:
    Direktmandats-Gewinner:innen UND Personen, die ueber die Landesliste
    eingezogen sind, aber persoenlich in diesem Wahlkreis angetreten sind.
    Kandidat:innen ohne Sitz (verloren und keine Listenabsicherung) fehlen -
    dafuer gibt es keine offene, maschinenlesbare Quelle.
    """
    text = _cached(MDB_INDEX_URL, "mdb_index.xml", MDB_CACHE_MAX_AGE_DAYS)
    by_wkr: dict = {}
    for fraktion, body in re.findall(r'<mdb fraktion="([^"]*)">(.*?)</mdb>', text, re.DOTALL):
        wkr_match = re.search(r"<mdbWahlkreisNummer>(\d+)</mdbWahlkreisNummer>", body)
        if not wkr_match:
            continue
        name_match = re.search(r'<mdbName status="([^"]*)">([^<]*)</mdbName>', body)
        gewaehlt_match = re.search(r"<mdbGewaehlt>([^<]*)</mdbGewaehlt>", body)
        by_wkr.setdefault(wkr_match.group(1), []).append({
            "name": name_match.group(2) if name_match else "",
            "status": name_match.group(1) if name_match else "",
            "fraktion": fraktion,
            "gewaehlt": gewaehlt_match.group(1) if gewaehlt_match else "",
        })
    return by_wkr


def _load_kerg2() -> list:
    text = _cached(KERG2_URL, "kerg2.csv")
    lines = text.splitlines()
    header_idx = next(i for i, l in enumerate(lines) if l.startswith("Wahlart;"))
    reader = csv.DictReader(lines[header_idx:], delimiter=";")
    return [r for r in reader if r.get("Gebietsart") == "Wahlkreis"]


def wahlkreis_suchen(name: str) -> str | None:
    """Findet die Wahlkreisnummer per (Teil-)Namen, z. B. "Flensburg"."""
    name = name.lower()
    for nr, row in _load_wahlkreisnamen().items():
        if name in row["WKR_NAME"].lower():
            return nr
    return None


def _stimmen(rows: list, stimme: str) -> list:
    out = []
    for r in rows:
        if r.get("Stimme") != stimme:
            continue
        if r.get("Gruppenart") not in ("Partei", "Einzelbewerber/Wählergruppe"):
            continue
        prozent = (r.get("Prozent") or "").replace(",", ".")
        if not prozent:
            continue
        out.append({
            "partei": r["Gruppenname"],
            "prozent": round(float(prozent), 2),
            "stimmen": int(r.get("Anzahl") or 0),
        })
    return sorted(out, key=lambda x: -x["prozent"])


def wahlkreis_ergebnis(wahlkreis) -> dict | None:
    """Bundestagswahl-2025-Ergebnis eines Wahlkreises, inkl. echter Namen.

    wahlkreis: Nummer (int/str, z. B. 1 oder "001") oder Name/Teilname
    (str, z. B. "Flensburg"). None, wenn nichts gefunden wurde.

    "gewinner_erststimme" ist die Partei mit den meisten Erststimmen - aus
    kerg2.csv, das keine Kandidatennamen fuehrt, nur Parteien.
    "mdb_direktmandat" ist der/die tatsaechliche Sitzinhaber:in mit echtem
    Namen (aus der MdB-Liste von bundestag.de). Das muss NICHT dieselbe
    Partei sein wie gewinner_erststimme: seit der Wahlrechtsreform 2023
    bekommt eine Partei nur so viele Sitze, wie ihr laut Zweitstimme im
    Land zustehen (Zweitstimmendeckung) - Erststimmen-Sieger:innen ohne
    ausreichende Zweitstimmendeckung bleiben ohne Mandat. Bei der BTW 2025
    betraf das 21 der 299 Wahlkreise, bei denen "mdb_direktmandat" deshalb
    None ist, obwohl es einen Erststimmen-Sieger gab.
    "mdb_weitere" listet andere aktuelle MdBs, die in diesem Wahlkreis
    persoenlich angetreten, aber ueber die Landesliste eingezogen sind.
    Kandidat:innen ganz ohne Sitz (verloren, keine Listenabsicherung)
    fehlen ueberall - dafuer gibt es keine offene Quelle.
    """
    if isinstance(wahlkreis, str) and not wahlkreis.strip().isdigit():
        nr = wahlkreis_suchen(wahlkreis)
    else:
        nr = str(wahlkreis).zfill(3)
    if nr is None:
        return None

    namen = _load_wahlkreisnamen().get(nr)
    if not namen:
        return None

    rows = [r for r in _load_kerg2() if r.get("Gebietsnummer") == nr]
    erststimme = _stimmen(rows, "1")
    zweitstimme = _stimmen(rows, "2")

    mdbs = _load_mdb_index().get(nr, [])
    direktmandat = next((m for m in mdbs if m["gewaehlt"] == "direkt" and m["status"] == "Aktiv"), None)
    weitere = [m for m in mdbs if m is not direktmandat]

    return {
        "wahlkreis_nr": nr,
        "wahlkreis_name": namen["WKR_NAME"],
        "land": namen["LAND_NAME"],
        "erststimme": erststimme,
        "zweitstimme": zweitstimme,
        "gewinner_erststimme": erststimme[0] if erststimme else None,
        "mdb_direktmandat": direktmandat,
        "mdb_weitere": weitere,
        "quelle": "Bundeswahlleiterin, Bundestagswahl 2025 (endgueltiges Ergebnis); "
                  "MdB-Zuordnung: bundestag.de",
        "url": ERGEBNIS_SEITE,
    }
