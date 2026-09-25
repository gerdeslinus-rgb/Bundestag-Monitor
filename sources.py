"""Holt Rohmaterial: Bundestag-DIP, Destatis, Lobbyregister, Parteispenden,
abgeordnetenwatch. Die Eigenheiten jeder Quelle stehen in QUELLEN.md."""

import csv
import hashlib
import html
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

import abstimmung
import config

SEEN_PATH = Path("data/seen.json")
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "politik-digest/1.0 (+kontakt@example.de)"),
    "Accept": "application/json, application/rss+xml, text/xml, */*",
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_seen() -> set:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text()))
    return set()


def save_seen(seen: set, keep: int = 4000) -> None:
    SEEN_PATH.parent.mkdir(exist_ok=True)
    SEEN_PATH.write_text(json.dumps(sorted(seen)[-keep:], indent=0))


def _clean(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _de_datum(d) -> str:
    """Datum im deutschen Format (TT.MM.JJJJ) fuer Fliesstext.

    Wichtig fuer die Beleg-Pruefung in llm.py: die dort generierten
    Meldungen schreiben Daten typischerweise als TT.MM.JJJJ, nicht als
    ISO-Datum. Wenn unser Quelltext das Datum nur als ISO enthaelt, findet
    verify() die Ziffernfolge nicht wieder und verwirft eine korrekte
    Meldung faelschlich als unbelegt. Das "date"-Feld der Items bleibt
    bewusst ISO (davon haengt die Sortierung/Anzeige an anderer Stelle ab) -
    nur der Fliesstext im "text"-Feld bekommt das deutsche Format.
    """
    return d.strftime("%d.%m.%Y")


def _ist_navigationsmuell(text: str) -> bool:
    """Erkennt Seitenmenues, die beim Nachladen statt des Inhalts kommen.

    Seiten, die ihren Inhalt erst per JavaScript aufbauen (z. B. die
    Vorgangsseiten von bundespuls.de), liefern im HTML nur das Geruest:
    Navigation, Vorschau-Listen, Teaser anderer Meldungen - gespickt mit
    Aufzaehlungszeichen. Das ist laenger als der RSS-Teaser und wuerde ihn
    deshalb verdraengen, ist aber inhaltlich wertlos und teilweise sogar
    irrefuehrend (es beschreibt fremde Vorgaenge).
    """
    return sum(text.count(z) for z in "◆•|·") > 3


def _fetch_full_text(url: str) -> str | None:
    """Holt bei duennen RSS-Teasern den Volltext von der Artikelseite nach.

    Hoeflich: gleicher User-Agent wie sonst, kurzer Timeout, ein Fehlschlag
    wird nur geloggt und stoppt den Lauf nicht - dann bleibt der Teaser stehen.
    """
    if not url:
        return None
    try:
        resp = requests.get(url, headers=UA, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    ! Volltext nicht ladbar ({url}): {exc}")
        return None

    html = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ",
                  resp.text, flags=re.IGNORECASE | re.DOTALL)
    text = _clean(html)
    if not text:
        return None
    if _ist_navigationsmuell(text):
        # Lieber der kurze, aber korrekte Teaser als ein langes Seitenmenue.
        return None
    return text[:config.FULLTEXT_MAX_CHARS]


def ensure_volltext(item: dict) -> dict:
    """Laedt fuer ein AUSGEWAEHLTES Thema den Artikeltext nach, falls duenn.

    Wird bewusst erst nach der Themenauswahl aufgerufen, nicht beim
    Einsammeln: nur die zwei gewaehlten Themen brauchen einen Text, der die
    Beleg-Pruefung in llm.verify_slides() ueberhaupt bestehen kann. Fuer alle
    136 Rohitems waere das ein Seitenaufruf pro Item - unnoetig und unhoeflich.

    Aendert das Item in place und gibt es zurueck. Schlaegt der Abruf fehl
    oder liefert er nicht mehr als der Teaser, bleibt der Teaser stehen: ein
    kurzer korrekter Text ist besser als gar keiner.
    """
    text = item.get("text", "")
    if len(text) >= config.VOLLTEXT_ZIEL_CHARS:
        return item

    # DIP-Vorgaenge haben keinen abrufbaren Artikel: dip.bundestag.de baut die
    # Seite erst per JavaScript auf, ein Abruf liefert nur das Geruest. Der
    # Volltext steht stattdessen in der Drucksache - und deren PDF ist auch
    # die ehrlichere Quellenangabe, weil man dort nachlesen kann.
    if item.get("dip_vorgang_id"):
        # Beide Schritte brauchen dieselben Vorgangspositionen - der Abruf
        # gehoert deshalb hierher und nicht doppelt in die Helfer.
        positionen = _dip_get("vorgangsposition",
                              **{"f.vorgang": item["dip_vorgang_id"]})
        voll, pdf = _dip_volltext(positionen)
        if voll and len(voll) > len(text):
            print(f"    + DIP-Volltext: {len(text)} -> {len(voll)} Zeichen")
            item["text"] = voll
            if pdf:
                item["url"] = pdf

        # Wer wie gestimmt hat, steht nicht in der Drucksache, sondern im
        # Plenarprotokoll - und nur bei namentlicher Abstimmung ueberhaupt.
        treffer = dip_abstimmung(item, positionen)
        if treffer:
            item["abstimmung"] = treffer
            item["text"] = (item["text"][:config.FULLTEXT_MAX_CHARS - 1200]
                            + " " + abstimmung_als_text(treffer))
        return item

    voll = _fetch_full_text(item.get("url", ""))
    if voll and len(voll) > len(text):
        print(f"    + Volltext: {len(text)} -> {len(voll)} Zeichen")
        item["text"] = voll
    return item


def fetch_destatis() -> list:
    """Die Pressemitteilungen aus dem Destatis-Feed, neueste zuerst.

    Der Feed haelt nur die letzten zehn - kein Zeitfenster noetig, das ist
    ohnehin weniger als eine Woche. Geliefert wird nur der Teaser; den
    sauberen Volltext samt Grafikdaten holt destatis_anreichern(), und zwar
    erst fuer die ausgewaehlten Meldungen, nicht fuer alle zehn.
    """
    try:
        resp = requests.get(config.DESTATIS_FEED, headers=UA, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        print(f"  ! Destatis nicht erreichbar: {exc}")
        return []

    items = []
    for entry in feed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        when = (datetime(*published[:6], tzinfo=timezone.utc) if published
                else datetime.now(timezone.utc))
        link = entry.get("link", "")
        items.append({
            "id": _hash(link + entry.get("title", "")),
            "source": "Statistisches Bundesamt",
            "weight": 3,
            "tier": "kern",
            "title": _clean(entry.get("title", "")),
            "text": _clean(entry.get("summary", "")),
            "url": link,
            "date": when.strftime("%Y-%m-%d"),
            "zeit": when.isoformat(),
        })
    # Neueste zuerst: die Auswahl nimmt die juengste alltagsnahe Meldung.
    items.sort(key=lambda i: i["zeit"], reverse=True)
    print(f"  + Destatis: {len(items)} Pressemitteilungen")
    return items


def _destatis_csv_saetze(csv_text: str) -> str:
    """Die Daten hinter einer Destatis-Grafik als Saetze fuer den Quelltext.

    Dieselbe Bauart wie abstimmung_als_text(): die Saetze entstehen
    deterministisch aus der amtlichen Datei, damit die Belegpruefung die
    Zahlen woertlich wiederfindet. Leere Zellen sind noch nicht erhobene
    Zeitraeume (z. B. die Monate nach dem aktuellen) - die fallen weg.
    """
    zeilen = [z for z in csv.reader(io.StringIO(csv_text.lstrip("﻿")),
                                    delimiter=";") if any(c.strip() for c in z)]
    if len(zeilen) < 2:
        return ""
    kopf = [k.strip() for k in zeilen[0]]
    saetze = []
    for zeile in zeilen[1:]:
        werte = [f"{kopf[i]}: {w.strip()}" for i, w in enumerate(zeile[1:], 1)
                 if i < len(kopf) and w.strip()]
        if werte:
            saetze.append(f"{zeile[0].strip()} - {', '.join(werte)}.")
    return " ".join(saetze)


def destatis_anreichern(item: dict) -> dict:
    """Volltext und Grafikdaten einer Destatis-Pressemitteilung.

    Der Text steht zwischen "Pressemitteilung Nr. ..." und "Kontakt fuer
    weitere Auskuenfte". Alles davor und danach ist Seitenrahmen ("Seite
    teilen", Navigation, Kontaktblock) - _fetch_full_text nahm das mit.

    Rund sechs von zehn Meldungen haben eine eingebettete Grafik, deren Daten
    als CSV an der Seite haengen (data-chart-csvurl). Das sind die amtlichen
    Zahlen als Zeitreihe; sie werden als Saetze angehaengt, damit das Modell
    das Diagramm daraus bauen kann und die Belegpruefung sie findet.
    """
    try:
        resp = requests.get(item["url"], headers=UA, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    ! Destatis-Seite nicht ladbar: {exc}")
        return item
    seite = resp.text

    nr = re.search(r"Pressemitteilung Nr\.\s*(\d+)", seite)
    start = seite.find("Pressemitteilung Nr.")
    ende = seite.find("Kontakt für weitere Auskünfte", start)
    if start > 0:
        teil = seite[start:ende if ende > start else None]
        teil = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", teil,
                      flags=re.IGNORECASE | re.DOTALL)
        text = _clean(html.unescape(teil))
        text = re.sub(r"\s*Lädt\.\.\.\s*", " ", text).strip()
        if len(text) > len(item.get("text", "")):
            item["text"] = text

    daten = []
    for url in re.findall(r'data-chart-csvurl="([^"]+)"', seite)[:2]:
        url = html.unescape(url)
        if url.startswith("/"):
            url = "https://www.destatis.de" + url
        try:
            antwort = requests.get(url, headers=UA, timeout=20)
            antwort.raise_for_status()
            saetze = _destatis_csv_saetze(antwort.content.decode("utf-8", "replace"))
        except Exception as exc:
            print(f"    ! Destatis-Grafikdaten nicht ladbar: {exc}")
            continue
        if saetze:
            daten.append("Daten der Grafik zur Pressemitteilung: " + saetze)
    if daten:
        item["text"] += "\n\n" + "\n\n".join(daten)

    if nr:
        item["source"] = f"Statistisches Bundesamt, Pressemitteilung Nr. {nr.group(1)}"
    item["text"] = item["text"][:config.FULLTEXT_MAX_CHARS]
    print(f"    + Destatis: {len(item['text'])} Zeichen, "
          f"{len(daten)} Grafik(en) mit Daten")
    return item


def _dip_get(pfad: str, **params):
    """Ein DIP-Aufruf. Gibt None zurueck, wenn etwas schiefgeht."""
    key = os.environ.get("DIP_API_KEY")
    if not key:
        return None
    params.update({"apikey": key, "format": "json"})
    # Plenarprotokolle sind gross - das hier geholte hatte 834.000 Zeichen.
    # Mit den ueblichen 30 Sekunden lief der Abruf regelmaessig in den Timeout.
    zeit = 120 if pfad.startswith("plenarprotokoll-text") else 30
    try:
        resp = requests.get(f"{config.DIP_BASE}/{pfad}", params=params,
                            headers=UA, timeout=zeit)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  ! DIP {pfad} nicht erreichbar: {exc}")
        return None


def _dip_text(vorgang: dict) -> str:
    """Quelltext aus den Vorgangsfeldern.

    Das abstract ist redaktionell geschrieben und nennt regelmaessig die
    geaenderten Paragraphen und konkrete Betraege - es ist damit besserer
    Belegtext als die meisten RSS-Teaser. Es enthaelt allerdings HTML
    (<br />, &quot;, <strong>), deshalb erst entschaerfen.
    """
    abstract = _clean(html.unescape(vorgang.get("abstract") or ""))
    titel = _clean(vorgang.get("titel", ""))

    satz = [f"{titel}."]
    if abstract:
        satz.append(abstract)

    stand = vorgang.get("beratungsstand")
    if stand:
        satz.append(f"Beratungsstand: {stand}.")
    initiative = ", ".join(vorgang.get("initiative") or [])
    if initiative:
        satz.append(f"Initiative: {initiative}.")
    sachgebiet = ", ".join(vorgang.get("sachgebiet") or [])
    if sachgebiet:
        satz.append(f"Sachgebiet: {sachgebiet}.")
    return " ".join(satz)


def fetch_dip(tage: int | None = None) -> list:
    """Entschiedene Gesetzgebungsvorgaenge aus dem DIP des Bundestages.

    Frueher wurden hier Drucksachen der letzten 30 Stunden geholt und als
    "text" ihr eigener Titel eingetragen. Ein solches Item konnte die
    Belegpruefung nie bestehen - der Beleg-Satz wurde gegen einen Text
    geprueft, der nur aus dem Titel bestand. Deshalb steht jetzt der Vorgang
    im Mittelpunkt: er hat abstract, Beratungsstand, Initiative und
    Sachgebiet. Den Volltext der zugehoerigen Drucksache holt erst
    ensure_volltext() nach, und nur fuer die tatsaechlich gewaehlten Themen.
    """
    if not (config.DIP_ENABLED and os.environ.get("DIP_API_KEY")):
        return []

    start = (datetime.now(timezone.utc)
             - timedelta(days=tage or config.GESETZE_LOOKBACK_DAYS)).date()
    # DIP liefert hoechstens 100 Vorgaenge je Seite. Ueber drei Wochen reicht
    # das meist, ueber drei Monate nicht (157 Vorgaenge am 25.09.2026) - ohne
    # Blaettern fielen Gesetze still weg. Blaettern per cursor, bis er sich
    # nicht mehr aendert.
    vorgaenge, cursor = [], None
    for _ in range(20):
        params = {"f.vorgangstyp": config.DIP_VORGANGSTYP,
                  "f.datum.start": start.isoformat()}
        if cursor:
            params["cursor"] = cursor
        data = _dip_get("vorgang", **params)
        if data is None:
            break
        vorgaenge += data.get("documents", [])
        if not data.get("documents") or data.get("cursor") in (None, cursor):
            break
        cursor = data.get("cursor")

    items = []
    for vorgang in vorgaenge:
        # Noch nicht entschieden heisst: es gibt nichts zu berichten ausser
        # dem Verfahren selbst - und genau das will dieser Ueberblick nicht.
        if vorgang.get("beratungsstand") not in config.DIP_BESCHLOSSEN:
            continue
        vid = str(vorgang.get("id"))
        items.append({
            "id": _hash("dipvorgang" + vid),
            "source": f"Bundestag, Vorgang {vorgang.get('beratungsstand', '')}",
            "weight": 5,
            "tier": "kern",
            "title": _clean(vorgang.get("titel", ""))[:120],
            "text": _dip_text(vorgang)[:config.FULLTEXT_MAX_CHARS],
            "url": f"https://dip.bundestag.de/vorgang/-/{vid}",
            "date": vorgang.get("datum", start.isoformat()),
            # Merker fuer ensure_volltext(): daran haengt der Volltext.
            "dip_vorgang_id": vid,
        })
    print(f"  + DIP: {len(items)} entschiedene Gesetzgebungsvorgaenge")
    return items


def _dip_volltext(positionen: dict) -> tuple:
    """Volltext und PDF-Adresse der massgeblichen Drucksache eines Vorgangs.

    Ausgewaehlt wird nach Drucksachentyp (config.DIP_DRUCKSACHE_REIHENFOLGE),
    nicht nach Datum. Ein Vorgang enthaelt neben dem Gesetzentwurf auch
    Stellungnahmen und Aenderungsantraege einzelner Fraktionen; die zuletzt
    eingegangene Drucksache ist regelmaessig gerade nicht das, was am Ende
    beschlossen wurde.

    Das PDF traegt oben den Vertriebsvermerk des Bundesanzeiger-Verlags -
    Kopfzeilen ohne Inhalt, die einen Beleg-Satz nur verwaessern wuerden.
    Sie werden abgeschnitten.
    """
    if not positionen:
        return "", ""

    ids = []
    for pos in positionen.get("documents", []):
        drs_id = (pos.get("fundstelle") or {}).get("id")
        if drs_id and str(drs_id) not in ids:
            ids.append(str(drs_id))

    # Erst alle Kandidaten einsammeln, dann nach Typ entscheiden.
    kandidaten = {}
    for drs_id in ids:
        doc = _dip_get(f"drucksache-text/{drs_id}")
        if not doc:
            continue
        text = _clean(doc.get("text") or "")
        if len(text) < config.VOLLTEXT_ZIEL_CHARS:
            continue
        kandidaten.setdefault(doc.get("drucksachetyp"), (text, doc))

    for typ in config.DIP_DRUCKSACHE_REIHENFOLGE:
        if typ not in kandidaten:
            continue
        text, doc = kandidaten[typ]
        schnitt = text.find("Drucksache")
        if 0 < schnitt < 600:
            text = text[schnitt:]
        print(f"    + DIP-Drucksache: {typ} {doc.get('dokumentnummer', '')}")
        return (text[:config.FULLTEXT_MAX_CHARS],
                (doc.get("fundstelle") or {}).get("pdf_url", ""))
    return "", ""


def dip_abstimmung(item: dict, positionen: dict) -> dict | None:
    """Namentliche Abstimmung zu einem DIP-Vorgang, falls es eine gab.

    Der Weg fuehrt ueber die Vorgangspositionen: jede Beschlussfassung nennt
    das Plenarprotokoll, in dem sie steht. Dessen Volltext wird nach dem
    Ankuendigungssatz durchsucht (siehe abstimmung.py) - nicht nach der
    Fundstelle, denn die Sitzungsleitung verkuendet Ergebnisse mitten in
    fremde Debatten hinein.

    Die meisten Gesetze werden per Handzeichen beschlossen. Dann gibt es
    schlicht keine Zahlen, und None ist die richtige Antwort.
    """
    if not (item.get("dip_vorgang_id") and config.ABSTIMMUNG_ENABLED
            and positionen):
        return None

    protokolle = []
    for pos in positionen.get("documents", []):
        fundstelle = pos.get("fundstelle") or {}
        if (pos.get("beschlussfassung")
                and fundstelle.get("dokumentart") == "Plenarprotokoll"
                and str(fundstelle.get("id")) not in protokolle):
            protokolle.append(str(fundstelle["id"]))

    for protokoll_id in protokolle:
        doc = _dip_get(f"plenarprotokoll-text/{protokoll_id}")
        if not (doc and doc.get("text")):
            continue
        treffer = abstimmung.aus_protokoll(doc["text"], item["title"])
        if treffer:
            treffer["protokoll"] = doc.get("dokumentnummer", "")
            treffer["datum"] = doc.get("datum", "")
            print(f"    + Namentliche Abstimmung: {treffer['ja']} Ja / "
                  f"{treffer['nein']} Nein (Protokoll {treffer['protokoll']})")
            return treffer
    return None


def abstimmung_als_text(treffer: dict) -> str:
    """Das Abstimmungsergebnis als Saetze fuer den Quelltext.

    Wird an item["text"] angehaengt, damit die Belegpruefung die Zahlen
    woertlich wiederfindet. Das ist kein Taschenspielertrick: die Saetze
    entstehen deterministisch aus dem amtlichen Protokoll, kein Modell ist
    daran beteiligt - dieselbe Bauart wie im Profil-Modus.
    """
    ergebnis = "angenommen" if treffer["angenommen"] else "abgelehnt"
    teile = [
        f"Namentliche Abstimmung am {treffer.get('datum', '')} "
        f"(Plenarprotokoll {treffer.get('protokoll', '')}): "
        f"{treffer['gesamt']} abgegebene Stimmen, davon {treffer['ja']} Ja, "
        f"{treffer['nein']} Nein und {treffer['enthalten']} Enthaltungen. "
        f"Die Vorlage wurde damit {ergebnis}."
    ]
    for fraktion, stimmen in sorted(treffer["fraktionen"].items()):
        teile.append(f"{fraktion}: {stimmen.get('ja', 0)} Ja, "
                     f"{stimmen.get('nein', 0)} Nein, "
                     f"{stimmen.get('enthalten', 0)} Enthaltungen.")
    return " ".join(teile)


# --- Lobbyregister -----------------------------------------------------------
#
# Zwei Zugaenge (Einzelheiten in QUELLEN.md): die Suche des Web-Frontends
# (sucheJson) und die API v2. Die Suche liefert Zaehler und kennt die
# Filter, die API den vollen Eintrag mit Personen und Regelungsvorhaben.

def lobby_suche(**params) -> list:
    """sucheJson mit Suchbegriff und/oder Filtern.

    Filter nur in der Form "filter[name][wert]": "true" - einfache Namen
    ignoriert der Server stillschweigend und liefert dann alle ~7.000
    Eintraege (17 MB). Deshalb wird geprueft, ob der Filter gegriffen hat,
    statt es zu hoffen.
    """
    try:
        resp = requests.get(config.LOBBYREGISTER_URL, params=params,
                            headers=UA, timeout=60)
        resp.raise_for_status()
        daten = resp.json()
    except Exception as exc:
        print(f"  ! Lobbyregister-Suche fehlgeschlagen: {exc}")
        return []
    such = daten.get("searchParameters", {})
    gefiltert = any(k.startswith("filter[") for k in params)
    if gefiltert and not (such.get("facets") or such.get("numberRanges")):
        print(f"  ! Lobbyregister hat den Filter ignoriert: {list(params)}")
        return []
    return daten.get("results", [])


def _lobby_api(pfad: str):
    key = os.environ.get("LOBBYREGISTER_API_KEY") or config.LOBBYREGISTER_API_KEY
    try:
        resp = requests.get(f"{config.LOBBYREGISTER_API}/{pfad}",
                            params={"format": "json"},
                            headers={**UA, "Authorization": f"ApiKey {key}"},
                            timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"    ! Lobbyregister-API {pfad} nicht ladbar: {exc}")
        return None


def lobby_eintrag(register_nr: str) -> dict | None:
    """Der volle Registereintrag aus der API v2 (Personen, Vorhaben, ...)."""
    return _lobby_api(f"registerentries/{register_nr}")


def lobby_statistik() -> dict:
    return _lobby_api("statistics/registerentries") or {}


def lobby_name(eintrag: dict) -> str:
    ident = eintrag.get("lobbyistIdentity") or {}
    name = ident.get("name") or " ".join(
        filter(None, [ident.get("firstName"), ident.get("lastName")]))
    return _clean(name)


def dip_drucksachen(vorgang_id: str) -> list:
    """Die Bundestags-Drucksachennummern eines Vorgangs ("21/6278").

    Ueber die Vorgangspositionen - die drucksache-Abfrage ignoriert den
    Filter f.vorgang und liefert dann die neuesten Drucksachen ueberhaupt.
    """
    positionen = _dip_get("vorgangsposition", **{"f.vorgang": vorgang_id}) or {}
    nummern = []
    for pos in positionen.get("documents", []):
        fund = pos.get("fundstelle") or {}
        nr = fund.get("dokumentnummer", "")
        if (fund.get("dokumentart") == "Drucksache" and fund.get("herausgeber") == "BT"
                and nr and nr not in nummern):
            nummern.append(nr)
    return nummern


# --- Parteispenden -----------------------------------------------------------

_PARTEI_KURZ = {"Bündnis 90/ Die Grünen": "Grüne", "Bündnis 90/Die Grünen": "Grüne",
                "Die Linke": "Linke", "Volt Deutschland": "Volt"}

# Woran eine Organisation zu erkennen ist. Alles andere gilt als Privatperson -
# lieber eine Firma zu vorsichtig behandeln als eine Person zu offen.
_ORG_MERKMALE = re.compile(
    r"(\b(GmbH|mbH|AG|Aktiengesellschaft|SE|KG|KGaA|OHG|GbR|eG|Ltd|Limited|"
    r"Inc|LLC|Holding|Stiftung|Verband|Verein|Gesellschaft|Gruppe|Group|Bank|"
    r"Campact|Institut|Partei)\b|e\.\s?V\.|S\.A\.|B\.V\.)")

# Anschrift am Ende des Spenderfelds: Strasse, Hausnummer, PLZ, Ort.
_ANSCHRIFT = re.compile(
    r"\s+((?:(?:Am|An der|An den|Auf der|Auf dem|Im|In der|Zum|Zur|Unter den|"
    r"Alt|Platz der|Hinter der|Vor dem)\s+)?\S+)\s+\d+\s*[a-zA-Z]?"
    r"(?:\s*[-/]\s*\d+\s*[a-zA-Z]?)?\s+\d{4,5}\s+\D+$")


def _spende_datum(text: str):
    """Eingangsdatum, auch bei Teilzahlungen ("18./20./24.10. 2025").
    Genommen wird der erste Tag - an dem hat die Spende begonnen."""
    m = re.search(r"(\d{1,2})\.(?:\s*/\s*\d{1,2}\.)*\s*(\d{1,2})\.\s*(\d{4})", text)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
    except ValueError:
        return None


def _betrag(text: str) -> float | None:
    zahl = re.search(r"\d[\d.]*(?:,\d+)?", text or "")
    if not zahl:
        return None
    return float(zahl.group(0).replace(".", "").replace(",", "."))


def parteispenden_jahr(jahr: int) -> list:
    """Alle Grossspenden (§ 25 PartG, ueber 35.000 Euro) eines Jahres.

    Das Spenderfeld enthaelt die Anschrift - bei Privatpersonen die
    Wohnadresse. Sie wird hier abgetrennt und nirgends weitergegeben.
    """
    url = f"{config.PARTEISPENDEN_URL}/{jahr}"
    try:
        resp = requests.get(url, headers=UA, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  ! Parteispenden {jahr} nicht erreichbar: {exc}")
        return []

    spenden = []
    for row in re.findall(r"<tr>((?:(?!<tr>).)*?)</tr>", resp.text, re.DOTALL):
        cells = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(cells) != 5:
            continue
        partei, betrag, spender, eingang, _anzeige = (
            _clean(html.unescape(c)).replace("\xad", "").replace("- ", "-")
            for c in cells)
        wert, datum = _betrag(betrag), _spende_datum(eingang)
        if wert is None or datum is None:
            print(f"    ! Spendenzeile nicht lesbar: {betrag} / {eingang}")
            continue
        name = _ANSCHRIFT.sub("", spender).strip() or spender
        spenden.append({
            "id": _hash("spende" + partei + betrag + spender + eingang),
            "partei": _PARTEI_KURZ.get(partei, partei),
            "betrag": wert,
            "spender": name,
            "organisation": bool(_ORG_MERKMALE.search(name)),
            "datum": datum,
            "jahr": jahr,
            "url": url,
        })
    return spenden


# --- abgeordnetenwatch -------------------------------------------------------

def aow(pfad: str, **params):
    """Ein Aufruf der abgeordnetenwatch-API, mit Ruecksicht aufs Rate-Limit.

    Schon zuegige Einzelabfragen enden in HTTP 429 mit leerem Body. Dann
    wird mit wachsender Pause wiederholt, statt den Lauf zu verlieren.
    """
    for versuch in range(5):
        try:
            resp = requests.get(f"https://www.abgeordnetenwatch.de/api/v2/{pfad}",
                                params=params, headers=UA, timeout=30)
            if resp.status_code == 429:
                time.sleep(3 * (versuch + 1))
                continue
            resp.raise_for_status()
            return resp.json().get("data")
        except Exception as exc:
            print(f"    ! abgeordnetenwatch {pfad}: {exc}")
            time.sleep(2)
    return None


def neben_zeitraum(e: dict) -> str:
    """Wofuer der gemeldete Betrag gilt. `interval` laut API-Doku:
    0 = einmalig, 1 = monatlich, 2 = jaehrlich. Ohne Intervall steht der
    Zeitraum oft in job_title_extra ("Einkommen im Jahr 2025") - das ist
    eine Jahressumme."""
    iv = str(e.get("interval") or "")
    if iv == "1":
        return "im Monat"
    if iv == "2" or re.search(r"im Jahr \d{4}", e.get("job_title_extra") or ""):
        return "im Jahr"
    if iv == "0":
        return "einmalig"
    return ""


def neben_jahreswert(e: dict) -> float:
    """Der Betrag aufs Jahr gerechnet, fuer jeden Vergleich: ein Monatsbetrag
    zaehlt zwoelffach. Linnemann meldete 11.227 Euro im Monat - roh gegen
    Jahressummen anderer verglichen, stand er auf Platz 51 statt weit vorn."""
    betrag = float(e.get("income") or 0)
    return betrag * 12 if str(e.get("interval") or "") == "1" else betrag


NEBEN_STATISTIK = Path("data/neben_statistik.json")
NEBEN_STATISTIK_TAGE = 7


def neben_statistik(periode: int = 161) -> dict:
    """Nebentaetigkeiten aller Abgeordneten einer Wahlperiode, je Mandat
    verdichtet: {mandat_id: {"n", "betrag", "max"}}.

    Fuer den Vergleich "diese Person gegen den Bundestag". Der Filter
    mandates[entity.parliament_period] greift serverseitig (WP 2025-2029:
    4.612 Meldungen am 25.09.2026, fuenf Seiten zu 1.000). Die Zahlen
    aendern sich schubweise, eine Woche Cache genuegt und schont das
    empfindliche Rate-Limit.
    """
    try:
        daten = json.loads(NEBEN_STATISTIK.read_text(encoding="utf-8"))
        # Version 3: "max" und "summe" aufs Jahr gerechnet (Monat x 12).
        if (daten.get("version") == 3 and daten.get("periode") == periode
                and (date.today() - date.fromisoformat(daten["stand"])).days
                < NEBEN_STATISTIK_TAGE):
            return daten
    except (OSError, ValueError, KeyError):
        pass

    # Eine Meldung nennt alle Mandate der Person, auch fruehere Wahlperioden
    # ("Merz (Bundestag 2021 - 2025)"). Gezaehlt wird nur das Mandat der
    # abgefragten Periode - sonst standen 1.205 "Abgeordnete" in der Liste.
    marke = {161: "Bundestag 2025 - 2029", 132: "Bundestag 2021 - 2025"}.get(periode, "")
    je, start = {}, 0
    while True:
        seite = aow("sidejobs", **{"mandates[entity.parliament_period]": periode},
                    range_start=start, range_end=1000)
        if seite is None:
            print("    ! Nebentaetigkeiten-Statistik unvollstaendig - ohne Vergleich")
            return {}
        for e in seite:
            betrag = neben_jahreswert(e)
            for m in e.get("mandates") or []:
                if marke not in m.get("label", ""):
                    continue
                z = je.setdefault(str(m["id"]), {"n": 0, "betrag": 0, "max": 0,
                                                 "summe": 0})
                z["n"] += 1
                z["betrag"] += 1 if betrag else 0
                z["max"] = max(z["max"], betrag)
                z["summe"] += betrag
        if len(seite) < 1000:
            break
        start += 1000
        time.sleep(1)

    daten = {"version": 3, "periode": periode, "stand": date.today().isoformat(),
             "meldungen": sum(z["n"] for z in je.values()), "je": je}
    NEBEN_STATISTIK.parent.mkdir(exist_ok=True)
    NEBEN_STATISTIK.write_text(json.dumps(daten, indent=0), encoding="utf-8")
    return daten


def mandat_in_periode(politiker_id: int, periode: int) -> int | None:
    """Mandats-ID einer Person in einer Wahlperiode (132 = 2021-2025)."""
    mandate = aow("candidacies-mandates", politician=politiker_id,
                  parliament_period=periode, type="mandate") or []
    return mandate[0]["id"] if mandate else None


def wikipedia_kurz(name: str) -> str:
    """Einleitung des deutschen Wikipedia-Artikels zu einer Organisation, oder "".

    Nur wenn der Artikeltitel wirklich zum Namen passt (gleiche Woerter ohne
    Rechtsform): ein falscher Artikel wuerde einer Organisation die
    Geschichte einer anderen zuschreiben.
    """
    import logos
    try:
        treffer = requests.get("https://de.wikipedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": name, "srlimit": 3,
            "format": "json"}, headers=UA, timeout=20).json()["query"]["search"]
        for t in treffer:
            titel = re.sub(r"\s*\([^)]*\)$", "", t["title"])
            if logos._woerter(titel) and logos._woerter(titel) <= logos._woerter(name):
                zusammen = requests.get(
                    "https://de.wikipedia.org/api/rest_v1/page/summary/"
                    + t["title"].replace(" ", "_"), headers=UA, timeout=20).json()
                return zusammen.get("extract", "")
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"    - Wikipedia zu {name}: {exc}")
    return ""


def prefilter(items: list, seen: set) -> list:
    """Deterministischer Vorfilter. Kein Modell, keine Kosten."""
    kept = []
    for item in items:
        if item["id"] in seen:
            continue
        haystack = (item["title"] + " " + item["text"]).lower()
        if any(bad in haystack for bad in config.BLOCKLIST):
            continue
        if not any(word in haystack for word in config.KEYWORDS):
            continue
        kept.append(item)

    kept.sort(key=lambda i: (-i["weight"], i["title"]))
    return kept[:40]


# Die Quellen haengen nicht voneinander ab und warten fast nur auf das
# Netz - nacheinander gelesen dauert das ueber 100 Sekunden, die praktisch
# vollstaendig Leerlauf sind. Bewusst wenige Arbeiter: es sind fremde, meist
# amtliche Server, und die Fetcher laden teilweise noch Artikelseiten nach.
_FETCHER = (fetch_destatis, fetch_dip)
COLLECT_WORKERS = 5


def collect_stufe(fetcher_namen: list, seen: set) -> list:
    """Liest nur die Fetcher einer Stufe und filtert vor.

    Gegenstueck zu collect(): dort werden alle Quellen auf einmal gelesen,
    hier nur die der aktuellen Stufe. Der Lauf steigt damit erst dann in die
    naechste, langsamere Quelle ein, wenn die vorige nichts hergegeben hat.
    """
    items = []
    with ThreadPoolExecutor(max_workers=COLLECT_WORKERS) as pool:
        futures = {pool.submit(globals()[n]): n for n in fetcher_namen}
        for future in as_completed(futures):
            try:
                items += future.result()
            except Exception as exc:
                print(f"  ! {futures[future]} fehlgeschlagen: {exc}")
    return prefilter(items, seen)


def collect() -> tuple:
    print("Quellen werden gelesen ...")
    seen = load_seen()

    raw = []
    with ThreadPoolExecutor(max_workers=COLLECT_WORKERS) as pool:
        futures = {pool.submit(f): f.__name__ for f in _FETCHER}
        for future in as_completed(futures):
            try:
                raw += future.result()
            except Exception as exc:
                # Eine tote Quelle darf den Lauf nicht kippen - genau wie in
                # den Fetchern selbst, die ihre Fehler schon einzeln abfangen.
                print(f"  ! {futures[future]} fehlgeschlagen: {exc}")

    filtered = prefilter(raw, seen)
    print(f"  = {len(raw)} roh, {len(filtered)} nach Vorfilter")
    return filtered, seen
