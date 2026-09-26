"""Sitzbogen fuer namentliche Abstimmungen - 630 Punkte, einer je Mandat.

Das Standarddiagramm fuer eine Abstimmung im ganzen Haus (Design-System §4).
Ein gefuellter Punkt ist ein Ja in der Farbe der eigenen Fraktion, ein hohler
Punkt derselben Farbe ein Nein oder eine Enthaltung. So sieht man den Dissens
INNERHALB einer Fraktion, statt nur die Fraktionslinie.

Zwei Dinge, die hier bewusst so und nicht anders geloest sind:

* Die Geometrie wird aus den Radien abgeleitet, nie hartkodiert. Eine feste
  viewBox schneidet die Randsitze ab, sobald sich Punktgroesse oder Reihenzahl
  aendert - und das faellt erst im gerenderten PNG auf.
* Gezeichnet wird das Roster (config.BUNDESTAG_SITZE), nicht die Zahl der
  abgegebenen Stimmen. Der Bogen zeigt das Haus; wer gefehlt hat, bleibt ein
  hohler Punkt. Die amtliche Ja-Zahl in der Mitte kommt dagegen unveraendert
  aus dem Protokoll.

Dieses Modul rechnet nur. Es kennt weder Jinja noch Playwright und laesst sich
deshalb direkt pruefen:

    python -c "import sitzbogen, json; print(json.dumps(sitzbogen.pruefen()))"
"""

import math

import config

# Canvas 1080 breit, Slide-Padding 76 links und rechts (Design-System §5).
BREITE = 1080 - 2 * 76

DOT = 7.4      # Punktradius
PAD = 6.0      # Luft zwischen Punktrand und Bildrand
RI = 260.0     # Innenradius: muss die Mittelbeschriftung freilassen
ABSTAND = 2 * DOT + 1.6      # Mindestabstand zweier Punkte auf einer Reihe
REIHENLUFT = 2 * DOT + 2.0   # Mindestabstand zweier Reihen


def _geometrie() -> dict:
    """Abgeleitete Masse des Bogens. Aendert sich DOT, aendert sich alles."""
    ro = BREITE / 2 - DOT - PAD
    w = 2 * (ro + DOT + PAD)
    cy = ro + DOT + PAD
    return {"ro": ro, "w": w, "cx": w / 2, "cy": cy, "h": cy + DOT + PAD}


def _reihen(sitze: int, ro: float) -> list:
    """Radien und Sitzzahl je Reihe.

    Gesucht ist die kleinste Reihenzahl, in die alle Sitze passen: wenige,
    gut gefuellte Reihen lesen sich als Bogen, viele halbleere als Raster.
    """
    for anzahl in range(4, 15):
        schritt = (ro - RI) / (anzahl - 1)
        if schritt < REIHENLUFT:
            break                      # enger duerfen die Reihen nicht stehen
        radien = [RI + i * schritt for i in range(anzahl)]
        kapazitaet = [int(math.pi * r / ABSTAND) for r in radien]
        if sum(kapazitaet) < sitze:
            continue

        # Proportional zum Radius verteilen: die aeusseren Reihen sind laenger
        # und tragen deshalb mehr Punkte.
        gesamt_radius = sum(radien)
        verteilung = [max(1, round(sitze * r / gesamt_radius)) for r in radien]
        verteilung = [min(v, k) for v, k in zip(verteilung, kapazitaet)]

        # Rundungsrest von aussen nach innen ausgleichen, ohne eine Reihe ueber
        # ihre Kapazitaet zu fuellen.
        rest = sitze - sum(verteilung)
        for i in sorted(range(anzahl), key=lambda i: -radien[i]):
            if rest == 0:
                break
            schub = max(-verteilung[i] + 1, min(rest, kapazitaet[i] - verteilung[i]))
            verteilung[i] += schub
            rest -= schub
        if rest == 0:
            return list(zip(radien, verteilung))

    raise ValueError(f"{sitze} Sitze passen in keinen Bogen mit DOT={DOT}")


def _punkte(sitze: int) -> list:
    """Alle Sitzpositionen, von links nach rechts sortiert.

    Jede Reihe spannt denselben Halbkreis, deshalb liegen die Fraktionen nach
    dem Sortieren nach Winkel als geschlossene Keile nebeneinander - genau wie
    im echten Plenum.
    """
    g = _geometrie()
    roh = []
    for radius, anzahl in _reihen(sitze, g["ro"]):
        for i in range(anzahl):
            # pi (links) bis 0 (rechts), Punkte mittig in ihrem Segment.
            winkel = math.pi - math.pi * (i + 0.5) / anzahl
            roh.append((winkel, radius))

    roh.sort(key=lambda p: -p[0])
    return [{"x": round(g["cx"] + r * math.cos(w), 1),
             "y": round(g["cy"] - r * math.sin(w), 1)} for w, r in roh]


def bogen(ergebnis: dict) -> dict | None:
    """Baut den Sitzbogen aus einer namentlichen Abstimmung.

    `ergebnis` ist die Struktur aus abstimmung.aus_protokoll(). None, wenn die
    Daten fehlen - dann faellt render.py auf das Balkendiagramm zurueck.
    """
    if not ergebnis or not ergebnis.get("fraktionen"):
        return None

    # Protokollschreibweise auf die Roster-Schluessel bringen. Fraktionslose
    # haben im Roster keine Sitze und werden deshalb nicht gezeichnet.
    ja_je_fraktion = {}
    for name, stimmen in ergebnis["fraktionen"].items():
        key = config.FRAKTION_ALIAS.get(name.strip())
        if key:
            ja_je_fraktion[key] = ja_je_fraktion.get(key, 0) + int(stimmen.get("ja", 0))

    sitze_gesamt = sum(f["sitze"] for f in config.BUNDESTAG_SITZE)
    g = _geometrie()
    punkte = _punkte(sitze_gesamt)

    gezeichnet, legende, gelaufen = [], [], 0
    for fraktion in config.BUNDESTAG_SITZE:
        ja = min(ja_je_fraktion.get(fraktion["key"], 0), fraktion["sitze"])
        for i in range(fraktion["sitze"]):
            p = punkte[gelaufen + i]
            gezeichnet.append({**p, "farbe": fraktion["farbe"], "hohl": i >= ja})
        gelaufen += fraktion["sitze"]
        legende.append({"name": fraktion["name"], "farbe": fraktion["farbe"],
                        "ja": ja, "sitze": fraktion["sitze"],
                        "position": (ergebnis.get("positionen") or {}).get(fraktion["key"])})

    gesamt = int(ergebnis.get("gesamt") or 0)
    return {
        "viewbox": f"0 0 {round(g['w'], 1)} {round(g['h'], 1)}",
        "w": round(g["w"], 1), "h": round(g["h"], 1),
        "cx": round(g["cx"], 1), "cy": round(g["cy"], 1),
        "dot": DOT,
        "punkte": gezeichnet,
        "ja": int(ergebnis.get("ja") or 0),
        # Mehrheit der abgegebenen Stimmen. Steht genau einmal auf der Slide,
        # naemlich in der Mitte des Bogens - nie noch einmal im Hinweis.
        "benoetigt": gesamt // 2 + 1,
        "angenommen": bool(ergebnis.get("angenommen")),
        # "handzeichen": gefuellt ist dann die ganze Fraktion, die dafuer war -
        # eine Position, keine Stimmenzahl. Der Bogen zeigt dann keine Zahl
        # (stimmen.py, Entscheidung 26.09.2026).
        "art": ergebnis.get("art") or "namentlich",
        "legende": legende,
    }


def pruefen() -> dict:
    """Selbstpruefung der Geometrie: passt der Bogen in seine viewBox?

    Genau der Fehler, den das Design-System anspricht - eine zu kleine Flaeche
    beschneidet die Randsitze, und zwar lautlos.
    """
    g = _geometrie()
    punkte = _punkte(sum(f["sitze"] for f in config.BUNDESTAG_SITZE))
    xs = [p["x"] for p in punkte]
    ys = [p["y"] for p in punkte]
    innen = min(math.dist((p["x"], p["y"]), (g["cx"], g["cy"])) for p in punkte)
    return {
        "punkte": len(punkte),
        "reihen": len(_reihen(sum(f["sitze"] for f in config.BUNDESTAG_SITZE), g["ro"])),
        "x_min": round(min(xs) - DOT, 1), "x_max": round(max(xs) + DOT, 1),
        "y_min": round(min(ys) - DOT, 1), "y_max": round(max(ys) + DOT, 1),
        "w": round(g["w"], 1), "h": round(g["h"], 1),
        "innenradius": round(innen, 1),
        "passt": (min(xs) - DOT >= -0.1 and max(xs) + DOT <= g["w"] + 0.1
                  and min(ys) - DOT >= -0.1 and max(ys) + DOT <= g["h"] + 0.1
                  and innen >= RI - 0.1),
    }
