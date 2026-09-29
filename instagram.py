"""Laedt ein freigegebenes Karussell nach Instagram.

Die Graph API nimmt keine Dateien entgegen: sie bekommt URLs und holt die
Bilder selbst ab. Die Karten muessen also schon oeffentlich stehen, bevor der
erste Aufruf hier passiert - darum kuemmert sich ablage.py.

Drei Schritte, weil die API es so verlangt:
  1. je Slide ein Medien-Container
  2. ein Sammel-Container ueber diese Container, mit der Caption
  3. veroeffentlichen

Anders als notify.py schluckt dieses Modul keine Fehler. Eine gescheiterte
Telegram-Nachricht ist aergerlich, ein halb angelegtes Karussell dagegen darf
nie als "gepostet" durchgehen - deshalb fliegt hier alles nach oben.
"""

import os
import time

import requests

# Meta stellt alte Versionen nach etwa zwei Jahren ab. Laeuft der Upload
# ploetzlich in einen 400er, der nach einem Rechteproblem aussieht, ist meist
# diese Zeile faellig und nicht der Code darunter.
API = "https://graph.instagram.com/v21.0"

# Grenzen der API, nicht des Projekts: ein Karussell nimmt 2 bis 10 Bilder.
MIN_BILDER, MAX_BILDER = 2, 10


def ohne_geheimnis(text: str) -> str:
    """Streicht das Zugriffstoken aus beliebigem Text.

    Gegenstueck zu notify.ohne_geheimnis, und aus demselben Grund: run.py
    schickt den kompletten Traceback in den Chat und ins Actions-Log. Ein
    langlebiges Instagram-Token, das dort im Klartext landet, gilt sechzig
    Tage und haengt an einem Konto, das posten darf.
    """
    for name in ("IG_ACCESS_TOKEN", "IG_EN_ACCESS_TOKEN"):
        token = os.environ.get(name, "")
        if token:
            text = text.replace(token, f"<{name}>")
    return text


def _token(konto: str) -> str:
    """Token des Kontos: "" ist das deutsche, "EN" das englische."""
    return os.environ[f"IG_{konto}_ACCESS_TOKEN" if konto else "IG_ACCESS_TOKEN"]


def _post(pfad: str, konto: str = "", **felder) -> dict:
    felder["access_token"] = _token(konto)
    # Token im Rumpf, nicht in der URL: sonst steht es in jeder Fehlermeldung
    # von requests und in jedem Proxy-Log.
    resp = requests.post(f"{API}/{pfad}", data=felder, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Instagram {pfad}: {ohne_geheimnis(resp.text[:300])}")
    return resp.json()


def _warte_auf_fertig(container: str, sekunden: int = 120, konto: str = "") -> None:
    """Wartet, bis der Sammel-Container verarbeitet ist.

    media_publish auf einen Container, der noch "IN_PROGRESS" ist, quittiert
    die API mit einer Meldung, die wie ein Rechteproblem aussieht. Lieber hier
    warten als dort raten.
    """
    token = _token(konto)
    ende = time.time() + sekunden
    while time.time() < ende:
        resp = requests.get(f"{API}/{container}",
                            params={"fields": "status_code",
                                    "access_token": token}, timeout=30)
        stand = resp.json().get("status_code") if resp.ok else None
        if stand == "FINISHED":
            return
        if stand == "ERROR":
            raise RuntimeError(f"Instagram: Container {container} fehlgeschlagen")
        time.sleep(5)
    raise RuntimeError(f"Instagram: Container {container} war nach "
                       f"{sekunden} s nicht fertig")


def veroeffentliche(bild_urls: list, caption: str, konto: str = "") -> str:
    """Postet die Bilder als ein Karussell und liefert die Post-ID.

    `konto` "EN" nimmt IG_EN_USER_ID und IG_EN_ACCESS_TOKEN (englisch.py)."""
    nutzer = os.environ[f"IG_{konto}_USER_ID" if konto else "IG_USER_ID"]
    if not MIN_BILDER <= len(bild_urls) <= MAX_BILDER:
        raise ValueError(f"Instagram nimmt {MIN_BILDER} bis {MAX_BILDER} "
                         f"Bilder, dieses Karussell hat {len(bild_urls)}")

    kinder = []
    for url in bild_urls:
        antwort = _post(f"{nutzer}/media", konto, image_url=url,
                        is_carousel_item="true")
        kinder.append(antwort["id"])
        print(f"    + Container {antwort['id']} ({url.rsplit('/', 1)[-1]})")

    sammel = _post(f"{nutzer}/media", konto, media_type="CAROUSEL",
                   children=",".join(kinder), caption=caption)["id"]
    _warte_auf_fertig(sammel, konto=konto)

    post = _post(f"{nutzer}/media_publish", konto, creation_id=sammel)["id"]
    print(f"  = veroeffentlicht, Post {post}")
    return post
