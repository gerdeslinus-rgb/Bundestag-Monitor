"""Sucht ein passendes Stockfoto fuer die Cover-Slide (Pexels).

Bewusst eng gebaut, damit nie ein beliebiges Bild auf einer Faktenkarte landet:

* Es wird NICHT mit dem Meldungstext gesucht. Gesucht wird mit einer festen
  Suchphrase aus config.BILDER_THEMEN - und nur dann, wenn eines dieser Themen
  im Titel/Hook vorkommt. Kein Thema getroffen = kein Bild. Damit kann die
  Suche nie etwas Halbpassendes zu einem Begriff liefern, den wir nicht kennen.
* Die Suchphrasen zeigen auf Orte, Gegenstaende und Situationen, nicht auf
  Personen. Ein Stockmodell neben einer politischen Aussage ist harmlos, ein
  erkennbarer Politiker neben einer Aussage, mit der er nichts zu tun hat,
  waere ein Problem (Recht am eigenen Bild).
* Jeder Fehler - kein Key, API tot, nichts gefunden - endet in "kein Bild".
  Der Lauf laeuft weiter, das Cover bleibt rein typografisch.

Lizenz: Pexels erlaubt die kostenlose Nutzung auch kommerziell. Die
API-Richtlinien verlangen dafuer die Nennung des Fotografen und einen Hinweis
auf Pexels - beides setzt render.py auf die Karte und in die Caption.
"""

import base64
import os

import requests

import config

SUCHE = "https://api.pexels.com/v1/search"


def _vergleichsform(text: str) -> str:
    """Kleinschreibung plus Umschrift der Umlaute.

    Ohne diesen Schritt war ein Teil der Stichwortliste tot: sie steht in
    Umschrift ("bafoeg", "beschaeftigung", "waerme"), echte Ueberschriften
    schreiben aber "BAföG", "Beschäftigung", "Wärme". Die Stichworte haben
    also nie gegriffen, und die Meldung bekam still kein Bild.
    """
    klein = text.lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        klein = klein.replace(alt, neu)
    return klein


def _thema_finden(text: str) -> dict | None:
    """Das am besten passende Thema. Sonst None.

    Gezaehlt wird, wie viele Stichworte eines Themas vorkommen - nicht, wer
    in der Liste zuerst steht. Sonst entscheidet die Reihenfolge der Liste
    ueber das Bild: "Kindergeld wird in den Steuerfreibetrag eingerechnet"
    bekam das Steuerformular, weil "steuern" oben steht, obwohl die Meldung
    von Familien handelt.

    `nicht` sind Gegenproben: Woerter, die dasselbe Stichwort enthalten, aber
    etwas anderes meinen ("Steuerungsgruppe" ist keine Steuer, "Gastronomie"
    kein Gas). Ein Treffer darin verwirft das Thema ganz.
    """
    klein = _vergleichsform(text)

    bester, bestpunkte = None, (0, 0)
    for thema in config.BILDER_THEMEN:
        if any(gegen in klein for gegen in thema.get("nicht", ())):
            continue
        treffer = [klein.index(wort) for wort in thema["woerter"]
                   if wort in klein]
        # Treffen zwei Themen MEHRFACH, gewinnt das, dessen Stichwort frueher
        # steht: deutsche Ueberschriften nennen ihren Gegenstand zuerst.
        # "Kindergeld wird in den Steuerfreibetrag eingerechnet" trifft beide
        # zweimal und handelt von dem, was vorne steht.
        # Bei einem einzelnen Treffer je Thema entscheidet dagegen die
        # Reihenfolge der Liste. Die Position waere hier irrefuehrend: in
        # "Verkehrsminister kuendigt Gasnetz-Rueckbau an" steht der Handelnde
        # vorn, das Thema hinten.
        punkte = (len(treffer),
                  -min(treffer) if len(treffer) > 1 else 0)
        # Der Rueckfall (parlament) greift nur, wenn sonst gar nichts passt.
        if thema.get("rueckfall") and treffer:
            punkte = (0.5, 0)
        if punkte > bestpunkte:
            bester, bestpunkte = thema, punkte
    return bester


def _als_data_uri(url: str) -> str | None:
    """Laedt das Bild und packt es als data:-URI.

    Playwright rendert die Karte aus set_content() heraus, also ohne eigene
    Herkunft - eine externe Bild-URL wuerde dort nicht zuverlaessig laden.
    Eingebettet ist es ausserdem reproduzierbar: die fertige PNG haengt nicht
    davon ab, ob Pexels in dem Moment erreichbar ist.
    """
    antwort = requests.get(url, timeout=config.BILDER_TIMEOUT)
    antwort.raise_for_status()
    typ = antwort.headers.get("Content-Type", "image/jpeg").split(";")[0]
    if not typ.startswith("image/"):
        return None
    return f"data:{typ};base64,{base64.b64encode(antwort.content).decode()}"


def thema(item: dict, slides: dict) -> dict | None:
    """Das Bildthema dieser Meldung, ohne einen einzigen Netzaufruf.

    Getrennt von hole(), weil die Cover-Variante zuerst feststehen muss: 1d
    und 1f brauchen ein Hochformat, 1e ein Querformat. Gezogen werden kann die
    Variante aber erst, wenn klar ist, ob es ueberhaupt ein Bild geben wird -
    und genau diese Frage beantwortet diese Funktion, ohne Pexels zu fragen.
    """
    if not config.BILDER_ENABLED:
        return None
    if not os.environ.get("PEXELS_API_KEY", "").strip():
        return None

    text = " ".join([item.get("title", ""), slides.get("titel", ""),
                     slides.get("hook", "")])
    getroffen = _thema_finden(text)
    if not getroffen:
        print("  - kein Bildthema getroffen, Cover bleibt typografisch")
    return getroffen


def hole(thema: dict, ausrichtung: str = "landscape") -> dict | None:
    """Holt das Foto zum Thema in der gewuenschten Ausrichtung. Wirft nie."""
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not thema or not key:
        return None

    try:
        antwort = requests.get(
            SUCHE,
            headers={"Authorization": key},
            params={"query": thema["suche"], "orientation": ausrichtung,
                    "locale": "de-DE", "per_page": 15},
            timeout=config.BILDER_TIMEOUT)
        antwort.raise_for_status()
        fotos = antwort.json().get("photos", [])

        for foto in fotos:
            if foto.get("width", 0) < config.BILDER_MIN_BREITE:
                continue
            quelle = foto.get("src", {}).get("large")
            if not quelle:
                continue
            data_uri = _als_data_uri(quelle)
            if not data_uri:
                continue
            print(f"  = Bild [{thema['thema']}] von {foto.get('photographer')}")
            return {
                "data_uri": data_uri,
                "fotograf": foto.get("photographer", "unbekannt"),
                "seite": foto.get("url", "https://www.pexels.com"),
                "thema": thema["thema"],
            }

        print(f"  - kein brauchbares Bild fuer '{thema['suche']}' ({ausrichtung})")
    except Exception as fehler:      # Bilder sind Kuer, nicht Pflicht.
        print(f"  ! Bildsuche fehlgeschlagen: {str(fehler)[:120]}")
    return None


def finde(item: dict, slides: dict, ausrichtung: str = "landscape",
          **_) -> dict | None:
    """Bild fuer die Cover-Slide oder None. Wirft nie.

    Die beiden Schritte in einem - fuer Aufrufer, die die Cover-Variante nicht
    kennen und nur ein Bild wollen.
    """
    return hole(thema(item, slides), ausrichtung)
