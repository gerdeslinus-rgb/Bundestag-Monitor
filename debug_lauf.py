"""Der Tageslauf in einzelnen Schritten - zum Nachsehen, wo etwas verloren geht.

Ein kompletter run.py dauert acht bis zehn Minuten, und am Ende steht
bestenfalls eine Zeile wie "x Beleg-Satz nicht in Quelle (0.64)". Das ist zu
wenig, um zu erkennen, an welcher Stelle die Information abhanden kam.

Deshalb hier: jede Stufe einzeln aufrufbar, jedes Zwischenergebnis auf Platte.
Wer an compose() arbeitet, laedt Quellen und Recherche aus dem Zwischenstand
und zahlt nur noch den einen Modellaufruf, um den es geht.

    python debug_lauf.py quellen      # Quellen holen            (kein Modell)
    python debug_lauf.py auswahl      # Themen waehlen           (Haiku)
    python debug_lauf.py volltext     # Quelltext nachladen      (kein Modell)
    python debug_lauf.py recherche    # Websuche                 (Sonnet)
    python debug_lauf.py entwurf      # Slides schreiben         (Sonnet)
    python debug_lauf.py pruefung     # Belegpruefung            (kein Modell)
    python debug_lauf.py faktencheck  # Faktencheck              (Sonnet)

    python debug_lauf.py karten       # Karussells rendern   (kein Modell)

    python debug_lauf.py bericht      # Trichter: was bleibt wo uebrig
    python debug_lauf.py zeige 0      # Thema 0 vollstaendig ansehen
    python debug_lauf.py alles        # alle Stufen nacheinander

'karten' ist die einzige Stufe, die etwas Ansehbares produziert: die fertigen
1080x1350-Karten plus Bildtext, aus dem Zwischenstand statt aus einem neuen
Lauf. Geschickt wird nichts - Telegram und Freigabe bleiben run.py.

Jede Stufe liest den Zwischenstand der vorherigen. Wer eine Stufe wiederholt,
ueberschreibt nur deren eigenen Stand - alles davor bleibt liegen.
"""

import difflib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

import config
import llm
import research
import sources

STAND = Path("out/debug")


# --- Zwischenstand ---------------------------------------------------------

def _pfad(name: str) -> Path:
    return STAND / f"{name}.json"


def sichern(name: str, daten) -> None:
    STAND.mkdir(parents=True, exist_ok=True)
    _pfad(name).write_text(
        json.dumps({"zeit": datetime.now().isoformat(timespec="seconds"),
                    "daten": daten}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"  -> out/debug/{name}.json")


def laden(name: str):
    pfad = _pfad(name)
    if not pfad.exists():
        raise SystemExit(f"Kein Zwischenstand '{name}'. Erst die Stufe davor laufen lassen.")
    inhalt = json.loads(pfad.read_text(encoding="utf-8"))
    print(f"  (Zwischenstand '{name}' von {inhalt['zeit']})")
    return inhalt["daten"]


def _kurz(text: str, n: int = 90) -> str:
    text = " ".join((text or "").split())
    return text[:n] + ("..." if len(text) > n else "")


# --- Stufen ----------------------------------------------------------------

def stufe_quellen() -> None:
    items, _ = sources.collect()
    sichern("quellen", items)
    nach_quelle = {}
    for it in items:
        nach_quelle.setdefault(it["source"], []).append(len(it["text"]))
    print(f"\n  {len(items)} Items nach Vorfilter, je Quelle:")
    for quelle, laengen in sorted(nach_quelle.items(), key=lambda x: -len(x[1])):
        schnitt = sum(laengen) // len(laengen)
        print(f"    {len(laengen):3}x  Text im Schnitt {schnitt:6} Zeichen  {quelle[:52]}")


def stufe_auswahl() -> None:
    items = laden("quellen")
    themen = llm.select_topics(items)
    sichern("auswahl", themen)
    for i, t in enumerate(themen):
        print(f"\n  [{i}] {t['title'][:80]}")
        print(f"      Quelle: {t['source'][:60]}  |  Text: {len(t['text'])} Zeichen")
        print(f"      Begruendung: {_kurz(t.get('begruendung', ''), 110)}")


def stufe_volltext() -> None:
    themen = laden("auswahl")
    for i, t in enumerate(themen):
        vorher = len(t["text"])
        sources.ensure_volltext(t)
        pfeil = "->" if len(t["text"]) != vorher else "  unveraendert"
        print(f"  [{i}] {vorher:6} {pfeil} {len(t['text']):6} Zeichen | {t['title'][:45]}")
        print(f"      Quelle-URL: {t['url'][:95]}")
    sichern("volltext", themen)


def stufe_recherche() -> None:
    themen = laden("volltext")
    ergebnisse = []
    for i, t in enumerate(themen):
        print(f"\n  [{i}] {t['title'][:70]}")
        r = research.enrich(t)
        ergebnisse.append(r)
        print(f"      Erklaerung : {_kurz(r.get('erklaerung', ''))}")
        print(f"      Vergleichszahlen: {len(r.get('vorher_nachher', []))}")
        for b in r.get("vorher_nachher", []):
            beleg = "mit Fundstelle" if b.get("quelle_url") else "OHNE FUNDSTELLE"
            print(f"        - {b['label']}: {b['wert']} {b['einheit']}  ({beleg})")
        print(f"      Fundstellen: {len(r.get('fundstellen', []))}")
    sichern("recherche", ergebnisse)


def stufe_entwurf() -> None:
    themen, recherchen = laden("volltext"), laden("recherche")
    entwuerfe = []
    for i, (t, r) in enumerate(zip(themen, recherchen)):
        print(f"\n  [{i}] {t['title'][:70]}")
        slides = llm.compose(t, r)
        entwuerfe.append(slides)
        if not slides:
            print("      -> kein Entwurf, Grund steht in der Zeile darueber")
            continue
        print(f"      Titel : {slides.get('titel', '')}")
        print(f"      Hook  : {_kurz(slides.get('hook', ''), 110)}")
        chart = slides.get("chart") or {}
        print(f"      Chart : {chart.get('titel', '-')} ({chart.get('einheit', '-')})")
        for b in chart.get("balken", []):
            print(f"        - {b.get('label')}: {b.get('wert')}")
        print(f"      Beleg : {len(slides.get('fakten_evidence', ''))} Zeichen")
    sichern("entwurf", entwuerfe)


def stufe_pruefung() -> None:
    """Belegpruefung mit Zwischenwerten - zeigt jeden Satz und sein Ergebnis.

    Die Entscheidung faellt weiterhin llm.verify_slides(); hier steht daneben,
    WIE knapp es war. Genau das fehlt im normalen Lauf: 0.64 sagt wenig, die
    Gegenueberstellung von Beleg-Satz und Quelle dagegen viel.
    """
    themen, recherchen, entwuerfe = laden("volltext"), laden("recherche"), laden("entwurf")
    for i, (t, r, slides) in enumerate(zip(themen, recherchen, entwuerfe)):
        print(f"\n  [{i}] {t['title'][:70]}")
        if not slides:
            print("      (kein Entwurf)")
            continue

        quelle = llm._normalise(t.get("text", ""))
        quelltext = t.get("text", "")
        print(f"      Quelltext normalisiert: {len(quelle)} Zeichen")
        print(f"      Schwelle: {config.EVIDENCE_THRESHOLD}, "
              f"Mindestblock: {config.EVIDENCE_MIN_BLOCK} (kurze Saetze anteilig)")
        for satz in llm.saetze(slides.get("fakten_evidence", "")):
            norm = llm._normalise(satz)
            if not norm:
                continue
            if norm in quelle:
                print(f"        1.00  woertlich enthalten | {_kurz(satz, 70)}")
                continue
            quote = llm.belegquote(norm, quelle)
            marke = "ok  " if quote >= config.EVIDENCE_THRESHOLD else "FAIL"
            print(f"        {quote:.2f}  {marke} | {_kurz(satz, 70)}")
            # Aus welchen Stuecken die Quote besteht, ist die eigentliche
            # Auskunft: zwei lange Bloecke bedeuten einen Einschub in der
            # Quelle, ein Dutzend kurze bedeuten eine Paraphrase.
            grenze = llm.mindestblock(norm)
            m = difflib.SequenceMatcher(None, norm, quelle, autojunk=False)
            bloecke = [b for b in m.get_matching_blocks() if b.size >= grenze]
            verworfen = sum(b.size for b in m.get_matching_blocks()
                            if 0 < b.size < grenze)
            print(f"              {len(bloecke)} Block/Bloecke ab {grenze} Zeichen "
                  f"gewertet, {verworfen} Zeichen in Schnipseln verworfen")
            for b in bloecke[:3]:
                print(f"              [{b.size:>3}] ...{_kurz(norm[b.a:b.a + b.size], 56)}...")
            if len(bloecke) > 3:
                print(f"              ... und {len(bloecke) - 3} weitere")

        for satz in llm.saetze(slides.get("fakten_evidence", "")):
            erfunden = llm.evidenz_zahl_erfunden(satz, quelltext)
            if erfunden:
                print(f"        Beleg-Zahl {erfunden} steht NICHT in der Quelle "
                      f"| {_kurz(satz, 50)}")

        # Dieselbe Regel wie in verify_slides, nicht eine zweite Fassung
        # davon: die knappere Kopie hier hat eine belegte Zahl faelschlich
        # als "NIRGENDS" gemeldet.
        quelltext = t.get("text", "")
        belegt = llm.recherche_zahlen(r)
        beispiele = llm.beispielwerte(slides)
        abgeleitet = llm.abgeleitete_zahlen(slides, quelltext, belegt)
        for schreibweisen in llm._slide_zahlen(slides):
            varianten = {w.rstrip(".,") for w in schreibweisen}
            if llm.zahl_belegt(varianten, quelltext, belegt):
                continue
            if varianten & beispiele:
                wo = "Rechenbeispiel"
            elif varianten & abgeleitet:
                wo = "abgeleitet (nachgerechnet)"
            else:
                wo = "NIRGENDS"
            print(f"        Zahl {sorted(varianten)[0]:>12} -> {wo}")

        print(f"      == verify_slides(): {llm.verify_slides(slides, t, r)}")


def stufe_faktencheck() -> None:
    themen, recherchen, entwuerfe = laden("volltext"), laden("recherche"), laden("entwurf")
    for i, (t, r, slides) in enumerate(zip(themen, recherchen, entwuerfe)):
        print(f"\n  [{i}] {t['title'][:70]}")
        if not slides:
            print("      (kein Entwurf)")
            continue
        bestanden, einwand = llm.judge_slides(slides, t, r)
        print(f"      == judge_slides(): {bestanden}")
        if einwand:
            # Der volle Einwand, nicht die auf 120 Zeichen gekuerzte Zeile
            # aus llm.py: genau daran arbeitet der zweite Versuch.
            print(f"      Einwand: {einwand}")


def stufe_bericht() -> None:
    """Der Trichter: wie viel bleibt nach jeder Stufe uebrig."""
    def zahl(name, fn):
        try:
            return fn(laden(name))
        except SystemExit:
            return None

    print()
    stufen = [
        ("Quellen (nach Vorfilter)", zahl("quellen", len)),
        ("Ausgewaehlte Themen", zahl("auswahl", len)),
        ("Mit Entwurf", zahl("entwurf", lambda d: sum(1 for x in d if x))),
    ]
    for name, wert in stufen:
        print(f"  {name:28} {'-' if wert is None else wert}")

    try:
        themen = laden("volltext")
        print("\n  Quelltext-Laengen der Themen:")
        for i, t in enumerate(themen):
            genug = "ok" if len(t["text"]) >= config.VOLLTEXT_ZIEL_CHARS else "duenn"
            sichtbar = min(len(t["text"]), config.PRUEFTEXT_MAX_CHARS)
            print(f"    [{i}] {len(t['text']):6} Zeichen ({genug}), "
                  f"davon sieht das Modell {sichtbar}  | {t['title'][:40]}")
    except SystemExit:
        pass


def stufe_karten() -> None:
    """Die gepruefften Entwuerfe als fertige Karten - zum Ansehen, nicht zum Senden.

    Bewusst ohne notify: der Freigabeschritt gehoert zum Lauf, nicht zur
    Fehlersuche. Wer hier rendert, will das Ergebnis beurteilen, nicht posten.
    """
    import cover
    import render

    themen, entwuerfe = laden("volltext"), laden("entwurf")
    zuletzt = cover.letzte_laden()
    gebaut = []

    for i, (t, slides) in enumerate(zip(themen, entwuerfe), start=1):
        if not slides:
            print(f"  [{i - 1}] kein Entwurf - uebersprungen")
            continue
        print(f"\n  [{i - 1}] {slides.get('titel', '')[:60]}")
        carousel = {"item": t, "slides": slides}
        pfade = render.build_carousel(carousel, i, zuletzt)
        # Nur merken, nicht speichern: letzte_speichern() gehoert dem echten
        # Lauf. Sonst sperrt eine Fehlersuche die Cover-Rotation des naechsten
        # Posts, und genau dagegen ist die Rotation gebaut.
        zuletzt = cover.merken(carousel["cover"], zuletzt)

        text = render.build_caption(carousel)
        ziel = pfade[0].parent / "bildtext.txt"
        ziel.write_text(text, encoding="utf-8")
        print(f"      {len(pfade)} Slides + bildtext.txt -> {pfade[0].parent}")
        gebaut.append((slides.get("titel", f"Karussell {i}"), pfade))

    if not gebaut:
        raise SystemExit("Nichts zu rendern - erst 'entwurf' laufen lassen.")

    uebersicht = STAND / "karten.png"
    _kontaktbogen(gebaut, uebersicht)
    print(f"\n  Kontaktbogen ueber alles: {uebersicht}")


def _kontaktbogen(gebaut: list, ziel: Path) -> None:
    """Alle Slides verkleinert nebeneinander - ein Blick, ein Urteil."""
    from playwright.sync_api import sync_playwright

    reihen = []
    for titel, pfade in gebaut:
        kacheln = "".join(
            f'<figure><img src="{p.resolve().as_uri()}"><figcaption>'
            f'{p.parent.name}/{p.name}</figcaption></figure>' for p in pfade)
        reihen.append(f"<h2>{titel}</h2><div class='reihe'>{kacheln}</div>")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ margin: 0; padding: 40px; background: #1b1b1b; color: #ddd;
              font: 15px/1.4 system-ui, sans-serif; width: 1660px; }}
      h2 {{ font-size: 17px; font-weight: 600; margin: 30px 0 14px; }}
      .reihe {{ display: flex; gap: 18px; flex-wrap: wrap; }}
      figure {{ margin: 0; }}
      img {{ width: 300px; display: block; }}
      figcaption {{ font-size: 12px; opacity: 0.6; margin-top: 6px; }}
    </style></head><body>{''.join(reihen)}</body></html>"""

    ziel.parent.mkdir(parents=True, exist_ok=True)
    seite = ziel.parent / "_kontaktbogen.html"
    seite.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1660, "height": 1200})
        page.goto(seite.resolve().as_uri())
        page.wait_for_timeout(400)
        page.screenshot(path=str(ziel), full_page=True)
        browser.close()
    seite.unlink()


def stufe_zeige() -> None:
    i = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    for name in ("volltext", "recherche", "entwurf"):
        try:
            daten = laden(name)
        except SystemExit:
            continue
        if i >= len(daten):
            continue
        print(f"\n===== {name.upper()} [{i}] " + "=" * 40)
        print(json.dumps(daten[i], ensure_ascii=False, indent=1)[:4000])


STUFEN = {
    "quellen": stufe_quellen, "auswahl": stufe_auswahl, "volltext": stufe_volltext,
    "recherche": stufe_recherche, "entwurf": stufe_entwurf, "pruefung": stufe_pruefung,
    "faktencheck": stufe_faktencheck, "karten": stufe_karten,
    "bericht": stufe_bericht, "zeige": stufe_zeige,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in STUFEN and sys.argv[1] != "alles":
        print(__doc__)
        return 1
    if sys.argv[1] == "alles":
        for name in ("quellen", "auswahl", "volltext", "recherche",
                     "entwurf", "pruefung", "faktencheck"):
            print(f"\n{'=' * 62}\n{name.upper()}\n{'=' * 62}")
            STUFEN[name]()
        return 0
    STUFEN[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
