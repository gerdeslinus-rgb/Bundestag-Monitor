"""Baut aus einem geprueften Karussell die Instagram-Slides (1080x1350)."""

import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from playwright.sync_api import sync_playwright

import bilder
import config
import cover
import logos
import sitzbogen

OUT = Path("out")
HANDLE = "@Bundestag_Monitor"
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


# Balkenbeschriftungen, die eine Ablehnung oder einen offenen Stand meinen.
# Die bekommen die leere Kontur statt eines Balkens: ein gefuellter Balken
# liest sich als Zustimmung, egal was daneben steht.
NEGATIV = ("nein", "abgelehnt", "dagegen", "offen", "ausstehend")

# Betrag und Einheit duerfen nie umbrechen: "1.500 €", nicht "1.500" + "€".
_BETRAG = re.compile(
    r"(\d[\d.,]*)\s+(%|€|Prozent|Euro|Mrd\.?|Mio\.?|Milliarden|Millionen)")

# Freistehender Gedankenstrich. Das Design-System laesst als Satzzeichen nur
# Doppelpunkt, Komma und Punkt zu, und ein Gedankenstrich ist eines der
# deutlichsten Merkmale von Modelltext. Bereiche ("2024–2026") bleiben, weil
# dort keine Leerzeichen stehen.
_STRICH = re.compile(r"\s+[–—]\s+")


def _grounds(anzahl: int, start: str = "ink") -> list:
    """Grundflaeche je Slide, streng abwechselnd - zwei gleiche Flaechen
    nebeneinander gibt es nicht.

    Angefangen wird beim Grund des gezogenen Covers: die sechs Architekturen
    stehen teils auf Ink (1a, 1b, 1d, 1f), teils auf Off-White (1c, 1e). Bei
    einem hellen Cover laeuft das Deck also light, ink, light, ink, light. Die
    Abwechslung ist die Regel, nicht die feste Zuordnung einzelner Slides.
    """
    wechsel = ["ink", "light"] if start == "ink" else ["light", "ink"]
    return [wechsel[i % 2] for i in range(anzahl)]


def _betrag_zusammenhalten(safe: str) -> str:
    return _BETRAG.sub(r"\1&nbsp;\2", safe)


def _betrag_filter(text) -> Markup:
    """Jinja-Filter fuer Fliesstext: maskiert, entstricht, haelt Betraege
    zusammen.

    Laeuft ueber jede Modell-Ausgabe im Template - deshalb hier maskieren und
    nicht im Template mit |safe an der Maskierung vorbei. Und deshalb steht
    auch die Strich-Regel hier: der Prompt verbietet Gedankenstriche, aber
    verlassen kann man sich darauf nicht, und auf der Karte faellt es auf.
    """
    return Markup(_betrag_zusammenhalten(escape(_ohne_strich(str(text)))))


def _ohne_strich(text: str) -> str:
    return _STRICH.sub(", ", text)


def _teilen(text: str):
    """Zerlegt eine Headline in Kopf und Schlussteil.

    Der Schlussteil ist das letzte Wort - ist das sehr kurz ("ab", "an"),
    die letzten beiden Woerter, sonst steht da ein Briefmarken-Kaestchen ohne
    Aussage. Rueckgabe: (Kopf-HTML, Trenner, Schlussteil) oder None.
    """
    safe = _betrag_zusammenhalten(escape(_ohne_strich(text.strip())))

    treffer = re.search(r"(?P<sep>\s+)(?P<letzt>\S+)\s*$", safe)
    if treffer and len(treffer.group("letzt")) <= 4:
        treffer = re.search(r"(?P<sep>\s+)(?P<letzt>\S+\s+\S+)\s*$",
                            safe) or treffer
    if not treffer:
        return None, None, safe

    return (safe[:treffer.start()].replace("\n", "<br>"),
            "<br>" if "\n" in treffer.group("sep") else " ",
            treffer.group("letzt").replace("\n", " "))


# Zwei Zeilen Headline, mehr nicht: bei 80 px Zilla Slab passen rund 25
# Zeichen in eine Zeile ueber die Slidebreite. Laenger heisst dritte Zeile,
# und dann rutscht der Inhaltsbereich nach unten weg.
HEADLINE_MAX = 50

# Ein einzelnes Wort ist die zweite Art, zu lang zu sein, und HEADLINE_MAX
# sieht sie nicht: "Werbungskostenpauschbetrag seit 1955" sind 35 Zeichen,
# also unauffaellig - trotzdem lief das Kompositum ueber den Rand. Seit das
# Template trennt, bricht es sauber um; die Warnung bleibt, weil eine
# getrennte Zeile drei Zeilen aus der Headline machen kann.
HEADLINE_WORT_MAX = 18

# Ab hier wird die Schlagzeile doch kleiner gesetzt - als letzte Stufe, wenn
# Trennung und Umbruch die Zeilenzahl nicht mehr halten.
#
# Das Design-System verbietet das in seiner urspruenglichen Fassung ("never
# shrink the display size: cut words instead"). Die Regel geht davon aus,
# dass eine zu lange Schlagzeile ein Textproblem ist - aber gekuerzt wird
# beim naechsten Lauf vom Modell, und bis dahin steht eine vierzeilige
# Schlagzeile auf der Karte. Vier Zeilen zerlegen das Cover: die Stuetzcopy
# rutscht weg, und bei 96 px versal steht in jeder Zeile nur noch ein
# Wortfragment.
#
# Die Stufung ist deshalb nach demselben Muster gebaut wie die einzige
# Ausnahme, die die Spec schon kennt (Hero-Zahl 240 -> 200): die kleinere
# Groesse ERSETZT die groessere, sie kommt nicht dazu. DESIGN-SYSTEM.md ist
# entsprechend nachgezogen.
HEADLINE_ZEILEN_MAX = 3
HEADLINE_STUFE_PX = 8
HEADLINE_MIN_PX = 56

# Zeilen zaehlen, nicht schaetzen. Eine Rechnung aus Zeichenzahl und
# mittlerer Zeichenbreite geht bei versal gesetzten Komposita daneben - und
# genau die sind der Fall, um den es geht. Gezaehlt werden die
# Oberkanten der Textkaestchen: der Highlight-Block (.hl) ist ein
# inline-block mit eigener Polsterung und liefert ein zweites Kaestchen in
# derselben Zeile, deshalb wird mit halber Zeilenhoehe gruppiert.
_ZEILEN_JS = """(el) => {
  const lh = parseFloat(getComputedStyle(el).lineHeight) || 1;
  const r = document.createRange();
  r.selectNodeContents(el);
  const tops = [...r.getClientRects()].map(k => k.top).sort((a, b) => a - b);
  let zeilen = 0, letzte = -1e9;
  for (const t of tops) {
    if (t - letzte > lh / 2) { zeilen++; letzte = t; }
  }
  return zeilen;
}"""


def _zeilen_deckeln(page, kind: str) -> None:
    """Setzt die Schlagzeile so lange kleiner, bis sie in drei Zeilen passt."""
    el = page.query_selector("section h1")
    if not el:
        return

    zeilen = page.evaluate(_ZEILEN_JS, el)
    if zeilen <= HEADLINE_ZEILEN_MAX:
        return

    start = page.evaluate("(el) => parseFloat(getComputedStyle(el).fontSize)", el)
    groesse = start
    while zeilen > HEADLINE_ZEILEN_MAX and groesse - HEADLINE_STUFE_PX >= HEADLINE_MIN_PX:
        groesse -= HEADLINE_STUFE_PX
        page.evaluate("([el, px]) => el.style.fontSize = px + 'px'", [el, groesse])
        zeilen = page.evaluate(_ZEILEN_JS, el)

    if zeilen > HEADLINE_ZEILEN_MAX:
        print(f"    ! Schlagzeile bleibt {zeilen}-zeilig auch bei "
              f"{groesse:.0f} px ({kind}) - im Modell kuerzen")
    else:
        print(f"    = Schlagzeile {start:.0f} -> {groesse:.0f} px "
              f"fuer {zeilen} Zeilen ({kind})")


def _block(text: str) -> str:
    """Letztes Wort im Highlight-Block. Genau einer pro Headline.

    Der Block ist das Signaturelement des Decks. Er steht auf den
    Inhalts-Slides und, seit es die sechs Architekturen gibt, auch auf den
    hellen Covern (1c und 1e) - dort ist er die eine Akzentbewegung.
    """
    kopf, trenner, schluss = _teilen(text)
    if kopf is None:
        return f'<span class="hl">{schluss}</span>'
    return f'{kopf}{trenner}<span class="hl">{schluss}</span>'


def _headline(text: str) -> str:
    """Headline der Inhalts-Slides.

    Die Laengenwarnung haengt an dieser Funktion und nicht an _block(): sie
    ist auf 80 px ueber die volle Slidebreite gerechnet und waere auf einem
    Cover, das versal bei 96 px setzt, schlicht die falsche Zahl.
    """
    if len(text or "") > HEADLINE_MAX:
        print(f"    ! Headline laeuft ueber zwei Zeilen ({len(text)} Zeichen): "
              f"{text[:60]}")
    laengstes = max((text or "").split(), key=len, default="")
    if len(laengstes) > HEADLINE_WORT_MAX:
        print(f"    ! Kompositum in der Headline ({len(laengstes)} Zeichen), "
              f"wird getrennt: {laengstes}")
    return _mit_parteilogos(text, _block)


def _cover_headline(text: str) -> str:
    """Cover-Headline auf Ink: kein Block, sondern akzentblaue Woerter.

    Der Block wuerde auf der versal gesetzten Cover-Zeile wie ein Etikett
    wirken. Auf dunklem Grund loest die Spec das Cover deshalb ueber Farbe.
    """
    kopf, trenner, schluss = _teilen(text)
    if kopf is None:
        return f'<span class="accent">{schluss}</span>'
    return f'{kopf}{trenner}<span class="accent">{schluss}</span>'


def _zahl(wert: float) -> str:
    """Deutsche Zahlendarstellung: 1200 -> 1.200, 59.1 -> 59,1"""
    if float(wert).is_integer():
        return f"{int(wert):,}".replace(",", ".")
    return f"{wert:.1f}".replace(".", ",")


# Parteien, wie sie in Schlagzeilen und Balkenbeschriftungen stehen, auf den
# Schluessel der Logo-Handliste (data/logos/logos.json). Gross geschrieben
# und als ganzes Wort: "linke Mehrheit" oder "gruener Wasserstoff" bleiben
# Text. Laengere Formen zuerst, sonst frisst "CDU" das "CDU/CSU".
PARTEIEN = [("CDU/CSU", ("CDU", "CSU")), ("Bündnis 90/Die Grünen", ("Grüne",)),
            ("Grünen", ("Grüne",)), ("Grüne", ("Grüne",)), ("Linken", ("Linke",)),
            ("Linke", ("Linke",)), ("CDU", ("CDU",)), ("CSU", ("CSU",)),
            ("SPD", ("SPD",)), ("AfD", ("AfD",)), ("FDP", ("FDP",)),
            ("BSW", ("BSW",)), ("SSW", ("SSW",)), ("Volt", ("Volt",))]
_PARTEI = re.compile(
    r"(?<![\w/])(?:(?:[Dd]ie|[Dd]er|[Dd]as|[Dd]en|[Dd]em)\s+)?(?P<p>"
    + "|".join(re.escape(p) for p, _ in PARTEIEN) + r")(?![\w/])")
_PARTEI_LOGOS = dict(PARTEIEN)

# Die Logos einer Slide-Folge, gesammelt fuer die Caption. build_carousel
# setzt die Liste je Karussell neu; die Headline-Funktionen haengen an.
_KOPF_CREDITS: list = []


def _partei_in(text: str) -> str | None:
    """Logo-Schluessel der ersten Partei im Text, oder None."""
    treffer = _PARTEI.search(text or "")
    return _PARTEI_LOGOS[treffer.group("p")][0] if treffer else None


def _partei_img(partei: str) -> str:
    """Die Logos einer Partei als Inline-Bilder fuer eine Schlagzeile. Ohne
    Logo bleibt der Name stehen - nie ein leerer Platz."""
    bilder = [_logo(k, _KOPF_CREDITS) for k in _PARTEI_LOGOS[partei]]
    if not all(bilder):
        return escape(partei)
    return "".join(f'<img class="partei-logo{" ohne-kachel" if b in _OHNE_KACHEL else ""}" '
                   f'src="{b}" alt="{escape(k)}">'
                   for b, k in zip(bilder, _PARTEI_LOGOS[partei]))


def _mit_parteilogos(text: str, bauer) -> str:
    """Schlagzeile mit Parteilogo statt Parteiname (Abstimmung 25.09.2026:
    in Kopfzeilen immer das Logo, im Fliesstext der Name).

    Steht die Partei am Ende ("Grossspende an die Gruenen"), traegt das Wort
    davor die Akzentbewegung - ein Logo im Highlight-Block waere ein
    Etikett auf einem Etikett. Der Artikel faellt mit dem Namen weg: "an
    [Logo]" liest sich, "an die [Logo]" nicht.
    """
    text = (text or "").strip()
    ende = None
    for t in _PARTEI.finditer(text):
        ende = t
    if ende and not text[ende.end():].strip(" .!?"):
        kopf = text[:ende.start()].rstrip()
        # "Grossspende an [Logo]": das "an" ist kein Wort fuer den Block -
        # markiert wird das Wort davor, das Kurzwort steht dahinter.
        kurz = ""
        teile = kopf.rsplit(" ", 1)
        if len(teile) == 2 and len(teile[1]) <= 4:
            kopf, kurz = teile[0], f" {escape(teile[1])}"
        html = bauer(kopf) if kopf else ""
        # Kurzwort und Logo bleiben zusammen: sonst stand "AN" am Zeilenende
        # und das Logo allein in der naechsten Zeile.
        schluss = f'<span class="partei-ende">{kurz.strip()} {_partei_img(ende.group("p"))}</span>'
        return f'{html} {schluss}'.strip()
    html = bauer(text)
    return _PARTEI.sub(lambda t: _partei_img(t.group("p")), html)


def _logo(name: str | None, credits: list) -> str:
    """data-URI des Logos oder "". Der Bildnachweis landet in `credits` und
    von dort in der Caption - auf der Karte steht er nicht."""
    gefunden = logos.logo(name) if name else None
    if not gefunden:
        return ""
    credits.append(gefunden["credit"])
    if not gefunden.get("kachel", True):
        _OHNE_KACHEL.add(gefunden["data_uri"])
    return gefunden["data_uri"]


# Logos mit eigener Flaeche (logos.json "kachel": false). Das Template fragt
# per Test "ohne_kachel", ob die weisse Kachel wegfaellt.
_OHNE_KACHEL: set = set()


def _chart_daten(chart: dict, credits: list | None = None) -> dict:
    """Rechnet die Balken auf Prozentbreiten um. Der groesste Balken ist 100 %,
    damit auch kleine Unterschiede noch sichtbar bleiben.

    Hervorgehoben wird der Balken, um den es in der Meldung geht - den gibt
    das Modell als "hervorheben" an. Ohne Angabe der letzte, denn der ist in
    einer Zeitreihe ueblicherweise der aktuelle Wert.
    """
    # "Bussgeldrahmen bisher vs neu (Euro)" - die Einheit steht schon an jedem
    # Balken. In der Headline kostet sie nur eine Zeile.
    titel = re.sub(r"\s*\((?:in\s+)?[^()]{2,12}\)\s*$", "",
                   chart.get("titel", "")).strip()

    # Ein Datenkarussell darf die Obergrenze fuer sich anheben (Parteien:
    # fuenf), das Modell nicht - dort bleibt es bei CHART_MAX_BARS.
    balken = list(chart.get("balken", []))[:chart.get("max_balken") or config.CHART_MAX_BARS]
    credits = [] if credits is None else credits
    werte = [abs(float(b.get("wert", 0))) for b in balken] or [1]
    groesster = max(werte) or 1

    # Sobald ein Wert negativ ist, laufen die Balken von einer Nulllinie in
    # der Mitte aus: Anstiege nach rechts, Rueckgaenge nach links. Vorher war
    # -10,2 % ein Balken fast so lang wie +12,7 % - nur das Minuszeichen
    # verriet die Richtung. Ohne negative Werte bleibt alles linksbuendig.
    divergent = any(float(b.get("wert", 0)) < 0 for b in balken)

    # Farbe nur auf ausdrueckliche Wertung des Modells, aus Sicht der
    # meisten Haushalte: "hoch_gut" (Loehne: Anstieg gruen) oder
    # "hoch_schlecht" (Preise, Unfaelle: Anstieg rot, Rueckgang gruen - seit
    # 25.09.2026, vorher blieben Hauspreise grau). Ohne Angabe neutral navy.
    wertung = chart.get("wertung")
    farbig = wertung in ("hoch_gut", "hoch_schlecht")
    umgekehrt = wertung == "hoch_schlecht"

    markiert = chart.get("hervorheben")
    if not isinstance(markiert, int) or not 0 <= markiert < len(balken):
        markiert = len(balken) - 1

    einheit = chart.get("einheit", "")
    aufbereitet = []
    for i, b in enumerate(balken):
        wert = float(b.get("wert", 0))
        label = b.get("label", "")
        # Die Einheit steht am Balken, und nur dort. Eine Zeile "Angaben in
        # Prozent" unter einer Reihe von "4,6 %" sagt denselben Fakt zweimal.
        anteil = abs(wert) / groesster
        if divergent:
            breite = max(round(anteil * 50, 1), 1)
            links = 50 if wert >= 0 else 50 - breite
        else:
            breite, links = max(round(anteil * 100), 2), 0
        richtung = ""
        if farbig and wert != 0:
            richtung = "gut" if (wert > 0) != umgekehrt else "schlecht"
        # Ablehnung und offener Stand bekommen die leere Kontur, der Balken
        # der Meldung die volle Farbe, der Rest gedaempft.
        tonung = ("nein" if label.strip().lower().startswith(NEGATIV)
                  else "" if i == markiert else "muted")
        aufbereitet.append({
            "label": label,
            # Ein Bauer darf die Anzeige vorgeben: bei Nebentaetigkeiten
            # steht der gemeldete Betrag mit Zeitraum ("11.227 € / Monat"),
            # die Balkenlaenge folgt dem Jahreswert.
            "anzeige": _wert(b["anzeige"]) if b.get("anzeige")
            else _wert(f"{_zahl(wert)} {einheit}".strip()),
            "prozent": breite,
            "links": links,
            "tonung": f"{tonung} {richtung}".strip(),
            # Parteien tragen in Diagrammen IMMER ihr Logo (25.09.2026), auch
            # wenn der Bauer keins angegeben hat - etwa beim Modell-Chart.
            "logo": _logo(b.get("logo") or _partei_in(label), credits),
        })
    return {**chart, "titel": titel, "balken": aufbereitet,
            "divergent": divergent}


# Die Teaserzeile unter der Schlagzeile ist eine Zeile, kein Absatz.
COVER_TEASER_MAX = 90

# Ab hier wird die Schlagzeile nicht kleiner gesetzt, sondern gekuerzt: das
# Design-System verbietet eine kleinere Display-Groesse auf dem Cover
# ausdruecklich ("cut words instead"). Die Warnung hier ist der Hinweis, dass
# im Modell Woerter zu streichen sind, nicht im Layout Pixel.
COVER_WOERTER_MAX = 14

# Eine Pill zeigt eine Figur in Display-Groesse. Laenger als das ist kein
# Wert mehr, sondern ein Satz ("Preisbehoerden der Laender").
PILL_FIGUR_MAX = 14

# Piktogramme, die das Template kennt. Alles andere faellt auf "person"
# zurueck - lieber ein neutrales Zeichen als ein leeres Kaestchen.
SYMBOLE = {"person", "haus", "auto", "geld", "uhr", "dokument"}

# Ueberschrift ueber den Schritten in Muster 4c.
SCHRITT_TITEL = "Nur in diesen Fällen musst du selbst ran"


# In Display-Groesse wird aus dem Wort das Zeichen. "100.000 Euro" ist bei
# 80 px rund 440 px breit und laeuft aus der Karte heraus, "100.000 €" passt -
# und das Design-System schreibt Betraege ohnehin so ("1.500 €", "~127 €").
# Nur fuer Figuren, nicht fuer Fliesstext: dort liest sich das Wort besser.
_EINHEIT = [(re.compile(r"(\d)\s*Euro\b"), r"\1 €"),
            (re.compile(r"(\d)\s*Prozent\b"), r"\1 %")]


def _wert(text) -> Markup:
    """Eine Zahl oder ein Betrag als sicheres HTML.

    Figuren stehen im Template in |safe, weil sie das geschuetzte Leerzeichen
    brauchen - maskiert wird deshalb hier.
    """
    roh = _ohne_strich(str(text or ""))
    for muster, ersatz in _EINHEIT:
        roh = muster.sub(ersatz, roh)
    return Markup(_betrag_zusammenhalten(escape(roh)))


def _cover_text(slides: dict, item: dict) -> tuple:
    """Schlagzeile und Stuetzzeile des Covers.

    Die Schlagzeile ist der Titel: er ist auf 60 Zeichen gebaut und traegt
    versal. Darunter steht der Haken als kurze Stuetzzeile. Umgekehrt ging es
    nicht - ein Haken von 150 Zeichen lief versal aus dem Panel heraus, und
    der amtliche Meldungstitel als Teaser las sich wie eine Drucksache.

    Ist der Haken doch einmal lang, bleibt nur sein erster Satz stehen: unter
    der Schlagzeile ist Platz fuer eine Zeile, nicht fuer einen Absatz.
    """
    hook = (slides.get("hook") or "").strip()
    titel = (slides.get("titel") or item.get("title") or "").strip()

    kopf = titel or hook
    zeile = hook if hook and hook != kopf else item.get("title", "")
    if len(zeile) > COVER_TEASER_MAX:
        erster = zeile.split(". ")[0].rstrip(".")
        zeile = f"{erster}." if len(erster) < len(zeile) else zeile

    return kopf, zeile


def _cover(slides: dict, item: dict, bild_thema: dict | None, zuletzt: list,
           erzwungen: str | None = None, bogen: bool = False) -> dict:
    """Der komplette Cover-Kontext: gezogene Architektur plus ihre Daten.

    Gezogen wird in cover.py und nur dort - hier steht, was die gezogene
    Variante an Daten braucht. Die Auszeichnung der Schlagzeile haengt am
    Grund: auf Ink akzentblaue Woerter, auf hellem Grund der Highlight-Block.
    Nie beides, das ist die eine erlaubte Akzentbewegung je Cover.
    """
    kopf, zeile = _cover_text(slides, item)
    variante = erzwungen or cover.waehlen(slides, bool(bild_thema), zuletzt,
                                          kopf, zeile, bogen)
    grund = cover.VARIANTEN[variante]

    # Die Ziehung kennt die Bogen-Regel, ein erzwungenes Cover umgeht sie.
    # Erzwungen wird nur in der Vorschau, und dort soll die Variante auch
    # wirklich kommen - aber ungesagt bleiben darf es nicht.
    if erzwungen and bogen and grund == "light":
        print(f"    ! Cover {variante} ist hell, damit wird Slide 2 dunkel - "
              f"auf Ink verschwinden die CDU/CSU-Punkte des Sitzbogens")

    # 1b traegt die Frage als Schlagzeile: sie ist der Haken dieser Architektur,
    # und Slide 3 beantwortet sie.
    if variante == "1b":
        kopf = str(slides.get("cover_frage") or "").strip() or kopf

    if len(kopf.split()) > COVER_WOERTER_MAX:
        print(f"    ! Cover-Schlagzeile hat {len(kopf.split())} Woerter - "
              f"Woerter streichen, die Groesse bleibt: {kopf[:60]}")

    ctx = {
        "cover_variante": variante,
        "ground": grund,
        # Genau eine Akzentbewegung je Cover: auf Ink akzentblaue Woerter, auf
        # hellem Grund der Highlight-Block. Nie beides.
        "headline_html": _mit_parteilogos(
            kopf, _cover_headline if grund == "ink" else _block),
        # Ein <div> je Satz: wo ein Umbruch sitzen soll, wird er strukturell
        # gesagt. Zwei Zeilen sind das Maximum, drei gibt es nicht.
        "lead_saetze": [zeile] if zeile else [],
    }

    if variante == "1a":
        # Alles, was sonst auf dem Cover steht: die Figur darf keines davon
        # wiederholen.
        figur = cover.figur(slides, f"{kopf} {zeile}")
        ctx["figur"] = _wert(figur)
        # Laenger als "1.500 €" passt die Figur nicht in eine Zeile. Die 200
        # ersetzen die 240, sie kommen nicht dazu: es bleiben drei Groessen.
        ctx["figur_breit"] = len(figur) > 7
    elif variante == "1c":
        paar = cover.vorher_nachher(slides) or {}
        ctx["vn"] = {**paar,
                     "bisher": _wert(paar.get("bisher")),
                     "neu": _wert(paar.get("neu"))}
    return ctx


# Die Begriffs-Slide traegt Karte und Pfeilliste. Beides zusammen kann laenger
# werden als die Slide hoch ist, und dann ueberdeckt die Karte die Headline -
# gerechnet wird deshalb vorher, nicht gehofft.
ZEILE_HOCH = 44.8               # 32 px Text, line-height 1.4
KARTE_SPALTE = 728              # Kartenbreite minus Polsterung minus Badge-Spur
PFEIL_SPALTE = 830              # Slidebreite minus 80 px Pfeilspur minus Luft
ZEICHEN_BREIT = 15.2            # mittlere Zeichenbreite bei 32 px Archivo
INHALT_HOCH = 930               # was zwischen Headline und Fuss frei ist


def _zeilen(text: str, spalte: float) -> int:
    return max(1, -(-int(len(text) * ZEICHEN_BREIT) // int(spalte)))


def _begriff_passt(begriff: dict) -> bool:
    bloecke = list(begriff.get("saetze", []))
    if begriff.get("beispiel"):
        bloecke.append(begriff["beispiel"])
    karte = 80 + 20 * (len(bloecke) - 1) + sum(
        _zeilen(t, KARTE_SPALTE) * ZEILE_HOCH for t in bloecke)

    warum = begriff.get("warum") or []
    pfeile = 0.0
    if warum:
        pfeile = 45 + 40 + 30 * (len(warum) - 1) + sum(
            max(_zeilen(t, PFEIL_SPALTE) * ZEILE_HOCH, 45) for t in warum)

    return karte + 40 + pfeile <= INHALT_HOCH


def _begriff_kuerzen(begriff: dict) -> dict:
    """Streicht so lange den letzten Grund bzw. Satz, bis die Slide passt.

    Das Design-System laesst 2 bis 3 Saetze und 2 bis 3 Pfeilzeilen zu - der
    dritte ist also verzichtbar, ein ueberlappender Text nicht. Gestrichen
    wird von hinten und nie unter zwei, und das Beispiel bleibt immer: es ist
    die Pointe der Karte.
    """
    gekuerzt = {**begriff,
                "saetze": list(begriff.get("saetze") or []),
                "warum": list(begriff.get("warum") or [])}

    while not _begriff_passt(gekuerzt):
        if len(gekuerzt["warum"]) > 2:
            gekuerzt["warum"].pop()
        elif len(gekuerzt["saetze"]) > 2:
            gekuerzt["saetze"].pop()
        elif len(gekuerzt["warum"]) > 1:
            gekuerzt["warum"].pop()
        else:
            print("    ! Begriffs-Slide bleibt eng - Text im Modell kuerzen")
            break

    weg = ((len(begriff.get("saetze") or []) - len(gekuerzt["saetze"]))
           + (len(begriff.get("warum") or []) - len(gekuerzt["warum"])))
    if weg:
        print(f"    - Begriffs-Slide: {weg} Block/Bloecke gestrichen, sonst "
              f"ueberlappt die Karte die Headline")
    return gekuerzt


def _figuren(folgen: dict) -> list:
    """Die Figuren des gewaehlten Musters, roh wie vom Modell geliefert.

    Nur die Felder, die auf der Karte in Display-Groesse stehen - Labels und
    Fliesstext gehoeren nicht dazu, sonst meldet die Doppelungspruefung jede
    Jahreszahl aus einem Nebensatz.
    """
    werte = []
    for zeile in folgen.get("zeilen", []) or []:
        werte += [zeile.get("bisher"), zeile.get("neu")]
    werte += [p.get("wert") for p in folgen.get("pills", []) or []]
    werte.append(folgen.get("payoff"))
    for fall in folgen.get("faelle", []) or []:
        werte += [k.get("wert") for k in fall.get("kennzahlen", []) or []]
    return [str(w) for w in werte if w]


_JAHR = re.compile(r"(?:19|20)\d{2}")


def _wiederholte_figur(slides: dict) -> list:
    """Zahlen, die Slide 4 aus Schlagzeile oder Chart wiederholt.

    Slide 4 soll den Befund uebersetzen, nicht noch einmal aufsagen. Die
    Erzeugerpreis-Meldung hatte "+4,6 Prozent" in der Schlagzeile, im Chart
    und als Hauptfigur der Folgen-Slide - dreimal dieselbe Zahl.

    Jahreszahlen bleiben aussen vor: "ab 2027" darf auf mehreren Slides
    stehen, das ist eine Zeitangabe und keine Kennzahl.
    """
    folgen = slides.get("folgen") or {}
    chart = slides.get("chart") or {}
    if not folgen:
        return []

    gezeigt = set()
    for balken in chart.get("balken", []) or []:
        try:
            gezeigt.add(_zahl(float(balken.get("wert"))))
        except (TypeError, ValueError):
            continue
    for text in (slides.get("titel"), slides.get("hook"), chart.get("titel")):
        gezeigt.update(z.rstrip(".,") for z in re.findall(r"\d[\d.,]*", text or ""))

    doppelt = {zahl.rstrip(".,")
               for figur in _figuren(folgen)
               for zahl in re.findall(r"\d[\d.,]*", figur)
               if zahl.rstrip(".,") in gezeigt
               and not _JAHR.fullmatch(zahl.rstrip(".,"))}
    return sorted(doppelt)


def _folgen(slides: dict) -> dict | None:
    """Slide 4 auf eines der vier Muster bringen (Design-System §7).

    Freier Fliesstext ist auf dieser Slide nicht vorgesehen: das Muster
    entscheidet ueber die Form, nicht die Textlaenge. Liefert das Modell kein
    `folgen` (aeltere Laeufe, Profil-Modus), wird aus dem vorhandenen `sowhat`
    ein 4c gebaut - Payoff-Karte plus Schritte.
    """
    folgen = slides.get("folgen") or {}
    muster = folgen.get("muster")

    if muster == "4a" and folgen.get("zeilen"):
        # Die Tabelle hat eine feste Breite; eine sehr lange Figur schiebt
        # sich sonst still aus der Karte. Lieber im Lauf sichtbar machen.
        for z in folgen["zeilen"]:
            if len(str(_wert(z.get("neu")))) > 16:
                print(f"    ! Figur '{z.get('neu')}' ist lang - Karte pruefen")

        # Eine Pill traegt eine Figur, keinen Satz: die Figur steht in
        # Display-Groesse und laeuft als Fliesstext aus der Pill heraus
        # ("Preisbehoerden der Laender" bei 80 px). Was keine Figur ist, wird
        # zur Nachbemerkung unter der Karte - dort ist Platz fuer Sprache.
        pills, prosa = [], []
        for p in folgen.get("pills", []) or []:
            roh = str(p.get("wert") or "").strip()
            if len(roh) <= PILL_FIGUR_MAX:
                pills.append({"label": p.get("label", ""), "wert": _wert(roh)})
            else:
                prosa.append(f"{p.get('label', '')}: {roh}".strip(": "))
        hinweis = ". ".join(filter(None, [folgen.get("hinweis", "").rstrip("."),
                                          *prosa]))
        if prosa:
            print(f"    - {len(prosa)} Pill(s) ohne Figur in die Nachbemerkung "
                  f"verschoben")
        return {
            "muster": "4a",
            "kopf_neu": folgen.get("kopf_neu") or "neu",
            "zeilen": [{"label": z.get("label", ""),
                        "bisher": _wert(z.get("bisher")),
                        "neu": _wert(z.get("neu"))}
                       for z in folgen["zeilen"]],
            # Was kein Vorher/Nachher ist (eine Frist, eine Handlung),
            # verlaesst die Tabelle und wird eine eigene Pill-Reihe.
            "pills": pills,
            "hinweis": hinweis,
        }

    if muster == "4b" and folgen.get("ja") and folgen.get("nein"):
        return {"muster": "4b", "ja": folgen["ja"], "nein": folgen["nein"],
                "hinweis": folgen.get("hinweis", "")}

    if muster == "4c" and folgen.get("payoff"):
        return {"muster": "4c", "payoff": folgen["payoff"],
                "erklaerung": folgen.get("erklaerung", ""),
                "schritt_titel": folgen.get("schritt_titel") or SCHRITT_TITEL,
                "schritte": folgen.get("schritte", []) or [],
                "hinweis": folgen.get("hinweis", "")}

    if muster == "4d" and len(folgen.get("faelle", []) or []) == 2:
        # Dieselbe Falle wie bei 4a: die Kennzahl steht in Display-Groesse,
        # und "Heizoel +65,3 %" ist dort keine Figur mehr, sondern ein Satz.
        for f in folgen["faelle"]:
            for k in f.get("kennzahlen", []) or []:
                if len(str(k.get("wert") or "")) > PILL_FIGUR_MAX:
                    print(f"    ! Kennzahl '{k.get('wert')}' ist keine Figur - "
                          f"Karte pruefen")
        faelle = [{"label": f.get("label", ""),
                   "symbol": f.get("symbol") if f.get("symbol") in SYMBOLE else "person",
                   "kennzahlen": [{"label": k.get("label", ""),
                                   "wert": _wert(k.get("wert"))}
                                  for k in f.get("kennzahlen", []) or []]}
                  for f in folgen["faelle"]]
        # Subgrid braucht die Zeilenzahl des Elternrasters: Piktogramm, Label
        # und je Kennzahl eine Zeile. Die laengere Karte gibt sie vor.
        return {"muster": "4d", "faelle": faelle,
                "zeilen_anzahl": 2 + max(len(f["kennzahlen"]) for f in faelle),
                "hinweis": folgen.get("hinweis", "")}

    # Rueckfall aus dem alten Feld: erster Satz als Payoff, Rest als Erklaerung.
    sowhat = slides.get("sowhat") or {}
    if sowhat.get("text"):
        satz, _, rest = sowhat["text"].strip().partition(". ")
        return {"muster": "4c",
                "payoff": satz if satz.endswith(".") else f"{satz}.",
                "erklaerung": rest,
                "schritt_titel": "Rechenweg",
                "schritte": sowhat.get("schritte", []) or [],
                "hinweis": ""}
    return None


def _seite(seite: dict, fundstelle: str, credits: list) -> dict:
    """Eine vom Datenkarussell vorgegebene Slide in den Template-Kontext.

    kind "context"    - Pfeilliste (`saetze`)
    kind "begriff"    - Begriffskarte (`begriff` wie beim Modell), optional
                        mit `logo` (Name der Organisation) im Badge
    kind "vergleich"  - Tabelle im Muster 4a, mit `kopf_alt`/`kopf_neu`
    kind "positionen" - Organisationen mit Logo und je einem Satz
    """
    art = seite["kind"]
    ctx = {"headline_html": _headline(seite.get("titel", "")),
           "foot_source": fundstelle}
    if art == "context":
        return {**ctx, "kind": "context", "context": seite.get("saetze", []),
                # Jahresvergleich als kleine Saeulenreihe ueber der Liste.
                "saeulen": _chart_daten(seite["saeulen"], credits)
                if seite.get("saeulen") else None}
    if art == "begriff":
        return {**ctx, "kind": "begriff",
                "begriff": _begriff_kuerzen(seite["begriff"]),
                "begriff_logo": _logo(seite.get("logo"), credits),
                "nachtitel": seite.get("nachtitel", "")}
    if art == "vergleich":
        folgen = _folgen({"folgen": {**seite, "muster": "4a"}})
        folgen["kopf_alt"] = seite.get("kopf_alt") or "bisher"
        return {**ctx, "kind": "folgen", "folgen": folgen}
    if art == "positionen":
        return {**ctx, "kind": "positionen",
                "positionen": [{"name": p["name"], "satz": p["satz"],
                                "logo": _logo(p.get("logo") or p["name"], credits)}
                               for p in seite.get("positionen", [])],
                "hinweis": seite.get("hinweis", "")}
    if art == "lager":
        return {**ctx, "kind": "lager",
                "lager": [{"titel": l["titel"],
                           "positionen": [{"name": p["name"], "satz": p["satz"],
                                           "logo": _logo(p.get("logo") or p["name"], credits)}
                                          for p in l["positionen"]]}
                          for l in seite["lager"]],
                "hinweis": seite.get("hinweis", "")}
    raise ValueError(f"unbekannte Slide-Art {art}")


def build_carousel(carousel: dict, nummer: int, zuletzt: list | None = None) -> list:
    """Rendert die Slides eines Karussells nach out/karussell_<n>/.

    `zuletzt` sind die zuletzt gezogenen Cover-Architekturen; sie werden von
    der Ziehung ausgeschlossen (§6.1). Die gezogene Variante steht danach in
    carousel["cover"]. Geschrieben wird der Stand hier nicht: der Zustand
    gehoert dem Lauf, nicht dem Renderer.

    carousel["cover"] vorab gesetzt heisst: diese Architektur, keine Ziehung.
    Dafuer gibt es genau einen Grund, und das ist die Vorschau - sie muss alle
    sechs zeigen koennen und darf nicht wuerfeln.
    """
    slides = carousel["slides"]
    item = carousel["item"]

    ziel = OUT / f"karussell_{nummer}"
    if ziel.exists():
        shutil.rmtree(ziel)
    ziel.mkdir(parents=True)

    env = Environment(loader=FileSystemLoader("templates"))
    env.filters["betrag"] = _betrag_filter
    env.tests["ohne_kachel"] = lambda uri: uri in _OHNE_KACHEL
    template = env.get_template("card.html")

    # Fundstelle im Fuss: jede Fakten-Slide nennt ihre Quelle. Der Name
    # genuegt - das Design-System verlangt "Cite the source in the footer"
    # und kennt keine URL. Nachpruefbar bleibt es ueber die Telegram-
    # Nachricht, die vor der Freigabe die Quelllinks liefert (SETUP.md 4.3),
    # und ueber die Quellenzeile im Bildtext.
    fundstelle = item["source"]
    credits = []
    _KOPF_CREDITS.clear()
    chart = _chart_daten(slides["chart"], credits)

    # Sitzbogen, wo es eine namentliche Abstimmung gibt - das ist das
    # Standarddiagramm fuer eine Abstimmung im ganzen Haus. Sonst bleibt es
    # beim Balkenvergleich.
    bogen = sitzbogen.bogen(item.get("abstimmung") or {})
    # Auch die Legende des Sitzbogens ist ein Diagramm: Logo vor den Namen.
    for f in (bogen or {}).get("legende", []):
        f["logos"] = [_logo(k, credits) for k in
                      _PARTEI_LOGOS.get(f["name"], ())]

    # Bild nur aufs Cover, nur wenn ein Thema trifft - sonst None. Wird am
    # Karussell vermerkt, damit build_caption den Foto-Credit mitschickt.
    # Auf dem Cover selbst steht der Credit nicht: dort steht nach der Spec
    # nichts ausser Haken und Stuetzzeile.
    #
    # Erst das Thema, dann die Variante, dann das Bild: 1d und 1f brauchen ein
    # Hochformat, 1e ein Querformat. Andersherum holte man ein Bild im
    # falschen Format und schnitte es hinterher zurecht.
    thema = bilder.thema(item, slides)
    cover_ctx = _cover(slides, item, thema, zuletzt or [],
                       carousel.get("cover"), bool(bogen))
    variante = cover_ctx["cover_variante"]
    carousel["cover"] = variante

    bild = None
    if variante in cover.FOTO_VARIANTEN:
        bild = bilder.hole(thema, cover.FOTO_VARIANTEN[variante])
        if not bild:
            # Das Bild ist ausgeblieben, die Fotovariante traegt also nicht
            # mehr. Neu ziehen, diesmal ohne Fotovarianten - ein Cover mit
            # leerer Fotospalte gibt es nicht.
            cover_ctx = _cover(slides, item, None, zuletzt or [],
                               bogen=bool(bogen))
            variante = cover_ctx["cover_variante"]
            carousel["cover"] = variante
    carousel["bild"] = bild
    print(f"  = Cover {variante} ({cover_ctx['ground']})")

    # Eine Abstimmungs-Slide nennt Quelle UND Wahlperiode, sonst ist die
    # Sitzverteilung nicht nachpruefbar.
    chart_fuss = (f"{item['source']}\n{config.WAHLPERIODE}. Wahlperiode"
                  if bogen else fundstelle)

    pages = [
        {"kind": "hook", **cover_ctx, "bild": bild,
         "portraet": slides.get("portraet")},
        {"kind": "chart",
         "headline_html": _headline(chart.get("titel", "")),
         "chart": chart,
         "bogen": bogen,
         # Im Bogen steht die noetige Mehrheit schon in der Mitte; sie hier
         # zu wiederholen waere derselbe Fakt zweimal auf einer Slide.
         "hinweis": "" if bogen else chart.get("hinweis", ""),
         "foot_source": chart_fuss},
    ]

    # Slide 3 erklaert den einen Begriff, an dem die Meldung haengt. Fehlt er
    # (Profil-Karussells bauen ihre Slides aus Daten), bleibt es bei der
    # Pfeilliste - ohne Frage-Badge, den gibt es nur auf der Begriffskarte.
    begriff = slides.get("begriff") or {}
    if slides.get("seiten"):
        # Datenkarussells (weitere.py) geben ihre Slides nach dem Chart selbst
        # vor: Begriffskarte, Vergleichstabelle, Positionen, Pfeilliste.
        pages += [_seite(seite, fundstelle, credits) for seite in slides["seiten"]]
    elif begriff.get("saetze"):
        pages.append({"kind": "begriff",
                      "headline_html": _headline(begriff.get("titel")
                                                 or "Worum es geht"),
                      "begriff": _begriff_kuerzen(begriff),
                      # Statistik-Karussells: "Genauer hingeschaut" statt
                      # "Warum ueberhaupt aendern?" (weitere.destatis).
                      "nachtitel": slides.get("begriff_nachtitel", ""),
                      "foot_source": fundstelle})
    else:
        pages.append({"kind": "context",
                      # Datenkarussells stellen hier ihre eigene Frage
                      # ("Wer ist der Spender?") - die Cover-Schlagzeile ein
                      # zweites Mal waere derselbe Satz auf zwei Slides.
                      "headline_html": _headline(slides.get("context_titel")
                                                 or slides.get("titel", item["title"])),
                      "context": slides.get("context", []),
                      "foot_source": fundstelle})

    # Slide 4: eines der vier Muster, nie freier Fliesstext. Profil-Karussells
    # haben bewusst keine - "was heisst das fuer dich" laesst sich dort nicht
    # serioes beantworten.
    folgen = None if slides.get("seiten") else _folgen(slides)
    for zahl in ([] if slides.get("seiten") else _wiederholte_figur(slides)):
        print(f"    ! Slide 4 wiederholt die Zahl {zahl} aus Schlagzeile oder "
              f"Chart - Muster passt vermutlich nicht")
    if folgen:
        pages.append({"kind": "folgen",
                      "headline_html": _headline("Was heißt das für dich?"),
                      "folgen": folgen,
                      "foot_source": fundstelle})

    slides["logo_credits"] = list(dict.fromkeys(credits + _KOPF_CREDITS))

    pages.append({"kind": "cta",
                  "headline_html": _headline(config.CTA_HEADLINE),
                  "cta_body": config.CTA_BODY,
                  "cta_action": config.CTA_ACTION,
                  "foot_source": HANDLE})

    # Der Wechsel startet am Grund des gezogenen Covers - bei 1c und 1e laeuft
    # das Deck also hell, ink, hell, ink, hell.
    grounds = _grounds(len(pages), cover_ctx["ground"])
    for i, ctx in enumerate(pages):
        ctx["index"] = i + 1
        ctx["total"] = len(pages)
        ctx["ground"] = grounds[i]

    paths = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350},
                                device_scale_factor=1)
        for n, ctx in enumerate(pages):
            # set_content wartet sonst auf JEDE Ressource - auch auf die
            # Schriften von fonts.googleapis.com. Ist das CDN langsam oder
            # nicht erreichbar, lief der komplette Lauf nach 30 Sekunden in
            # einen TimeoutError, nachdem Recherche und Entwurf laengst
            # bezahlt waren. Eine fehlende Schrift darf ein fertiges
            # Karussell nicht kosten: erst das Markup, dann die Schriften -
            # und wenn die ausbleiben, wird eben mit Ersatzschrift gerendert.
            page.set_content(template.render(**ctx),
                             wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_function("document.fonts.status === 'loaded'",
                                       timeout=8000)
            except Exception:
                print("    ! Webfonts nicht geladen - Ersatzschrift")
            page.wait_for_timeout(200)
            # Nach den Schriften, vor dem Bild: mit Ersatzschrift gemessen
            # waere die Zeilenzahl eine andere als die auf der Karte.
            _zeilen_deckeln(page, ctx.get("kind", "?"))
            path = ziel / f"{n:02d}.png"
            page.screenshot(path=str(path))
            paths.append(path)
            # Dieselbe Karte noch einmal als JPEG: die Instagram-API nimmt
            # kein PNG an. Der zweite Schuss kostet Millisekunden, weil die
            # Seite ohnehin fertig im Browser steht - ein nachtraegliches
            # Umwandeln kostete ein weiteres Paket. Das PNG bleibt der
            # Master fuer Telegram und Kontaktbogen: bei Haarlinien und
            # 56-px-Headlines sieht man JPEG-Artefakte sofort.
            page.screenshot(path=str(ziel / f"{n:02d}.jpg"),
                            type="jpeg", quality=95)
        browser.close()

    print(f"  = Karussell {nummer}: {len(paths)} Slides gerendert")
    return paths


def build_caption(carousel: dict) -> str:
    slides = carousel["slides"]
    item = carousel["item"]
    now = datetime.now(ZoneInfo(config.TIMEZONE))

    lines = [slides.get("titel", item["title"]), "", slides.get("hook", ""), ""]
    lines += slides.get("context", [])
    if slides.get("sowhat"):
        lines += ["", slides["sowhat"].get("text", "")]
    lines += [
        "",
        f"Quelle: {item['source']}, {now.day}. {MONATE[now.month - 1]} {now.year}. "
        "Zusammengestellt aus amtlichen Veröffentlichungen, vor der "
        "Veröffentlichung redaktionell geprüft.",
    ]

    # Pexels verlangt fuer die API-Nutzung die Nennung des Fotografen und
    # einen Hinweis auf Pexels. Das Cover traegt nach der Spec keine Zeile
    # ausser Haken und Stuetzzeile - der Credit steht deshalb allein hier.
    bild = carousel.get("bild")
    if bild:
        lines += ["", f"Titelfoto: {bild['fotograf']} / Pexels: {bild['seite']}"]

    # Portraets und Logos stehen unter freier Lizenz (Commons) - die
    # Nennung gehoert, wie der Pexels-Credit, in den Bildtext.
    credits = [c for c in [(slides.get("portraet") or {}).get("credit"),
                           *(slides.get("logo_credits") or [])] if c]
    if credits:
        lines += [""] + list(dict.fromkeys(credits))

    lines += ["", "#politik #bundestag #deutschland #erklaert"]
    return "\n".join(lines)
