"""Namentliche Abstimmungen aus den Plenarprotokollen des Bundestages.

Was hier geht und was nicht - beides ist wichtig, bevor man darauf baut:

- NUR namentliche Abstimmungen liefern Namen und Zahlen. Die meisten Gesetze
  werden per Handzeichen beschlossen; das Protokoll haelt dann allein den
  Tenor fest ("Annahme in Ausschussfassung"), ohne jede Zahl. Fuer solche
  Vorgaenge gibt dieses Modul nichts zurueck, und das ist richtig so.
- Die Zuordnung darf NICHT ueber die Position im Protokoll laufen. Das
  Ergebnis einer Abstimmung wird von der Sitzungsleitung mitten in eine
  voellig andere Debatte hinein verkuendet. Beim Kindergeld-Gesetz stand das
  Ergebnis zum Strassenverkehrsgesetz mitten in der Kindergeld-Aussprache -
  wer nach Naehe zuordnet, behauptet das Gegenteil des Richtigen. Massgeblich
  ist allein der Ankuendigungssatz: "Ergebnis der namentlichen Abstimmung
  ueber X bekannt:".

Der Protokolltext kommt aus der DIP-API (plenarprotokoll-text) und enthaelt
geschuetzte Leerzeichen und Tabulatoren aus dem Satz; die werden vereinheit-
licht, bevor irgendetwas gesucht wird.
"""

import re
import unicodedata

import config

# Fraktionsueberschriften im Namensteil. Der Bundestag setzt sie genau so;
# "Fraktionslos" steht fuer Abgeordnete ohne Fraktion.
FRAKTIONEN = [
    "BÜNDNIS 90/ DIE GRÜNEN", "BÜNDNIS 90/DIE GRÜNEN",
    "CDU/CSU", "SPD", "AfD", "Die Linke", "Fraktionslos", "Fraktionslose",
]

RICHTUNGEN = {"Ja": "ja", "Nein": "nein", "Enthalten": "enthalten"}

_ANKUENDIGUNG = re.compile(
    r"Ergebnis der namentlichen Abstimmung über (?:den |die |das )?(.{5,180}?) bekannt\s*:",
    re.DOTALL)
_SUMME = re.compile(
    r"Abgegebene Stimmen:?\s*(\d+)\s*;?\s*davon\s*ja:?\s*(\d+)\s*nein:?\s*(\d+)"
    r"(?:\s*enthalten:?\s*(\d+))?", re.IGNORECASE)


def _glatt(text: str) -> str:
    """Geschuetzte Leerzeichen und Tabulatoren zu normalen Leerzeichen."""
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("\t", " ")


def _wortmenge(text: str) -> set:
    """Aussagekraeftige Woerter eines Titels - fuer den Abgleich."""
    text = _glatt(text).lower()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    woerter = re.findall(r"[a-z]{4,}", text)
    stopp = {"eines", "einer", "gesetz", "gesetzes", "gesetzentwurf",
             "entwurf", "zweite", "dritte", "beratung", "aenderung", "ueber"}
    return {w for w in woerter if w not in stopp}


def _passt(titel_a: str, titel_b: str) -> float:
    """Wie stark ueberlappen zwei Titel? 0 bis 1, bezogen auf den kuerzeren."""
    a, b = _wortmenge(titel_a), _wortmenge(titel_b)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _namensliste(block: str, erwartet: dict) -> dict | None:
    """Zaehlt Stimmen je Fraktion und Richtung im Namensteil.

    Aufbau im Protokoll: "Ja", dann eine Fraktionsueberschrift, dann die
    Namen, dann die naechste Fraktion - und irgendwann "Nein" mit demselben
    Muster. Jede Zeile, die weder Richtung noch Fraktion ist, ist ein Name.

    Das Ende der Liste ist im Text durch nichts markiert: danach laeuft die
    Sitzung einfach weiter. Wer stumpf bis zum naechsten Anker weiterzaehlt,
    haelt jede folgende Redner- und Zwischenrufzeile fuer eine Stimme - im
    ersten Versuch kamen so 1137 Nein-Stimmen statt 467 heraus. Deshalb sind
    die im Ergebnisblock genannten Summen die Obergrenze: ist eine Richtung
    voll, wird dort nicht weitergezaehlt.

    Stimmen die gezaehlten Summen am Ende nicht mit den amtlichen ueberein,
    gibt die Funktion None zurueck. Eine halb erkannte Namensliste waere
    schlimmer als gar keine - sie saehe vollstaendig aus.
    """
    ergebnis = {}
    gezaehlt = {"ja": 0, "nein": 0, "enthalten": 0}
    richtung = None
    fraktion = None

    for zeile in block.splitlines():
        zeile = _glatt(zeile).strip()
        if not zeile:
            continue
        if zeile in RICHTUNGEN:
            richtung, fraktion = RICHTUNGEN[zeile], None
            continue
        if zeile in FRAKTIONEN:
            fraktion = zeile.replace("BÜNDNIS 90/ DIE", "BÜNDNIS 90/DIE")
            continue
        if not (richtung and fraktion):
            continue
        if gezaehlt[richtung] >= erwartet.get(richtung, 0):
            continue                      # diese Richtung ist vollstaendig
        gezaehlt[richtung] += 1
        ergebnis.setdefault(fraktion, {}).setdefault(richtung, 0)
        ergebnis[fraktion][richtung] += 1
        if all(gezaehlt[r] >= erwartet.get(r, 0) for r in gezaehlt):
            break

    if gezaehlt != {r: erwartet.get(r, 0) for r in gezaehlt}:
        print(f"    ! Namensliste unvollstaendig: {gezaehlt} statt {erwartet}")
        return None
    return ergebnis


def aus_protokoll(protokoll_text: str, titel: str) -> dict | None:
    """Sucht die namentliche Abstimmung zu `titel` in einem Plenarprotokoll.

    Gibt None zurueck, wenn es zu diesem Vorgang keine namentliche Abstimmung
    gab oder der Ankuendigungssatz nicht sicher zugeordnet werden kann. Lieber
    nichts zeigen als das Ergebnis einer fremden Abstimmung.
    """
    text = _glatt(protokoll_text)

    bester = None
    for treffer in _ANKUENDIGUNG.finditer(text):
        gegenstand = " ".join(treffer.group(1).split())
        guete = _passt(gegenstand, titel)
        if guete >= config.ABSTIMMUNG_MIN_UEBERLAPPUNG and (
                bester is None or guete > bester[0]):
            bester = (guete, treffer.end(), gegenstand)
    if bester is None:
        return None

    guete, ab, gegenstand = bester
    # Der Namensteil folgt dem Ankuendigungssatz; der naechste
    # Ankuendigungssatz begrenzt ihn nach hinten.
    naechste = _ANKUENDIGUNG.search(text, ab)
    block = text[ab:naechste.start() if naechste else ab + 120000]

    summe = _SUMME.search(block)
    if not summe:
        return None
    gesamt, ja, nein, enthalten = (int(summe.group(1)), int(summe.group(2)),
                                   int(summe.group(3)),
                                   int(summe.group(4) or 0))

    erwartet = {"ja": ja, "nein": nein, "enthalten": enthalten}
    fraktionen = _namensliste(block[summe.end():], erwartet)
    if fraktionen is None:
        return None

    return {
        "gegenstand": gegenstand,
        "guete": round(guete, 2),
        "gesamt": gesamt, "ja": ja, "nein": nein, "enthalten": enthalten,
        "angenommen": ja > nein,
        "fraktionen": fraktionen,
    }
