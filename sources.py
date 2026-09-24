"""Holt Rohmaterial aus RSS-Feeds und der Bundestag-DIP-API."""

import hashlib
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from datetime import datetime, timedelta, timezone
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


def _fetch_feed_list(feeds: list) -> list:
    """Liest eine Liste von RSS-Feeds (gleiche Form wie RSS_SOURCES). Ein
    toter Feed stoppt den Lauf nicht. Wird von fetch_rss() und
    fetch_bundespuls() geteilt, da beide dieselbe Feed-Struktur haben."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.LOOKBACK_HOURS)
    items = []

    for src in feeds:
        try:
            resp = requests.get(src["url"], headers=UA, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as exc:
            print(f"  ! {src['name']} nicht erreichbar: {exc}")
            continue

        for entry in feed.entries:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                when = datetime(*published[:6], tzinfo=timezone.utc)
                if when < cutoff:
                    continue
            else:
                when = datetime.now(timezone.utc)

            body = _clean(entry.get("summary", "")) or _clean(entry.get("title", ""))
            link = entry.get("link", "")
            if len(body) < config.FULLTEXT_MIN_CHARS and link:
                full = _fetch_full_text(link)
                if full and len(full) > len(body):
                    body = full

            items.append({
                "id": _hash(entry.get("link", "") + entry.get("title", "")),
                "source": src["name"],
                "weight": src["weight"],
                "tier": src.get("tier", "kern"),
                "title": _clean(entry.get("title", "")),
                "text": body[:config.FULLTEXT_MAX_CHARS],
                "url": entry.get("link", ""),
                "date": when.strftime("%Y-%m-%d"),
            })
        print(f"  + {src['name']}: {len(feed.entries)} Eintraege")

    return items


def fetch_rss() -> list:
    """Liest die klassischen Behoerden-RSS-Feeds aus RSS_SOURCES."""
    return _fetch_feed_list(config.RSS_SOURCES)


def fetch_bundespuls() -> list:
    """Liest die Bundespuls-Aggregator-Feeds (Vorgaenge, Abstimmungen,
    Plenarprotokolle). Ergaenzt DIP/AOW um eine zweite, unabhaengige
    Quelle - Ueberschneidungen sind moeglich, das Vorfilter/Ranking
    filtert nicht inhaltlich auf Dopplungen, nur auf id."""
    if not config.BUNDESPULS_ENABLED:
        return []
    return _fetch_feed_list(config.BUNDESPULS_FEEDS)


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


def fetch_dip() -> list:
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
             - timedelta(days=config.GESETZE_LOOKBACK_DAYS)).date()
    data = _dip_get("vorgang", **{"f.vorgangstyp": config.DIP_VORGANGSTYP,
                                  "f.datum.start": start.isoformat()})
    if data is None:
        return []

    items = []
    for vorgang in data.get("documents", []):
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


def _aow_current_legislature(parliament_id: int) -> int | None:
    """Loest die aktuelle Wahlperioden-Id auf (aendert sich nach jeder Wahl).

    Die Poll-API filtert nicht mehr direkt nach Parlament, sondern nach
    field_legislature (Wahlperiode). Diese Id holen wir uns dynamisch, damit
    der Code nicht nach jeder Bundestagswahl von Hand angepasst werden muss.
    """
    try:
        resp = requests.get(f"https://www.abgeordnetenwatch.de/api/v2/parliaments/{parliament_id}",
                            headers=UA, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("current_project", {}).get("id")
    except Exception as exc:
        print(f"  ! Abgeordnetenwatch Wahlperiode nicht ermittelbar: {exc}")
        return None


def fetch_aow() -> list:
    """Namentliche Abstimmungen von abgeordnetenwatch.de (JSON, kein Key).

    Die Poll-API wird nach Datum absteigend sortiert. Wir nehmen die
    neuesten und behalten nur die innerhalb des Zeitfensters.
    """
    if not config.AOW_ENABLED:
        return []

    legislature = _aow_current_legislature(config.AOW_PARLIAMENT_ID)
    if legislature is None:
        return []

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=config.LOOKBACK_HOURS)).date()
    params = {
        "field_legislature": legislature,
        "range_end": 15,
        "sort_by": "field_poll_date",
        "sort_direction": "desc",
    }
    try:
        resp = requests.get("https://www.abgeordnetenwatch.de/api/v2/polls",
                            params=params, headers=UA, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        print(f"  ! Abgeordnetenwatch nicht erreichbar: {exc}")
        return []

    items = []
    for poll in data:
        ts = poll.get("field_poll_date")
        if ts:
            try:
                poll_date = datetime.fromisoformat(ts).date()
                if poll_date < cutoff:
                    continue
            except ValueError:
                poll_date = cutoff
        label = _clean(poll.get("label", ""))
        result = _clean(poll.get("field_accepted", "") and "angenommen" or "")
        items.append({
            "id": _hash("aow" + str(poll.get("id"))),
            "source": "Bundestag, namentliche Abstimmung (abgeordnetenwatch.de)",
            "weight": 4,
            "tier": "kern",
            "title": label,
            "text": (label + ". " + _clean(str(poll.get("field_intro", ""))))[:4000],
            "url": poll.get("url", "https://www.abgeordnetenwatch.de/"),
            "date": str(ts)[:10] if ts else cutoff.isoformat(),
        })
    print(f"  + Abgeordnetenwatch: {len(items)} Abstimmungen")
    return items


def _fetch_ordnungspunkt_artikel(article_id: str) -> dict | None:
    """Holt den Volltext-Artikel zu einem Tagesordnungspunkt, falls vorhanden.

    Viele Punkte (Sitzungseroeffnung, Ueberweisungen ohne Debatte) haben
    keinen Artikel - dann bleibt es beim blossen Titel aus conferences.xml,
    das ist normal. Wenn articleId gesetzt ist, gibt es aber oft einen
    ausformulierten Nachrichtentext mit Zahlen und Zitaten (echtes
    Belegmaterial statt nur einer Tagesordnungs-Ueberschrift).
    """
    if not article_id:
        return None
    url = f"https://www.bundestag.de/blueprint/servlet/content/{article_id}/asAppV2NewsarticleXml"
    try:
        resp = requests.get(url, headers=UA, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    ! Tagesordnung-Artikel {article_id} nicht ladbar: {exc}")
        return None

    title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text, re.DOTALL)
    text_match = re.search(r"<text><!\[CDATA\[(.*?)\]\]></text>", resp.text, re.DOTALL)
    source_match = re.search(r"<sourceURL>(.*?)</sourceURL>", resp.text)
    if not text_match:
        return None
    return {
        "title": _clean(title_match.group(1)) if title_match else "",
        "text": _clean(text_match.group(1)),
        "url": source_match.group(1) if source_match else url,
    }


def fetch_tagesordnung() -> list:
    """Tagesordnungspunkte der letzten Plenarsitzungen (Bundestag Live-API).

    conferences.xml selbst liefert nur Titel, Start-/Endzeit und optional
    eine articleId. Wenn eine articleId da ist, wird der zugehoerige
    Nachrichtenartikel (echter Fliesstext mit Zahlen, Zitaten) nachgeladen -
    das besteht die Beleg-Pruefung in llm.py oft. Ohne articleId bleibt nur
    der Titel, der meist an der Pruefung scheitert (skip). Beides ist
    gewollt: was durchkommt, ist dann auch wirklich belegt.
    """
    if not config.TAGESORDNUNG_ENABLED:
        return []

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=config.LOOKBACK_HOURS)).date()
    try:
        resp = requests.get(config.TAGESORDNUNG_URL, headers=UA, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  ! Tagesordnung nicht erreichbar: {exc}")
        return []

    items = []
    for sitzung in re.findall(r"<tagesordnung>(.*?)</tagesordnung>", resp.text, re.DOTALL):
        date_match = re.search(r"<date>(\d{2})\.(\d{2})\.(\d{4})</date>", sitzung)
        if not date_match:
            continue
        day, month, year = date_match.groups()
        sitzung_date = datetime(int(year), int(month), int(day)).date()
        if sitzung_date < cutoff:
            continue

        for punkt in re.findall(r"<diskussionspunkt>(.*?)</diskussionspunkt>", sitzung, re.DOTALL):
            titel_match = re.search(r"<titel>(.*?)</titel>", punkt)
            titel = _clean(titel_match.group(1)) if titel_match else ""
            if not titel:
                continue
            top_match = re.search(r"<top>(.*?)</top>", punkt)
            top = _clean(top_match.group(1)) if top_match else ""

            start_match = re.search(r"<startzeit>(\d{14})</startzeit>", punkt)
            end_match = re.search(r"<endzeit>(\d{14})</endzeit>", punkt)
            zeit = ""
            if start_match and end_match:
                s, e = start_match.group(1), end_match.group(1)
                zeit = f"{s[8:10]}:{s[10:12]}-{e[8:10]}:{e[10:12]} Uhr"

            article_match = re.search(r"<articleId>(\d+)</articleId>", punkt)
            artikel = _fetch_ordnungspunkt_artikel(article_match.group(1)) if article_match else None

            if artikel and len(artikel["text"]) > 100:
                item_title = artikel["title"] or titel
                text = artikel["text"]
                url = artikel["url"]
                weight = 3
                tier = "kern"
            else:
                item_title = titel
                details = ", ".join(d for d in (top, zeit) if d)
                text = titel + (f" ({details})" if details else "")
                url = "https://www.bundestag.de/tagesordnung"
                weight = 2
                tier = "kontext"

            items.append({
                "id": _hash("top" + sitzung_date.isoformat() + titel),
                "source": "Bundestag, Tagesordnung Plenarsitzung",
                "weight": weight,
                "tier": tier,
                "title": item_title,
                "text": text[:config.FULLTEXT_MAX_CHARS],
                "url": url,
                "date": sitzung_date.isoformat(),
            })
    print(f"  + Tagesordnung: {len(items)} Punkte")
    return items


def fetch_lobbyregister() -> list:
    """Neu registrierte oder aktualisierte Eintraege im Lobbyregister."""
    if not config.LOBBYREGISTER_ENABLED:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.LOOKBACK_HOURS)
    try:
        resp = requests.get(config.LOBBYREGISTER_URL,
                            params={"sortierung": "AKTUALITAET", "seite": 1},
                            headers=UA, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as exc:
        print(f"  ! Lobbyregister nicht erreichbar: {exc}")
        return []

    items = []
    for entry in results:
        details = entry.get("registerEntryDetails", {}) or {}
        ts = details.get("validFromDate", "")
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when < cutoff:
            continue

        identity = entry.get("lobbyistIdentity", {}) or {}
        name = _clean(identity.get("name", ""))
        activity = ((entry.get("activitiesAndInterests") or {}).get("activity") or {}).get("de", "")
        expenses = ((entry.get("financialExpenses") or {}).get("financialExpensesEuro") or {})
        text = (f"{name} wurde am {_de_datum(when.date())} im Lobbyregister des "
                f"Bundestages registriert bzw. aktualisiert. Taetigkeit: {activity}. "
                f"Finanzieller Aufwand fuer Interessenvertretung: "
                f"{expenses.get('from', 0)} bis {expenses.get('to', 0)} Euro.")
        items.append({
            "id": _hash("lobby" + str(details.get("registerEntryId", ""))),
            "source": "Lobbyregister beim Deutschen Bundestag",
            "weight": 2,
            "tier": "kontext",
            "title": f"Lobbyregister: {name}",
            "text": text[:4000],
            "url": details.get("detailsPageUrl", "https://www.lobbyregister.bundestag.de/"),
            "date": when.date().isoformat(),
        })
    print(f"  + Lobbyregister: {len(items)} Eintraege")
    return items


def fetch_parteispenden() -> list:
    """Parteispenden ueber 35.000 Euro (§ 25 PartG), aktuelle Jahresseite."""
    if not config.PARTEISPENDEN_ENABLED:
        return []

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=config.LOOKBACK_HOURS)).date()
    year = datetime.now(timezone.utc).year
    url = f"{config.PARTEISPENDEN_URL}/{year}"
    try:
        resp = requests.get(url, headers=UA, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  ! Parteispenden nicht erreichbar: {exc}")
        return []

    items = []
    for row in re.findall(r"<tr>((?:(?!<tr>).)*?)</tr>", resp.text, re.DOTALL):
        cells = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        if len(cells) != 5:
            continue
        partei, spende, spender, eingang, anzeige = (_clean(c) for c in cells)
        date_match = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", eingang)
        if not date_match:
            continue
        day, month, yr = date_match.groups()
        spende_date = datetime(int(yr), int(month), int(day)).date()
        if spende_date < cutoff:
            continue

        text = (f"Die Partei {partei} erhielt am {_de_datum(spende_date)} eine Spende "
                f"in Hoehe von {spende} von {spender}. Eingang der Anzeige beim "
                f"Bundestagspraesidium: {anzeige}.")
        items.append({
            "id": _hash("spende" + partei + spende + spender + eingang),
            "source": "Bundestag, Parteispenden über 35.000 Euro (§ 25 PartG)",
            "weight": 3,
            "tier": "kern",
            "title": f"{partei}: Spende {spende}",
            "text": text[:4000],
            "url": url,
            "date": spende_date.isoformat(),
        })
    print(f"  + Parteispenden: {len(items)} Eintraege")
    return items


VOTE_LABELS = {"yes": "Ja", "no": "Nein", "abstain": "Enthaltung"}


def fetch_einzelstimmen() -> list:
    """Fraktionen, die bei einer namentlichen Abstimmung nicht einheitlich
    gestimmt haben (abgeordnetenwatch /votes). Ein Item pro Fraktion und
    Abstimmung, nicht pro Einzelstimme - sonst waeren es hunderte Items fuer
    eine einzige Abstimmung. "Abweichler" ab EINZELSTIMMEN_MIN_ABWEICHLER.
    """
    if not config.EINZELSTIMMEN_ENABLED:
        return []

    legislature = _aow_current_legislature(config.AOW_PARLIAMENT_ID)
    if legislature is None:
        return []

    # Schubweise veroeffentlichtes Register - eigenes Fenster, siehe config.
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=config.REGISTER_LOOKBACK_DAYS)).date()
    try:
        resp = requests.get("https://www.abgeordnetenwatch.de/api/v2/polls",
                            params={"field_legislature": legislature, "range_end": 15,
                                    "sort_by": "field_poll_date", "sort_direction": "desc"},
                            headers=UA, timeout=30)
        resp.raise_for_status()
        polls = resp.json().get("data", [])
    except Exception as exc:
        print(f"  ! Einzelstimmen (Abstimmungsliste) nicht erreichbar: {exc}")
        return []

    items = []
    for poll in polls:
        ts = poll.get("field_poll_date")
        try:
            poll_date = datetime.fromisoformat(ts).date() if ts else cutoff
        except ValueError:
            poll_date = cutoff
        if poll_date < cutoff:
            continue

        try:
            vresp = requests.get("https://www.abgeordnetenwatch.de/api/v2/votes",
                                params={"poll": poll["id"], "range_end": 1000},
                                headers=UA, timeout=30)
            vresp.raise_for_status()
            votes = vresp.json().get("data", [])
        except Exception as exc:
            print(f"    ! Einzelstimmen fuer Poll {poll.get('id')} nicht ladbar: {exc}")
            continue

        by_fraktion: dict = {}
        for v in votes:
            fraktion = (v.get("fraction") or {}).get("label", "").split(" (")[0]
            if not fraktion or v.get("vote") not in VOTE_LABELS:
                continue
            by_fraktion.setdefault(fraktion, {}).setdefault(v["vote"], 0)
            by_fraktion[fraktion][v["vote"]] += 1

        label = _clean(poll.get("label", ""))
        url = poll.get("url", "https://www.abgeordnetenwatch.de/")
        for fraktion, counts in by_fraktion.items():
            total = sum(counts.values())
            mehrheit = max(counts.values())
            minderheit = total - mehrheit
            if minderheit < config.EINZELSTIMMEN_MIN_ABWEICHLER:
                continue
            aufschluesselung = ", ".join(f"{n} {VOTE_LABELS[v]}" for v, n in sorted(counts.items()))
            text = (f"Bei der Abstimmung \"{label}\" am {_de_datum(poll_date)} stimmte die "
                    f"Fraktion {fraktion} nicht einheitlich ab: {aufschluesselung}.")
            items.append({
                "id": _hash("votes" + str(poll["id"]) + fraktion),
                "source": "Bundestag, namentliche Abstimmung - Einzelstimmen (abgeordnetenwatch.de)",
                "weight": 3,
                "tier": "kern",
                "art": "einzelstimme",
                "title": f"{fraktion} uneinig bei: {label}"[:120],
                "text": text[:4000],
                "url": url,
                "date": poll_date.isoformat(),
            })
    print(f"  + Einzelstimmen: {len(items)} abweichende Fraktionen")
    return items


def fetch_nebentaetigkeiten() -> list:
    """Neu erfasste/aktualisierte Nebeneinkuenfte (abgeordnetenwatch /sidejobs)."""
    if not config.NEBENTAETIGKEITEN_ENABLED:
        return []

    # Schubweise veroeffentlichtes Register - eigenes Fenster, siehe config.
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=config.REGISTER_LOOKBACK_DAYS)).date()
    try:
        resp = requests.get("https://www.abgeordnetenwatch.de/api/v2/sidejobs",
                            params={"range_end": 200, "sort_by": "data_change_date",
                                    "sort_direction": "desc",
                                    "data_change_date[gte]": cutoff.isoformat()},
                            headers=UA, timeout=30)
        resp.raise_for_status()
        entries = resp.json().get("data", [])
    except Exception as exc:
        print(f"  ! Nebentaetigkeiten nicht erreichbar: {exc}")
        return []

    items = []
    for entry in entries:
        mandate = (entry.get("mandates") or [{}])[0]
        name = mandate.get("label", "").split(" (")[0]
        if not name:
            continue
        job = _clean(entry.get("label", ""))
        organisation = ((entry.get("sidejob_organization") or {}).get("label", ""))
        change_date = entry.get("data_change_date") or cutoff.isoformat()
        try:
            change_date_de = _de_datum(datetime.fromisoformat(change_date).date())
        except ValueError:
            change_date_de = change_date

        text = f"{name} (MdB) hat die Nebentaetigkeit \"{job}\""
        if organisation:
            text += f" bei {organisation}"
        text += f" gemeldet bzw. aktualisiert (Stand: {change_date_de})."

        items.append({
            "id": _hash("sidejob" + str(entry.get("id", ""))),
            "source": "Nebentätigkeiten der Abgeordneten (abgeordnetenwatch.de)",
            "weight": 2,
            "tier": "kontext",
            "art": "nebentaetigkeit",
            "title": f"Nebentaetigkeit: {name} - {job}"[:120],
            "text": text[:4000],
            "url": config.NEBENTAETIGKEITEN_URL,
            "date": change_date,
        })
    print(f"  + Nebentaetigkeiten: {len(items)} Eintraege")
    return items


def fetch_ausschuesse() -> list:
    """Besetzungsaenderungen in Bundestagsausschuessen (Bundestag XML).

    Das lastChanged auf Uebersichtsebene aendert sich kaum und ist kein
    brauchbares Signal fuer Mitgliederwechsel. Das lastChanged JE MITGLIED
    in der Detail-XML waere brauchbar, ist aber verrauscht: an manchen Tagen
    haben ploetzlich fast alle Mitglieder eines Ausschusses dasselbe Datum -
    ein technischer Sammel-Sync, keine echte Nachricht. Deshalb wird pro
    Ausschuss das haeufigste Mitglieder-Datum als "Sync-Rauschen" verworfen;
    nur Mitglieder mit einem DAVON ABWEICHENDEN, aktuellen Datum zaehlen als
    Kandidat fuer eine echte Aenderung. Von denen wiederum nur Leitungs-
    rollen (Vorsitz, Obleute, Sprecher) - ein normales "Ordentliches" oder
    "Stellvertretendes Mitglied" wechselt staendig routinemaessig, das waere
    reines Rauschen im Digest. Das kostet einen Request pro Ausschuss (~25),
    einmal taeglich vertretbar.
    """
    if not config.AUSSCHUESSE_ENABLED:
        return []

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=config.LOOKBACK_HOURS)).date()
    try:
        resp = requests.get(config.AUSSCHUESSE_INDEX_URL, headers=UA, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  ! Ausschuesse nicht erreichbar: {exc}")
        return []

    items = []
    for ausschuss_id, body in re.findall(r'<ausschuss id="([^"]+)">(.*?)</ausschuss>', resp.text, re.DOTALL):
        name_match = re.search(r"<ausschussName>(.*?)</ausschussName>", body)
        name = _clean(name_match.group(1)) if name_match else ausschuss_id
        detail_match = re.search(r"<ausschussDetailXML>(.*?)</ausschussDetailXML>", body)
        detail_url = detail_match.group(1) if detail_match else None
        if not detail_url:
            continue

        try:
            dresp = requests.get(detail_url, headers=UA, timeout=20)
            dresp.raise_for_status()
        except Exception as exc:
            print(f"    ! Ausschuss-Detail {name} nicht ladbar: {exc}")
            continue

        members = re.findall(r'<mdb fraktion="([^"]*)">(.*?)</mdb>', dresp.text, re.DOTALL)
        parsed = []
        for fraktion, mbody in members:
            name_m = re.search(r'<mdbName status="[^"]*">([^<]*)</mdbName>', mbody)
            role_m = re.search(r"<role>([^<]*)</role>", mbody)
            changed_m = re.search(r"<lastChanged>(\d{2})\.(\d{2})\.(\d{4})</lastChanged>", mbody)
            if not (name_m and changed_m):
                continue
            d, mo, y = changed_m.groups()
            parsed.append({
                "name": _clean(name_m.group(1)),
                "fraktion": fraktion,
                "role": _clean(role_m.group(1)) if role_m else "",
                "date": datetime(int(y), int(mo), int(d)).date(),
            })
        if not parsed:
            continue

        dates = [m["date"] for m in parsed]
        sync_noise_date = max(set(dates), key=dates.count)
        # Nur Leitungsrollen zaehlen als meldenswert - "Ordentliches" oder
        # "Stellvertretendes Mitglied" ist Routine-Umbesetzung, kein Digest-Stoff.
        leitungsrollen = ("vorsitz", "obleute", "sprecher")
        auffaellig = [m for m in parsed
                      if m["date"] != sync_noise_date and m["date"] >= cutoff
                      and any(r in m["role"].lower() for r in leitungsrollen)]
        if not auffaellig:
            continue

        source_match = re.search(r"<ausschussSourceURL>(.*?)</ausschussSourceURL>", dresp.text)
        url = source_match.group(1) if source_match else detail_url
        for m in auffaellig:
            rolle = f" ({m['role']})" if m['role'] else ""
            text = (f"{m['name']}{rolle}, Fraktion {m['fraktion']}, ist laut Bundestag seit "
                    f"{_de_datum(m['date'])} im Ausschuss {name} gefuehrt.")
            items.append({
                "id": _hash("ausschuss" + ausschuss_id + m["name"] + m["date"].isoformat()),
                "source": f"Bundestag, Ausschuss {name}",
                "weight": 2,
                "tier": "kontext",
                "title": f"Ausschuss {name}: {m['name']}{rolle}"[:120],
                "text": text[:config.FULLTEXT_MAX_CHARS],
                "url": url,
                "date": m["date"].isoformat(),
            })
    print(f"  + Ausschuesse: {len(items)} Besetzungsaenderungen")
    return items


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


# Die zehn Quellen haengen nicht voneinander ab und warten fast nur auf das
# Netz - nacheinander gelesen dauert das ueber 100 Sekunden, die praktisch
# vollstaendig Leerlauf sind. Bewusst wenige Arbeiter: es sind fremde, meist
# amtliche Server, und die Fetcher laden teilweise noch Artikelseiten nach.
_FETCHER = (fetch_rss, fetch_bundespuls, fetch_dip, fetch_aow,
            fetch_tagesordnung, fetch_lobbyregister, fetch_parteispenden,
            fetch_einzelstimmen, fetch_nebentaetigkeiten, fetch_ausschuesse)
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
