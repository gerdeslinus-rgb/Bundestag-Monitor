"""Lauf: Quellen -> Themenwahl -> Recherche -> Slides -> Pruefung -> Telegram
-> deine Freigabe -> Instagram.

Veroeffentlicht wird nur, was du per Knopfdruck freigibst. Am Ende liegen die
fertigen Karussells auf deinem Handy, dazu die Frage, welches online geht:
Option 1, Option 2 oder keines. Ohne Antwort passiert nichts - der Ausfall der
Freigabe fuehrt nie zu einem Post, sondern immer nur zu keinem.

Gedacht fuer alle zwei Tage.
"""

import sys
import traceback

# Windows-Konsole ist oft cp1252, Quelltexte enthalten aber beliebige
# Unicode-Zeichen (Pfeile, Sonderzeichen). Ohne das crasht ein print().
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()   # liest .env, bevor Module die Keys brauchen

import ablage
import config
import cover
import instagram
import llm
import notify
import profile_mode
import render
import research
import sources


def main() -> int:
    seen = sources.load_seen()
    carousels = []

    # Stufenweise: erst die beste Quelle, und nur wenn die nichts Sende-
    # faehiges hergibt, die naechste. Entscheidend ist dabei nicht, ob eine
    # Quelle Items liefert, sondern ob daraus ein Karussell wird, das beide
    # Pruefungen besteht - eine Quelle mit 200 Eintraegen, die alle
    # durchfallen, hat nichts beigetragen.
    for name, fetcher, bauart in config.QUELLEN_STUFEN:
        fehlend = config.CAROUSELS_PER_RUN - len(carousels)
        if fehlend <= 0:
            break

        print()
        print(f"Stufe '{name}' ({fehlend} Karussell(s) gesucht) ...")
        items = sources.collect_stufe(fetcher, seen)
        if not items:
            print("  = keine Items - weiter zur naechsten Stufe")
            continue

        if bauart == "profil":
            neue = profile_mode.build(items, fehlend)
        else:
            neue = llm.build_carousels(items, research.enrich, fehlend)
        carousels += neue
        print(f"  = Stufe '{name}': {len(neue)} Karussell(s)")

    if not carousels:
        notify.send_error("Keine Quelle hat ein sendefertiges Karussell "
                          "geliefert. Stufen und Feeds pruefen.")
        return 1

    print("Karussells werden gebaut ...")
    # Die zuletzt gezogenen Cover-Architekturen bleiben ueber Laeufe hinweg
    # gesperrt - sonst kann zwei Posts hintereinander dieselbe kommen, und
    # genau dagegen ist die Rotation gebaut.
    zuletzt = cover.letzte_laden()
    gebaut = []
    for nummer, carousel in enumerate(carousels, start=1):
        paths = render.build_carousel(carousel, nummer, zuletzt)
        zuletzt = cover.merken(carousel["cover"], zuletzt)
        caption = render.build_caption(carousel)
        notify.send_carousel(paths, caption, carousel, nummer)
        gebaut.append((paths, caption))

    # Stand sichern, BEVOR die Freigabe abgewartet wird: gebaut ist gebaut.
    # Faellt der Lauf beim Upload aus oder antwortest du nicht, sollen
    # dieselben Meldungen morgen trotzdem nicht noch einmal kommen - sie
    # standen ja auf deinem Handy.
    seen.update(c["item"]["id"] for c in carousels)
    sources.save_seen(seen)
    cover.letzte_speichern(zuletzt)

    wahl = notify.frage_auswahl(len(gebaut))
    if wahl is None:
        print("Nichts freigegeben. Fertig.")
        return 0

    paths, caption = gebaut[wahl - 1]
    print(f"Option {wahl} wird veroeffentlicht ...")
    try:
        urls = ablage.ablegen(paths, wahl)
        ablage.warte_bis_erreichbar(urls[0])
        instagram.veroeffentliche(urls, caption)
    except Exception as exc:
        # Eigene Meldung statt nur des Tracebacks unten: hier ist der
        # Unterschied wichtig. Der Lauf war erfolgreich, du hast freigegeben,
        # und trotzdem steht nichts online - das muss man sofort sehen.
        notify.send_error("Freigabe erteilt, aber der Upload ist "
                          f"fehlgeschlagen:\n{instagram.ohne_geheimnis(str(exc))}")
        raise

    notify.send_text(f"Option {wahl} ist online.")
    print("Fertig. Online.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Auch die Konsolenausgabe saeubern: der Traceback eines
        # Telegram-Fehlers enthaelt die URL samt Bot-Token. Seit dem Upload
        # kann ausserdem das Instagram-Token darin stehen - beide Filter,
        # sonst landet es im Actions-Log, und das gilt sechzig Tage.
        trace = instagram.ohne_geheimnis(
            notify.ohne_geheimnis(traceback.format_exc()))
        print(trace)
        try:
            notify.send_error(trace)
        except Exception:
            pass
        sys.exit(1)
