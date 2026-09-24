"""Reichert ein Thema um Hintergrund an - per Websuche und eigenen Quellen.

Arbeitsteilung mit llm.py (wichtig fuer das Verstaendnis der Pruefung):

- Die harten Fakten der Meldung (Beschluss, Zahlen, Abstimmungsergebnis)
  stammen aus unseren amtlichen Quellen und werden in llm.verify_slides()
  woertlich gegen den Quelltext geprueft. Daran aendert die Recherche nichts.
- Die Recherche hier liefert ERKLAERENDEN Hintergrund ("Was ist ein
  Freibetrag?", "Seit wann gilt die Regel?"). Fuer solche Erklaerungen gibt
  es keinen woertlichen Beleg-Satz und deshalb auch keine Beleg-Pruefung -
  sie werden stattdessen vom Faktencheck in llm.judge_slides() beurteilt.
  Jede genannte Zahl bekommt aber ihre Fundstelle mit, damit du vor der
  Freigabe nachsehen kannst.

Die Websuche findet nur Fundstellen; die Suchtreffer selbst sind
verschluesselt (encrypted_content) und lassen sich nicht als Belegtext
weiterverwenden - deshalb werden Titel und URL der Treffer gesammelt.
"""

import math
import os
from datetime import datetime

from anthropic import Anthropic

import config
from llm import _json_from   # gleiche robuste JSON-Extraktion wie im Rest

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

RESEARCH_PROMPT = """Du recherchierst Hintergrund fuer eine Erklaer-Grafik zur
deutschen Politik. Die Meldung selbst steht schon fest - du lieferst NUR das,
was ein Laie zusaetzlich wissen muss, um sie zu verstehen.

ZUERST den Quelltext lesen, DANN erst suchen. Der Quelltext unten ist bei
Bundestagsvorlagen ein Ausschussbericht und enthaelt in aller Regel schon
Problem, Loesung, Kosten und Erfuellungsaufwand. Suche ausschliesslich das,
was dort fehlt. Steht alles Noetige im Quelltext, such gar nicht - eine
Antwort ohne einzige Suche ist ein gutes Ergebnis, kein schlechtes.

Was gebraucht wird:
1. Worum geht es sachlich? Erklaere den Fachbegriff so, dass ihn jemand ohne
   Vorwissen versteht (z. B. "Was ist ein Freibetrag?"). Steht die Erklaerung
   sinngemaess im Quelltext, nimm sie von dort.
2. Was galt VORHER? Vergleichszahlen aus frueheren Jahren, aus dem
   Koalitionsvertrag oder aus Forderungen im Wahlkampf. Das ist der haeufigste
   Grund, ueberhaupt zu suchen: fuer ein Vergleichsdiagramm braucht es einen
   frueheren Wert, und der steht selten in der Vorlage selbst.
3. Wen betrifft das konkret im Alltag - und wie stark?
4. Nennt der Quelltext einen Geldbetrag, der seit vielen Jahren unveraendert
   gilt (etwa "102 Euro seit 1955")? Dann trag Betrag und Jahr ein. Das
   kostet keine Suche - beides steht im Quelltext.

Antworte NUR mit JSON, kein Text davor oder danach:
{{"erklaerung": "2-4 Saetze, was der Fachbegriff bedeutet",
  "vorher_nachher": [{{"label": "kurzes Label", "wert": 1200, "einheit": "Euro",
                       "quelle_url": "https://..."}}],
  "kaufkraft": {{"betrag": 102, "jahr": 1955, "einheit": "Euro"}},
  "betroffene": "Wen es betrifft, in einem Satz",
  "alltagswirkung": "Wie es sich konkret auswirkt, 1-2 Saetze"}}

Regeln:
- "vorher_nachher" sind die Zahlen fuers Diagramm, {min_bars} bis {max_bars} Stueck,
  in sinnvoller zeitlicher oder logischer Reihenfolge. "wert" ist eine reine
  Zahl ohne Tausenderpunkt, ohne Waehrungszeichen.
- Zu JEDER Zahl gehoert die quelle_url, aus der sie stammt.
- "kaufkraft": NICHT suchen und NICHT umrechnen. Trag nur ein, was im
  Quelltext steht: den Betrag und das Jahr, seit dem er unveraendert gilt.
  Den heutigen Gegenwert rechnet der Code selbst. Gibt es keinen solchen
  Betrag, lass "kaufkraft" weg.
- Erfinde nichts. Wenn du eine Vergleichszahl nicht findest, lass sie weg.
- Wenn du gar nichts Brauchbares findest: {{"erklaerung": "", "vorher_nachher": [],
  "betroffene": "", "alltagswirkung": ""}}

Thema:
Titel: {title}
Quelle: {source}
Quelltext: {text}"""


def _text_block(resp) -> str:
    """Letzter Textblock - bei Websuche schreibt das Modell oft erst Zwischen-
    kommentare und liefert das JSON zum Schluss."""
    texte = [b.text for b in resp.content if b.type == "text"]
    if not texte:
        raise ValueError("keine Textantwort im Modell-Ergebnis")
    return texte[-1]


def _fundstellen(resp) -> list:
    """Sammelt Titel und URL der Suchtreffer als Fundstellen-Liste.

    Bei einem Fehler ist content KEINE Liste, sondern ein Objekt mit
    error_code - die Websuche wirft keine Exception, sondern liefert den
    Fehler im Antwortblock. Deshalb vor dem Iterieren auf Liste pruefen.
    """
    treffer = []
    for block in resp.content:
        if block.type != "web_search_tool_result":
            continue
        if not isinstance(block.content, list):
            print(f"    ! Websuche-Fehler: {getattr(block.content, 'error_code', block.content)}")
            continue
        for result in block.content:
            url = getattr(result, "url", "")
            if url:
                treffer.append({"titel": getattr(result, "title", ""), "url": url})
    return treffer


ABSCHLUSS = """Das Suchbudget ist aufgebraucht - weitere Suchen sind nicht
moeglich. Antworte jetzt mit dem JSON im oben beschriebenen Format, und zwar
ausschliesslich mit dem, was du bereits gefunden hast. Erfinde nichts: was du
nicht belegen kannst, laesst du weg bzw. leer."""


def _budget_erschoepft(resp) -> bool:
    """True, sobald die Websuche max_uses_exceeded meldet.

    Danach ist jeder weitere Such-Turn verloren: das Modell fragt weiter an,
    bekommt denselben Fehler zurueck und der volle Kontext wird jedes Mal neu
    bezahlt. Einmal gesehen heisst: aufhoeren zu suchen.
    """
    for block in resp.content:
        if block.type != "web_search_tool_result":
            continue
        if isinstance(block.content, list):
            continue
        if getattr(block.content, "error_code", "") == "max_uses_exceeded":
            return True
    return False


def enrich(item: dict) -> dict:
    """Recherchiert Hintergrund zu einem Thema. Fehler sind nicht toedlich -
    dann gibt es eben ein Karussell ohne Zusatzkontext."""
    leer = {"erklaerung": "", "vorher_nachher": [], "kaufkraft": {},
            "betroffene": "", "alltagswirkung": "", "fundstellen": []}
    if not config.RESEARCH_ENABLED:
        return leer

    prompt = RESEARCH_PROMPT.format(
        title=item["title"], source=item["source"],
        text=item["text"][:config.RESEARCH_QUELLTEXT_CHARS],
        min_bars=config.CHART_MIN_BARS, max_bars=config.CHART_MAX_BARS)

    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search",
              "max_uses": config.RESEARCH_MAX_SEARCHES,
              "allowed_domains": config.RESEARCH_DOMAINS}]

    def _such_turn(msgs):
        """Ein Such-Durchgang, gestreamt.

        Streaming ist hier nicht Kosmetik: Suchturns dauern Minuten, und ein
        normaler Aufruf mit diesem max_tokens laeuft in den 10-Minuten-Timeout
        des SDK - der dann zweimal stillschweigend wiederholt wird. Genau so
        stand ein Lauf 17 Minuten, ohne dass etwas passierte.
        """
        with client.messages.stream(model=config.MODEL_RESEARCH, max_tokens=12000,
                                    output_config={"effort": config.EFFORT_RESEARCH},
                                    tools=tools, messages=msgs) as stream:
            return stream.get_final_message()

    try:
        resp = _such_turn(messages)
        # Bei langen Such-Turns pausiert das Modell - Antwort zurueckgeben
        # und fortsetzen lassen, sonst fehlt das Ergebnis.
        guard = 0
        while resp.stop_reason == "pause_turn" and guard < 3:
            messages.append({"role": "assistant", "content": resp.content})
            # Ist das Suchbudget weg, bringt Weitersuchen nichts mehr. Statt
            # die Recherche wegzuwerfen, das Modell einmal ausdruecklich zum
            # Abschluss auffordern - das bisher Gefundene ist ja brauchbar.
            if _budget_erschoepft(resp):
                print("    ! Suchbudget aufgebraucht - Abschluss angefordert")
                messages.append({"role": "user", "content": ABSCHLUSS})
                resp = _such_turn(messages)
                break
            resp = _such_turn(messages)
            guard += 1
    except Exception as exc:
        print(f"    ! Recherche fehlgeschlagen: {exc}")
        return leer

    fundstellen = _fundstellen(resp)
    try:
        data = _json_from(_text_block(resp))
    except Exception as exc:
        print(f"    ! Rechercheergebnis unlesbar: {exc}")
        return {**leer, "fundstellen": fundstellen}

    balken = []
    for b in data.get("vorher_nachher", []) or []:
        try:
            wert = float(b.get("wert"))
        except (TypeError, ValueError):
            continue
        # Nur eine echte Adresse zaehlt als Fundstelle. Das Modell traegt
        # hier auch schon mal "Drucksache 21/6984" ein - als Herkunftsangabe
        # richtig, als Beleg wertlos: llm.recherche_zahlen schaltet jede Zahl
        # frei, deren quelle_url irgendwie befuellt ist, und damit waere ein
        # beliebiger String ein Beleg. Der Balken bleibt trotzdem stehen -
        # steht seine Zahl im Quelltext, ist sie ueber diesen Weg belegt.
        url = str(b.get("quelle_url", ""))
        if not url.startswith("http"):
            if url:
                print(f"    ! Fundstelle ist keine Adresse: {url[:40]!r} "
                      f"({b.get('label', '')[:30]})")
            url = ""
        balken.append({"label": str(b.get("label", ""))[:40],
                       "wert": wert,
                       "einheit": str(b.get("einheit", "")),
                       "quelle_url": url})

    return {
        "erklaerung": str(data.get("erklaerung", "")),
        "vorher_nachher": balken[:config.CHART_MAX_BARS],
        "kaufkraft": _kaufkraft(data.get("kaufkraft"), item.get("text", "")),
        "betroffene": str(data.get("betroffene", "")),
        "alltagswirkung": str(data.get("alltagswirkung", "")),
        "fundstellen": fundstellen,
    }


def _kaufkraft(roh, quelltext: str) -> dict:
    """Was ein historischer Betrag heute ungefaehr wert waere.

    Gerechnet, nicht recherchiert - und das ist eine bewusste Entscheidung.
    Der Versuch, den Gegenwert zu suchen, ist einmal gelaufen: die Recherche
    hat 40 Fundstellen durchgesehen, die Bundesbank-Tabelle sogar gefunden
    und trotzdem keinen verwertbaren Wert geliefert - dafuer aber das
    Suchbudget aufgebraucht, sodass fuer dasselbe Thema gar keine
    Vergleichszahlen mehr uebrig blieben. Eine offengelegte Annahme ist
    hier mehr wert als eine Suche, die meistens scheitert.

    Deshalb: KAUFKRAFT_INFLATION pro Jahr, und die Annahme steht auf der
    Karte. Der Wert ist eine Groessenordnung, keine amtliche Zahl - genau so
    muss er auch beschriftet sein (siehe COMPOSE_PROMPT).

    Betrag und Jahr muessen im Quelltext stehen. Ohne diese Bedingung waere
    die Rechnung dieselbe Waschanlage, gegen die llm.abgeleitete_zahlen
    seine Operandenpruefung hat: eine erfundene Ausgangszahl ergaebe sonst
    einen sauber gerechneten und trotzdem falschen Balken.
    """
    if not isinstance(roh, dict):
        return {}
    try:
        betrag = float(roh["betrag"])
        jahr = int(roh["jahr"])
    except (KeyError, TypeError, ValueError):
        return {}

    heute = datetime.now().year
    # Unter zehn Jahren Abstand lohnt der Balken nicht, und ein Jahr aus der
    # Zukunft oder vor der Waehrungsreform ist ein Lesefehler des Modells.
    if not 1900 <= jahr <= heute - 10 or betrag <= 0:
        return {}

    if not _steht_im_text(betrag, quelltext) or str(jahr) not in quelltext:
        print(f"    ! Kaufkraft verworfen: {betrag:g}/{jahr} steht nicht im Quelltext")
        return {}

    jahre = heute - jahr
    gegenwert = betrag * (1 + config.KAUFKRAFT_INFLATION) ** jahre
    return {"betrag": betrag, "jahr": jahr, "jahre": jahre,
            "heute_etwa": _rund(gegenwert),
            "einheit": str(roh.get("einheit", "Euro")),
            "annahme": f"{config.KAUFKRAFT_INFLATION * 100:g} % Inflation pro Jahr"}


def _rund(wert: float) -> float:
    """Auf zwei geltende Ziffern. 416,3 wird 420.

    Eine gerechnete Groessenordnung mit Nachkommastelle auf der Karte taeuscht
    eine Genauigkeit vor, die die Annahme nicht hergibt.
    """
    if wert <= 0:
        return 0.0
    stufe = 10 ** (math.floor(math.log10(wert)) - 1)
    return float(round(wert / stufe) * stufe)


def _steht_im_text(zahl: float, text: str) -> bool:
    """Kommt die Zahl in einer der ueblichen Schreibweisen im Quelltext vor?"""
    ganz = int(zahl)
    formen = {str(ganz), f"{ganz:,}".replace(",", ".")}
    if zahl != ganz:
        formen |= {f"{zahl:g}", f"{zahl:g}".replace(".", ",")}
    return any(f in text for f in formen)
