"""Prueft einmalig, ob alle Feed-URLs erreichbar sind und Eintraege liefern.

Aufruf: python check_sources.py
Feeds von Behoerden aendern sich gelegentlich. Wenn hier etwas rot ist,
suche die aktuelle RSS-URL auf der jeweiligen Website und trage sie in
config.py ein.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from dotenv import load_dotenv

import config

# Windows-Konsole ist oft cp1252, Quelltexte enthalten aber beliebige
# Unicode-Zeichen. Ohne das crasht ein print().
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "politik-digest/1.0 (+kontakt@example.de)"),
    "Accept": "application/json, application/rss+xml, text/xml, */*",
}


def check_feeds(feeds: list) -> None:
    for src in feeds:
        try:
            resp = requests.get(src["url"], headers=UA, timeout=20)
            feed = feedparser.parse(resp.content)
            count = len(feed.entries)
            status = "OK " if count else "LEER"
            print(f"{status} {src['name']}: {count} Eintraege ({resp.status_code})")
        except Exception as exc:
            print(f"FEHL {src['name']}: {exc}")


def check_lobbyregister() -> None:
    # Mit Filter: ohne liefert die Suche alle ~7.000 Eintraege (17 MB). Greift
    # der Filter nicht mehr, ist das hier sichtbar statt erst im Lauf.
    try:
        resp = requests.get(config.LOBBYREGISTER_URL,
                            params={"filter[revolvingdooractive][true]": "true"},
                            headers=UA, timeout=60)
        resp.raise_for_status()
        daten = resp.json()
        count = daten.get("resultCount", 0)
        ok = bool(daten.get("searchParameters", {}).get("facets")) and count < 1000
        print(f"{'OK ' if ok else 'WARN'} Lobbyregister-Suche: Filter "
              f"{'greift' if ok else 'greift NICHT'}, {count} Treffer ({resp.status_code})")
    except Exception as exc:
        print(f"FEHL Lobbyregister-Suche: {exc}")
    key = os.environ.get("LOBBYREGISTER_API_KEY") or config.LOBBYREGISTER_API_KEY
    try:
        resp = requests.get(f"{config.LOBBYREGISTER_API}/statistics/registerentries",
                            params={"format": "json"},
                            headers={**UA, "Authorization": f"ApiKey {key}"}, timeout=30)
        resp.raise_for_status()
        print(f"OK  Lobbyregister-API: Key gueltig ({resp.status_code})")
    except Exception as exc:
        print(f"FEHL Lobbyregister-API (Key auf der Open-Data-Seite pruefen): {exc}")


def check_parteispenden() -> None:
    year = datetime.now().year
    url = f"{config.PARTEISPENDEN_URL}/{year}"
    try:
        resp = requests.get(url, headers=UA, timeout=20)
        resp.raise_for_status()
        count = resp.text.count("<tr>")
        print(f"OK  Parteispenden: Seite {year} erreichbar, ~{count} Tabellenzeilen ({resp.status_code})")
    except Exception as exc:
        print(f"FEHL Parteispenden: {exc}")


def check_dip() -> None:
    key = os.environ.get("DIP_API_KEY")
    if not key:
        print("INFO DIP: kein DIP_API_KEY gesetzt, wird uebersprungen")
        return
    try:
        # Geprueft wird, was der Lauf wirklich holt: Gesetzgebungsvorgaenge
        # im eingestellten Fenster - und davon die entschiedenen. Null
        # entschiedene Vorgaenge ist der haeufigste Grund fuer einen leeren
        # Lauf und soll sichtbar sein, statt als "OK" durchzugehen.
        start = (datetime.now(timezone.utc)
                 - timedelta(days=config.GESETZE_LOOKBACK_DAYS)).date()
        resp = requests.get(f"{config.DIP_BASE}/vorgang",
                            params={"apikey": key, "format": "json",
                                    "f.vorgangstyp": config.DIP_VORGANGSTYP,
                                    "f.datum.start": start.isoformat()},
                            headers=UA, timeout=30)
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        fertig = [d for d in docs
                  if d.get("beratungsstand") in config.DIP_BESCHLOSSEN]
        print(f"{'OK ' if fertig else 'WARN'} DIP: {len(docs)} Vorgaenge "
              f"({config.DIP_VORGANGSTYP}) seit {start}, davon "
              f"{len(fertig)} entschieden ({resp.status_code})")
        for d in fertig[:3]:
            print(f"       - [{d.get('beratungsstand')}] {d.get('titel', '')[:68]}")
    except Exception as exc:
        print(f"FEHL DIP: {exc}")


def check_nebentaetigkeiten() -> None:
    try:
        resp = requests.get("https://www.abgeordnetenwatch.de/api/v2/sidejobs",
                            params={"range_end": 1, "sort_by": "data_change_date",
                                    "sort_direction": "desc"},
                            headers=UA, timeout=20)
        resp.raise_for_status()
        total = resp.json().get("meta", {}).get("result", {}).get("total", 0)
        print(f"OK  Nebentaetigkeiten: {total} Eintraege insgesamt in der API ({resp.status_code})")
    except Exception as exc:
        print(f"FEHL Nebentaetigkeiten: {exc}")


if __name__ == "__main__":
    check_feeds([{"name": "Destatis", "url": config.DESTATIS_FEED}])
    check_dip()
    check_lobbyregister()
    check_parteispenden()
    check_nebentaetigkeiten()
