"""Die englische Fassung fuer das zweite Instagram-Konto.

Laeuft NACH dem deutschen Post, ohne eigene Freigabe (Entscheidung
28.09.2026): die deutsche Freigabe deckt den Inhalt, die englische Fassung
ist dieselbe Geschichte, uebersetzt. Deshalb auch keine zweite Faktenpruefung
und kein Uebersetzungshinweis auf den Karten.

Geprueft wird nur eines: ob die englischen Karten sauber aussehen
(render._UEBERLAUF_JS - nichts laeuft aus der Karte). Findet die Pruefung
etwas, geht die englische Fassung nicht online, und Telegram sagt warum. Der
deutsche Post ist davon nie betroffen: er ist zu diesem Zeitpunkt schon
online.

Braucht IG_EN_USER_ID und IG_EN_ACCESS_TOKEN (zweites Konto, SETUP.md). Ohne
die beiden passiert nichts - dann gibt es eben nur das deutsche Konto.
"""

import copy
import json
import os

import ablage
import config
import instagram
import llm
import notify
import render
import sprache

# Steuerfelder und Beleg-Material: werden nicht angezeigt oder duerfen sich
# nicht aendern. Alles andere, was Text ist, wird uebersetzt.
_NICHT_UEBERSETZEN = {"muster", "symbol", "kind", "wertung", "logo", "stimme",
                      "art", "portraet", "logo_credits", "fakten_evidence",
                      "beispielwerte", "abgeleitete_zahlen", "hervorheben",
                      "cover_figur", "keine_figur", "sprache"}

PROMPT = """Translate the German texts below for an English-language Instagram
account that explains German politics to an international audience. The
German version is already published; this is the same content in English.

Rules:
- Return EXACTLY one English string per input string, in the same order.
- Same meaning, no additions, no omissions, no opinions. Keep it short:
  these texts sit on fixed-size slides.
- Numbers stay the same values, written the English way: 82,6 -> 82.6,
  1.200 -> 1,200, 14,04 Cent -> 14.04 cents, "11.227 €" -> "€11,227".
  Dates as "25 Sep 2026" when they stand alone.
- Headlines (strings marked [HEADLINE]) stay headline-short. No glosses in
  headlines, labels or chart labels (strings marked [LABEL]).
- In body text, give terms a foreign reader will not know a short gloss the
  FIRST time they appear, using this glossary where it applies:
{glossar}
- Party names: keep CDU/CSU, SPD, AfD as they are; Grüne -> Greens,
  Die Linke / Linke -> The Left.
- The string marked [KEYWORD] is the key term; translate it exactly as it
  appears in your translation of the string marked [TITLE].
- Use "you" for the reader (German "du").

Answer ONLY with JSON: {{"texte": ["...", "..."]}}

Input:
{eingabe}"""


def _sammeln(wert, pfad=()):
    """Alle Textstellen als (Pfad, Text)."""
    if isinstance(wert, str):
        if wert.strip():
            yield pfad, wert
    elif isinstance(wert, dict):
        for k, v in wert.items():
            if k not in _NICHT_UEBERSETZEN:
                yield from _sammeln(v, pfad + (k,))
    elif isinstance(wert, list):
        for i, v in enumerate(wert):
            yield from _sammeln(v, pfad + (i,))


def _setzen(ziel, pfad, text):
    for schritt in pfad[:-1]:
        ziel = ziel[schritt]
    ziel[pfad[-1]] = text


def _markierung(pfad) -> str:
    letzter = pfad[-1] if pfad else ""
    if pfad[:2] == ("slides", "titel"):
        return "[TITLE] [HEADLINE] "
    if pfad[:2] == ("slides", "schluesselwort"):
        return "[KEYWORD] "
    if letzter in ("titel", "hook", "cover_frage", "context_titel", "payoff"):
        return "[HEADLINE] "
    if letzter in ("label", "einheit", "anzeige", "kopf_neu", "kopf_alt", "wert",
                   "an", "rest", "nachtitel", "name", "stelle", "source"):
        return "[LABEL] "
    return ""


def uebersetze(carousel: dict) -> dict:
    """Das Karussell mit englischen Texten. Wirft, wenn die Antwort nicht passt."""
    en = copy.deepcopy(carousel)
    # Was auf den Karten steht: die Slides, die Quelle im Fuss und die Stelle,
    # die "Was fruehere Faelle zeigen" im Fuss nennt.
    wurzel = {"slides": en["slides"], "item": {"source": en["item"]["source"]},
              "recherche": {"fruehere_faelle": [
                  {"stelle": f.get("stelle", "")}
                  for f in (en.get("recherche") or {}).get("fruehere_faelle", [])]}}
    stellen = list(_sammeln(wurzel))
    eingabe = "\n".join(f"{i}. {_markierung(p)}{json.dumps(t, ensure_ascii=False)}"
                        for i, (p, t) in enumerate(stellen))
    glossar = "\n".join(f"    {de} -> {en_}" for de, en_ in sprache.GLOSSAR.items())

    resp = llm.client.messages.create(
        model=config.MODEL_DRAFT, max_tokens=16000,
        messages=[{"role": "user", "content": PROMPT.format(
            glossar=glossar, eingabe=eingabe)}])
    texte = llm._json_from(llm._text_block(resp)).get("texte", [])
    if len(texte) != len(stellen):
        raise ValueError(f"Uebersetzung: {len(texte)} statt {len(stellen)} Texte")

    for (pfad, _), text in zip(stellen, texte):
        _setzen(wurzel, pfad, str(text))
    en["item"]["source"] = wurzel["item"]["source"]
    for f, u in zip((en.get("recherche") or {}).get("fruehere_faelle", []),
                    wurzel["recherche"]["fruehere_faelle"]):
        f["stelle"] = u["stelle"]

    # Das Hauptwort muss in der Schlagzeile stehen, sonst sucht der Renderer
    # es vergeblich - dann lieber die uebliche Hervorhebung.
    s = en["slides"]
    if s.get("schluesselwort") and s["schluesselwort"].lower() not in s.get("titel", "").lower():
        s.pop("schluesselwort")
    return en


def eingerichtet() -> bool:
    return bool(os.environ.get("IG_EN_USER_ID") and os.environ.get("IG_EN_ACCESS_TOKEN"))


def posten(carousel: dict, nummer: int) -> None:
    """Uebersetzen, rendern, pruefen, posten. Scheitert still fuer den
    deutschen Post: der ist schon online, hier geht es nur ums zweite Konto."""
    if not eingerichtet():
        print("  - Englisches Konto nicht eingerichtet (IG_EN_USER_ID, "
              "IG_EN_ACCESS_TOKEN) - nur Deutsch")
        return
    print("Englische Fassung ...")
    en = uebersetze(carousel)
    # Dasselbe Cover, dasselbe Foto: es ist dieselbe Geschichte.
    en["cover"] = carousel.get("cover")
    en["bild_fest"] = carousel.get("bild")
    paths = render.build_carousel(en, nummer, [], sprache_="en")
    if en.get("layout_probleme"):
        notify.send_text("Englische Fassung NICHT gepostet - die Karten sehen "
                         "nicht sauber aus:\n" + "\n".join(en["layout_probleme"][:5]))
        return
    caption = render.build_caption(en)
    urls = ablage.ablegen(paths, nummer, suffix="_en")
    ablage.warte_bis_erreichbar(urls[0])
    instagram.veroeffentliche(urls, caption, konto="EN")
    notify.send_carousel(paths, caption, en, f"{nummer} (EN)")
    notify.send_text("Englische Fassung ist online.")
    print("  = Englische Fassung online")
