"""Umlaut-Reparatur: was repariert werden MUSS und was unangetastet bleibt."""
import os
import sys

# Projektwurzel aus dem eigenen Pfad, nicht aus dem Arbeitsverzeichnis:
# so laeuft der Test auch als "python tests/test_x.py" von ueberall.
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
load_dotenv(os.path.join(WURZEL, ".env"))
import llm

# --- Muss repariert werden (die echten Fehler aus Karussell 1) -------------
REPARIEREN = [
    ("Heizoel", "Heizöl"),
    ("fuer", "für"),
    ("Fuer", "Für"),
    ("ueber", "über"),
    ("Ueber", "Über"),
    ("hoehere", "höhere"),
    ("Zapfsaeule", "Zapfsäule"),
    ("Befuerworter", "Befürworter"),
    ("haelt", "hält"),
    ("vernachlaessigbar", "vernachlässigbar"),
    ("ausgestossenes", "ausgestoßenes"),
    ("Gasrechnung", "Gasrechnung"),
    ("Buero", "Büro"),
    ("Gebuehr", "Gebühr"),
    ("koennen", "können"),
    ("muessen", "müssen"),
    ("waere", "wäre"),
    ("laesst", "lässt"),
    ("naechste", "nächste"),
    ("zurueck", "zurück"),
    ("spaeter", "später"),
    ("Freibetraege", "Freibeträge"),
    ("Erhoehung", "Erhöhung"),
    ("heisst", "heißt"),
    ("gross", "groß"),
    ("groesser", "größer"),
    ("Grossbritannien", "Großbritannien"),
    ("Massnahme", "Maßnahme"),
    ("schliesslich", "schließlich"),
    ("ausserdem", "außerdem"),
    ("Strasse", "Straße"),
    ("Koeln", "Köln"),
    ("Oelpreis", "Ölpreis"),
    ("aeussern", "äußern"),
]

# --- Darf NIEMALS angetastet werden ----------------------------------------
UNANTASTBAR = [
    # der gefaehrlichste Fall: eu + e
    "Steuer", "Steuern", "Steuerrecht", "Steuertarif", "Steuerzahler",
    "neue", "neuen", "neuer", "neues", "Neuerung",
    "Bauer", "Bauern", "Frauen", "Dauer", "Mauer", "Trauer", "genauer",
    "Feuer", "teuer", "Abenteuer", "erneuern", "Erneuerung",
    # q + ue
    "Quelle", "Quellen", "Konsequenz", "Frequenz", "konsequent", "Sequenz",
    # -uell / -uett
    "aktuell", "eventuell", "individuell", "manuell", "virtuell",
    "intellektuell", "punktuell", "Duett", "Duell",
    # Wortende
    "Statue", "Revue", "Aloe", "Oboe",
    # Namen und echte ae/oe
    "Michael", "Israel", "Raphael", "Poet", "Poesie", "Goethe", "Boeing",
    "soeben", "Koexistenz", "Koeffizient", "Aerosol", "Aerodynamik",
    # ss, das korrekt ss bleibt
    "dass", "Masse", "Wasser", "muss", "Fluss", "Beschluss", "Kongress",
    "Prozess", "Interesse", "Adresse", "essen", "lassen", "wissen",
    # schon korrekte Umlaute duerfen nicht doppelt umgebaut werden
    "für", "über", "Heizöl", "größer", "heißt", "Zapfsäule",
    # Zahlen und Satzzeichen bleiben
    "2026", "102 Euro", "21/8065",
]

fehler = 0

print("MUSS repariert werden:")
for roh, soll in REPARIEREN:
    ist = llm.umlaute_reparieren(roh)
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {roh:>20} -> {ist:<22}"
          f"{'' if ok else '(erwartet: ' + soll + ')'}")

print("\nDARF NICHT angetastet werden:")
for wort in UNANTASTBAR:
    ist = llm.umlaute_reparieren(wort)
    ok = ist == wort
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {wort:>20} -> {ist}")

# --- Ganze Saetze aus dem echten Entwurf -----------------------------------
print("\nGanze Saetze:")
SAETZE = [
    ("Der CO2-Preis ist ein Aufschlag auf Sprit, Heizoel und Gas fuer jede "
     "Tonne ausgestossenes CO2.",
     "Der CO2-Preis ist ein Aufschlag auf Sprit, Heizöl und Gas für jede "
     "Tonne ausgestoßenes CO2."),
    ("Firmen zahlen ihn und geben ihn ueber hoehere Preise an der Zapfsaeule "
     "oder Gasrechnung weiter.",
     "Firmen zahlen ihn und geben ihn über höhere Preise an der Zapfsäule "
     "oder Gasrechnung weiter."),
    ("Die AfD haelt CO2-Emissionen aus Deutschland fuer weltweit "
     "vernachlaessigbar.",
     "Die AfD hält CO2-Emissionen aus Deutschland für weltweit "
     "vernachlässigbar."),
    # Gegenprobe: ein Satz voller Fallen, der unveraendert bleiben muss
    ("Neue Steuern auf Quellen erneuerbarer Energie sind aktuell teuer "
     "fuer Bauern, dass die Masse der Frauen das Interesse verliert.",
     "Neue Steuern auf Quellen erneuerbarer Energie sind aktuell teuer "
     "für Bauern, dass die Masse der Frauen das Interesse verliert."),
]
for roh, soll in SAETZE:
    ist = llm.umlaute_reparieren(roh)
    ok = ist == soll
    fehler += not ok
    print(f"  {'OK  ' if ok else 'FEHL'} {ist}")
    if not ok:
        print(f"       erwartet: {soll}")

# --- Struktur: rekursiv ueber Dict und Liste -------------------------------
probe = {"titel": "Heizoel wird teurer", "context": ["fuer alle", "ueber 70"],
         "chart": {"balken": [{"label": "1955", "wert": 102}]}, "skip": False}
erg = llm.umlaute_reparieren(probe)
strukt_ok = (erg["titel"] == "Heizöl wird teurer"
             and erg["context"] == ["für alle", "über 70"]
             and erg["chart"]["balken"][0]["wert"] == 102
             and erg["skip"] is False)
fehler += not strukt_ok
print(f"\nStruktur rekursiv: {'OK' if strukt_ok else 'FEHL'} -> {erg}")

print(f"\n{'ALLE BESTANDEN' if not fehler else str(fehler) + ' FEHLER'}")
sys.exit(1 if fehler else 0)
