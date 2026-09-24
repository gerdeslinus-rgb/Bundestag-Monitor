"""Ruhiger-Tag-Modus: Karussells aus Abgeordnetendaten statt aus Nachrichten.

Greift, wenn an einem Tag keine alltagsrelevante Entscheidung anliegt. Statt
den Ueberblick mit Verfahrensmeldungen zu fuellen, entsteht ein erklaerendes
Profil aus Daten, die wir ohnehin schon holen:

- Abstimmungsverhalten: welche Fraktion war bei welcher Abstimmung uneinig
  (sources.fetch_einzelstimmen)
- Nebeneinkuenfte: was Abgeordnete neben dem Mandat gemeldet haben
  (sources.fetch_nebentaetigkeiten)
- Wahlkreis-Einordnung: echtes Ergebnis und Sitzinhaber (wahlergebnisse.py)

Diese Karussells haben bewusst KEINE So-what-Slide - "was heisst das fuer
dich" laesst sich bei einem Profil nicht serioes beantworten, und eine
erfundene Betroffenheit waere genau das, was dieses Projekt vermeiden will.
"""

from collections import Counter

import config
import llm
import sources


def _karussell(item: dict, hook: str, chart: dict, context: list) -> dict:
    return {
        "item": item,
        "slides": {
            "titel": item["title"][:60],
            "hook": hook,
            "chart": chart,
            "context": context,
            "sowhat": None,          # bewusst leer, siehe Modul-Docstring
        },
        "recherche": {"fundstellen": []},
    }


ART_NEBEN = "nebentaetigkeit"
ART_EINZEL = "einzelstimme"


def _nebentaetigkeiten_karussell(eintraege: list) -> dict | None:
    """Aggregiert die gemeldeten Nebentaetigkeiten nach Fraktion bzw. Person."""
    if len(eintraege) < 5:
        return None

    # Wer hat im Zeitraum am meisten gemeldet? Das ist die eigentliche Aussage.
    namen = Counter()
    for e in eintraege:
        name = e["title"].replace("Nebentaetigkeit: ", "").split(" - ")[0]
        namen[name] += 1
    top = namen.most_common(config.CHART_MAX_BARS)
    if len(top) < config.CHART_MIN_BARS:
        return None

    gesamt = len(eintraege)
    quelle = eintraege[0]
    item = {
        **quelle,
        "title": f"Nebeneinkünfte: {gesamt} neue Meldungen",
        "text": (f"Im Beobachtungszeitraum wurden {gesamt} Nebentätigkeiten von "
                 f"Bundestagsabgeordneten neu gemeldet oder aktualisiert. "
                 + " ".join(f"{n}: {c} Meldungen." for n, c in top)),
    }
    return _karussell(
        item,
        hook=(f"{gesamt} Nebentätigkeiten haben Bundestagsabgeordnete zuletzt "
              f"gemeldet: hier ist, wer wie oft gemeldet hat."),
        # Absteigend sortiert: der erste Balken ist die Aussage, nicht der letzte.
        chart={"titel": "Gemeldete Nebentätigkeiten", "einheit": "Meldungen",
               "balken": [{"label": n, "wert": c} for n, c in top],
               "hervorheben": 0,
               "hinweis": "Quelle: abgeordnetenwatch.de, Meldungen laut Verhaltensregeln."},
        context=[
            "Abgeordnete müssen Tätigkeiten neben dem Mandat anzeigen, wenn sie "
            "bestimmte Betragsgrenzen überschreiten.",
            f"Insgesamt kamen {gesamt} Meldungen zusammen, das sind Neueinträge "
            "und Aktualisierungen, keine Bewertung.",
            "Eine Meldung ist kein Vorwurf: die Pflicht zur Anzeige dient der "
            "Transparenz, nicht der Schuldzuweisung.",
        ],
    )


def _abweichler_karussell(eintraege: list) -> dict | None:
    """Fraktionen, die bei einer namentlichen Abstimmung uneinig waren."""
    if not eintraege:
        return None

    quelle = eintraege[0]
    # Aus dem generierten Text die Stimmenaufteilung zurueckholen waere
    # fragil - stattdessen zeigen wir, wie viele Fraktionen uneinig waren.
    nach_abstimmung = Counter()
    for e in eintraege:
        nach_abstimmung[e["title"].split(" uneinig bei: ")[-1]] += 1
    top = nach_abstimmung.most_common(config.CHART_MAX_BARS)
    if len(top) < config.CHART_MIN_BARS:
        return None

    item = {
        **quelle,
        "title": "Uneinige Fraktionen bei namentlichen Abstimmungen",
        "text": (" ".join(f"Bei der Abstimmung \"{t}\" stimmten {c} Fraktionen "
                          f"nicht einheitlich." for t, c in top)),
    }
    return _karussell(
        item,
        hook=("Fraktionszwang gibt es formal nicht: hier sind die Abstimmungen, "
              "bei denen Fraktionen zuletzt auseinanderfielen."),
        # Absteigend sortiert: der erste Balken ist die Aussage, nicht der letzte.
        chart={"titel": "Uneinige Fraktionen je Abstimmung", "einheit": "Fraktionen",
               "balken": [{"label": t[:30], "wert": c} for t, c in top],
               "hervorheben": 0,
               "hinweis": "Quelle: namentliche Abstimmungen, abgeordnetenwatch.de."},
        context=[
            "Bei namentlichen Abstimmungen wird festgehalten, wie jede und jeder "
            "Abgeordnete gestimmt hat.",
            "Weicht ein Teil einer Fraktion von der Mehrheit der eigenen Leute ab, "
            "zeigt das internen Dissens: rechtlich ist jede und jeder Abgeordnete "
            "nur dem eigenen Gewissen verpflichtet.",
            "Die Zahlen sind das amtliche Ergebnis, keine Wertung der Motive.",
        ],
    )


def build(items: list, anzahl: int) -> list:
    """Liefert bis zu `anzahl` Profil-Karussells. Keine Modell-Belegpruefung
    noetig: die Texte werden aus den Daten selbst erzeugt, nicht vom Modell
    erfunden. Der Faktencheck laeuft trotzdem."""
    # Die Items kommen jetzt von der aufrufenden Stufe - frueher hat jeder
    # Bauer seine Quelle selbst noch einmal geholt, obwohl collect() sie
    # kurz zuvor schon gelesen hatte.
    # Jeder Bauer bekommt AUSSCHLIESSLICH Items seiner eigenen Art. Ohne
    # diese Trennung baut _abweichler_karussell() klaglos ein Karussell
    # "Uneinige Fraktionen bei namentlichen Abstimmungen" aus Nebentaetig-
    # keiten - die Titel werden dann als Abstimmungsnamen gelesen und die
    # Meldungen je Person als Zahl uneiniger Fraktionen ausgegeben. Das ist
    # frei erfunden, sieht aber vollstaendig aus, und keine der beiden
    # Pruefungen faengt es: der Quelltext dieser Karussells wird aus
    # denselben Daten erzeugt und ist deshalb immer "widerspruchsfrei".
    kandidaten = []
    for art, bauer in ((ART_EINZEL, _abweichler_karussell),
                       (ART_NEBEN, _nebentaetigkeiten_karussell)):
        passend = [i for i in items if i.get("art") == art]
        if not passend:
            continue
        try:
            karussell = bauer(passend)
        except Exception as exc:
            print(f"  ! Profil-Karussell fehlgeschlagen: {exc}")
            continue
        # judge_slides liefert (bestanden, einwand). Das Ergebnis direkt als
        # Wahrheitswert zu nehmen waere hier fatal: ein Tupel ist immer wahr,
        # und der Faktencheck haette ohne jede Fehlermeldung nichts mehr
        # geprueft. Profil-Karussells bauen ihre Slides aus Daten, nicht aus
        # einem Modelltext - einen zweiten Versuch gibt es hier deshalb
        # nicht, der Einwand wird nur verworfen.
        if karussell:
            bestanden, _ = llm.judge_slides(karussell["slides"],
                                            karussell["item"],
                                            karussell["recherche"])
            if bestanden:
                kandidaten.append(karussell)
        if len(kandidaten) >= anzahl:
            break

    print(f"  = {len(kandidaten)} Profil-Karussell(s)")
    return kandidaten[:anzahl]
