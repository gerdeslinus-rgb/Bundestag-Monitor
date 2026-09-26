"""Wer wie gestimmt hat - fuer den Sitzbogen auf Slide 2, noch am Sitzungstag.

Zwei Wege, beide ohne Modell (QUELLEN.md, Abschnitte 3 und 7):

1. Namentliche Abstimmung: die Abstimmungsliste des Bundestages mit einer
   XLSX je Abstimmung, eine Zeile je Abgeordnetem. Sie steht am selben Tag
   online - das Plenarprotokoll, aus dem abstimmung.py liest, erst am
   naechsten Morgen. Zugeordnet wird deterministisch: gleiches Datum, und
   Ja- und Nein-Zahl stehen woertlich im Artikel (Tankrabatt 25.09.2026:
   434 und 128, XLSX 20260925_2 - exakt). Stehen mehrere Abstimmungen des
   Tages im Artikel (Tankrabatt plus Entschliessungsantrag), gewinnt die,
   deren Titel zur Ueberschrift passt.

2. Handzeichen: die meisten Gesetze. Dann gibt es keine Einzelstimmen, nur
   den Satz der Redaktion, welche Fraktion wofuer war ("Dafuer stimmten
   CDU/CSU und SPD, dagegen die AfD. Die Linke enthielt sich."). Daraus wird
   ein Bogen nach Fraktionspositionen - ausdruecklich als Handzeichen
   beschriftet, ohne Zahlen, die es nicht gibt. Laesst sich nicht JEDE
   Fraktion sicher zuordnen, gibt es keinen Bogen: lieber das Balkendiagramm
   als ein Bogen, der eine Fraktion falsch einfaerbt.

Beides liefert dieselbe Struktur wie abstimmung.aus_protokoll(), damit
sitzbogen.bogen() und sources.abstimmung_als_text() nichts unterscheiden
muessen.
"""

import io
import re
from datetime import date

import requests

import config

UA = {"User-Agent": "Mozilla/5.0 politik-digest/1.0"}

# XLSX-Schreibweise -> Protokollschreibweise (config.FRAKTION_ALIAS kennt die).
_XLSX_FRAKTION = {"BÜ90/GR": "BÜNDNIS 90/DIE GRÜNEN", "CDU/CSU": "CDU/CSU",
                  "SPD": "SPD", "AfD": "AfD", "Die Linke": "Die Linke"}

_MONATSNR = {m: i for i, m in enumerate(
    ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
     "September", "Oktober", "November", "Dezember"], start=1)}


# --- 1. Namentliche Abstimmung ---------------------------------------------

def _liste() -> list:
    """Die juengsten Eintraege der Abstimmungsliste: Datum, Titel, XLSX."""
    resp = requests.get(config.ABSTIMMUNGSLISTE, headers=UA, timeout=30,
                        params={"limit": 30, "offset": 0, "noFilterSet": "true"})
    resp.raise_for_status()
    eintraege = []
    for zeile in re.findall(r"<tr.*?</tr>", resp.text, re.DOTALL):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", zeile)).strip()
        datum = re.match(r"(\d{1,2})\. (\w+) (\d{4})", text)
        xlsx = re.search(r'href="([^"]+\.xlsx)"', zeile)
        if not (datum and xlsx and datum.group(2) in _MONATSNR):
            continue
        url = xlsx.group(1)
        eintraege.append({
            "datum": date(int(datum.group(3)), _MONATSNR[datum.group(2)],
                          int(datum.group(1))),
            "titel": re.sub(r"\s*PDF.*$", "", text[datum.end():]).strip(),
            "xlsx": url if url.startswith("http") else config.TEXTARCHIV_BASIS + url,
        })
    return eintraege


def xlsx_ergebnis(inhalt: bytes) -> dict:
    """Eine Abstimmungs-XLSX als Ergebnis im Format von aus_protokoll()."""
    import openpyxl     # nur hier gebraucht - der Rest laeuft ohne

    blatt = openpyxl.load_workbook(io.BytesIO(inhalt), read_only=True).active
    zeilen = list(blatt.iter_rows(values_only=True))
    spalte = {name: i for i, name in enumerate(zeilen[0])}
    fraktionen, summe = {}, {"ja": 0, "nein": 0, "enthalten": 0}
    for z in zeilen[1:]:
        roh = str(z[spalte["Fraktion/Gruppe"]] or "")
        name = _XLSX_FRAKTION.get(roh, roh)
        stimmen = fraktionen.setdefault(name, {"ja": 0, "nein": 0, "enthalten": 0})
        for feld, schluessel in (("ja", "ja"), ("nein", "nein"),
                                 ("Enthaltung", "enthalten")):
            if z[spalte[feld]]:
                stimmen[schluessel] += int(z[spalte[feld]])
                summe[schluessel] += int(z[spalte[feld]])
    return {"gesamt": sum(summe.values()), **summe,
            "angenommen": summe["ja"] > summe["nein"],
            "fraktionen": fraktionen}


def _zahl_im_text(zahl: int, text: str) -> bool:
    return re.search(rf"(?<![\d.,]){zahl}(?![\d.,]\d)", text) is not None


def _titelnaehe(a: str, b: str) -> int:
    woerter = lambda t: {w for w in re.findall(r"\w{5,}", t.lower())}
    return len(woerter(a) & woerter(b))


def namentlich(item: dict) -> dict | None:
    """Die namentliche Abstimmung zu einem Textarchiv-Artikel, falls es eine gab."""
    try:
        tag = date.fromisoformat(item.get("date", ""))
        kandidaten = [e for e in _liste() if e["datum"] == tag]
    except Exception as exc:
        print(f"    ! Abstimmungsliste nicht lesbar: {exc}")
        return None

    text = item.get("text", "")
    treffer = []
    for eintrag in kandidaten:
        try:
            resp = requests.get(eintrag["xlsx"], headers=UA, timeout=30)
            resp.raise_for_status()
            ergebnis = xlsx_ergebnis(resp.content)
        except Exception as exc:
            print(f"    ! Abstimmungs-XLSX nicht lesbar: {exc}")
            continue
        # Ja und Nein muessen woertlich im Artikel stehen. Enthaltungen
        # schreibt die Redaktion oft als "keine Enthaltungen" - dort nicht
        # zu verlangen, kostet keine Sicherheit: zwei dreistellige Zahlen am
        # selben Tag sind eindeutig genug.
        if _zahl_im_text(ergebnis["ja"], text) and _zahl_im_text(ergebnis["nein"], text):
            treffer.append((_titelnaehe(eintrag["titel"], item.get("title", "")),
                            eintrag, ergebnis))
    if not treffer:
        return None
    treffer.sort(key=lambda t: -t[0])
    _, eintrag, ergebnis = treffer[0]
    ergebnis.update({"datum": tag.strftime("%d.%m.%Y"), "art": "namentlich",
                     "protokoll": "", "quelle": f"Abstimmungsliste, {eintrag['titel']}"})
    print(f"    + Namentliche Abstimmung (Liste): {ergebnis['ja']} Ja / "
          f"{ergebnis['nein']} Nein - {eintrag['titel'][:50]}")
    return ergebnis


# --- 2. Handzeichen ----------------------------------------------------------

# Wie die Redaktion die Fraktionen nennt -> Roster-Schluessel (config).
_FRAKTION_WORT = [
    (r"CDU/CSU(?:-Fraktion)?|Unionsfraktion|der Union\b|Union\b", "CDU/CSU"),
    (r"SPD(?:-Fraktion)?", "SPD"),
    (r"AfD(?:-Fraktion)?", "AfD"),
    (r"Bündnis 90/Die Grünen|Grünen(?:-Fraktion)?|Grüne", "Gruene"),
    (r"Die Linke|Linksfraktion|Linken|Linke", "Linke"),
]
_KOALITION = ("CDU/CSU", "SPD")


def _fraktionen_in(teil: str) -> set:
    gefunden = set()
    for muster, key in _FRAKTION_WORT:
        if re.search(muster, teil):
            gefunden.add(key)
    if re.search(r"Koalitionsfraktionen|Koalition\b", teil):
        gefunden |= set(_KOALITION)
    return gefunden


# Die Satzbauten der Redaktion, die eine Position je Fraktion hergeben.
# "Dafuer stimmten" oder "Fuer den Gesetzentwurf stimmten"; die Gegenseite
# darf fehlen, wenn der naechste Satz die Enthaltungen nennt ("Dafuer
# stimmten die Koalitionsfraktionen. Die Oppositionsfraktionen ... enthielten
# sich." - Designrecht, 24.09.2026).
_DAFUER = re.compile(
    r"(?:Dafür|Für (?:den|die|das) [^.,]{3,80}?) stimmten (?P<ja>[^.]+?)"
    r"(?:, dagegen(?: stimmten?)? (?P<nein>[^.]+?))?"
    r"(?:, (?P<ent1>[^.]+?) enthielt(?:en)? sich)?\.\s*"
    r"(?:(?P<ent2>[^.]+?) enthielt(?:en)? sich\.)?")
_MIT_STIMMEN = re.compile(
    r"mit den Stimmen (?:von |der |des )?(?P<ja>[^.]+?) gegen die Stimmen "
    r"(?:von |der |des )?(?P<nein>[^.]+?)(?: bei Enthaltung (?:von |der |des )?"
    r"(?P<ent1>[^.]+?))?(?: (?:angenommen|abgelehnt|beschlossen)|\.)")
_UEBRIGE = re.compile(r"übrigen Fraktionen|aller anderen Fraktionen")


def handzeichen(text: str) -> dict | None:
    """Positionen der Fraktionen aus dem ersten Satz, der sie vollstaendig nennt.

    Nur ein Satz, der JEDE Fraktion des Rosters (ausser SSW) genau einer
    Seite zuordnet, zaehlt - sonst None. "Aller uebrigen Fraktionen" wird
    aufgeloest, wenn die andere Seite genannt ist.
    """
    roster = {f["key"] for f in config.BUNDESTAG_SITZE if f["key"] != "SSW"}
    for muster in (_DAFUER, _MIT_STIMMEN):
        for m in muster.finditer(text):
            teile = m.groupdict()
            seiten = {
                "dafür": _fraktionen_in(teile.get("ja") or ""),
                "dagegen": _fraktionen_in(teile.get("nein") or ""),
                "enthalten": _fraktionen_in((teile.get("ent1") or "")
                                            + " " + (teile.get("ent2") or "")),
            }
            for seite in ("dafür", "dagegen"):
                if _UEBRIGE.search(teile.get("ja" if seite == "dafür" else "nein") or ""):
                    andere = set().union(*(v for k, v in seiten.items() if k != seite))
                    seiten[seite] = roster - andere
            zugeordnet = [k for v in seiten.values() for k in v]
            if len(zugeordnet) != len(set(zugeordnet)) or set(zugeordnet) != roster:
                continue
            return _als_ergebnis(seiten, m.group(0))
    return None


def _als_ergebnis(seiten: dict, satz: str) -> dict:
    """Positionen als Ergebnis-Struktur. "ja" ist hier die Sitzzahl der
    Fraktion, nicht eine Stimmenzahl - deshalb "art": "handzeichen", und der
    Bogen zeigt dann keine Zahlen."""
    sitze = {f["key"]: f["sitze"] for f in config.BUNDESTAG_SITZE}
    namen = {"CDU/CSU": "CDU/CSU", "SPD": "SPD", "AfD": "AfD",
             "Gruene": "BÜNDNIS 90/DIE GRÜNEN", "Linke": "Die Linke"}
    fraktionen, position = {}, {}
    for seite, keys in seiten.items():
        for key in keys:
            fraktionen[namen[key]] = {"ja": sitze[key] if seite == "dafür" else 0,
                                      "nein": 0, "enthalten": 0}
            position[key] = seite
    ja = sum(sitze[k] for k in seiten["dafür"])
    nein = sum(sitze[k] for k in seiten["dagegen"])
    return {"art": "handzeichen", "fraktionen": fraktionen, "positionen": position,
            "angenommen": ja > nein, "satz": satz.strip(),
            "gesamt": 0, "ja": 0, "nein": 0, "enthalten": 0}


def fuer_textarchiv(item: dict) -> dict | None:
    """Namentlich, wenn es die Liste hergibt - sonst die Positionen aus dem Text."""
    if not config.ABSTIMMUNG_ENABLED:
        return None
    ergebnis = namentlich(item)
    if ergebnis:
        return ergebnis
    ergebnis = handzeichen(item.get("text", ""))
    if ergebnis:
        seiten = {}
        for key, seite in ergebnis["positionen"].items():
            seiten.setdefault(seite, []).append(key)
        print(f"    + Handzeichen: {seiten}")
    return ergebnis
