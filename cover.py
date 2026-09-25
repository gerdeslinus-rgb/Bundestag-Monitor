"""Waehlt die Cover-Architektur eines Karussells (Design-System §6).

Ein wiederkehrender Account stirbt an Gleichfoermigkeit. Das Cover ist deshalb
die einzige Slide mit variabler Architektur: sechs Layouts, alle aus denselben
zwei Grundflaechen, zwei Schriften und drei Groessen - das Profil bleibt
erkennbar, aber keine zwei Posts sehen aus wie aus einer Form gestanzt.

Gewaehlt wird MECHANISCH, nie nach Laune (§6.1):

1. Nach Eignung filtern. 1a und 1c brauchen eine Figur, 1c ein echtes
   Vorher/Nachher-Paar, 1b eine Frage, die jemand wirklich eintippen wuerde,
   1d/1e/1f ein Foto.
2. Aus dem Rest zufaellig ziehen, die letzten zwei ausgeschlossen. Das
   garantiert drei Posts Abstand, bevor sich ein Layout wiederholt.
3. Bleibt dabei nichts uebrig, nur noch das letzte ausschliessen. Niemals einen
   Liebling von Hand setzen, niemals zweimal hintereinander dieselbe Architektur.

Dieses Modul kennt weder Jinja noch Playwright und laesst sich deshalb direkt
pruefen:

    python -c "import cover; print(cover.pruefen())"
"""

import json
import random
import re
from pathlib import Path

# Variante -> Grundflaeche. Mehr als diese zwei Flaechen gibt es nicht, und der
# Grund des Covers gibt den Wechsel des ganzen Decks vor (§1).
VARIANTEN = {
    "1a": "ink",     # Zahl zuerst
    "1b": "ink",     # Frage
    "1c": "light",   # Vorher / Nachher
    "1d": "ink",     # Senkrechter Schnitt (Foto links)
    "1e": "light",   # Foto unten
    "1f": "ink",     # Vollbild mit Band
    "1g": "light",   # Portraet: Farbfeld rechts, Person auf der Kante (nur Personen)
    "1h": "light",   # Portraet gespiegelt: Farbfeld und Person links, Text rechts
    "1i": "ink",     # Portraet auf Ink: Person rechts vor grossem Akzentkreis
}

# Personen-Karussells ziehen aus diesen drei (Abstimmung 25.09.2026: 1g
# gefiel, aber zwei Personen hintereinander sahen gleich aus).
PORTRAET_VARIANTEN = ("1g", "1h", "1i")

# Varianten, die ein Foto brauchen - und die Ausrichtung, in der sie es
# brauchen. 1d ist eine 430 px schmale Spalte ueber die volle Hoehe, 1f fuellt
# das ganze 1080x1350-Feld: beides Hochformat. Nur 1e nimmt ein Querformat.
FOTO_VARIANTEN = {"1d": "portrait", "1e": "landscape", "1f": "portrait"}

STAND = Path("data/cover_state.json")

# Wie viele Varianten von der Ziehung ausgeschlossen bleiben. Zwei heisst: drei
# Posts Abstand, bevor sich ein Layout wiederholen darf.
GEDAECHTNIS = 2

# Eine Figur ist eine Zahl, ein Betrag, ein Datum - kein Satz. Dieselbe
# Schwelle wie fuer die Pills in render.py: laenger als das laeuft sie in
# Display-Groesse aus ihrem Block heraus.
FIGUR_MAX = 14

# 1f: das Band waechst mit dem Text nach oben und frisst irgendwann das Foto.
# Laenger als das gehoert die Meldung auf 1e.
BAND_WOERTER_MAX = 8

# 1d: die Textspalte ist 650 px breit. Ein Wort wie "GKV-Beitragssatz-
# stabilisierungsgesetz" braucht dort auch bei 56 px vier Zeilen - die Regel
# "hoechstens drei" (§6.2) ist damit nicht zu halten. So ein Wort passt auf
# die volle Breite, nicht in die Spalte.
SPALTE_WORT_MAX = 22


def letzte_laden() -> list:
    """Die zuletzt gezogenen Varianten. Fehlt die Datei, ist das kein Fehler:
    beim ersten Lauf gibt es schlicht noch keine Vorgeschichte."""
    try:
        daten = json.loads(STAND.read_text(encoding="utf-8"))
        return [v for v in daten.get("lastCovers", []) if v in VARIANTEN]
    except (OSError, ValueError, AttributeError):
        return []


def letzte_speichern(ids: list) -> None:
    STAND.parent.mkdir(exist_ok=True)
    STAND.write_text(
        json.dumps({"lastCovers": list(ids)[:GEDAECHTNIS]}, indent=1),
        encoding="utf-8")


def merken(variante: str, zuletzt: list) -> list:
    """Die gezogene Variante vorn anstellen, auf zwei kuerzen."""
    return [variante, *[v for v in zuletzt if v != variante]][:GEDAECHTNIS]


def _figur_kandidaten(slides: dict) -> list:
    """Figuren, die als Hero-Zahl auf dem Cover taugen, beste zuerst.

    1a heisst "Zahl zuerst" und traegt nur, wo eine Summe die Meldung IST.
    Deshalb zuerst die neue Spalte der Folgen-Tabelle und die Kennzahlen der
    Fallkarten: das sind Betraege und Saetze. Die Pills stehen dahinter, denn
    dort liegt nach der Spec gerade das, was KEIN Vorher/Nachher ist - eine
    Frist, eine Handlung. "01.01.27" in 240 px ist ein Kalenderblatt, keine
    Schlagzeile.

    Der hervorgehobene Chart-Balken steht am Ende als Boden: ein Chart hat
    jedes Karussell, auch ein Profil-Karussell. Damit ist 1a praktisch immer
    waehlbar, und die Ziehung laeuft nie ins Leere.
    """
    # Datenkarussells (weitere.py) wissen selbst, welche Zahl die Meldung
    # IST - "61 Organisationen" steht in keinem Balken, sondern ist ihre Summe.
    # Und sie wissen, wann es keine gibt: eine Anzahl "3" oder die Groesse
    # einer Vergleichsgruppe traegt kein "Zahl zuerst".
    if slides.get("keine_figur"):
        return []
    folgen = slides.get("folgen") or {}
    kandidaten = [slides.get("cover_figur")]
    kandidaten += [z.get("neu") for z in folgen.get("zeilen", []) or []]
    for fall in folgen.get("faelle", []) or []:
        kandidaten += [k.get("wert") for k in fall.get("kennzahlen", []) or []]
    kandidaten += [p.get("wert") for p in folgen.get("pills", []) or []]

    # Rueckfall aus dem Chart: der hervorgehobene Balken ist der Wert, um den
    # es geht. Ohne Angabe der letzte - in einer Zeitreihe der aktuelle.
    chart = slides.get("chart") or {}
    balken = chart.get("balken", []) or []
    if balken:
        i = chart.get("hervorheben")
        if not isinstance(i, int) or not 0 <= i < len(balken):
            i = len(balken) - 1
        wert, einheit = balken[i].get("wert"), chart.get("einheit", "")
        if wert is not None:
            kandidaten.append(f"{_zahl(wert)} {einheit}".strip())

    return [str(k).strip() for k in kandidaten
            if k is not None and 0 < len(str(k).strip()) <= FIGUR_MAX]


def _zahl(wert) -> str:
    """Deutsche Zahlendarstellung: 1200 -> 1.200, 59.1 -> 59,1."""
    try:
        wert = float(wert)
    except (TypeError, ValueError):
        return str(wert)
    if wert.is_integer():
        return f"{int(wert):,}".replace(",", ".")
    return f"{wert:.1f}".replace(".", ",")


def vorher_nachher(slides: dict) -> dict | None:
    """Das erste echte Vorher/Nachher-Paar der Folgen-Slide, oder None.

    1c lebt von zwei Zahlen nebeneinander. Ein Paar, bei dem eine Seite fehlt
    oder ein Satz statt einer Figur steht, traegt die Variante nicht.
    """
    folgen = slides.get("folgen") or {}
    if folgen.get("muster") != "4a":
        return None
    for zeile in folgen.get("zeilen", []) or []:
        alt, neu = str(zeile.get("bisher") or ""), str(zeile.get("neu") or "")
        if alt and neu and max(len(alt), len(neu)) <= FIGUR_MAX:
            return {"label": zeile.get("label", ""), "bisher": alt, "neu": neu,
                    "kopf_neu": folgen.get("kopf_neu") or "neu"}
    return None


def _frage(slides: dict) -> str:
    """Die Cover-Frage des Modells, wenn es eine gibt.

    Sie muss eine Frage sein und vom Karussell beantwortet werden - das
    Zweite kann hier niemand pruefen, das Erste schon.
    """
    frage = str(slides.get("cover_frage") or "").strip()
    return frage if frage.endswith("?") and len(frage) > 5 else ""


def passende(slides: dict, foto: bool, headline: str = "",
             stuetzzeile: str = "", bogen: bool = False) -> list:
    """Die Varianten, die zu dieser Meldung ueberhaupt passen (§6.1 Schritt 1).

    `foto` sagt nur, OB ein Foto zu holen ist - geholt wird es erst, wenn die
    Ziehung eine Fotovariante ergeben hat, denn die Ausrichtung haengt von der
    Variante ab.

    `bogen` heisst: auf Slide 2 steht ein Sitzbogen. Siehe unten - das
    entscheidet ueber die Grundflaeche des Covers.
    """
    passt = []
    # 1a nur, wenn es eine Figur gibt, die nicht ohnehin schon auf dem Cover
    # steht: eine Schlagzeile mit der Zahl darin macht "Zahl zuerst" ueberfluessig.
    if figur(slides, f"{headline} {stuetzzeile}", streng=True):
        passt.append("1a")
    if _frage(slides):
        passt.append("1b")
    if vorher_nachher(slides):
        passt.append("1c")
    if foto:
        laengstes = max((len(w) for w in (headline or "").split()), default=0)
        if laengstes <= SPALTE_WORT_MAX:
            passt.append("1d")
        passt.append("1e")
        if len((headline or "").split()) <= BAND_WOERTER_MAX:
            passt.append("1f")

    # Ein Sitzbogen braucht eine helle Slide 2, und die Grundflaechen wechseln
    # streng ab - also muss das Cover dunkel sein. Der Bogen setzt die Punkte
    # in den Fraktionsfarben, und CDU/CSU ist #151B20: exakt die Ink-Flaeche.
    # Auf dunklem Grund verschwinden damit 208 von 630 Sitzen spurlos, und die
    # uebrigen Fraktionen stehen schlecht darauf. Die Farben sind gesetzt, die
    # Flaeche ist es nicht - also weicht die Flaeche.
    if bogen:
        passt = [v for v in passt if VARIANTEN[v] == "ink"]
    return passt


def waehlen(slides: dict, foto: bool, zuletzt: list, headline: str = "",
            stuetzzeile: str = "", bogen: bool = False) -> str:
    """Eine Variante ziehen (§6.1 Schritt 2 und 3).

    Zufaellig aus den geeigneten, die letzten zwei ausgeschlossen. Bleibt
    dabei nichts uebrig, wird auf "nur das letzte ausschliessen" verbreitert -
    und erst, wenn auch das leer ist, auf den ganzen Eignungssatz. Ein
    Lieblingslayout von Hand gibt es an keiner Stelle.
    """
    # Ein Personen-Karussell zeigt die Person, immer (Abstimmung 25.09.2026):
    # gezogen wird nur unter den Portraet-Architekturen, mit derselben Sperre
    # fuer die letzten zwei.
    if slides.get("portraet"):
        frei = [v for v in PORTRAET_VARIANTEN if v not in zuletzt[:GEDAECHTNIS]]
        return random.choice(frei or list(PORTRAET_VARIANTEN))
    geeignet = passende(slides, foto, headline, stuetzzeile, bogen) or ["1a"]
    for sperre in (zuletzt[:GEDAECHTNIS], zuletzt[:1], []):
        uebrig = [v for v in geeignet if v not in sperre]
        if uebrig:
            return random.choice(uebrig)
    return geeignet[0]


_ZIFFERN = re.compile(r"\d[\d.,]*")


def figur(slides: dict, gezeigt: str = "", streng: bool = False) -> str:
    """Die Hero-Figur fuer 1a: die beste, die auf dem Cover noch nicht steht.

    Kein Fakt zweimal auf derselben Slide. `gezeigt` ist deshalb ALLES, was
    sonst auf dem Cover steht - Schlagzeile UND Stuetzzeile. Die Schlagzeile
    weglassen zu koennen war ein Trugschluss: der erste echte Lauf lieferte
    "Bund und Laender senken Spritsteuer um 17 Cent" und setzte "17 Cent"
    daneben in 240 px. Das ist keine zweite Aussage, das ist ein Echo.

    `streng` trennt die beiden Fragen, die hier zusammenfallen:
    - streng=True fragt "taugt 1a ueberhaupt fuer diese Meldung?" und
      antwortet mit "" , wenn jede Figur schon dasteht. Dann steht die Zahl
      eben in der Schlagzeile, und "Zahl zuerst" haette nichts hinzuzufuegen.
    - streng=False fragt "welche Figur nehmen wir?" und nimmt notfalls die
      erste: ist 1a erst einmal gezogen, waere ein leerer Hero schlimmer als
      eine Wiederholung.
    """
    kandidaten = _figur_kandidaten(slides)
    if not kandidaten:
        return ""
    schon_da = {z.rstrip(".,") for z in _ZIFFERN.findall(gezeigt or "")}
    for kandidat in kandidaten:
        zahlen = {z.rstrip(".,") for z in _ZIFFERN.findall(kandidat)}
        if not (zahlen & schon_da):
            return kandidat
    return "" if streng else kandidaten[0]


def pruefen() -> dict:
    """Selbsttest ohne Netz und ohne Modell: zieht 200 Mal hintereinander und
    prueft, dass sich keine Architektur wiederholt, solange Abstand moeglich
    ist."""
    slides = {"cover_frage": "Was ist eine Pendlerpauschale?",
              "chart": {"einheit": "Cent", "hervorheben": 1,
                        "balken": [{"label": "2024", "wert": 30},
                                   {"label": "ab 2027", "wert": 45}]},
              "folgen": {"muster": "4a", "kopf_neu": "ab 2027",
                         "zeilen": [{"label": "Je Kilometer",
                                     "bisher": "38 Cent", "neu": "45 Cent"}]}}

    zuletzt, folge = [], []
    for _ in range(200):
        gezogen = waehlen(slides, True, zuletzt, "Pendlerpauschale steigt")
        folge.append(gezogen)
        zuletzt = merken(gezogen, zuletzt)

    doppelt = [a for a, b in zip(folge, folge[1:]) if a == b]
    return {"gezogen": sorted(set(folge)),
            "direkte_wiederholung": len(doppelt),
            "figur": figur(slides, "Ab 2027 zahlst du weniger Steuern."),
            "vorher_nachher": vorher_nachher(slides)}


if __name__ == "__main__":
    print(json.dumps(pruefen(), ensure_ascii=False, indent=1))
