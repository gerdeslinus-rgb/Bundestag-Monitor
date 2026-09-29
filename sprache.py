"""Feste Texte der Karten je Sprache - alles, was nicht vom Modell kommt.

Deutsch ist die Fassung, die du freigibst. Englisch ist die Uebersetzung fuer
das zweite Konto (englisch.py): die Modelltexte uebersetzt ein Modell, die
festen Saetze stehen hier, damit sie in jedem Karussell gleich lauten.

Parteinamen: Die Logos haengen an den deutschen Namen (render.PARTEIEN).
"parteien" gibt nur den ANGEZEIGTEN Namen in der Sitzbogen-Legende vor.
"""

import config

TEXTE = {
    "de": {
        "lang": "de",
        "abgestimmt": "So hat der Bundestag abgestimmt",
        "fruehere": "Was frühere Fälle zeigen",
        "fuer_dich": "Was heißt das für dich?",
        "worum": "Worum es geht",
        "warum": "Warum überhaupt ändern?",
        "schritte": "Nur in diesen Fällen musst du selbst ran",
        "auswertung": "Auswertung: ",
        "wahlperiode": "{n}. Wahlperiode",
        "bisher": "bisher",
        "neu": "neu",
        "gegen": "gegen",
        "ja_wenn": "Ja, wenn",
        "nein_wenn": "Nein, wenn",
        "angenommen": "Angenommen",
        "abgelehnt": "Abgelehnt",
        "per_handzeichen": "per Handzeichen",
        "benoetigt": "von {n} benötigten",
        "von": "von",
        "lager": {"dafür": "Dafür", "dagegen": "Dagegen",
                  "enthalten": "Enthalten", "geteilt": "Geteilt"},
        "stimmen": {"ja": "Ja", "nein": "Nein", "enthalten": "Enthalten",
                    "fehlt": "nicht abgestimmt"},
        "positionen": {"ja": "dafür", "nein": "dagegen", "enthalten": "enthalten",
                       "fehlt": "ohne Position"},
        "handzeichen_hinweis": "Position der Fraktion, keine Einzelstimmen",
        "parteien": {},
        "cta_headline": config.CTA_HEADLINE,
        "cta_body": config.CTA_BODY,
        "cta_action": config.CTA_ACTION,
        # Caption
        "details": "Alle Details im Karussell ➡️",
        "quelle": "Quelle",
        "geprueft": "Aus amtlichen Quellen, redaktionell geprüft.",
        "foto": "Foto",
        "datum": "%d.%m.%Y",
        "hashtags": "#politik #bundestag #deutschland #erklaert",
    },
    "en": {
        "lang": "en",
        "abgestimmt": "How the Bundestag voted",
        "fruehere": "What past cases show",
        "fuer_dich": "What does this mean for you?",
        "worum": "What it is about",
        "warum": "Why change it at all?",
        "schritte": "Only in these cases do you need to act",
        "auswertung": "Analysis: ",
        "wahlperiode": "Legislative term {n}",
        "bisher": "before",
        "neu": "new",
        "gegen": "vs",
        "ja_wenn": "Yes, if",
        "nein_wenn": "No, if",
        "angenommen": "Passed",
        "abgelehnt": "Rejected",
        "per_handzeichen": "by show of hands",
        "benoetigt": "of {n} needed",
        "von": "of",
        "lager": {"dafür": "For", "dagegen": "Against",
                  "enthalten": "Abstained", "geteilt": "Split"},
        "stimmen": {"ja": "Yes", "nein": "No", "enthalten": "Abstained",
                    "fehlt": "did not vote"},
        "positionen": {"ja": "for", "nein": "against", "enthalten": "abstained",
                       "fehlt": "no position"},
        "handzeichen_hinweis": "Party position, no individual votes",
        "parteien": {"Grüne": "Greens", "Linke": "Left", "Fraktionslos": "Independent"},
        "cta_headline": "Context,\nnot headlines.",
        "cta_body": "German politics explained: one decision at a time, "
                    "with source and the math.",
        "cta_action": "Follow for the next one",
        # Caption
        "details": "All details in the carousel ➡️",
        "quelle": "Source",
        "geprueft": "From official German sources, editorially reviewed.",
        "foto": "Photo",
        "datum": "%d %b %Y",
        "hashtags": "#germany #politics #bundestag #explained",
    },
}

# Fuer die Uebersetzung: Begriffe, die ein internationales Publikum nicht
# kennt, bekommen beim ersten Auftreten eine kurze Erklaerung - immer
# dieselbe, damit das Konto einheitlich spricht.
GLOSSAR = {
    "Bundestag": "Bundestag (German parliament)",
    "Bundesrat": "Bundesrat (upper house of the states)",
    "CDU/CSU": "CDU/CSU (centre-right)",
    "SPD": "SPD (centre-left)",
    "AfD": "AfD (far-right)",
    "Grüne": "Greens",
    "Die Linke": "The Left",
    "Tankrabatt": "fuel tax cut (Tankrabatt)",
    "Energiesteuer": "energy tax on fuel",
    "Mehrwertsteuer": "VAT",
    "Bundeskartellamt": "Federal Cartel Office",
    "Destatis": "Destatis (Federal Statistical Office)",
    "Lobbyregister": "lobby register",
    "Wahlperiode": "legislative term",
    "Fraktion": "parliamentary group",
    "Fraktionslos": "independent",
    "Bürgergeld": "Bürgergeld (basic income support)",
    "Kindergeld": "child benefit",
    "Nebentätigkeiten": "side jobs",
}
