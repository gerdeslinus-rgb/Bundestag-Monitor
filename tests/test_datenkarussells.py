"""Prueft die Maschinerie der Datenkarussells, die still Falsches liefern
kann: die Belegpruefung modellgeschriebener Saetze (llm._belegt), das
Kuerzen von Organisationsnamen und die Trefferwahl bei der Logo-Suche.

Kein Netz, kein Modell. Die Faelle stammen aus der ersten Probe am
25.09.2026:

- "Campact e.V." blieb ungekuerzt, weil \\b hinter "e.V." am Namensende
  keine Wortgrenze findet - auf der Karte stand die Rechtsform.
- Die Logo-Suche nahm "Campact DZ 31934" (ohne Logo) vor "Campact".
"""
import os
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
os.chdir(WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
load_dotenv(os.path.join(WURZEL, ".env"))
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
import llm
import logos
import weitere

fehler = 0


def pruefe(name, ist, soll):
    global fehler
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {name}: {ist!r}" + ("" if ok else f" (soll {soll!r})"))


QUELLE = ("Stellungnahme (Auszug): Der vorliegende Entwurf erfüllt diesen Anspruch "
          "nicht. Ein Weiterbetrieb von fossilen Heizungsanlagen nach 2045 "
          "gefährdet die Einhaltung der Ziele des Klimaschutzgesetzes. Der "
          "Kennwert für Biogas wird von 140 g/kWh auf 80 g/kWh gesetzt.")

print("llm._belegt - Positionen gegen ihre Quelle:")
pruefe("belegter Satz",
       llm._belegt("Kritisiert, dass fossile Heizungsanlagen nach 2045 weiterlaufen "
                   "dürfen und die Ziele des Klimaschutzgesetzes gefährden.", QUELLE), True)
pruefe("falsche Zahl",
       llm._belegt("Kritisiert, dass fossile Heizungsanlagen nach 2050 weiterlaufen "
                   "dürfen.", QUELLE), False)
pruefe("Zahl aus der Quelle",
       llm._belegt("Kritisiert den neuen Kennwert für Biogas von 80 g/kWh.", QUELLE), True)
pruefe("erfundener Inhalt",
       llm._belegt("Fordert höhere Förderung für Wärmepumpen in Mietwohnungen und "
                   "Mieterstrom.", QUELLE), False)

print("\nweitere._kurzname - Rechtsform am Namensende:")
for name, soll in [("Campact e.V.", "Campact"),
                   ("Verbraucherzentrale Bundesverband e.V.", "Verbraucherzentrale Bundesverband"),
                   ("E.ON SE", "E.ON"),
                   ("Eintracht Frankfurt Fußball AG", "Eintracht Frankfurt Fußball"),
                   ("Deutsche Energie-Agentur GmbH (dena)", "Deutsche Energie-Agentur (dena)"),
                   ("AGRAVIS Raiffeisen AG", "AGRAVIS Raiffeisen"),
                   ("Bundeszahnärztekammer - Arbeitsgemeinschaft der deutschen "
                    "Zahnärztekammern e.V.", "Bundeszahnärztekammer")]:
    pruefe(name, weitere._kurzname(name, 60), soll)

print("\nlogos - Suchnamen und Trefferwahl:")
pruefe("Suchnamen Campact", logos._suchnamen("Campact e.V."), ["Campact e.V.", "Campact"])
pruefe("BSW ist kein Bahnhof",
       logos._passt("BSW", {"label": "Birmingham Snow Hill station",
                            "match": {"text": "Birmingham Snow Hill station"}}), False)
pruefe("Alias passt",
       logos._passt("Bayerische Motoren Werke Aktiengesellschaft",
                    {"label": "BMW", "match": {"text": "Bayerische Motoren Werke"}}), True)

print("\nrender - Parteilogo statt Parteiname in der Schlagzeile:")
import re
import render


def ohne_bild(html):
    return re.sub(r'<img class="partei-logo[^"]*" src="[^"]+" alt="([^"]+)">', r"[\1]", html)


for text, soll in [
        # Das Kurzwort "an" bekommt nie den Block, das Wort davor schon; "an"
        # und Logo bleiben in einer Zeile.
        ("Großspende an die Grünen",
         '<span class="hl">Großspende</span> <span class="partei-ende">an [Grüne]</span>'),
        ("Die SPD will mehr Geld für Kitas", '[SPD] will mehr Geld für <span class="hl">Kitas</span>'),
        ("Eine linke Mehrheit", 'Eine linke <span class="hl">Mehrheit</span>'),
        ("Grüner Wasserstoff kommt", 'Grüner Wasserstoff <span class="hl">kommt</span>')]:
    pruefe(text, ohne_bild(render._mit_parteilogos(text, render._block)), soll)
pruefe("Partei im Balken", render._partei_in("Übrige an die Grünen 2026"), "Grüne")
pruefe("keine Partei im Balken", render._partei_in("Durchschnitt Großspende"), None)

print(f"\n{fehler} Fehler" if fehler else "\nalle Faelle bestanden")
sys.exit(1 if fehler else 0)
