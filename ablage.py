"""Legt die Karten dorthin, wo Instagram sie abholen kann.

Die Graph API laedt die Bilder selbst per URL herunter, statt einen Upload
entgegenzunehmen. Sie muessen also oeffentlich stehen, bevor der Post
beginnt. Billigster Weg ohne zweiten Dienst: GitHub Pages aus docs/ desselben
Repos - dieselbe Mechanik, die schon das Impressum ausliefert.

Zwei Dinge sind dabei nicht selbstverstaendlich:

  - Gepusht wird nur, was freigegeben wurde. Verworfene Entwuerfe landen
    nicht im oeffentlichen Verlauf, und der bleibt fuer immer.
  - Nach dem Push ist die Datei noch nicht da. Pages baut erst, und das
    dauert. Deshalb warte_bis_erreichbar() - ohne das laeuft der erste
    Instagram-Aufruf in einen 404, den die API als "Bild nicht ladbar"
    meldet.
"""

import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import config

DOCS = Path("docs")
UNTERORDNER = "karten"


def _git(*args: str) -> None:
    ergebnis = subprocess.run(["git", *args], capture_output=True, text=True)
    if ergebnis.returncode:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{ergebnis.stderr.strip()[:300]}")


def _identitaet_sichern() -> None:
    """Setzt einen Committer, falls keiner konfiguriert ist.

    Im Actions-Runner tut das sonst erst der Schritt "Stand merken" - der
    laeuft aber nach run.py, und bis dahin ist dieser Commit hier laengst
    faellig.
    """
    vorhanden = subprocess.run(["git", "config", "user.email"],
                               capture_output=True, text=True)
    if not vorhanden.stdout.strip():
        _git("config", "user.email", "bot@users.noreply.github.com")
        _git("config", "user.name", "digest-bot")


def ablegen(pfade: list, nummer: int) -> list:
    """Kopiert die JPEGs nach docs/, pusht sie und liefert ihre URLs.

    Der Datumsordner haelt die Laeufe auseinander: ohne ihn ueberschreibt der
    Lauf von morgen die Bilder von heute, und Instagram zeigt dann beim alten
    Post die neuen Karten - die API merkt sich die URL, nicht das Bild.
    """
    basis = os.environ["PAGES_BASE_URL"].rstrip("/")
    tag = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")
    ziel = DOCS / UNTERORDNER / tag / f"karussell_{nummer}"

    if ziel.exists():
        shutil.rmtree(ziel)
    ziel.mkdir(parents=True)

    urls = []
    for pfad in pfade:
        jpg = Path(pfad).with_suffix(".jpg")
        if not jpg.exists():
            raise FileNotFoundError(
                f"{jpg} fehlt - render.py schreibt das JPEG neben das PNG")
        shutil.copy2(jpg, ziel / jpg.name)
        urls.append(f"{basis}/{UNTERORDNER}/{tag}/karussell_{nummer}/{jpg.name}")

    _identitaet_sichern()
    _git("add", "--", str(DOCS))
    _git("commit", "-m", f"karten: {tag} karussell {nummer}")
    # Der Lauf wartet bis zu Stunden auf die Freigabe. Pusht in der Zeit
    # jemand anderes nach main, wird ein blankes push abgewiesen - und die
    # Freigabe ist erteilt, aber nichts geht online.
    _git("pull", "--rebase", "--autostash")
    _git("push")
    print(f"  = {len(urls)} Karten nach {ziel} gepusht")
    return urls


def warte_bis_erreichbar(url: str, sekunden: int = 300) -> None:
    """Wartet, bis Pages die Datei ausliefert.

    Der Bau nach einem Push dauert ueblicherweise ein bis zwei Minuten, beim
    allerersten Mal laenger. Laeuft die Zeit ab, bricht der Upload lieber hier
    ab als drueben mit einer Meldung, die nach einem Rechteproblem aussieht.
    """
    ende = time.time() + sekunden
    while time.time() < ende:
        try:
            if requests.head(url, timeout=15, allow_redirects=True).ok:
                print(f"  = Pages liefert aus: {url}")
                return
        except Exception:
            pass    # Netz, DNS, Pages noch nicht da - alles dasselbe: warten
        time.sleep(10)
    raise RuntimeError(f"Pages liefert {url} auch nach {sekunden} s nicht aus")
