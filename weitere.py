"""Das zweite Karussell des Tages: Destatis, Lobbyregister, Parteispenden oder
Nebentaetigkeiten - eine Kategorie, zufaellig gezogen (run.py).

Die Vorlagen je Kategorie (Slide fuer Slide) stehen in VORLAGEN.md; die
Eigenheiten der Quellen in QUELLEN.md. Hier steht, wie aus den Daten die
Slides werden.

Grundsatz: Was auf einer Karte als Tatsache steht, entsteht aus den amtlichen
Daten, nicht aus einem Modelltext. Ein Modell schreibt nur, was sich aus
Daten nicht bauen laesst - die Destatis-Karussells (normale Strecke mit
Belegpruefung), den einen Satz, was ein Gesetz aendert (gegen den DIP-Text
geprueft), die Positionen der Organisationen aus ihren Stellungnahmen im
Lobbyregister und die zwei Saetze "Wer ist der Spender?" aus Lobbyregister
und Wikipedia. Die letzten beiden werden mechanisch gegen ihre Quelle
geprueft (llm._belegt) und gehen NICHT in den Quelltext des Faktenchecks
(`modelltexte`) - der prueft sie gegen dieselben Auszuege. Jedes Karussell
geht danach durch den Faktencheck in llm.judge_slides().

Seit 25.09.2026 geben Datenkarussells ihre Slides nach dem Chart selbst vor
(`seiten`: Begriffskarte, Vergleichstabelle, Positionen, Pfeilliste), statt
alles in eine Pfeilliste zu legen. Logos (logos.py, nur Commons) und
Portraets (portraet.py) haengen per Name daran; render.py loest sie auf.

Jede Kategorie liefert ein Karussell oder None. None ist kein Fehler: dann
zieht run.py die naechste Kategorie.
"""

import json
import random
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import config
import llm
import portraet
import research
import sources

STAND = Path("data/weitere_state.json")
POLITIKER = Path("data/politiker.json")

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


# --- Hilfen ------------------------------------------------------------------

def _stand() -> dict:
    try:
        return json.loads(STAND.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stand_merken(schluessel: str, wert: str, laenge: int = 30) -> None:
    daten = _stand()
    liste = [wert, *[w for w in daten.get(schluessel, []) if w != wert]]
    daten[schluessel] = liste[:laenge]
    STAND.parent.mkdir(exist_ok=True)
    STAND.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                     encoding="utf-8")


def _zahl(wert: float) -> str:
    """1962943 -> 1.962.943"""
    return f"{round(wert):,}".replace(",", ".")


def _mio(wert: float) -> float:
    return round(wert / 1_000_000, 1)


def _mio_text(wert: float) -> str:
    return f"{_mio(wert):.1f}".replace(".", ",")


# "Grossspende an Gruene" liest sich wie ein Telegramm. Parteinamen mit
# Artikel, im Akkusativ ("an die Gruenen", "an das BSW", "an den SSW").
_PARTEI_AKK = {"CDU": "die CDU", "CSU": "die CSU", "SPD": "die SPD",
               "Grüne": "die Grünen", "Linke": "die Linke", "AfD": "die AfD",
               "FDP": "die FDP", "BSW": "das BSW", "SSW": "den SSW",
               "MLPD": "die MLPD", "Freie Wähler": "die Freien Wähler",
               "DKP": "die DKP", "Volt": "Volt"}


def _an(partei: str) -> str:
    return _PARTEI_AKK.get(partei, partei)


def _themen(felder: list, anzahl: int = 2) -> list:
    """Interessenfelder aus dem Lobbyregister, ohne die Sammelposten
    ("Sonstiges im Bereich ...") - die sagen als Beispiel nichts."""
    namen = [f.get("de", "") for f in felder or []]
    return [n for n in namen if n and not n.startswith("Sonstige")][:anzahl]


def _satz(text: str) -> str:
    """Genau ein Schlusspunkt - "Foundation e.V." plus "." ergibt sonst "e.V.."."""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _datum(d) -> str:
    return f"{d.day}. {MONATE[d.month - 1]} {d.year}"


def _aufzaehlung(teile: list) -> str:
    teile = [t for t in teile if t]
    if len(teile) <= 1:
        return "".join(teile)
    return ", ".join(teile[:-1]) + " und " + teile[-1]


# Lookarounds statt \b: hinter "e.V." am Namensende steht keine Wortgrenze,
# mit \b blieb "Campact e.V." ungekuerzt.
_RECHTSFORM = re.compile(
    r"\s*(,\s*)?(?<!\w)(GmbH\s*&\s*Co\.?\s*KG|gGmbH|GmbH|mbH|AG|SE|KGaA|KG|OHG|GbR|"
    r"e\.\s?V\.|eG|Aktiengesellschaft)(?!\w)\.?", re.IGNORECASE)


def _kurzname(name: str, laenge: int = 30) -> str:
    """Organisationsname fuer einen Balken: ohne Rechtsform, gekuerzt am
    Wortende. "Eintracht Frankfurt Fussball AG" -> "Eintracht Frankfurt Fussball"."""
    kurz = _RECHTSFORM.sub("", name).strip(" ,-")
    # "Bundeszahnaerztekammer - Arbeitsgemeinschaft der Deutschen
    # Zahnaerztekammern": der Teil vor dem Strich ist der Name, der Rest
    # Erlaeuterung. Mitten darin abgeschnitten stand "... der deutschen" da.
    if len(kurz) > laenge and " - " in kurz:
        kurz = kurz.split(" - ", 1)[0]
    if len(kurz) <= laenge:
        return kurz
    return kurz[:laenge].rsplit(" ", 1)[0].rstrip(" ,-")


def _seiten_texte(seiten: list) -> list:
    """Alle Aussagen der vorgegebenen Slides als Saetze - fuer Faktencheck
    und Caption, die beide nur `context` lesen. Logos und Bilder sind keine
    Aussagen und bleiben draussen."""
    saetze = []
    for s in seiten:
        if s["kind"] == "context":
            if s.get("saeulen"):
                c = s["saeulen"]
                saetze.append(f"{c['hinweis']}: " + ", ".join(
                    f"{b['label']} {str(b['wert']).replace('.', ',')} {c['einheit']}"
                    for b in c["balken"]) + ".")
            saetze += s["saetze"]
        elif s["kind"] == "begriff":
            b = s["begriff"]
            saetze += [*b.get("saetze", []), b.get("beispiel", ""), *b.get("warum", [])]
        elif s["kind"] == "vergleich":
            saetze += [f"{z['label']}: {s['kopf_neu']} {z['neu']}, "
                       f"{s['kopf_alt']} {z['bisher']}." for z in s["zeilen"]]
            saetze += [f"{p['label']}: {p['wert']}." for p in s.get("pills", [])]
            saetze.append(s.get("hinweis", ""))
        elif s["kind"] == "positionen":
            saetze += [f"{p['name']}: {p['satz']}" for p in s["positionen"]]
            saetze.append(s.get("hinweis", ""))
        elif s["kind"] == "lager":
            for l in s["lager"]:
                saetze += [f"{l['titel']}: {p['name']}: {p['satz']}" for p in l["positionen"]]
            saetze.append(s.get("hinweis", ""))
    return [x for x in saetze if x]


def _karussell(item: dict, titel: str, hook: str, chart: dict, context: list,
               context_titel: str = "", cover_frage: str = "",
               cover_figur: str = "", keine_figur: bool = False,
               seiten: list | None = None, portraet: dict | None = None,
               modelltexte: tuple = ()) -> dict:
    """`seiten` gibt die Slides nach dem Chart vor (sonst eine Pfeilliste aus
    `context`). `modelltexte` sind Saetze, die ein Modell geschrieben hat -
    die gehen NICHT in den Quelltext, sonst prueft der Faktencheck sie
    gegen sich selbst."""
    if seiten:
        context = _seiten_texte(seiten)
    slides = {
        "titel": titel,
        "context_titel": context_titel,
        "hook": hook,
        "cover_frage": cover_frage,
        "cover_figur": cover_figur,
        "chart": chart,
        "context": [c for c in context if c],
        "sowhat": None,     # Datenkarussells haben keine "Was heisst das fuer dich"-Slide
    }
    if keine_figur:
        slides["keine_figur"] = True
    if seiten:
        slides["seiten"] = seiten
    if portraet:
        slides["portraet"] = portraet
    # Feste Erklaersaetze (Rechtslage, Grenzen des Registers) stehen auf der
    # Karte, aber in keiner Datenzeile. Sie gehen deshalb auch in den
    # Quelltext - sonst verwirft der Faktencheck sie als unbelegt. Das ist
    # gewollt: diese Saetze sind hier im Code redigiert und muessen stimmen;
    # der Faktencheck prueft, ob die DATEN richtig auf der Karte landen.
    for satz in slides["context"]:
        if satz not in item["text"] and not any(m in satz for m in modelltexte):
            item["text"] += " " + satz
    return {"item": item, "slides": slides, "recherche": {"fundstellen": []}}


def _geprueft(karussell: dict | None) -> dict | None:
    """Faktencheck wie bei jedem Karussell. Einen zweiten Anlauf gibt es hier
    nicht: die Saetze entstehen aus den Daten, ein Einwand ist ein Hinweis
    auf einen Fehler im Bau, nicht auf eine Formulierung."""
    if not karussell:
        return None
    bestanden, einwand = llm.judge_slides(karussell["slides"], karussell["item"],
                                          karussell["recherche"])
    if not bestanden:
        print(f"    ! Faktencheck abgelehnt: {str(einwand)[:160]}")
        return None
    return karussell


def _item(id_: str, titel: str, quelle: str, url: str, saetze: list) -> dict:
    return {
        "id": id_,
        "source": quelle,
        "weight": 3,
        "tier": "kern",
        "title": titel,
        "text": " ".join(s for s in saetze if s),
        "url": url,
        "date": date.today().isoformat(),
    }


# --- A. Destatis -------------------------------------------------------------

def destatis(seen: set, kontext: dict) -> dict | None:
    """Die juengste Destatis-Meldung mit Alltagsbezug, normale LLM-Strecke.

    Die Auswahl fragt nur ja/nein je Meldung; die Rangfolge ist das Datum.
    Zwei weitere passende Meldungen stehen als Reserve bereit, falls die
    erste an der Belegpruefung scheitert.
    """
    items = [i for i in sources.fetch_destatis() if i["id"] not in seen]
    passend = llm.destatis_auswahl(items)
    if not passend:
        print("  = keine Destatis-Meldung mit Alltagsbezug")
        return None
    themen = []
    for item in passend[:1 + config.THEMEN_RESERVE]:
        sources.destatis_anreichern(item)
        item["bereich"] = "alltag"
        item["begruendung"] = "juengste Destatis-Meldung mit Alltagsbezug"
        # Statistik statt Entscheidung: eigene Regel im Entwurf (mehr
        # Zusammenhang statt "Warum aendern?"), siehe llm.STATISTIK_REGEL.
        item["art"] = "statistik"
        themen.append(item)
    fertig = llm.build_carousels([], research.enrich, 1, themen=themen)
    if not fertig:
        return None
    fertig[0]["slides"]["begriff_nachtitel"] = "Genauer hingeschaut"
    return fertig[0]


# --- B. Lobbyregister --------------------------------------------------------

# Taetigkeitsart laut Register -> kurzes Label fuer den Balken.
_ART = {
    "ACT_ORGANIZATION": "Unternehmen",
    "ACT_TRADE_ASSOC": "Wirtschaftsverbände",
    "ACT_EMPLOYER_ASSOC": "Wirtschaftsverbände",
    "ACT_BILATERAL_CHAMBER": "Wirtschaftsverbände",
    "ACT_PRIVATE_CHAMBER": "Wirtschaftsverbände",
    "ACT_PROFESSION_ASSOC": "Berufsverbände",
    "ACT_EMPLOYEE_ASSOC": "Berufsverbände",
    "ACT_PRIVATE_ORGA_V2": "Vereine, NGOs",
    "ACT_NONPROFIT_ORGA_V2": "Vereine, NGOs",
    "ACT_NETWORK_WITHOUT_LEGAL_FORM": "Vereine, NGOs",
    "ACT_RELIGIOUS_GROUP": "Vereine, NGOs",
    "ACT_CONSULTING": "Beratung, Kanzleien",
    "ACT_LAWYER": "Beratung, Kanzleien",
    "ACT_RESEARCH_FACILITY_V2": "Wissenschaft",
}


def _art(eintrag: dict) -> str:
    """Kurzes Label der Taetigkeitsart. Die API v2 haengt an manche Codes
    "_V2" an, die Suche nicht ("ACT_ORGANIZATION_V2" vs. "ACT_ORGANIZATION")
    - ohne diesen Abgleich landeten 44 Unternehmen unter "Sonstige"."""
    code = (((eintrag.get("activitiesAndInterests") or {}).get("activity") or {})
            .get("code") or "")
    return _ART.get(code) or _ART.get(code.removesuffix("_V2"), "Sonstige")


def lobbyregister(seen: set, kontext: dict) -> dict | None:
    """Wer zu einem aktuellen Gesetz lobbyiert hat - sonst Drehtuer, sonst
    die Ausgaben-Rangliste."""
    return (_lobby_gesetz(seen, kontext) or _drehtuer(seen)
            or _lobby_rangliste(seen))


def _verweist(eintrag: dict, vorgang_id: str, drucksachen: list) -> list:
    """Die Regelungsvorhaben des Eintrags, die nachweislich auf den Vorgang
    zeigen. Die Volltextsuche nach "21/6278" trifft auch Eintraege, die die
    Nummer nur irgendwo erwaehnen - gezaehlt wird erst, was hier besteht."""
    treffer = []
    for vorhaben in ((eintrag.get("regulatoryProjects") or {})
                     .get("regulatoryProjects") or []):
        for ds in vorhaben.get("printedMatters") or []:
            if (str(ds.get("projectUrl", "")).rstrip("/").endswith("/" + vorgang_id)
                    or (ds.get("issuer") == "BT"
                        and ds.get("printingNumber") in drucksachen)):
                treffer.append(ds)
    return treffer


def _lobby_gesetz(seen: set, kontext: dict) -> dict | None:
    gesetze = [g for g in sources.fetch_dip(config.LOBBY_GESETZE_TAGE)
               if g.get("dip_vorgang_id")
               and sources._hash("lobbygesetz" + g["dip_vorgang_id"]) not in seen
               and g["id"] not in kontext.get("heute", set())]
    if not gesetze:
        return None

    # Erst schnell zaehlen (Suche, je Drucksache eine Anfrage), dann nur fuer
    # die Spitzenreiter einzeln pruefen - das kostet rund 40 s je Gesetz.
    kandidaten = []
    for gesetz in gesetze:
        drucksachen = sources.dip_drucksachen(gesetz["dip_vorgang_id"])
        treffer = {}
        for nr in drucksachen:
            for e in sources.lobby_suche(q=nr):
                treffer[e["registerNumber"]] = e
        print(f"    {len(treffer):3} Eintraege | {gesetz['title'][:60]}")
        if len(treffer) >= config.LOBBY_MIN_ORGANISATIONEN:
            kandidaten.append((len(treffer), gesetz, drucksachen, treffer))
    kandidaten.sort(key=lambda k: -k[0])

    for _, gesetz, drucksachen, treffer in kandidaten[:3]:
        belegt = []
        for nr in treffer:
            voll = sources.lobby_eintrag(nr)
            if voll:
                verweise = _verweist(voll, gesetz["dip_vorgang_id"], drucksachen)
                if verweise:
                    belegt.append((voll, verweise))
        print(f"    = {len(belegt)} von {len(treffer)} verweisen nachweislich "
              f"auf das Gesetz")
        if len(belegt) < config.LOBBY_MIN_ORGANISATIONEN:
            continue
        kurz = llm.gesetz_kurz(gesetz)
        if not kurz:
            continue
        karussell = _geprueft(_lobby_gesetz_karussell(gesetz, kurz, belegt,
                                                      drucksachen))
        if karussell:
            return karussell
    return None


def _budget(voll: dict) -> float:
    return (((voll.get("financialExpenses") or {})
             .get("financialExpensesEuro") or {}).get("to") or 0)


def _ohne_umbruch(text: str) -> str:
    """PDF-Text aus dem Register: Zeilenumbrueche mitten im Satz, Silben-
    trennung am Zeilenende ("Gebäude-\\nenergie"). Beides glaetten."""
    text = re.sub(r"-\s*\r?\n\s*(?=[a-zäöü])", "", text or "")
    return " ".join(text.split())


def _position_quelle(voll: dict, vorgang_id: str, drucksachen: list) -> str:
    """Was die Organisation selbst zum Gesetz sagt: Titel und Beschreibung
    ihrer Regelungsvorhaben zu diesem Gesetz, dazu ein Auszug der
    Stellungnahme zu genau diesen Vorhaben. Derselbe Text geht ans Modell
    und in den Faktencheck."""
    vorhaben = []
    for v in ((voll.get("regulatoryProjects") or {}).get("regulatoryProjects") or []):
        if any(str(ds.get("projectUrl", "")).rstrip("/").endswith("/" + vorgang_id)
               or (ds.get("issuer") == "BT" and ds.get("printingNumber") in drucksachen)
               for ds in v.get("printedMatters") or []):
            vorhaben.append(v)
    nummern = {v.get("regulatoryProjectNumber") for v in vorhaben}
    teile = [f"Vorhaben: {v.get('title', '')}. {v.get('description', '')}"
             for v in vorhaben[:2]]
    for st in ((voll.get("statements") or {}).get("statements") or []):
        if st.get("regulatoryProjectNumber") in nummern:
            text = _ohne_umbruch((st.get("text") or {}).get("text", ""))
            if text:
                teile.append("Stellungnahme (Auszug): " + text[:config.LOBBY_AUSZUG])
                break
    return _ohne_umbruch(" ".join(teile))


def _lobby_gesetz_karussell(gesetz: dict, kurz: dict, belegt: list,
                            drucksachen: list) -> dict | None:
    anzahl = len(belegt)
    arten = Counter(_art(v) for v, _ in belegt)
    # "Sonstige" ist Rest, keine Gruppe: es steht einmal und immer am Ende,
    # auch wenn es gross ist. Passen nicht alle Gruppen in vier Balken, geht
    # der Ueberhang mit hinein.
    sonstige = arten.pop("Sonstige", 0)
    reihe = arten.most_common()
    platz = config.CHART_MAX_BARS - (1 if sonstige or len(reihe) > config.CHART_MAX_BARS else 0)
    sonstige += sum(n for _, n in reihe[platz:])
    reihe = reihe[:platz] + ([("Sonstige", sonstige)] if sonstige else [])

    # Was die Organisationen wollten (Abstimmung 25.09.2026: Namen allein
    # sind kein Befund). Zuerst, wer eine Stellungnahme hinterlegt hat, dann
    # nach Budget. Gemischt nach Art, damit nicht drei Wirtschaftsverbaende
    # nebeneinander stehen.
    kandidaten = []
    for voll, _ in belegt:
        quelle = _position_quelle(voll, gesetz["dip_vorgang_id"], drucksachen)
        if len(quelle) > 120:
            kandidaten.append({"name": sources.lobby_name(voll).strip(),
                               "art": _art(voll), "quelle": quelle,
                               "stellungnahme": "Stellungnahme" in quelle,
                               "budget": _budget(voll)})
    kandidaten.sort(key=lambda k: (not k["stellungnahme"], -k["budget"]))
    auswahl, arten_gesehen = [], set()
    for runde in (0, 1):
        for k in kandidaten:
            if len(auswahl) >= config.LOBBY_KANDIDATEN:
                break
            if k in auswahl or (runde == 0 and k["art"] in arten_gesehen):
                continue
            auswahl.append(k)
            arten_gesehen.add(k["art"])
    name = kurz["kurzname"]
    saetze_modell, lager = llm.lobby_positionen(name, auswahl)
    # Zwei Lager, die sich gegenueberstehen (Abstimmung 25.09.2026): je
    # hoechstens zwei Organisationen, in der Reihenfolge der Auswahl
    # (Stellungnahme zuerst, dann Budget). Ohne echten Gegensatz bleibt es
    # bei der einfachen Liste.
    if lager:
        lager = [{"titel": l["titel"],
                  "positionen": [{**auswahl[nr - 1], "satz": saetze_modell[nr]}
                                 for nr in sorted(l["nr"])][:config.LOBBY_JE_LAGER]}
                 for l in lager]
        positionen = [p for l in lager for p in l["positionen"]]
    else:
        positionen = [{**auswahl[nr - 1], "satz": satz}
                      for nr, satz in sorted(saetze_modell.items())][:config.LOBBY_POSITIONEN]
    if len(positionen) < config.LOBBY_POSITIONEN_MIN:
        print(f"    - nur {len(positionen)} belegte Positionen - naechstes Gesetz")
        return None
    # Slide 4 wie Slide 3 bei DIP: was das Gesetz aendert und warum.
    karte = llm.gesetz_karte(gesetz)

    ministerien = Counter(m.get("title") for _, verweise in belegt
                          for ds in verweise for m in ds.get("leadingMinistries") or []
                          if m.get("title"))
    federfuehrend = [m for m, _ in ministerien.most_common(2)]

    saetze = [
        gesetz["text"],
        f"Im Lobbyregister des Bundestages verweisen {anzahl} Einträge mit "
        f"ihren Regelungsvorhaben auf dieses Gesetz (Drucksache "
        f"{_aufzaehlung(drucksachen)}).",
        "Nach Art der Organisation: " + ", ".join(
            f"{art} {n}" for art, n in reihe) + ".",
        (f"Federführend laut Register: {_aufzaehlung(federfuehrend)}."
         if federfuehrend else ""),
        # Die Quellen der Positionen: gegen genau diese Auszuege prueft der
        # Faktencheck die Saetze auf "Was sie wollten".
        *[f"Angaben von {p['name']} im Lobbyregister: {p['quelle']}" for p in positionen],
    ]
    item = _item(sources._hash("lobbygesetz" + gesetz["dip_vorgang_id"]),
                 f"Lobbyarbeit zum {name}",
                 "Lobbyregister des Deutschen Bundestages",
                 f"https://www.lobbyregister.bundestag.de/suche?q={quote(drucksachen[0])}",
                 saetze)

    zeige = lambda p: {"name": _kurzname(p["name"], 60), "logo": p["name"],
                       "satz": p["satz"]}
    grenzen = ("Zusammengefasst aus Angaben und Stellungnahmen im Lobbyregister. "
               "Dort steht nur, wer Kontakt zu Bundestag oder Bundesregierung "
               "meldet.")
    federf = (_satz(f"Federführend: {_aufzaehlung(federfuehrend)}")
              if federfuehrend else "")
    if federf:
        grenzen += " " + federf
    if lager:
        seite3 = {"kind": "lager", "titel": "Wer was wollte",
                  "lager": [{"titel": l["titel"],
                             "positionen": [zeige(p) for p in l["positionen"]]}
                            for l in lager],
                  "hinweis": grenzen}
    else:
        seite3 = {"kind": "positionen", "titel": "Was sie wollten",
                  "positionen": [zeige(p) for p in positionen], "hinweis": grenzen}

    if karte:
        seite4 = {"kind": "begriff", "titel": "Was das Gesetz ändert",
                  "begriff": karte}
    else:
        seite4 = {"kind": "context", "titel": "Worum es ging",
                  "saetze": [kurz["satz"], federf]}

    return _karussell(
        item,
        titel=f"Wer beim {name} mitredete",
        # Die Zahl steht im Haken selbst: nur 1a setzt sie gross daneben, auf
        # jeder anderen Cover-Architektur hinge "So viele" in der Luft.
        # Kurz (Abstimmung 25.09.2026: der ganze Satz war zu lang), aber mit
        # eigener Information - "61 Organisationen haben Lobbyarbeit
        # gemeldet" allein wiederholte fuer den Faktencheck die Schlagzeile.
        hook=(f"{anzahl} Organisationen, zwei Lager." if lager else
              f"{anzahl} Organisationen, von {_kurzname(positionen[0]['name'], 30)} "
              f"bis {_kurzname(positionen[-1]['name'], 30)}."),
        cover_frage=f"Wer hat beim {name} mitgeredet?",
        # Die Zahl steht schon im Haken. Als Hero-Figur bliebe sonst nur der
        # groesste Balken ("39") - das waere die falsche Zahl.
        keine_figur=True,
        chart={"titel": "Wer lobbyiert hat, nach Art",
               "einheit": "",
               "balken": [{"label": art, "wert": n} for art, n in reihe],
               "hervorheben": 0,
               "hinweis": f"{anzahl} Einträge im Lobbyregister"},
        context=[],
        seiten=[seite3, seite4],
        modelltexte=tuple(p["satz"] for p in positionen)
        + tuple(lg["titel"] for lg in lager)
        + (tuple(karte["saetze"] + karte["warum"] + [karte["beispiel"]]) if karte else ()),
    )


def _drehtuer(seen: set) -> dict | None:
    """Ein ehemaliges Regierungsmitglied, das jetzt im Lobbyregister steht."""
    kandidaten = []
    for treffer in sources.lobby_suche(
            **{"filter[revolvingdoorareas][FEDERAL_GOVERNMENT]": "true"}):
        voll = sources.lobby_eintrag(treffer["registerNumber"])
        if not voll:
            continue
        ident = voll.get("lobbyistIdentity") or {}
        personen = ([ident] + (ident.get("legalRepresentatives") or [])
                    + (ident.get("entrustedPersons") or []))
        for p in personen:
            funktion = p.get("recentGovernmentFunction") or {}
            regierung = funktion.get("federalGovernment") or {}
            code = (regierung.get("function") or {}).get("code")
            # Nur wer das Amt hinter sich hat. Laufende Aemter sind meist
            # Gremiensitze kraft Amtes, keine Drehtuer.
            if not (funktion.get("ended") and code in config.DREHTUER_FUNKTIONEN):
                continue
            name = " ".join(" ".join(filter(None, [p.get("firstName"),
                                                   p.get("lastName")])).split())
            id_ = sources._hash("drehtuer" + name + voll["registerNumber"])
            if name and id_ not in seen:
                kandidaten.append((id_, name, funktion, regierung, voll))
    if not kandidaten:
        return None
    # Einmal pro Person und Organisation; wer zuletzt dran war, kommt spaeter.
    zuletzt = _stand().get("drehtuer", [])
    random.shuffle(kandidaten)
    kandidaten.sort(key=lambda k: k[1] in zuletzt)

    statistik = ((sources.lobby_statistik().get("lobbyists") or {})
                 .get("recentGovernmentFunction") or {}).get("existing", {}).get("type", {})
    for id_, name, funktion, regierung, voll in kandidaten:
        karussell = _geprueft(_drehtuer_karussell(id_, name, funktion, regierung,
                                                  voll, statistik))
        if karussell:
            _stand_merken("drehtuer", name)
            return karussell
    return None


def _drehtuer_karussell(id_, name, funktion, regierung, voll, statistik) -> dict | None:
    org = sources.lobby_name(voll)
    amt = (regierung.get("function") or {}).get("de", "")
    ressort = (regierung.get("department") or {}).get("title", "")
    ende = funktion.get("endDate", "")          # "2024-11"
    bis = f"{ende[5:7]}/{ende[:4]}" if len(ende) >= 7 else ""
    taetig = voll.get("activitiesAndInterests") or {}
    art = (taetig.get("activity") or {}).get("de", "")
    felder = _themen(taetig.get("fieldsOfInterest"), 3)
    vorhaben = (voll.get("regulatoryProjects") or {}).get("regulatoryProjectsCount") or 0

    gv = statistik.get("federalGovernment", {})
    bt = statistik.get("houseOfRepresentatives", {})
    verw = statistik.get("federalAdministration", {})
    werte = [("Bundesminister/-innen", (gv.get("memberOfTheGovernment") or {}).get("number")),
             ("Parl. Staatssekretär/-innen", (gv.get("parliamentalSecretary") or {}).get("number")),
             ("Bundestagsabgeordnete", (bt.get("memberOfTheParliament") or {}).get("number")),
             ("Bundesverwaltung", (verw.get("member") or {}).get("number"))]
    werte = [(l, w) for l, w in werte if isinstance(w, (int, float))]
    if len(werte) < config.CHART_MIN_BARS:
        return None
    eigene = "Bundesminister/-innen" if "MINISTER" == (regierung.get("function") or {}).get("code") \
        else "Parl. Staatssekretär/-innen"
    markiert = next((i for i, (l, _) in enumerate(werte) if l == eigene), 0)

    selbst = org.strip().lower() == name.strip().lower()
    wo = "ist selbst im Lobbyregister eingetragen" if selbst \
        else f"ist im Lobbyregister für {org} eingetragen"
    satz_amt = f"{name} war bis {bis} in der Bundesregierung: {amt}" + \
        (f", {ressort}." if ressort else ".")
    satz_org = "" if selbst else (
        f"{org} ist im Register als {art} eingetragen"
        + (f", Themen u. a.: {_aufzaehlung(felder)}." if felder else "."))
    satz_vorhaben = (f"Laut Register betreibt {org} Interessenvertretung zu "
                     f"{vorhaben} Regelungsvorhaben." if vorhaben and not selbst else "")
    saetze = [f"{name} {wo}.", satz_amt, satz_org, satz_vorhaben,
              "Personen mit einer Funktion in Bundesregierung, Bundestag oder "
              "Bundesverwaltung laut Statistik des Lobbyregisters: "
              + ", ".join(f"{l} {int(w)}" for l, w in werte) + "."]
    item = _item(id_, f"Drehtür: {name}", "Lobbyregister des Deutschen Bundestages",
                 (voll.get("registerEntryDetails") or {}).get("detailsPageUrl",
                                                             "https://www.lobbyregister.bundestag.de/"),
                 saetze)
    return _karussell(
        item,
        titel="Von der Regierungsbank ins Lobbyregister",
        hook=f"{name} {wo}.",
        context_titel="Vom Amt zur Interessenvertretung",
        cover_frage=f"Wo ist {name} heute im Lobbyregister eingetragen?",
        keine_figur=True,
        chart={"titel": "Im Register mit früherem Amt",
               "einheit": "",
               "balken": [{"label": l, "wert": w} for l, w in werte],
               "hervorheben": markiert,
               "hinweis": "Personen mit Funktion in Regierung, Bundestag oder Verwaltung"},
        context=[satz_amt, f"Heute {wo}.", satz_org, satz_vorhaben,
                 "Die Angaben im Lobbyregister machen die Eingetragenen selbst."],
    )


def _lobby_rangliste(seen: set) -> dict | None:
    """Die groessten Lobby-Budgets, insgesamt oder je Themenfeld - jede
    Variante einmal je Geschaeftsjahr."""
    for code, feld in config.LOBBY_RANG_THEMEN:
        params = {"filter[financialexpenses][1000000-999999999]": "true"}
        if code:
            params[f"filter[fieldsofinterest][{code}]"] = "true"
        treffer = sources.lobby_suche(**params)
        eintraege, namen = [], set()
        for e in sorted(treffer, key=lambda e: -((e.get("financialExpenses") or {})
                                               .get("financialExpensesEuro") or {}).get("to", 0)):
            name = sources.lobby_name(e)
            # Doppelte Eintraege kommen vor (der BDI steht zweimal drin).
            if name.lower() in namen:
                continue
            namen.add(name.lower())
            eintraege.append(e)
        if len(eintraege) < config.CHART_MIN_BARS:
            continue
        jahr = str((eintraege[0].get("financialExpenses") or {})
                   .get("relatedFiscalYearEnd", ""))[:4]
        id_ = sources._hash(f"lobbyrang{jahr}{code}")
        if id_ in seen:
            continue
        karussell = _geprueft(_rangliste_karussell(id_, eintraege, jahr, feld))
        if karussell:
            return karussell
    return None


def _rangliste_karussell(id_, eintraege, jahr, feld) -> dict:
    def obergrenze(e):
        return ((e.get("financialExpenses") or {}).get("financialExpensesEuro") or {}).get("to", 0)

    top = eintraege[:config.CHART_MAX_BARS]
    erster = top[0]
    fte = (erster.get("employeesInvolvedInLobbying") or {}).get("employeeFTE")
    im_feld = f" im Bereich {feld}" if feld else ""
    saetze = [f"Gemeldete Ausgaben für Interessenvertretung im Geschäftsjahr {jahr}, "
              f"Obergrenze der gemeldeten Spanne{im_feld}: "
              + "; ".join(f"{sources.lobby_name(e)} {_zahl(obergrenze(e))} Euro"
                          for e in top) + ".",
              (f"{sources.lobby_name(erster)} meldet {str(fte).replace('.', ',')} "
               f"Vollzeitstellen für Interessenvertretung." if fte else ""),
              f"{len(eintraege)} Organisationen{im_feld} melden mehr als eine "
              f"Million Euro im Jahr."]
    item = _item(id_, f"Lobby-Budgets {jahr}{im_feld}",
                 "Lobbyregister des Deutschen Bundestages",
                 "https://www.lobbyregister.bundestag.de/suche", saetze)
    return _karussell(
        item,
        titel="Die größten Lobby-Budgets" + (f": {feld}" if feld else ""),
        hook=f"Was Organisationen {jahr} für Lobbyarbeit ausgegeben haben, "
             f"nach eigener Angabe.",
        context_titel="So liest du die Zahlen",
        chart={"titel": f"Lobbyausgaben {jahr}",
               "einheit": "Mio. €",
               "balken": [{"label": _kurzname(sources.lobby_name(e)),
                           "wert": _mio(obergrenze(e))} for e in top],
               "hervorheben": 0,
               "hinweis": "Obergrenze der gemeldeten Spanne"},
        context=[
            (f"Vorn liegt {sources.lobby_name(erster)} mit rund "
             f"{_mio_text(obergrenze(erster))} Millionen Euro"
             + (f" und {str(fte).replace('.', ',')} Vollzeitstellen für Lobbyarbeit."
                if fte else ".")),
            f"{len(eintraege)} Organisationen{im_feld} melden mehr als eine "
            f"Million Euro im Jahr.",
            "Die Beträge melden die Organisationen selbst, als Spanne. "
            "Gezeigt ist die Obergrenze.",
        ],
    )


# --- C. Parteispenden --------------------------------------------------------

def parteispenden(seen: set, kontext: dict) -> dict | None:
    """Eine aktuelle Grossspende, sonst die Jahresbilanz nach Partei."""
    heute = date.today()
    alle = []
    for jahr in (heute.year - 2, heute.year - 1, heute.year):
        alle += sources.parteispenden_jahr(jahr)
    diesjahr = [s for s in alle if s["jahr"] == heute.year]
    if not diesjahr:
        return None

    gross = [s for s in diesjahr
             if s["betrag"] >= config.SPENDE_GROSS and s["id"] not in seen
             and (heute - s["datum"]).days <= config.SPENDE_TAGE]
    if gross:
        spende = max(gross, key=lambda s: s["datum"])
        karussell = _geprueft(_spende_karussell(spende, alle, diesjahr))
        if karussell:
            return karussell

    id_ = sources._hash(f"spendenjahr{heute:%Y-%m}")
    if id_ in seen:
        return None
    return _geprueft(_spendenjahr_karussell(id_, diesjahr, heute.year, alle))


def _gleicher_spender(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"[^a-z0-9äöüß]", "", s.lower())
    return norm(a) == norm(b)


def _lobby_zu_spender(name: str) -> dict | None:
    """Der Lobbyregister-Eintrag des Spenders, wenn es eindeutig einen gibt.

    Eindeutig heisst: alle Woerter des Registernamens (ohne Rechtsform)
    stehen im Spendernamen. Lieber keinen Treffer als einen falschen - auf
    der Karte stuende sonst eine fremde Organisation."""
    woerter = lambda s: set(re.findall(r"[a-zäöüß0-9]{3,}", _kurzname(s, 200).lower()))
    spender = woerter(name)
    passend = [e for e in sources.lobby_suche(q=_kurzname(name, 60))
               if woerter(sources.lobby_name(e)) and woerter(sources.lobby_name(e)) <= spender]
    return passend[0] if len(passend) == 1 else None


def _spender_quelle(name: str) -> str:
    """Was ueber eine spendende Organisation belegt ist: ihr Eintrag im
    Lobbyregister (Selbstbeschreibung, Art, Themen, Budget, Personal) und
    der Anfang des Wikipedia-Artikels. Leer, wenn es beides nicht gibt."""
    teile = []
    treffer = _lobby_zu_spender(name)
    voll = sources.lobby_eintrag(treffer["registerNumber"]) if treffer else None
    if voll:
        taetig = voll.get("activitiesAndInterests") or {}
        ident = voll.get("lobbyistIdentity") or {}
        art = (taetig.get("activity") or {}).get("de", "")
        form = (ident.get("legalForm") or {}).get("de", "")
        ort = (ident.get("address") or {}).get("city", "")
        felder = _themen(taetig.get("fieldsOfInterest"), 4)
        fte = (voll.get("employeesInvolvedInLobbying") or {}).get("employeeFTE")
        geschaeftsjahr = str((voll.get("financialExpenses") or {})
                             .get("relatedFiscalYearEnd", ""))[:4]
        satz = (f"Lobbyregister des Bundestages: {sources.lobby_name(voll)}"
                f"{f', {form}' if form else ''}{f', Sitz {ort}' if ort else ''}"
                f"{f', eingetragen als {art}' if art else ''}.")
        if felder:
            satz += f" Themen u. a.: {_aufzaehlung(felder)}."
        if geschaeftsjahr and _budget(voll):
            satz += (f" Ausgaben für Interessenvertretung {geschaeftsjahr}: bis "
                     f"{_zahl(_budget(voll))} Euro.")
        if fte:
            satz += f" {str(fte).replace('.', ',')} Vollzeitstellen für Interessenvertretung."
        satz += " Selbstbeschreibung: " + _ohne_umbruch(
            taetig.get("activityDescription", ""))[:1500]
        teile.append(satz)
    wiki = sources.wikipedia_kurz(name)
    if wiki:
        teile.append(f"Wikipedia: {wiki[:1200]}")
    return " ".join(teile)


def _spende_karussell(spende: dict, alle: list, diesjahr: list) -> dict:
    jahr, partei, name = spende["jahr"], spende["partei"], spende["spender"]
    kurz = _kurzname(name, 40)
    rangfolge = sorted(diesjahr, key=lambda s: -s["betrag"])
    platz = next(i for i, s in enumerate(rangfolge, 1) if s["id"] == spende["id"])
    frueher = [s for s in alle if s["id"] != spende["id"]
               and _gleicher_spender(s["spender"], name)]
    uebrige = sum(s["betrag"] for s in diesjahr
                  if s["partei"] == partei and s["id"] != spende["id"])
    schnitt = sum(s["betrag"] for s in diesjahr) / len(diesjahr)

    if frueher:
        summe = sum(s["betrag"] for s in frueher)
        an = sorted({s["partei"] for s in frueher})
        vorher = (f"Seit {jahr - 2} hat {kurz} {len(frueher)} weitere Großspende"
                  f"{'n' if len(frueher) > 1 else ''} über 35.000 Euro gemacht, "
                  f"zusammen {_zahl(summe)} Euro, an {_aufzaehlung([_an(p) for p in an])}.")
    else:
        vorher = f"Seit {jahr - 2} ist das die erste Großspende über 35.000 Euro von {kurz}."
    faktor = spende["betrag"] / schnitt if schnitt else 0
    rang = (f"Es ist die größte Einzelspende des Jahres {jahr}." if platz == 1 else
            f"Unter den {len(diesjahr)} Großspenden {jahr} liegt sie auf Platz {platz}.")
    if faktor >= 1.5:
        rang += (f" Sie ist rund {round(faktor)}-mal so hoch wie eine "
                 f"durchschnittliche Großspende ({_zahl(schnitt)} Euro).")
    melde = ("Spenden über 35.000 Euro müssen Parteien sofort dem Bundestag "
             "melden (§ 25 Parteiengesetz).")

    # Slide 3: bei Organisationen eine Begriffskarte "Wer ist ...?" wie beim
    # DIP-Karussell (Abstimmung 25.09.2026: ein Satz war zu duenn). Die zwei
    # Saetze schreibt ein Modell aus Lobbyregister und Wikipedia, belegt;
    # die fette Zeile darunter sind die eigenen Spenden-Daten.
    quelle, portraet_saetze = "", []
    if spende["organisation"]:
        quelle = _spender_quelle(name)
        if quelle:
            portraet_saetze = llm.spender_portraet(kurz, quelle)
    if portraet_saetze:
        seite3 = {"kind": "begriff", "titel": f"Wer ist {kurz}?", "logo": name,
                  "nachtitel": "Die Spende einordnen",
                  "begriff": {"saetze": portraet_saetze, "beispiel": vorher,
                              "warum": [rang, melde]}}
    elif spende["organisation"]:
        seite3 = {"kind": "context", "titel": "Wer ist der Spender?",
                  "saetze": [vorher, rang, melde]}
    else:
        seite3 = {"kind": "context", "titel": "Die Spende",
                  "saetze": ["Der Spender ist eine Privatperson. Name und Betrag "
                             "veröffentlicht der Bundestag, weil die Spende über "
                             "35.000 Euro liegt.", vorher, rang, melde]}

    balken = [{"label": "Diese Spende", "wert": spende["betrag"]}]
    if uebrige:
        balken.append({"label": f"Übrige an {_an(partei)} {jahr}", "wert": uebrige,
                       "logo": partei})
    balken.append({"label": f"Durchschnitt Großspende {jahr}", "wert": round(schnitt)})

    saetze = [f"{_an(partei)[0].upper() + _an(partei)[1:]} hat am {_datum(spende['datum'])} eine Spende "
              f"über {_zahl(spende['betrag'])} Euro von {name} erhalten.",
              vorher, rang,
              f"Übrige Großspenden an {_an(partei)} {jahr}: zusammen {_zahl(uebrige)} Euro.",
              f"Durchschnittliche Großspende {jahr}: {_zahl(schnitt)} Euro "
              f"({len(diesjahr)} Spenden).", melde,
              # Gegen diese Angaben prueft der Faktencheck "Wer ist ...?".
              f"Angaben zum Spender: {quelle}" if quelle else ""]
    item = _item(spende["id"], f"Großspende an {_an(partei)}",
                 "Deutscher Bundestag, Parteispenden über 35.000 Euro (§ 25 PartG)",
                 spende["url"], saetze)
    return _karussell(
        item,
        titel=f"Großspende an {_an(partei)}",
        hook=f"Von {kurz}, eingegangen am {_datum(spende['datum'])}.",
        cover_figur=f"{_zahl(spende['betrag'])} €",
        chart={"titel": "Diese Spende im Vergleich",
               "einheit": "Euro",
               "balken": balken,
               "hervorheben": 0,
               "hinweis": f"Großspenden über 35.000 Euro, {jahr}"},
        context=[],
        seiten=[seite3],
        modelltexte=tuple(portraet_saetze),
    )


# Bundestagswahlen - im Wahljahr ballen sich die Spenden vor dem Termin.
_WAHLJAHRE = {2021, 2025, 2029}


def _spendenjahr_karussell(id_: str, diesjahr: list, jahr: int,
                           alle: list | None = None) -> dict | None:
    summen, anzahl = Counter(), Counter()
    for s in diesjahr:
        summen[s["partei"]] += s["betrag"]
        anzahl[s["partei"]] += 1
    reihe = summen.most_common()
    if len(reihe) < 3:
        return None
    # Auf den Euro genau: gerundet auf Millionen standen CDU (1,96) und "Alle
    # anderen" (1,96) als zwei gleiche Balken "2 Mio. EUR" da. Fuenf Parteien
    # mit Logo; der Rest steht im Hinweis, nicht als eigener Balken.
    n_balken = config.SPENDEN_JAHR_BALKEN
    balken = [{"label": p, "wert": round(v), "logo": p} for p, v in reihe[:n_balken]]
    rest = sum(v for _, v in reihe[n_balken:])
    rest_parteien = [p for p, _ in reihe[n_balken:]]

    gesamt = sum(summen.values())
    schnitt = gesamt / len(diesjahr)
    groesste = max(diesjahr, key=lambda s: s["betrag"])
    von = (f" von {_kurzname(groesste['spender'], 40)}" if groesste["organisation"]
           else " von einer Privatperson")
    meiste, n_meiste = anzahl.most_common(1)[0]
    faktor = groesste["betrag"] / schnitt

    # Derselbe Zeitraum in den Vorjahren: 1. Januar bis heutiges Datum.
    heute = max(s["datum"] for s in diesjahr)
    vergleich = []
    for vj in (jahr - 1, jahr - 2):
        bis = heute.replace(year=vj)
        teil = [s for s in (alle or []) if s["jahr"] == vj and s["datum"] <= bis]
        if teil:
            januar = sum(1 for s in teil if s["datum"].month == 1)
            vergleich.append((vj, len(teil), sum(s["betrag"] for s in teil), januar))
    stichtag = f"{heute.day}. {MONATE[heute.month - 1]}"
    satz_vorjahr = ""
    if vergleich:
        vj, n_vj, summe_vj, januar = vergleich[0]
        veraenderung = round(100 * (gesamt - summe_vj) / summe_vj) if summe_vj else 0
        richtung = "mehr" if veraenderung >= 0 else "weniger"
        # Die Betraege stehen in der Saeulenreihe darueber - der Satz nennt
        # nur noch die Veraenderung.
        satz_vorjahr = (f"{abs(veraenderung)} Prozent {richtung} Geld als bis zum "
                        f"{stichtag} {vj}.")
        # Im Wahljahr ballen sich die Spenden vor dem Termin - ohne diesen
        # Satz liest sich der Rueckgang wie ein Einbruch.
        if vj in _WAHLJAHRE and januar >= 0.3 * n_vj:
            satz_vorjahr += (f" {vj} war Bundestagswahl, allein im Januar kamen "
                             f"{januar} Großspenden.")

    # Jahresvergleich als kleine Saeulenreihe: jeweils 1. Januar bis heute,
    # damit ein halbes Jahr nicht gegen ein ganzes steht.
    saeulen = None
    if vergleich:
        reihe_j = sorted([(vj, summe) for vj, _, summe, _ in vergleich] + [(jahr, gesamt)])
        saeulen = {"titel": "", "einheit": "Mio. €",
                   "balken": [{"label": str(j), "wert": _mio(v)} for j, v in reihe_j],
                   "hervorheben": len(reihe_j) - 1,
                   "hinweis": f"Großspenden, jeweils 1. Januar bis {stichtag}"}

    satz_groesste = (f"Die größte Einzelspende, {_zahl(groesste['betrag'])} Euro an "
                     f"{_an(groesste['partei'])}{von}, ist rund {round(faktor)}-mal so "
                     f"hoch wie eine durchschnittliche Großspende "
                     f"({_zahl(schnitt)} Euro).")
    satz_meiste = f"Die meisten Spenden gingen an {_an(meiste)}: {n_meiste} von {len(diesjahr)}."

    saetze = [f"Seit Januar {jahr} haben Parteien {len(diesjahr)} Spenden über "
              f"35.000 Euro gemeldet, zusammen {_zahl(gesamt)} Euro "
              f"(rund {_mio_text(gesamt)} Millionen Euro).",
              "Nach Partei: " + "; ".join(
                  f"{p} {_zahl(v)} Euro, rund {_mio_text(v)} Millionen, "
                  f"{anzahl[p]} Spenden" for p, v in reihe) + ".",
              f"Durchschnittliche Großspende {jahr}: {_zahl(schnitt)} Euro.",
              *[f"Großspenden {vj} bis zum {stichtag}: {n} Spenden, zusammen "
                f"{_zahl(summe)} Euro, davon {jan} im Januar."
                for vj, n, summe, jan in vergleich]]
    item = _item(id_, f"Großspenden an Parteien {jahr}",
                 "Deutscher Bundestag, Parteispenden über 35.000 Euro (§ 25 PartG)",
                 f"{config.PARTEISPENDEN_URL}/{jahr}", saetze)
    hinweis = "Summe der Spenden über 35.000 Euro"
    if rest:
        hinweis += (f". Übrige ({_aufzaehlung(rest_parteien)}) zusammen "
                    f"{_zahl(rest)} Euro")
    return _karussell(
        item,
        titel=f"Großspenden an Parteien {jahr}",
        hook=f"{len(diesjahr)} Spenden über 35.000 Euro seit Januar.",
        cover_figur=f"{_mio_text(gesamt)} Mio. €",
        chart={"titel": f"Großspenden {jahr} nach Partei",
               "einheit": "Euro",
               "balken": balken,
               "max_balken": n_balken,
               "hervorheben": 0,
               "hinweis": hinweis},
        context=[],
        seiten=[{"kind": "context", "titel": "Was dahintersteckt",
                 "saeulen": saeulen,
                 # Der feste Satz zur Veroeffentlichungspflicht ist mit der
                 # Saeulenreihe weggefallen (25.09.2026: Slide zu voll).
                 "saetze": [satz_groesste, satz_vorjahr, satz_meiste]}],
    )


# --- D. Nebentaetigkeiten ----------------------------------------------------

def _politiker() -> dict:
    """Name -> abgeordnetenwatch-IDs. Einmal aufgeloest, dann aus der Datei:
    die IDs aendern sich innerhalb der Wahlperiode nicht, und die API ist
    beim Rate-Limit empfindlich."""
    try:
        bekannt = json.loads(POLITIKER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bekannt = {}
    geaendert = False
    for name in config.POLITIKER_BACKLOG + config.POLITIKER_RESERVE:
        if name in bekannt:
            continue
        info = None
        for p in sources.aow("politicians", label=name) or []:
            mandate = sources.aow("candidacies-mandates", politician=p["id"],
                                  parliament_period=161, type="mandate") or []
            if mandate:
                info = {"politiker": p["id"], "mandat": mandate[0]["id"],
                        "url": p.get("abgeordnetenwatch_url", "")}
                break
        bekannt[name] = info      # None heisst: kein aktuelles Mandat
        geaendert = True
    if geaendert:
        POLITIKER.parent.mkdir(exist_ok=True)
        POLITIKER.write_text(json.dumps(bekannt, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    return bekannt


def nebentaetigkeiten(seen: set, kontext: dict) -> dict | None:
    """Eine Person aus dem Backlog, der Reihe nach."""
    ids = _politiker()
    zuletzt = _stand().get("neben", [])
    sperre = set(zuletzt[:len(config.POLITIKER_BACKLOG) - 1])

    # Wer zuletzt neue Meldungen hatte, kommt zuerst dran - ein Abruf fuer alle.
    grenze = date.today().toordinal() - config.REGISTER_LOOKBACK_DAYS
    frisch = set()
    for s in sources.aow("sidejobs", range_end=200, sort_by="data_change_date",
                         sort_direction="desc") or []:
        try:
            if date.fromisoformat(s.get("data_change_date", "")[:10]).toordinal() >= grenze:
                frisch.update(m["id"] for m in s.get("mandates") or [])
        except ValueError:
            pass

    def rang(name):
        info = ids.get(name) or {}
        nie = name not in zuletzt
        return (info.get("mandat") not in frisch, not nie,
                -zuletzt.index(name) if name in zuletzt else 0)

    for gruppe in (config.POLITIKER_BACKLOG, config.POLITIKER_RESERVE):
        for name in sorted((n for n in gruppe if ids.get(n) and n not in sperre), key=rang):
            karussell = _geprueft(_neben_karussell(name, ids[name]))
            if karussell:
                _stand_merken("neben", name)
                return karussell
    return None


def _taetigkeit(eintrag: dict) -> str:
    """"Mitglied des Kuratoriums, ehrenamtlich (ab 17.09.2026)" -> ohne Datum."""
    return re.sub(r"\s*\((ab|bis|seit)[^)]*\)", "", eintrag.get("label", "")).strip(" ,")


def _jahr(eintrag: dict) -> str:
    treffer = re.search(r"\b(20\d\d)\b", eintrag.get("job_title_extra") or "")
    return treffer.group(1) if treffer else ""


def _mandat_vorher(name: str, info: dict) -> int | None:
    """Mandats-ID der vorigen Wahlperiode, einmal aufgeloest und in
    data/politiker.json gemerkt (0 heisst: damals kein Mandat)."""
    if "mandat_vorher" not in info:
        info["mandat_vorher"] = sources.mandat_in_periode(
            info["politiker"], config.NEBEN_PERIODE_VORHER) or 0
        try:
            bekannt = json.loads(POLITIKER.read_text(encoding="utf-8"))
            bekannt[name] = info
            POLITIKER.write_text(json.dumps(bekannt, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
        except (OSError, ValueError):
            pass
    return info["mandat_vorher"] or None


# Parteien melden sich bei abgeordnetenwatch mit vollem Namen. Auf der Karte
# steht das Kuerzel - dann traegt der Balken auch das Parteilogo.
_PARTEI_LANG = [("Christlich Demokratische Union", "CDU"),
                ("Christlich-Soziale Union", "CSU"),
                ("Sozialdemokratische Partei Deutschlands", "SPD"),
                ("Bündnis 90/Die Grünen", "Grüne"), ("Alternative für Deutschland", "AfD"),
                ("Freie Demokratische Partei", "FDP"), ("Bündnis Sahra Wagenknecht", "BSW")]


def _org(e: dict) -> str:
    name = (e.get("sidejob_organization") or {}).get("label", "")
    for lang, kurz in _PARTEI_LANG:
        if name.startswith(lang):
            return kurz
    return name


def _verschiedene(meldungen: list) -> int:
    """Wie viele verschiedene Taetigkeiten: Organisation plus Taetigkeit,
    ohne Datum. Dieselbe Funktion in zwei Jahren ist eine, nicht zwei."""
    return len({(_org(e).lower(), _taetigkeit(e).lower()) for e in meldungen})


def _komma(wert: float) -> str:
    return f"{wert:.1f}".replace(".", ",")


def _anzeige(e: dict) -> str:
    """Gemeldeter Betrag mit Zeitraum fuer Balken: "11.227 € / Monat"."""
    zeitraum = {"im Monat": " / Monat", "im Jahr": " / Jahr",
                "einmalig": " einmalig"}.get(sources.neben_zeitraum(e), "")
    return f"{_zahl(float(e['income']))} €{zeitraum}"


def _meldung_satz(e: dict) -> str:
    art = config.NEBEN_KATEGORIEN.get(e.get("category"), ("",))[0]
    extra = f" ({e['job_title_extra']})" if e.get("job_title_extra") else ""
    zeitraum = sources.neben_zeitraum(e)
    # Der Jahreswert steht mit im Quelltext: auf der Karte wird mit ihm
    # verglichen, und der Faktencheck soll ihn finden.
    jahr = (f", aufs Jahr gerechnet {_zahl(sources.neben_jahreswert(e))} Euro"
            if zeitraum == "im Monat" else "")
    betrag = (f", gemeldeter Betrag {_zahl(float(e['income']))} Euro"
              f"{' ' + zeitraum if zeitraum else ''}{jahr}{extra}"
              if e.get("income") else "")
    org = f" ({_org(e)})" if _org(e) else ""
    return _satz(f"Meldung: {_taetigkeit(e)}{org}{f' ({art})' if art else ''}{betrag}")


def _neben_karussell(name: str, info: dict) -> dict | None:
    meldungen = sources.aow("sidejobs", mandates=info["mandat"], range_end=200) or []
    if not meldungen:
        return None
    nachname = name.split()[-1]
    # Nach Jahreswert: ein Monatsbetrag zaehlt zwoelffach (sources.neben_jahreswert).
    mit_betrag = sorted((e for e in meldungen if e.get("income")),
                        key=lambda e: -sources.neben_jahreswert(e))
    monatlich = any(sources.neben_zeitraum(e) == "im Monat" for e in mit_betrag)
    jahr_hinweis = "Monatsbeträge × 12 gerechnet. " if monatlich else ""

    # Befund 2: deutliche Aenderung gegenueber der vorigen Wahlperiode.
    vorher_n = None
    mandat_alt = _mandat_vorher(name, info)
    if mandat_alt:
        alt = sources.aow("sidejobs", mandates=mandat_alt, range_end=200)
        if alt is not None:
            vorher_n = _verschiedene(alt)
    jetzt_n = _verschiedene(meldungen)
    aenderung = (vorher_n is not None
                 and abs(jetzt_n - vorher_n) >= config.NEBEN_AENDERUNG_MIN
                 and abs(jetzt_n - vorher_n)
                 >= config.NEBEN_AENDERUNG_ANTEIL * max(vorher_n, 1))

    # Ohne Betrag und ohne deutliche Aenderung gibt es nichts zu erzaehlen:
    # eine Liste von Ehrenaemtern nach Art ist kein Befund (Spahn, 25.09.2026).
    if not mit_betrag and not aenderung:
        print(f"    - {name}: kein Betrag, keine deutliche Aenderung "
              f"({vorher_n} -> {jetzt_n}) - naechste Person")
        return None

    statistik = sources.neben_statistik()
    je = statistik.get("je") or {}
    alle = config.ABGEORDNETE
    eigene = je.get(str(info["mandat"])) or {
        "n": len(meldungen), "betrag": len(mit_betrag),
        "max": sources.neben_jahreswert(mit_betrag[0]) if mit_betrag else 0,
        "summe": sum(sources.neben_jahreswert(e) for e in mit_betrag)}
    hoechster = eigene["max"]

    if len(mit_betrag) >= config.CHART_MIN_BARS:
        # Der Zeitraum steht in job_title_extra ("Einkommen im Jahr 2025").
        # Ohne ihn stuende dieselbe Organisation zweimal da, als waere es ein
        # Doppeleintrag - tatsaechlich sind es zwei Jahre.
        balken, gezaehlt = [], Counter()
        for e in mit_betrag[:config.CHART_MAX_BARS]:
            jahr = _jahr(e)
            label = _kurzname(_org(e) or _taetigkeit(e), 22 if jahr else 28)
            label = f"{label} {jahr}".strip()
            gezaehlt[label] += 1
            if gezaehlt[label] > 1:
                label = f"{label} ({gezaehlt[label]})"
            balken.append({"label": label, "wert": round(sources.neben_jahreswert(e)),
                           "anzeige": _anzeige(e), "logo": _org(e)})
        chart = {"titel": "Höchste gemeldete Beträge", "einheit": "Euro",
                 "balken": balken, "hervorheben": 0,
                 "hinweis": ("Balkenlänge aufs Jahr gerechnet (Monatsbeträge × 12). "
                             if monatlich else "")
                 + "Je Meldung, nicht zusammengerechnet"}
    elif mit_betrag:
        e = mit_betrag[0]
        schnitt = sum(z["max"] for z in je.values()) / alle if je else 0
        chart = {"titel": "Der gemeldete Betrag im Vergleich", "einheit": "Euro",
                 "balken": [{"label": _kurzname(_org(e) or _taetigkeit(e), 28),
                             "wert": round(sources.neben_jahreswert(e)),
                             # Monatsbetrag als Jahreswert, sonst wie gemeldet
                             # (ein einmaliger Betrag ist kein "/ Jahr").
                             "anzeige": (f"{_zahl(sources.neben_jahreswert(e))} € / Jahr"
                                         if sources.neben_zeitraum(e) == "im Monat"
                                         else _anzeige(e)),
                             "logo": _org(e)},
                            {"label": "Ø je Abgeordnetem", "wert": round(schnitt)}],
                 "hervorheben": 0,
                 "hinweis": jahr_hinweis + "Höchster gemeldeter Betrag je "
                            f"Abgeordnetem, alle {alle} gezählt"}
    else:
        chart = {"titel": "Verschiedene gemeldete Tätigkeiten", "einheit": "",
                 "balken": [{"label": "Wahlperiode 2021 bis 2025", "wert": vorher_n},
                            {"label": "Seit 2025", "wert": jetzt_n}],
                 "hervorheben": 1,
                 "hinweis": "Tätigkeiten und Organisationen, ohne Wiederholungen"}

    if mit_betrag:
        e = mit_betrag[0]
        quelle = _kurzname(_org(e) or _taetigkeit(e), 40)
        # "von CDU" fehlt der Artikel: Parteien im Dativ ("von der CDU").
        if quelle in _PARTEI_AKK:
            quelle = _PARTEI_AKK[quelle].replace("die ", "der ", 1).replace(
                "das ", "dem ", 1).replace("den ", "dem ", 1)
        zeitraum = sources.neben_zeitraum(e)
        hook = (f"{_zahl(float(e['income']))} Euro{' ' + zeitraum if zeitraum else ''} "
                f"von {quelle}: der höchste Betrag, den {nachname} gemeldet hat.")
    else:
        hook = (f"In der vorigen Wahlperiode {vorher_n} verschiedene Tätigkeiten, "
                f"seit 2025 bisher {jetzt_n}.")

    # Slide 3: die Person gegen den Durchschnitt aller Abgeordneten.
    fest = ("Abgeordnete müssen Tätigkeiten neben dem Mandat und Einkünfte daraus "
            "beim Bundestag melden. Eine Meldung ist kein Vorwurf.")
    if je:
        zeilen = [
            {"label": "Meldungen",
             "bisher": _komma(sum(z["n"] for z in je.values()) / alle),
             "neu": str(eigene["n"])},
        ]
        # Betraege gegen den Durchschnitt, nicht der Anteil der Meldungen
        # mit Betrag (Abstimmung 25.09.2026). Ø ueber alle Sitze, auch wer
        # nichts gemeldet hat - wie in der Zeile "Meldungen".
        if hoechster:
            summe = eigene.get("summe") or sum(sources.neben_jahreswert(e)
                                               for e in mit_betrag)
            zeilen += [
                {"label": "Höchster Betrag im Jahr",
                 "bisher": f"{_zahl(sum(z['max'] for z in je.values()) / alle)} €",
                 "neu": f"{_zahl(hoechster)} €"},
            ]
            # Bei nur einem Betrag ist die Summe derselbe Wert - zweimal
            # "11.227 €" untereinander sah wie ein Fehler aus (Linnemann).
            if eigene["betrag"] > 1:
                zeilen.append(
                    {"label": "Alle Beträge zusammen",
                     "bisher": f"{_zahl(sum(z.get('summe', 0) for z in je.values()) / alle)} €",
                     "neu": f"{_zahl(summe)} €"})
        pills = []
        if hoechster:
            platz = 1 + sum(1 for z in je.values() if z["max"] > hoechster)
            pills.append({"label": "Platz beim höchsten Betrag",
                          "wert": f"{platz} von {alle}"})
        if aenderung and mit_betrag:
            pills.append({"label": "Tätigkeiten 2021 bis 2025, seit 2025",
                          "wert": f"{vorher_n} → {jetzt_n}"})
        seite3 = {"kind": "vergleich", "titel": "Im Vergleich zum Bundestag",
                  "kopf_alt": "Ø Bundestag", "kopf_neu": nachname,
                  "zeilen": zeilen, "pills": pills,
                  "hinweis": f"Ø: Durchschnitt je Abgeordnetem, alle {alle} gezählt, "
                             f"Wahlperiode seit 2025. {jahr_hinweis}{fest}"}
    else:
        seite3 = {"kind": "context", "titel": "Was dahintersteckt",
                  "saetze": [f"Insgesamt {len(meldungen)} Meldungen in dieser "
                             f"Wahlperiode, {len(mit_betrag) or 'keine'} davon "
                             f"mit Betrag.", fest]}

    saetze = [f"{name} hat in der Wahlperiode 2025 bis 2029 {len(meldungen)} "
              f"Tätigkeiten und Einkünfte neben dem Mandat gemeldet, "
              f"{len(mit_betrag) or 'keine'} davon mit Betrag."]
    if vorher_n is not None:
        saetze.append(f"Verschiedene Tätigkeiten in der Wahlperiode 2021 bis 2025: "
                      f"{vorher_n}; seit 2025: {jetzt_n}.")
    if je:
        saetze.append(f"Im Bundestag der Wahlperiode seit 2025 sind "
                      f"{statistik['meldungen']} Meldungen erfasst, bei {alle} "
                      f"Abgeordneten.")
    saetze += [_meldung_satz(e) for e in meldungen]
    item = _item(sources._hash("neben" + name + date.today().isoformat()),
                 f"Nebentätigkeiten: {name}",
                 # Kurz: die Quelle steht im Fuss neben dem Seitenzaehler.
                 "Deutscher Bundestag via abgeordnetenwatch.de",
                 info.get("url") or config.NEBENTAETIGKEITEN_URL, saetze)
    return _karussell(
        item,
        titel=f"{name} neben dem Mandat",
        hook=hook,
        cover_frage=f"Was meldet {name} neben dem Mandat?",
        keine_figur=not mit_betrag,
        chart=chart,
        context=[],
        seiten=[seite3],
        portraet=portraet.portraet(name),
    )


# --- Auswahl -----------------------------------------------------------------

BAUER = {
    "destatis": destatis,
    "lobbyregister": lobbyregister,
    "parteispenden": parteispenden,
    "nebentaetigkeiten": nebentaetigkeiten,
}


def baue(anzahl: int, seen: set, kontext: dict) -> list:
    """Bis zu `anzahl` Karussells aus verschiedenen Kategorien, in
    zufaelliger Reihenfolge gezogen. Faellt eine Kategorie aus, rueckt die
    naechste nach."""
    reihenfolge = list(config.WEITERE_KATEGORIEN)
    random.shuffle(reihenfolge)
    fertig = []
    for kategorie in reihenfolge:
        if len(fertig) >= anzahl:
            break
        print()
        print(f"Kategorie '{kategorie}' ...")
        try:
            karussell = BAUER[kategorie](seen, kontext)
        except Exception as exc:
            print(f"  ! Kategorie {kategorie} fehlgeschlagen: {exc}")
            karussell = None
        if karussell:
            karussell["kategorie"] = kategorie
            fertig.append(karussell)
            print(f"  = {kategorie}: {karussell['slides']['titel'][:60]}")
        else:
            print(f"  = {kategorie}: nichts - naechste Kategorie")
    return fertig
