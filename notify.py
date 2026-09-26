"""Schickt die fertigen Karten plus Caption per Telegram aufs Handy."""

import json
import os
import secrets
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import config

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
    # Die Slide "Was fruehere Faelle zeigen" stuetzt sich allein auf diese
    # Befunde - deshalb stehen sie einzeln da, mit Zahl und Adresse, und
    # nicht nur irgendwo in der Trefferliste darunter.
    faelle = carousel.get("recherche", {}).get("fruehere_faelle", [])
    if faelle and (carousel.get("slides") or {}).get("vergleich"):
        zeilen.append("\nFruehere Faelle (Slide 'Was fruehere Faelle zeigen', bitte pruefen):")
        for f in faelle:
            zeilen.append(f"- {f['massnahme']}: {f['wert']:g} {f['einheit']} "
                          f"laut {f['stelle']}\n  {f['quelle_url']}")

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


def _abgelaufen(anfrage: dict) -> None:
    """Quittiert einen Knopf, der zu keinem laufenden Lauf gehoert.

    Ohne Quittung dreht sich der Knopf im Client endlos, und es sieht aus, als
    haenge der Lauf. Die Knoepfe der alten Nachricht fliegen gleich mit raus,
    damit sie nicht weiter wie eine offene Frage aussehen.
    """
    _call("answerCallbackQuery", data={
        "callback_query_id": anfrage["id"],
        "text": "Diese Frage ist abgelaufen - es gilt nur die neueste.",
        "show_alert": True})
    nachricht = anfrage.get("message") or {}
    if nachricht:
        _call("editMessageReplyMarkup", data={
            "chat_id": nachricht["chat"]["id"],
            "message_id": nachricht["message_id"]})


def frage_auswahl(anzahl: int, minuten: int = config.FREIGABE_MINUTEN) -> int | None:
    """Fragt, welches Karussell online geht - genau eines oder keines.

    Rueckgabe ist die Nummer (1-basiert) oder None. None heisst in beiden
    Faellen dasselbe: es wird nichts veroeffentlicht - ob du "Keine" gedrueckt
    hast oder gar nicht geantwortet hast. Das ist Absicht. Der Freigabeschritt
    traegt die redaktionelle Kontrolle nach Art. 50 Abs. 4 KI-VO, und der
    Ausfall dieser Kontrolle darf nie zu einem Post fuehren, sondern immer nur
    zu keinem.

    Es zaehlt nur ein Knopf dieser einen Frage, aus deinem Chat. Die Knoepfe
    tragen dafuer eine Kennung pro Lauf: frueher galt jedes "wahl:0" - auch
    das "Keine" unter einer alten Frage von gestern, und das beendete den Lauf
    lautlos ohne Post.
    """
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    # Erst leeren, dann fragen: sonst zaehlt eine alte Antwort mit.
    offset = _updates_leeren()
    kennung = secrets.token_hex(4)

    knoepfe = [[{"text": f"Option {i}", "callback_data": f"wahl:{kennung}:{i}"}]
               for i in range(1, anzahl + 1)]
    knoepfe.append([{"text": "Keine", "callback_data": f"wahl:{kennung}:0"}])
    frist = datetime.now(ZoneInfo(config.TIMEZONE)) + timedelta(minutes=minuten)
    frage = _call("sendMessage", data={
        "chat_id": chat_id,
        "text": ("Welches Karussell geht online?\n"
                 "Vorher die Quelllinks oben oeffnen und pruefen.\n\n"
                 f"Ohne Antwort bis {frist:%H:%M} Uhr wird nichts "
                 "veroeffentlicht."),
        "reply_markup": json.dumps({"inline_keyboard": knoepfe})})
    frage_id = (frage.json()["result"]["message_id"]
                if frage is not None and frage.ok else None)

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
            daten = anfrage.get("data", "")
            if not daten.startswith("wahl:"):
                continue
            teile = daten.split(":")
            aus_chat = str((anfrage.get("message") or {})
                           .get("chat", {}).get("id"))
            if len(teile) != 3 or teile[1] != kennung or aus_chat != chat_id:
                _abgelaufen(anfrage)
                continue
            wahl = int(teile[2])
            # Ohne Quittung dreht sich der Knopf im Client weiter, als haenge
            # der Lauf.
            _call("answerCallbackQuery", data={
                "callback_query_id": anfrage["id"],
                "text": (f"Option {wahl} wird veroeffentlicht ..." if wahl
                         else "Nichts wird veroeffentlicht.")})
            _call("editMessageText", data={
                "chat_id": chat_id,
                "message_id": anfrage["message"]["message_id"],
                "text": (f"Option {wahl} freigegeben - Upload laeuft."
                         if wahl else "Nichts freigegeben.")})
            print(f"  = Antwort: {'Option ' + str(wahl) if wahl else 'Keine'}")
            return wahl or None

    print("  ! keine Antwort im Zeitfenster - es wird nichts veroeffentlicht")
    if frage_id is not None:
        # Knoepfe weg: sonst sieht die Frage noch offen aus, und ein spaeter
        # Druck dreht sich ins Leere, weil kein Lauf mehr zuhoert.
        _call("editMessageText", data={
            "chat_id": chat_id, "message_id": frage_id,
            "text": "Zeitfenster abgelaufen, nichts veroeffentlicht."})
    else:
        send_text("Zeitfenster abgelaufen, nichts veroeffentlicht.")
    return None


def send_error(message: str) -> None:
    message = ohne_geheimnis(message)
    _call("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                               "text": f"Digest-Lauf fehlgeschlagen:\n{message[:600]}"})
