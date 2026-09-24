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
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    return text.replace(token, "<IG_ACCESS_TOKEN>") if token else text


def _post(pfad: str, **felder) -> dict:
    felder["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    # Token im Rumpf, nicht in der URL: sonst steht es in jeder Fehlermeldung
    # von requests und in jedem Proxy-Log.
    resp = requests.post(f"{API}/{pfad}", data=felder, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Instagram {pfad}: {ohne_geheimnis(resp.text[:300])}")
    return resp.json()


def _warte_auf_fertig(container: str, sekunden: int = 120) -> None:
    """Wartet, bis der Sammel-Container verarbeitet ist.

    media_publish auf einen Container, der noch "IN_PROGRESS" ist, quittiert
    die API mit einer Meldung, die wie ein Rechteproblem aussieht. Lieber hier
    warten als dort raten.
    """
    token = os.environ["IG_ACCESS_TOKEN"]
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


def veroeffentliche(bild_urls: list, caption: str) -> str:
    """Postet die Bilder als ein Karussell und liefert die Post-ID."""
    nutzer = os.environ["IG_USER_ID"]
    if not MIN_BILDER <= len(bild_urls) <= MAX_BILDER:
        raise ValueError(f"Instagram nimmt {MIN_BILDER} bis {MAX_BILDER} "
                         f"Bilder, dieses Karussell hat {len(bild_urls)}")

    kinder = []
    for url in bild_urls:
        antwort = _post(f"{nutzer}/media", image_url=url,
                        is_carousel_item="true")
        kinder.append(antwort["id"])
        print(f"    + Container {antwort['id']} ({url.rsplit('/', 1)[-1]})")

    sammel = _post(f"{nutzer}/media", media_type="CAROUSEL",
                   children=",".join(kinder), caption=caption)["id"]
    _warte_auf_fertig(sammel)

    post = _post(f"{nutzer}/media_publish", creation_id=sammel)["id"]
    print(f"  = veroeffentlicht, Post {post}")
    return post
