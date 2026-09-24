"""Schickt die fertigen Karten plus Caption per Telegram aufs Handy."""

import json
import os
import time

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def ohne_geheimnis(text: str) -> str:
    """Streicht das Bot-Token aus beliebigem Text.

    Telegram verlangt das Token im Pfad der URL. Damit steht es in jeder
    Fehlermeldung von requests - und run.py schickt den kompletten Traceback
    per send_error() in den Chat und ins Log. Eine einzige gescheiterte
    Namensaufloesung hat es so schon im Klartext ausgegeben.
    """
    token = os.environ.get("TELEGRAM_TOKEN", "")
    return text.replace(token, "<TELEGRAM_TOKEN>") if token else text


def _call(method: str, **kwargs):
    token = os.environ["TELEGRAM_TOKEN"]
    try:
        resp = requests.post(API.format(token=token, method=method),
                             timeout=60, **kwargs)
    except Exception as exc:
        # Kein raise: ein Netzfehler beim Melden darf den Lauf nicht kippen,
        # und die Meldung selbst darf das Token nicht mitnehmen.
        print(f"  ! Telegram {method} nicht erreichbar: {ohne_geheimnis(str(exc))}")
        return None
    if not resp.ok:
        print(f"  ! Telegram {method}: {ohne_geheimnis(resp.text[:200])}")
    return resp


def send_carousel(image_paths: list, caption: str, carousel: dict, nummer: int) -> None:
    """Schickt ein komplettes Karussell: Slides als Album, Caption zum
    Kopieren, Quellenliste zum Nachpruefen vor der Freigabe."""
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    item = carousel["item"]
    slides = carousel["slides"]

    # Die gezogene Cover-Architektur steht mit in der Kopfzeile: beim Freigeben
    # auf dem Handy soll sichtbar sein, welche der sechs gekommen ist.
    variante = carousel.get("cover")
    kopf = f"KARUSSELL {nummer}: {slides.get('titel', item['title'])}"
    _call("sendMessage", data={
        "chat_id": chat_id,
        "text": f"{kopf}\nCover: {variante}" if variante else kopf})

    # 1. Slides als Album (max 10 pro Nachricht)
    files, media = {}, []
    for i, path in enumerate(image_paths[:10]):
        key = f"file{i}"
        files[key] = open(path, "rb")
        media.append({"type": "photo", "media": f"attach://{key}"})

    _call("sendMediaGroup",
          data={"chat_id": chat_id, "media": json.dumps(media)},
          files=files)
    for handle in files.values():
        handle.close()

    # 2. Caption zum Kopieren
    _call("sendMessage", data={"chat_id": chat_id, "text": caption})

    # 3. Quellen: amtliche Hauptquelle plus alles, was die Recherche benutzt hat.
    #    Die Recherche-Fundstellen sind NICHT woertlich gegengeprueft - deshalb
    #    stehen sie hier getrennt und ausdruecklich zum Nachsehen.
    zeilen = [f"Hauptquelle (belegt):\n{item['url']}"]
    fundstellen = carousel.get("recherche", {}).get("fundstellen", [])
    if fundstellen:
        zeilen.append("\nRecherche (bitte pruefen):")
        for f in fundstellen[:6]:
            zeilen.append(f"- {f['titel'][:70]}\n  {f['url']}")

    _call("sendMessage", data={"chat_id": chat_id,
                               "text": "\n".join(zeilen),
                               "disable_web_page_preview": True})


def send_text(text: str) -> None:
    _call("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                               "text": text})


def _updates_leeren() -> int:
    """Raeumt liegengebliebene Updates weg und liefert den naechsten Offset.

    Telegram haelt unabgeholte Updates 24 Stunden vor. Ohne diesen Schritt
    beantwortet der Knopfdruck von gestern den Lauf von heute - und zwar
    lautlos, weil die Antwort formal gueltig aussieht.
    """
    resp = _call("getUpdates", data={"timeout": 0})
    if resp is None or not resp.ok:
        return 0
    ergebnisse = resp.json().get("result", [])
    return ergebnisse[-1]["update_id"] + 1 if ergebnisse else 0


def frage_auswahl(anzahl: int, minuten: int = 25) -> int | None:
    """Fragt, welches Karussell online geht - genau eines oder keines.

    Rueckgabe ist die Nummer (1-basiert) oder None. None heisst in beiden
    Faellen dasselbe: es wird nichts veroeffentlicht - ob du "Keine" gedrueckt
    hast oder gar nicht geantwortet hast. Das ist Absicht. Der Freigabeschritt
    traegt die redaktionelle Kontrolle nach Art. 50 Abs. 4 KI-VO, und der
    Ausfall dieser Kontrolle darf nie zu einem Post fuehren, sondern immer nur
    zu keinem.
    """
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    # Erst leeren, dann fragen: sonst zaehlt eine alte Antwort mit.
    offset = _updates_leeren()

    knoepfe = [[{"text": f"Option {i}", "callback_data": f"wahl:{i}"}]
               for i in range(1, anzahl + 1)]
    knoepfe.append([{"text": "Keine", "callback_data": "wahl:0"}])
    _call("sendMessage", data={
        "chat_id": chat_id,
        "text": ("Welches Karussell geht online?\n"
                 "Vorher die Quelllinks oben oeffnen und pruefen.\n\n"
                 f"Ohne Antwort binnen {minuten} Minuten wird nichts "
                 "veroeffentlicht."),
        "reply_markup": json.dumps({"inline_keyboard": knoepfe})})

    ende = time.time() + minuten * 60
    while time.time() < ende:
        # Long Polling: der Aufruf haengt bis zu 30 Sekunden, statt im
        # Sekundentakt zu fragen.
        resp = _call("getUpdates", data={"offset": offset, "timeout": 30})
        if resp is None or not resp.ok:
            time.sleep(5)
            continue
        for update in resp.json().get("result", []):
            offset = update["update_id"] + 1
            anfrage = update.get("callback_query") or {}
            if not anfrage.get("data", "").startswith("wahl:"):
                continue
            wahl = int(anfrage["data"].split(":")[1])
            # Ohne Quittung dreht sich der Knopf im Client weiter, als haenge
            # der Lauf.
            _call("answerCallbackQuery",
                  data={"callback_query_id": anfrage["id"]})
            _call("editMessageText", data={
                "chat_id": chat_id,
                "message_id": anfrage["message"]["message_id"],
                "text": (f"Option {wahl} freigegeben." if wahl
                         else "Nichts freigegeben.")})
            return wahl or None

    print("  ! keine Antwort im Zeitfenster - es wird nichts veroeffentlicht")
    send_text("Zeitfenster abgelaufen, nichts veroeffentlicht. "
              "Die Karten liegen im Lauf-Protokoll.")
    return None


def send_error(message: str) -> None:
    message = ohne_geheimnis(message)
    _call("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                               "text": f"Digest-Lauf fehlgeschlagen:\n{message[:600]}"})
