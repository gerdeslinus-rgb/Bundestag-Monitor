"""Modellaufrufe und die Pruefstufen fuer die Erklaer-Karussells.

Zwei Pruefspuren, bewusst getrennt:

1. HARTE FAKTEN (der Beschluss, die Zahlen, das Abstimmungsergebnis) stammen
   aus unseren amtlichen Quellen. Dafuer gilt unveraendert die alte Regel:
   das Modell muss den woertlichen Belegsatz liefern, und Code - nicht das
   Modell - prueft, ob dieser Satz wirklich im Quelltext steht. Diese Huerde
   wurde NICHT gesenkt.
2. ERKLAERENDER HINTERGRUND ("Was ist ein Freibetrag?") kommt aus der
   Recherche. Dafuer gibt es keinen woertlichen Beleg-Satz, also auch keine
   woertliche Pruefung - stattdessen beurteilt ein getrennter Faktencheck
   (judge_slides), ob die Erklaerung zu den geprueften Fakten passt und die
   So-what-Slide rechnerisch bzw. logisch traegt.
"""

import difflib
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re

from anthropic import Anthropic

import config
import sources

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SELECT_PROMPT = """Du waehlst Themen fuer ein erklaerendes Instagram-Karussell zur
deutschen Politik aus. Zielgruppe: normale Leute ohne Politik-Studium.

Zwei Kriterien, in dieser Reihenfolge. Das erste schlaegt das zweite.

1. IST ES ENTSCHIEDEN? Jede Meldung unten ist mit ENTSCHIEDEN oder GEPLANT
   markiert. Dieser Ueberblick berichtet, was beschlossen wurde - nicht, was
   jemand vorschlaegt. Ein verabschiedetes Gesetz schlaegt jeden Antrag, auch
   einen thematisch interessanteren. Auch eine Ablehnung ist eine
   Entscheidung: dass der Bundestag etwas NICHT beschlossen hat, ist eine
   Nachricht.
   Nimm ein GEPLANT-Thema nur, wenn es zu wenige entschiedene gibt. Wer einen
   Antrag waehlt, ueber den erst noch abgestimmt wird, erklaert einer Leserin
   etwas, das vielleicht nie eintritt.

2. VERAENDERT ES ETWAS IN DER WELT? Drei gleichrangige Wege - keiner zaehlt
   mehr als die anderen, und Geld ist keiner davon:
   a) Alltag: Was aendert sich fuer eine konkrete Person - in ihren Rechten,
      ihrer Gesundheit, ihrer Arbeit, ihrer Wohnung, ihrer Mobilitaet, ihren
      Papieren? Eine Regel, die niemanden Geld kostet, aber viele betrifft
      (Organspende, Fuehrerschein, Haftung bei Unfaellen, Patientenrechte),
      ist genauso stark wie eine mit einem Betrag daran.
   b) Wirtschaft: Was aendert sich fuer eine Branche, fuer Betriebe, fuer
      Preise oder Arbeitsplaetze? Was ein Werk ausstossen darf, was ein
      Laden auszeichnen muss, wer gefoerdert wird - auch wenn die Leserin
      nicht selbst betroffen ist, lebt sie in dieser Wirtschaft.
   c) Oeffentliches Interesse: Sport, Kultur, Bildung, Forschung, alles
      Sichtbare. Die Foerderung des Spitzensports betrifft fast niemanden
      unmittelbar und ist trotzdem ein Thema, ueber das geredet wird.
   Der Test bleibt derselbe, nur breiter: Du musst in EINEM Satz sagen
   koennen, was sich fuer wen aendert - fuer eine Person, eine Branche oder
   die Oeffentlichkeit. Geht das nicht, ist es das falsche Thema.

Die Trennlinie verlaeuft nicht zwischen gross und klein, sondern zwischen
WELT und VERFAHREN. Ungeeignet ist, was nur regelt, wie Behoerden, Gerichte
oder Gremien untereinander vorgehen - auch wenn "Wirtschaft" oder
"Modernisierung" im Titel steht: Informationsaustausch zwischen Behoerden,
Zustaendigkeiten, Rechtsbehelfe fuer Verbaende, Statistikverfahren,
Berichtspflichten, Ueberweisungen an Ausschuesse, Geschaeftsordnungs-
debatten, Personalien, Lobbyregister-Eintraege, reine Ankuendigungen.
Ein Gesetz, das Grenzwerte, Auflagen, Foerderung, Haftung oder Preisangaben
aendert, veraendert die Welt. Eines, das den Dienstweg aendert, nicht.

Waehle bis zu {n} Themen - lieber weniger als schlechte.
Erst wenn zwei Themen nach 1 und 2 gleich stark sind, entscheidet, ob
konkrete Zahlen vorkommen: daraus wird spaeter ein Vergleichsdiagramm. Das
ist der Stichentscheid, nicht das Kriterium.

Antworte NUR mit JSON:
{{"themen": [{{"index": 0, "entschieden": true,
              "bereich": "alltag|wirtschaft|oeffentlich",
              "begruendung": "was sich fuer wen aendert",
              "hat_zahlen": true}}]}}

Wenn nichts den Massstab erfuellt: {{"themen": []}}

Meldungen:
{items}"""

COMPOSE_PROMPT = """Du schreibst ein Instagram-Karussell, das einen politischen
Beschluss fuer normale Leute erklaert. Sachlich, ohne Wertung, ohne Parteinahme,
aber konkret und in Alltagssprache. Kein Werbe-Ton, keine Ausrufezeichen.

Aufbau:
0. titel: die Schlagzeile des Covers, max 60 Zeichen. Sie steht versal und
   gross auf der ersten Slide und entscheidet allein, ob jemand weiterwischt.
   Bau sie aus zwei Teilen: vorne der Anker, an dem man die Sache
   wiedererkennt, hinten der eine konkrete Umstand, der aufhorchen laesst.
     gut: "Kalte Progression: 102-Euro-Pauschale gilt seit 1955"
     gut: "E-Scooter-Haftung: Jetzt zahlt der Vermieter"
     gut: "Preisangaben: Bis zu 100.000 Euro Strafe fuer falsche Schilder"
     gut: "Spitzensport: Neue Agentur verteilt kuenftig das Foerdergeld"
     schlecht: "AfD-Entwurf: Steuertarif automatisch an Inflation anpassen"
     schlecht: "E-Scooter-Haftung: Diese Regel von 2019 wurde jetzt geaendert"
   Die vier guten Zeilen haben NICHT dieselbe Bauform - genau darum geht es.
   Such den einen Umstand, der bei DIESER Meldung ueberrascht, und nimm die
   Form, die zu ihm passt: wer kuenftig zahlt, was es kostet, wer entscheidet,
   seit wann etwas gilt.
   Eine Jahreszahl traegt nur, wenn die Spanne selbst die Nachricht ist
   ("seit 1955", "seit der Einfuehrung 1949"). "Diese Regel von 2019 wurde
   geaendert" traegt nicht: sechs Jahre sind nichts Besonderes, und der Satz
   sagt nur, dass sich etwas geaendert hat - das tut jede Meldung hier.
   Wenn du keinen ueberraschenden Umstand findest, nenn schlicht die Folge:
   wer ab jetzt was tun muss oder bekommt.
   Du DARFST hier Unternehmen beim Namen nennen, wenn sie erkennbar zur
   betroffenen Gruppe gehoeren - "Jetzt zahlen Lime, Bolt und Co." statt
   "Jetzt zahlt der Vermieter". Das Gesetz sagt "Vermieter", aber niemand
   sucht danach; der Name macht abstraktes Recht greifbar. Nur in der
   Schlagzeile, und nur unter zwei Bedingungen: Das Unternehmen muss in
   Deutschland in diesem Geschaeft taetig sein - bist du unsicher, lass es
   weg. Und die Aussage muss fuer die Firma genauso gelten wie fuer alle
   anderen der Gruppe; schreib nie, als sei dieses eine Unternehmen gemeint,
   schuld oder besonders betroffen.
   Nimm dafuer die OFFENE Form, nicht die geschlossene: "Lime, Bolt und
   Co.", "Lime, Bolt und andere", "Vermieter wie Lime und Bolt". Sie sagt
   mit zwei Woertern, dass die Gruppe groesser ist als die genannten Namen,
   und genau das verlangt die zweite Bedingung. "Jetzt zahlen Lime und
   Bolt" liest sich dagegen, als waeren es diese beiden Firmen und sonst
   niemand - und wenn das Gesetz alle Halter trifft, auch private, ist das
   schlicht falsch.
   - Schreib ein Verb. Keine Nominalketten wie "Automatische Anpassung des
     Steuerrechts an die kalte Progression": das ist der Titel der Vorlage,
     nicht deine Schlagzeile.
   - Der Dokumenttyp gehoert nicht in die Zeile. "Gesetzentwurf", "Antrag",
     "Vorlage", "Beschlussempfehlung", "zur Abstimmung" kosten Zeichen und
     sagen der Leserin nichts. Wer den Vorstoss eingebracht hat, steht auf
     Slide 2 - als Aufhaenger ist die Partei die schwaechste Information,
     die du hast.
   - Sag trotzdem ehrlich, wie weit es ist: was erst beantragt oder beraten
     wird, heisst "soll" - niemals "wird", "kommt" oder "steigt". Eine
     Schlagzeile, die einen Beschluss behauptet, den es nicht gibt, ist
     falsch, auch wenn jedes einzelne Wort belegt ist.
   - Keine Masche: kein Fragezeichen, kein "Das aendert alles", keine
     Wertung, keine Uebertreibung.
1. hook: die Teaserzeile unter der Cover-Schlagzeile, max 70 Zeichen. Sie
   gibt der Zeile darueber Futter - sie macht kein zweites Fass auf.
   Die Zeile darueber sagt WAS. Deine Zeile sagt, WEN es angeht und WANN
   man es merkt: die Alltagssituation, in der die Sache auftaucht.
     gut:      "Beim naechsten Tanken zahlst du den Aufschlag mit"
     schlecht: "Faellt die Abgabe, koennten auch Entlastungen wie bei der
                EEG-Umlage wegfallen"
   Die schlechte Zeile hat zwei Fehler, und beide sind haeufig: sie bringt
   ein Thema herein, das im ganzen Karussell nicht mehr vorkommt, und sie
   benutzt mit "EEG-Umlage" ein Wort, das die Karte nirgends erklaert.
   Also:
   - Nur Woerter, die eine Leserin ohne Vorwissen kennt. Kein Fachbegriff,
     keine Abkuerzung, kein Gesetzes-, Abgaben- oder Behoerdenname - ausser
     dem EINEN Begriff, den Slide 3 erklaert.
   - Kein zweiter Gegenstand. Nichts, was die Slides nicht aufgreifen.
   - Kurz, direkt, du-Form. Keine Fragezeichen-Masche, keine Uebertreibung,
     kein Versprechen, das die Slides nicht einloesen.
   - Wiederhole die Zahl aus der Schlagzeile nicht. Werde stattdessen
     konkreter: derselbe Gegenstand, aber die Situation dazu.
   - Sag nicht dasselbe zweimal. Beide Zeilen stehen direkt untereinander,
     und der Platz reicht nicht fuer eine Aussage in zwei Fassungen.
     Schlagzeile "Jetzt zahlt der Vermieter" mit Teaserzeile "Verletzt dich
     ein Leih-Scooter, haftet ab jetzt der Vermieter" ist genau dieser
     Fehler: zweimal, wer haftet. Richtig waere hier, was die Schlagzeile
     offenlaesst - wann man es merkt, was man dann tun muss, wen es sonst
     noch trifft ("Auch wenn der Fahrer laengst weg ist"). Der Faktenpruefer
     laesst eine blosse Umformulierung durchfallen.
   Diese Zeile steht auch unter der Cover-Frage, wenn die Architektur mit
   der Frage gezogen wird - sie muss also auch dort als Antwort-Anfang
   taugen und darf der Frage nicht davonlaufen.
   Laesst sich keine unmittelbare Betroffenheit ehrlich benennen, nimm den
   Befund selbst ("Hersteller verlangen 4,6 Prozent mehr als vor einem
   Jahr"). Eine schwer zu formulierende Teaserzeile ist NIE ein Grund, das
   Thema zu ueberspringen.
1b. cover_frage: die Frage, die eine Leserin zu diesem Thema tatsaechlich in
   eine Suchmaschine tippen wuerde, max 60 Zeichen, endet auf einem
   Fragezeichen ("Was ist eine Pendlerpauschale?", "Wer bekommt jetzt mehr
   Wohngeld?"). Eine der sechs Cover-Architekturen setzt diese Frage gross auf
   die erste Slide.
   Zwei harte Bedingungen: Das Karussell MUSS sie beantworten - Slide 3
   erklaert genau einen Begriff, und die Frage darf nicht darueber
   hinausgehen. Und sie ist eine echte Frage, keine Masche: nicht "Wusstest du
   das?", nicht "Betrifft dich das auch?".
   Faellt dir keine ehrliche Frage ein, die das Karussell einloest, lass das
   Feld leer. Ein leeres Feld kostet nichts - eine Frage ohne Antwort schon.
2. chart: das Vergleichsdiagramm. "titel" ist die Headline dieser Slide und
   darf hoechstens 45 Zeichen haben, telegrafisch statt amtlich: nicht
   "Erzeugerpreise nach Bereich, August 2026 gegenueber Vorjahr", sondern
   "Erzeugerpreise nach Bereich vs Vorjahr". Die Einheit steht an den Balken,
   also nicht noch einmal in den Titel.
   Nimm die Zahlen aus "Recherche-Zahlen", wenn
   sie passen, sonst aus dem Quelltext. {min_bars} bis {max_bars} Balken.
   "hervorheben" ist der Index (ab 0) des Balkens, um den es in der Meldung
   geht - also der neue, beschlossene oder aktuelle Wert. Der wird farblich
   betont, die anderen bleiben grau als Vergleich.
   "wertung" - aus Sicht der meisten Haushalte im Alltag, und NUR fuer
   gemessene Werte (Statistik), nie fuer die Regeln eines Gesetzes
   (Bussgeld, Steuersatz, Freibetrag: dort immer "neutral"):
   - "hoch_gut": hoeher ist besser (Loehne, Renten, Lebenserwartung,
     Kita-Plaetze, Beschaeftigung - und Haeuser- und Wohnungspreise: sie
     sind der Wert des Eigentums, steigend gilt als gut, fallend als
     schlecht). Anstieg gruen, Rueckgang rot.
   - "hoch_schlecht": hoeher ist fuer die meisten schlechter
     (Verbraucherpreise, Inflation, Mieten, Energiekosten, Unfaelle,
     Verkehrstote, Straftaten, Arbeitslosigkeit). Anstieg rot, Rueckgang
     gruen.
   - "neutral": keine klare Alltagsrichtung (Bevoelkerung, Exporte,
     Zuwanderung, Ausgaben des Staates, Ernte). Im Zweifel "neutral".
   Steht unter "Kaufkraft" etwas anderes als "keine", dann gehoert ein
   zusaetzlicher Balken ans ENDE des Diagramms: Label "<Jahr> in heutiger
   Kaufkraft", "wert" ist der dort genannte Gegenwert - Ziffer fuer Ziffer
   uebernommen, nicht gerundet und nicht nachgerechnet. Das ist der Fall, in
   dem ein unveraenderter Betrag zweimal gleich lang im Diagramm stuende und
   damit nichts zeigt - der dritte Balken macht daraus den Vergleich, um den
   es geht. Setz "hervorheben" dann auf diesen Balken.
   "hinweis" MUSS in diesem Fall die Annahme nennen, die unter "Kaufkraft"
   steht, zum Beispiel "Kaufkraft, Annahme: 2 % Inflation pro Jahr". Der
   Gegenwert ist gerechnet, keine amtliche Zahl. Schreib ihn nirgends als
   Tatsache ("entspricht heute 420 Euro"), sondern immer als Schaetzung
   ("haette heute etwa die Kaufkraft von 420 Euro"). Ohne diesen Hinweis
   behauptet das Diagramm mehr, als es zeigt.
   Steht unter "Kaufkraft" nichts, bleibt es bei den Balken aus Quelltext
   und Recherche - rechne dann selbst nichts um.
3. context: 3 bis 4 kurze Absaetze, je max 200 Zeichen: Was ist das ueberhaupt,
   was galt vorher, was gilt jetzt, wer hat wie entschieden.
4. begriff: der EINE Fachbegriff, an dem die ganze Meldung haengt, erklaert
   fuer einen klugen Fuenfzehnjaehrigen. "titel" ist die Headline der Slide
   und endet auf dem Begriff selbst ("Was ist ein Freibetrag"). "saetze" sind
   GENAU 2 kurze Saetze ohne Fachsprache und ohne Schachtelsatz, je max 130
   Zeichen. "beispiel" ist ein gerechneter Fall mit konkreten Zahlen ("Bei
   1.500 Euro Zinsen zahlst du 0 Euro Steuern"), max 130 Zeichen. "warum"
   sind 2 Gruende, je max 110 Zeichen. Auf der Karte stehen sie unter der
   Frage "Warum ueberhaupt aendern?" - sie muessen diese Frage beantworten:
   Welches Problem gab es, was sollte die Aenderung bewirken? Ein Pro und
   ein Contra sind erlaubt, aber nicht verlangt; zwei Gruende fuer die
   Aenderung sind genauso richtig.
   Was NICHT geht: ein Einwand gegen das Ergebnis als erster Punkt. Unter
   "Warum ueberhaupt aendern?" liest sich "Kritiker fuerchten, die neue
   Agentur lasse Athleten zu wenig Mitsprache" wie ein Widerspruch - die
   Frage lautet, warum geaendert wurde, nicht was man davon haelt.
   Beide Gruende muessen ausserdem aus den "saetze" darueber verstaendlich
   sein. Haengt ein Grund an einer Eigenschaft, die du oben genannt hast,
   dann erklaere oben, was sie bedeutet: steht oben "eine neue, unabhaengige
   Behoerde" und unten etwas ueber ihre Unabhaengigkeit, muss oben stehen,
   WOVON sie unabhaengig ist ("unabhaengig vom Ministerium").
   Die Slide hat feste Masse: was laenger ist, wird gestrichen.
5. sowhat: Was heisst das fuer eine normale Person? Entweder art "rechnung"
   (mit nachvollziehbaren Schritten an einem Beispielfall) ODER art
   "erklaerung" (wenn sich nichts sinnvoll ausrechnen laesst). Zwinge keine
   Rechnung herbei, wo keine hingehoert.
   Sei hier sprachlich genau: beschreibe, was sich TATSAECHLICH aendert.
   Eine angehobene Grenze heisst "du darfst bis zu X verdienen, ohne dass ..."
   - NICHT "du bekommst X mehr". Ein Anspruch ist kein Auszahlungsbetrag,
   eine Obergrenze ist kein Einkommen. Wenn du mit einem Beispielfall
   rechnest, benenne ihn als Beispiel ("Wer bisher genau an der Grenze lag,
   ...") statt ihn als Normalfall auszugeben.
6. folgen: dieselbe Aussage wie sowhat, aber als Layout-Muster.
   Diese Slide UEBERSETZT den Befund in die Lage der Leserin. Sie wiederholt
   weder das Chart noch die Schlagzeile:
   - Die Hauptfigur von Slide 4 darf NICHT die Kennzahl sein, die das Chart
     schon zeigt. Zeigt das Chart bereits ein Vorher/Nachher derselben
     Groesse, ist "4a" gesperrt.
   - Bei Statistiken, Indizes und anderen Aggregaten ist "4d" der Normalfall:
     zwei konkrete Alltagsfaelle, die den Gesamtwert aufschluesseln ("Wer
     tankt oder heizt" gegen "Wer einkaufen geht"), mit den Detailzahlen aus
     der Quelle statt der Gesamtzahl.
   Waehle das Muster danach, was sich fuer die Leserin aendert, nicht nach der
   Textlaenge:
   - "4a" wenn sich ein Betrag oder Satz aendert, den die Leserin selbst zahlt
     oder bekommt, und dieser Wert nicht schon im Chart steht: "zeilen" mit
     label, bisher, neu (je als
     fertige Anzeige, "30 Cent" / "45 Cent"), "kopf_neu" ist die Ueberschrift
     der neuen Spalte ("ab 2027"). Was kein Vorher/Nachher ist (eine Frist,
     eine noetige Handlung), gehoert NICHT in die Tabelle, sondern nach
     "pills" mit label und wert. Der "wert" einer Pill ist eine Figur, kein
     Satz: eine Zahl, ein Betrag, ein Datum, hoechstens 14 Zeichen
     ("01.01.27", "100.000 €"). Wer zustaendig ist oder was noch aussteht,
     gehoert in "hinweis".
   - "4b" wenn die Anspruchsberechtigung die Geschichte ist: "ja" und "nein"
     als je 2 bis 3 kurze Bedingungen.
   - "4c" wenn die Aenderung automatisch greift oder Schritte noetig sind:
     "payoff" ist die grosse Antwort in ein bis zwei Woertern ("Nichts."),
     "erklaerung" ein Satz dazu, "schritte" die Faelle, in denen man doch
     selbst taetig werden muss (darf leer sein).
     Der payoff lautet meistens "Nichts." - das ist die ehrliche Antwort und
     bleibt der Normalfall. NUR wenn der "Bereich" unten "oeffentlich" ist,
     darfst du ihn stattdessen augenzwinkernd formulieren und EIN Emoji
     voranstellen: bei der Sportfoerderung etwa die deutsche Flagge und
     "Anfeuern.", darunter der Satz, dass sich am Geld nichts aendert.
     Das ist die einzige Stelle im ganzen Karussell, an der ein Emoji
     erlaubt ist, und die einzige, an der du nicht streng sachlich sein
     musst. Steht unter "Bereich" etwas anderes als "oeffentlich" - also
     "alltag" oder "wirtschaft" -, bleibt es nuechtern, ohne Emoji und ohne
     Pointe. Ein Gesetz ueber Unfallhaftung wird nicht witzig, auch wenn der
     payoff "Nichts." lautet.
     Und selbst bei "oeffentlich": Wenn das Thema Verletzte, Kranke, Tote,
     Straftaten, Krieg, Armut oder Diskriminierung beruehrt, bleibt es
     sachlich. Im Zweifel "Nichts." - eine verunglueckte Pointe kostet mehr
     Glaubwuerdigkeit, als eine gelungene einbringt.
   - "4d" wenn eine abstrakte Regel einen konkreten Fall braucht: genau zwei
     "faelle" mit label, symbol (person, haus, auto, geld, uhr oder dokument)
     und denselben "kennzahlen" in derselben Reihenfolge, je label und wert.
     Je Fall ZWEI Kennzahlen, in beiden Faellen gleich viele. Das "label"
     benennt die konkrete Sache ("Heizoel", "Kraftstoffe" / "Butter",
     "Schweinefleisch"), der "wert" ist die nackte Figur ("+65,3 %"),
     hoechstens 10 Zeichen. Der Name gehoert NICHT in den Wert, und
     "Produkt 1" ist kein Label: ohne die Sache steht die Zahl ohne Bezug.
   Liefere nur die Felder des gewaehlten Musters. Jede Zahl darin unterliegt
   derselben Belegpflicht wie der Rest.

Schreibweise:
- Keine Gedankenstriche. Trenne mit Doppelpunkt, Komma oder Punkt.
- Keine Ausrufezeichen.
- Keine Emojis, mit genau einer Ausnahme: dem "payoff" der Folgen-Slide im
  Muster 4c, und auch dort nur unter den Bedingungen, die bei "4c" stehen.
  Nirgends sonst - nicht in Schlagzeile, Teaserzeile, Context, Begriff oder
  So-what.
- Schreibe korrektes Deutsch mit Umlauten und Eszett: "für", "über",
  "Heizöl", "Zapfsäule", "heißt". Niemals die Umschrift ae/oe/ue/ss als
  Ersatz - dieser Text steht so auf der Karte. Dass diese Anweisung selbst
  ohne Umlaute gesetzt ist, ist eine Eigenheit des Quelltextes und kein
  Vorbild fuer deine Antwort.

Rechenbeispiele sind erlaubt und erwuenscht:
- Die Begriffskarte endet an einem gerechneten Beispiel, und eine Rechnung
  braucht einen Ausgangswert ("Aus 100 Euro werden 104,60 Euro").
- Jede Zahl, die DU als Beispielwert gewaehlt hast, und jedes Ergebnis, das
  du daraus ausrechnest, gehoert in "beispielwerte". Nur was dort steht, darf
  ausserhalb der Quellen vorkommen.
- Ein Beispielwert muss im Text als Beispiel erkennbar sein. Eine
  Tatsachenbehauptung ist kein Beispielwert: ein Beschlussdatum, ein
  amtlicher Betrag oder eine Veraenderungsrate gehoeren NIE dorthin.

Gerechnete Zahlen sind erlaubt, wenn du die Rechnung offenlegst:
- Eine Zahl, die nicht in den Quellen steht, sich aber aus belegten Zahlen
  ergibt ("seit 1955" + "2026" = "seit ueber 70 Jahren"), gehoert nach
  "abgeleitete_zahlen". Der Code rechnet sie nach.
- Je Eintrag: "wert" (die nackte Zahl, also 70 und nicht "ueber 70", 2.6 und
  nicht "2,6-fache" - das Signalwort gehoert in den Kartentext), "aus" (die
  Zahlen, aus denen du gerechnet hast - jede muss selbst im Quelltext oder
  in den Recherche-Zahlen stehen) und "rechnung", eines von:
  "differenz", "summe", "anteil" (a geteilt durch b mal 100), "faktor".
- Runden darfst du, aber nur auf ein Vielfaches von 5, hoechstens 5 Prozent
  weit, und das Signalwort muss zur Richtung passen: kommt 71 heraus,
  schreibe "ueber 70" - niemals "knapp 70". Wer nicht rundet, braucht kein
  Signalwort.
- Geht deine Rechnung nicht auf, faellt die Zahl durch. Schreibe im Zweifel
  den exakten Wert.

Keine Zahl aus dem eigenen Wissen:
- Jede andere Zahl muss aus dem Quelltext oder aus den Recherche-Zahlen
  stammen.
  Auch eine allgemein bekannte, zutreffende Zahl (etwa der aktuelle
  Kindergeldbetrag) ist unbelegt, wenn sie in keiner der beiden Quellen
  steht - und faellt in der Pruefung durch.
- Der "Verfahrensstand" unten ist davon ausgenommen: er stammt aus der
  Datenbank des Bundestages und ist damit belegt, auch wenn der Quelltext
  ihn nicht hergibt. Steht dort, dass verabschiedet wurde, darfst und
  sollst du "beschlossen" schreiben - obwohl der Quelltext die
  Beschlussempfehlung von vor der Abstimmung ist und "empfiehlt" sagt.
  Steht dort "nicht bekannt", schreib nichts ueber den Stand.
- Fehlt dir eine Zahl, schreibe den Satz ohne sie. Das gilt besonders fuer
  Datumsangaben: schreibe kein Beschluss-, Verkuendungs- oder Inkrafttretens-
  datum, das nicht im Quelltext steht. "Seit dem Beschluss" ist richtig, ein
  erfundenes Datum faellt durch.
- Vermische keine Zeitraeume: ein Vorjahresvergleich ist kein Vormonats-
  vergleich. Nimm die Angabe so, wie die Quelle sie zieht.

Aufzaehlungen NICHT erweitern:
- Nennt die Quelle Beispiele ("Versorgungsbetriebe wie etwa Strom- oder
  Gasanbieter"), dann uebernimm genau diese Beispiele. Ergaenze keine
  naheliegenden weiteren (Wasser, Fernwaerme, Muellabfuhr), auch wenn sie
  sachlich zur Kategorie passen wuerden.
- Steht ein Begriff an anderer Stelle der Quelle in einem ANDEREN
  Zusammenhang, gehoert er nicht hierher. Zwei getrennte Aussagen der Quelle
  duerfen nicht zu einer verschmolzen werden.

Belegpflicht - nur fuer harte Fakten aus dem QUELLTEXT:
- "fakten_evidence": die WOERTLICHEN Saetze aus dem Quelltext, die die Zahlen
  und Aussagen deiner Meldung belegen. Exakt kopieren, nicht umformulieren.
  Mehrere Saetze mit Leerzeichen verbinden.
- Erklaerender Hintergrund aus der Recherche braucht KEINEN woertlichen Beleg.

Antworte NUR mit JSON:
{{"skip": false,
  "titel": "Kalte Progression: Diese Regel aus 1955 soll geaendert werden",
  "hook": "...",
  "cover_frage": "Was ist eine Pendlerpauschale?",
  "chart": {{"titel": "...", "einheit": "Euro|Prozent|...",
            "balken": [{{"label": "...", "wert": 1200}},
                       {{"label": "1955 in heutiger Kaufkraft", "wert": 1100}}],
            "hervorheben": 1,
            "wertung": "neutral",
            "hinweis": "optionale Einordnung, max 90 Zeichen"}},
  "context": ["Absatz 1", "Absatz 2", "Absatz 3"],
  "begriff": {{"titel": "Was ist ein Freibetrag",
              "saetze": ["...", "..."],
              "beispiel": "...",
              "warum": ["...", "..."]}},
  "sowhat": {{"art": "rechnung", "text": "...", "schritte": ["1000 Euro x 12 = 12.000 Euro"]}},
  "folgen": {{"muster": "4a",
             "kopf_neu": "ab 2027",
             "zeilen": [{{"label": "Je Kilometer", "bisher": "30 Cent", "neu": "45 Cent"}}],
             "pills": [{{"label": "Gilt ab", "wert": "01.01.27"}}]}},
  "beispielwerte": [100, 104.60],
  "abgeleitete_zahlen": [{{"wert": 70, "aus": [1955, 2026], "rechnung": "differenz"}}],
  "fakten_evidence": "..."}}

Uebersprungen wird NUR, wenn der Quelltext zu duenn ist oder das Thema
keinerlei Alltagsbezug hat. Nicht, weil eine einzelne Zeile schwerfaellt,
und nicht, weil die Meldung eine Statistik statt eines Beschlusses ist:
{{"skip": true}}

Quelle: {source}
Datum: {date}
Titel: {title}
Quelltext:
{text}

{einwand}
Bereich: {bereich}
Verfahrensstand: {stand}
Recherche-Erklaerung: {erklaerung}
Recherche-Zahlen: {zahlen}
Kaufkraft: {kaufkraft}
Betroffene: {betroffene}
Alltagswirkung: {alltagswirkung}
{sonderregel}"""

JUDGE_PROMPT = """Du bist Faktenpruefer. Du pruefst NICHT den Stil, nur die
Haltbarkeit der Aussagen. Sei streng: im Zweifel durchfallen lassen.

Geprueft und belegt sind diese Fakten aus der amtlichen Quelle:
{fakten}

Verfahrensstand, belegt durch die Bundestags-Datenbank DIP:
{stand}
   Das ist eine eigenstaendige Fundstelle. Wenn dort steht, dass der Vorgang
   verabschiedet ist, dann IST er es - auch wenn der Quelltext oben die
   Beschlussempfehlung von vor der Abstimmung ist und nur "empfiehlt" sagt.
   Beanstande "beschlossen" in diesem Fall also nicht. Umgekehrt gilt weiter:
   steht dort nichts, ist jede Aussage ueber den Stand unbelegt.

Zusaetzlich belegt durch Recherche (jede Angabe mit eigener Fundstelle):
{recherche}

Zu pruefen:

A0) Schlagzeile und Teaserzeile der ersten Slide, direkt untereinander:
    Schlagzeile: {titel}
    Teaserzeile: {hook}

A) Context-Absaetze:
{context}

B) So-what-Slide (art: {art}):
{sowhat}

C) Begriffserklaerung (Slide 3):
{begriff}

D) Folgen-Slide (Slide 4), als Layout-Muster:
{folgen}

E) Zahlen, die das Modell als eigenes Rechenbeispiel deklariert hat:
{beispielwerte}

F) Cover-Frage (steht gross auf Slide 1, wenn diese Architektur gezogen wird):
{cover_frage}

G) Zahlen, die aus belegten Zahlen ausgerechnet wurden:
{abgeleitete}
   Die Rechnung selbst ist bereits nachgerechnet - sie geht auf, sonst
   laege dir dieser Entwurf nicht vor. Deine Frage ist eine andere: sagt
   der Satz auf der Karte das, was die Rechnung hergibt? Eine Zeitspanne
   ist keine Aussage ueber die Sache selbst ("seit ueber 70 Jahren
   unveraendert" stimmt nur, wenn die Quelle die Unveraendertheit auch
   behauptet, nicht bloss die Jahreszahl).

Pruefe:
- Widerspricht irgendeine Aussage den belegten Fakten?
- Enthaelt sie eine konkrete Zahl oder Tatsachenbehauptung, die weder in den
  belegten Fakten noch in der Recherche steht und auch nicht als allgemein
  bekannte Begriffserklaerung durchgeht? Allgemeine Erklaerungen ("Ein
  Freibetrag ist der Teil des Einkommens, auf den keine Steuer faellt") sind
  in Ordnung.
- Die Recherche zaehlt als Beleg: sie ist Hintergrund mit eigener Fundstelle,
  kein Zitat aus der amtlichen Quelle. Lass eine Aussage NICHT allein deshalb
  durchfallen, weil sie in der amtlichen Quelle fehlt - entscheidend ist, ob
  sie einer der beiden Belegquellen widerspricht.
- Achte dagegen weiter darauf, ob zwei getrennte Aussagen der Quelle zu einer
  vermengt werden (Beispiel: die Quelle nennt bei Zahlungsrueckstaenden Strom
  und Gas, an anderer Stelle Wasser als Wohnungsnebenkosten - "Strom-, Gas-
  oder Wasserrueckstand" waere daraus unzulaessig zusammengezogen).
- Bei art "rechnung": Stimmt die Arithmetik Schritt fuer Schritt? Sind die
  Ausgangswerte die belegten? Ist ein angenommener Beispielwert klar als
  Beispiel erkennbar und nicht als Tatsache ausgegeben?
- Bei art "erklaerung": Folgt die Aussage aus den belegten Fakten, ohne neue
  unbelegte Behauptung?
- Begriffserklaerung: Ist die Erklaerung sachlich richtig, und geht das
  Rechenbeispiel auf? Eine allgemeine Definition darf allgemein bleiben,
  ein gerechnetes Beispiel muss stimmen.
- Beispielwerte: Diese Zahlen stehen absichtlich in keiner Quelle, sie sind
  erlaubt - aber nur als Beispiel. Pruefe zweierlei, und lass im Zweifel
  durchfallen: Ist jede davon im Text klar als angenommenes Beispiel
  erkennbar ("aus 100 Euro werden ...")? Und geht die Rechnung mit den
  belegten Werten auf? Eine Tatsachenbehauptung, die als Beispielwert
  deklariert wurde - ein Datum, ein amtlicher Betrag, eine Veraenderungs-
  rate -, ist ein Durchfaller, kein Beispiel.
- Folgen-Slide: Sagen Tabelle, Bedingungen oder Fallkarten dasselbe wie die
  belegten Fakten? Achte besonders auf Vorher/Nachher-Paare (steht der
  "bisher"-Wert wirklich so in den Fakten?), auf Fristen und Datumsangaben
  und darauf, ob eine Bedingung strenger oder lockerer wiedergegeben wird,
  als sie belegt ist.
- Schlagzeile und Teaserzeile: Sagt die Teaserzeile etwas ANDERES als die
  Schlagzeile? Beide stehen direkt untereinander auf der ersten Slide, und
  der Platz ist zu knapp, um denselben Satz zweimal zu bringen. Gemeint ist
  nicht Wortgleichheit, sondern Informationsgewinn: "Jetzt zahlt der
  Vermieter" ueber "Verletzt dich ein Leih-Scooter, haftet ab jetzt der
  Vermieter" ist zweimal dieselbe Aussage und faellt durch - die zweite
  Zeile muesste sagen, WANN man es merkt oder WEN es sonst noch angeht.
  Nennt die Teaserzeile dagegen eine Situation, eine Bedingung oder eine
  weitere Betroffenengruppe, ist sie in Ordnung.
- Firmennamen: Die Schlagzeile darf Unternehmen beim Namen nennen, wenn sie
  erkennbar zur betroffenen Gruppe gehoeren - "Jetzt zahlen Lime, Bolt und Co."
  fuer ein Gesetz ueber E-Scooter-Vermieter ist zulaessig, auch wenn die
  Namen in keiner Quelle stehen. Das ist eine bewusste Ausnahme von der
  Belegpflicht, weil der Gesetzestext nur "Vermieter" sagt und niemand
  danach sucht.
  Zwei Grenzen, und bei beiden faellst du durch: Das Unternehmen muss in
  Deutschland in diesem Geschaeft taetig sein - rate nicht, und nimm keinen
  Namen, bei dem du unsicher bist. Und die Aussage muss fuer die genannte
  Firma genauso gelten wie fuer die Gruppe; ein Name darf nicht so stehen,
  als sei dieses Unternehmen besonders gemeint, betroffen oder schuld.
  Eine OFFENE Aufzaehlung erfuellt die zweite Bedingung bereits: "Tier,
  Lime und Co.", "Lime, Bolt und andere", "Vermieter wie Tier und Lime"
  sagen ausdruecklich, dass die Gruppe groesser ist als die genannten
  Namen. Das ist kein Beanstandungsgrund - beanstande hier nur die
  geschlossene Form, die klingt, als waeren es diese Firmen und sonst
  niemand. Lies die Zeile dabei so, wie sie dasteht: Wer "und Co."
  ueberliest und anschliessend bemaengelt, die zwei Namen seien nicht
  repraesentativ, beanstandet eine Zeile, die so nicht geschrieben wurde.
- Cover-Frage: Beantworten die Slides sie wirklich? Die Frage steht auf der
  ersten Slide und verspricht damit eine Antwort. Verspricht sie mehr, als
  Begriffserklaerung und Folgen-Slide einloesen, oder setzt sie eine Tatsache
  voraus, die nicht belegt ist ("Warum steigt die Miete 2027?", wenn die
  Quelle das gar nicht hergibt), ist sie ein Durchfaller. Ein leeres Feld ist
  in Ordnung.

Antworte NUR mit JSON:
{{"ok": true, "problem": ""}}
oder
{{"ok": false, "problem": "was genau nicht traegt"}}"""


def _json_from(text: str):
    """Holt das JSON-Objekt aus der Antwort.

    Das Modell haengt trotz Anweisung gelegentlich noch Prosa an oder packt
    das JSON in einen Codeblock. Deshalb erst der direkte Versuch, dann das
    erste vollstaendig geklammerte Objekt aus dem Text.
    """
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError("kein JSON in der Antwort")
    tiefe, in_string, escaped = 0, False, False
    for i, zeichen in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif zeichen == "\\":
                escaped = True
            elif zeichen == '"':
                in_string = False
            continue
        if zeichen == '"':
            in_string = True
        elif zeichen == "{":
            tiefe += 1
        elif zeichen == "}":
            tiefe -= 1
            if tiefe == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unvollstaendiges JSON in der Antwort")


def _text_block(resp) -> str:
    """Holt den Textblock aus der Antwort. Bei Extended Thinking steht davor
    ein ThinkingBlock, deshalb nicht blind content[0] nehmen."""
    for block in resp.content:
        if block.type == "text":
            return block.text
    raise ValueError("keine Textantwort im Modell-Ergebnis")


# Tiefgestellte Indizes: die Bundestag-Seite liefert "CO 2 -Bepreisung",
# wer korrekt zitiert schreibt "CO2-Bepreisung". Der laengste gemeinsame
# Teilstring brach genau an dieser Stelle ab. Beide Seiten laufen durch
# _normalise, das Zusammenziehen ist also symmetrisch.
_INDEX = re.compile(r"\b(co|no|so|ch|nh|h|n) (2|3|4|x)\b")


def _normalise(text: str) -> str:
    """Vergleichsform fuer die Belegpruefung.

    Der Trennstrich-Schritt ist kein Schoenheitsfehler, sondern der Grund,
    warum ein korrekt abgeschriebener Satz durchfallen konnte: PDF-Texte
    tragen die Silbentrennung des Zeilenumbruchs mit, im Ausschussbericht
    etwa "BUEND- NIS 90/DIE GRUENEN". Wer richtig zitiert, schreibt
    "BUENDNIS" - und der laengste gemeinsame Teilstring brach genau dort ab
    (gemessen: 0.64 statt 1.00). Beide Seiten laufen durch diese Funktion,
    deshalb ist das Entfernen symmetrisch und kann keinen Beleg erfinden.

    Die Reihenfolge der letzten Schritte ist aus demselben Grund keine
    Geschmacksfrage: frueher wurden erst die Leerzeichen zusammengezogen
    und danach die Satzzeichen durch Leerzeichen ersetzt - die dabei neu
    entstandenen Doppel-Leerzeichen blieben stehen. Ein korrekt
    abgeschriebener Satz brach damit an jedem Bindestrich ab (gemessen:
    0.70 statt 1.00). Deshalb jetzt: erst Satzzeichen, dann Leerzeichen.
    """
    text = re.sub(r"-\s+", "", text)
    text = text.lower()
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = _INDEX.sub(r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def quelltext_tragfaehig(item: dict) -> bool:
    """Reicht der Quelltext ueberhaupt fuer die Beleg-Pruefung?

    Kostenbremse: die Recherche ist mit Abstand der teuerste Schritt
    (Suchergebnisse landen im Kontext, ~65k Input-Tokens pro Aufruf). Ein
    Thema, dessen Quelltext nur aus Metadaten-Schnipseln besteht
    ("21/7563 - PDF - Antwort der Bundesregierung - Drs."), faellt spaeter
    ohnehin durch die Belegpflicht. Das erkennen wir vorher gratis, statt
    erst zu recherchieren und dann zu verwerfen.
    """
    text = (item.get("text") or "").strip()
    if len(text) < config.MIN_QUELLTEXT_CHARS:
        return False

    # Echte Prosa hat Saetze. Metadaten-Zeilen haben Trenner, aber kaum Punkte.
    if len(re.findall(r"[.!?](?:\s|$)", text)) < 2:
        return False

    # Navigations-Muell aussortieren: beim Nachladen von Aggregator-Seiten
    # kommt oft nur das Seitenmenue zurueck ("Vorschau Naechste Sitzung ...
    # Neu im DIP ..."), gespickt mit Aufzaehlungszeichen. Das ist lang genug
    # und hat formal Saetze, ist aber nichts, woraus man zitieren kann - das
    # Modell scheitert daran spaeter an der Belegpflicht, nachdem die teure
    # Recherche schon gelaufen ist.
    if sum(text.count(z) for z in "◆•|·") > 3:
        return False

    return True


def verfahrensstand(item: dict) -> str:
    """Wie weit der Vorgang ist - als Tatsache, nicht als Vermutung.

    Diese Angabe kommt aus den DIP-Metadaten des Bundestages, nicht aus dem
    Quelltext. Der Unterschied ist der Grund fuer diese Funktion: bei einem
    verabschiedeten Gesetz laedt ensure_volltext() die Beschlussempfehlung,
    und die ist VOR der Abstimmung geschrieben. Sie sagt "wird empfohlen",
    nicht "wurde beschlossen".

    Ohne diese Zeile schrieb das Modell zu Recht "beschlossen", konnte es
    aber nicht belegen - und der Faktencheck verwarf das Karussell mit der
    Begruendung, die Quelle sei nur eine Beschlussempfehlung. Beide hatten
    recht; gefehlt hat die Auskunft, dass die Abstimmung laengst gelaufen
    ist. Sie steht deshalb sowohl im Entwurfs- als auch im Pruefprompt.
    """
    quelle = item.get("source", "")
    kopf = "Bundestag, Vorgang "
    if kopf in quelle:
        stand = quelle.split(kopf, 1)[1].strip()
        if stand:
            return (f"Der Vorgang ist laut Bundestags-Datenbank DIP "
                    f"'{stand}'. Die Abstimmung hat also stattgefunden, auch "
                    f"wenn der Quelltext unten die Beschlussempfehlung von "
                    f"davor ist.")
    if quelle.startswith("Bundestag, Textarchiv"):
        return ("Der Quelltext ist der Bericht der Parlamentsredaktion des "
                "Bundestages ueber die Sitzung, in der abgestimmt wurde. Was "
                "er als beschlossen, abgelehnt oder zugestimmt nennt, ist "
                "entschieden. Nicht jedes Gesetz ist damit schon in Kraft: "
                "der Bundesrat kann noch ausstehen - schreibe dazu nur, was "
                "der Quelltext sagt.")
    if "namentliche Abstimmung" in quelle:
        return "Die Abstimmung hat stattgefunden, das Ergebnis liegt vor."
    return "nicht bekannt - schreibe nichts ueber den Verfahrensstand"


def _entschieden(item: dict) -> bool:
    """Beschreibt das Item eine bereits gefallene Entscheidung?

    Aus der Quellenbezeichnung abgeleitet statt geraten: fetch_dip() laesst
    nur Vorgaenge aus DIP_BESCHLOSSEN durch, ihr "source" traegt den
    Beratungsstand. Ein Tagesordnungspunkt steht dagegen erst an.
    """
    quelle = item.get("source", "")
    return any(m in quelle for m in config.ENTSCHIEDEN_QUELLEN)


def select_topics(items: list, anzahl: int | None = None) -> list:
    """Waehlt alltagsrelevante Themen aus. Leere Liste = heute nichts dabei.

    `anzahl` ist die Zahl der noch fehlenden Karussells: im Stufenbetrieb
    hat eine fruehere Quelle womoeglich schon eines geliefert.
    """
    anzahl = anzahl or config.CAROUSELS_PER_RUN
    kern = [it for it in items
            if it.get("tier") == "kern" and quelltext_tragfaehig(it)]
    if not kern:
        return []

    # Entschiedene zuerst, und ausdruecklich als solche markiert. Beides
    # zusammen: die Markierung ist die Regel, die Reihenfolge der Anstoss -
    # ohne sie standen die neun verabschiedeten Gesetze am Listenanfang
    # zwischen 24 Tagesordnungspunkten und gingen unter.
    kern.sort(key=lambda it: not _entschieden(it))
    listing = "\n".join(
        f"[{i}] {'ENTSCHIEDEN' if _entschieden(it) else 'GEPLANT    '} | "
        f"{it['source']}: {it['title']}"
        for i, it in enumerate(kern)
    )
    try:
        resp = client.messages.create(
            model=config.MODEL_RANK, max_tokens=4000,
            messages=[{"role": "user", "content": SELECT_PROMPT.format(
                n=anzahl, items=listing)}],
        )
        data = _json_from(_text_block(resp))
    except Exception as exc:
        print(f"  ! Themenauswahl fehlgeschlagen: {exc}")
        return []

    gewaehlt = []
    for eintrag in data.get("themen", []) or []:
        idx = eintrag.get("index")
        if isinstance(idx, int) and 0 <= idx < len(kern):
            gewaehlt.append({**kern[idx],
                             "begruendung": eintrag.get("begruendung", ""),
                             "bereich": eintrag.get("bereich", "")})
    gewaehlt = gewaehlt[:anzahl]

    # Sichtbar machen, was die Auswahl getan hat. Ein Lauf, der nur geplante
    # Vorhaben waehlt, obwohl entschiedene vorlagen, ist kein Fehler im
    # Code - aber der Grund, hier nachzusehen.
    offen = sum(1 for it in kern if not _entschieden(it))
    print(f"  ({len(kern) - offen} entschieden, {offen} geplant zur Auswahl)")
    for it in gewaehlt:
        print(f"    {'ENTSCHIEDEN' if _entschieden(it) else 'GEPLANT'} "
              f"[{it.get('bereich') or '?'}]: {it['title'][:52]}")
    return gewaehlt


# Eine Statistik ist keine Entscheidung: "Warum ueberhaupt aendern?" hat
# darauf keine Antwort (Abstimmung 25.09.2026). Die zwei Punkte unter der
# Begriffskarte geben stattdessen mehr Zusammenhang aus der Meldung.
STATISTIK_REGEL = """
SONDERREGEL - diese Meldung ist eine Statistik, keine Entscheidung:
- "begriff.warum" sind KEINE Gruende fuer eine Aenderung. Es sind 2 Punkte
  MEHR ZUSAMMENHANG aus dem Quelltext, je max 110 Zeichen: Unterschiede
  zwischen Regionen (z. B. Metropolen gegen laendliche Kreise), Gruppen
  (Neubau gegen Bestand, Frauen gegen Maenner) oder ein laengerer
  Vergleich, den die Meldung nennt. Mit Zahlen aus dem Quelltext. Auf der
  Karte stehen sie unter "Genauer hingeschaut".
- "chart.wertung": setze "hoch_gut" oder "hoch_schlecht", wo die Regel
  oben eine Richtung hergibt. Haeuser- und Wohnungspreise: "hoch_gut";
  Verbraucherpreise und Mieten: "hoch_schlecht".
"""


DESTATIS_PROMPT = """Unten stehen Pressemitteilungen des Statistischen
Bundesamtes. Markiere jede, die den ALLTAG normaler Leute beruehrt: was sie
zahlen (Preise, Mieten, Energie, Lebensmittel), was sie verdienen (Loehne,
Renten, Arbeitsmarkt), wie sie wohnen, sich bewegen, gesund bleiben, lernen,
Familien gruenden - oder was im Land sichtbar geschieht (Unfaelle,
Bevoelkerung, Wetterfolgen).

Nicht markieren: Branchen- und Aussenhandelsdetails ohne Folge fuer
Verbraucher (Pkw-Exporte, Erzeugerpreise einzelner Dienstleistungen),
Nischenstatistik (Kirschenernte, Schlachtmengen), reine
Methoden- oder Terminhinweise.

Antworte NUR mit JSON: {{"alltag": [0, 3]}}

Meldungen:
{items}"""


def destatis_auswahl(items: list) -> list:
    """Die Destatis-Meldungen mit Alltagsbezug, in Feed-Reihenfolge.

    Die Items kommen neueste zuerst; die Reihenfolge bleibt erhalten, damit
    die juengste passende Meldung vorn steht. Gefragt wird nur ja/nein je
    Meldung - die Rangfolge ist das Datum, nicht der Geschmack des Modells.
    """
    if not items:
        return []
    listing = "\n".join(f"[{i}] {it['title']} - {it['text'][:200]}"
                        for i, it in enumerate(items))
    try:
        resp = client.messages.create(
            model=config.MODEL_RANK, max_tokens=500,
            messages=[{"role": "user",
                       "content": DESTATIS_PROMPT.format(items=listing)}])
        data = _json_from(_text_block(resp))
    except Exception as exc:
        print(f"  ! Destatis-Auswahl fehlgeschlagen: {exc}")
        return []
    markiert = {i for i in data.get("alltag", []) or []
                if isinstance(i, int) and 0 <= i < len(items)}
    for i, it in enumerate(items):
        print(f"    {'ja  ' if i in markiert else 'nein'} {it['title'][:66]}")
    return [it for i, it in enumerate(items) if i in markiert]


GESETZ_PROMPT = """Ein Gesetz aus dem Bundestag, unten Titel und
Zusammenfassung aus der Parlamentsdatenbank.

1. "kurzname": der kurze Name, unter dem das Gesetz laeuft, hoechstens 40
   Zeichen, im Nominativ (z. B. "Gebaeudemodernisierungsgesetz"). Er MUSS
   woertlich in Titel oder Zusammenfassung vorkommen. Gibt es keinen, nimm
   das erste zusammengesetzte Wort auf "-gesetz" aus dem Titel.
2. "satz": EIN Satz, was sich durch das Gesetz KONKRET aendert, fuer Leute
   ohne Vorwissen, hoechstens 160 Zeichen: wer darf, muss oder bekommt jetzt
   was? Nicht "Das Gesetz aendert das X-Gesetz" - das sagt der Titel schon.
   Beginne mit dem Gesetzesnamen ("Das Umwelt-Rechtsbehelfsgesetz regelt
   kuenftig ..."). Nur was in Titel oder Zusammenfassung steht, keine
   Wertung.

Antworte NUR mit JSON: {{"kurzname": "...", "satz": "..."}}

Titel: {title}
Zusammenfassung: {text}"""


GESETZ_SATZ_MAX = 200


def _gesetz_aus_titel(titel: str) -> str:
    """Das erste Kompositum auf "-gesetz" im Titel, im Nominativ:
    "... des Gebaeudeenergiegesetzes, ..." -> "Gebaeudeenergiegesetz"."""
    for wort in re.findall(r"[\w-]+gesetz(?:es|s)?\b", titel):
        if wort.lower() in ("gesetz", "gesetzes"):
            continue
        return re.sub(r"(?<=gesetz)(es|s)$", "", wort)
    return ""


def gesetz_kurz(item: dict) -> dict | None:
    """Kurzname und Ein-Satz-Beschreibung eines DIP-Gesetzes.

    Der Kurzname geht auf die Schlagzeile - er wird deshalb gegen den
    Quelltext geprueft, nicht dem Modell geglaubt. Das Modell kennt oft den
    gelaeufigen Namen ("Gebaeudemodernisierungsgesetz"), der im DIP-Text
    gar nicht steht; dann gilt das erste "-gesetz" aus dem Titel.

    Der Satz haelt sich oft nicht an die Laenge. Er wird nicht gekuerzt - ein
    abgeschnittener Satz auf einer Karte ist schlimmer als keiner -, sondern
    einmal neu angefordert.
    """
    quelle = f"{item['title']} {item['text']}".lower()
    einwand = ""
    for _ in range(2):
        try:
            resp = client.messages.create(
                model=config.MODEL_RANK, max_tokens=400,
                messages=[{"role": "user", "content": GESETZ_PROMPT.format(
                    title=item["title"], text=item["text"][:3000]) + einwand}])
            data = _json_from(_text_block(resp))
        except Exception as exc:
            print(f"    ! Gesetzesname nicht ermittelt: {exc}")
            return None
        kurz = umlaute_reparieren(str(data.get("kurzname", "")).strip())
        satz = umlaute_reparieren(str(data.get("satz", "")).strip())

        # Der Titel steht oft im Genitiv ("des Gebaeudeenergiegesetzes").
        if not kurz or not any(kurz.lower() + endung in quelle
                               for endung in ("", "es", "s")):
            ersatz = _gesetz_aus_titel(item["title"])
            print(f"    - Kurzname '{kurz}' steht nicht in der Quelle, "
                  f"nehme '{ersatz or '-'}' aus dem Titel")
            if not ersatz:
                return None
            satz = satz.replace(kurz, ersatz) if kurz else satz
            kurz = ersatz
        if satz and len(satz) <= GESETZ_SATZ_MAX:
            return {"kurzname": kurz, "satz": satz}
        print(f"    - Satz zu lang ({len(satz)} Zeichen), zweiter Versuch")
        einwand = (f"\n\nDein letzter Satz hatte {len(satz)} Zeichen. "
                   f"Hoechstens 160 - nenne nur die wichtigste Aenderung.")
    return None


# --- Datenkarussells: Saetze aus Registertexten -----------------------------
#
# Zwei Stellen, an denen ein Datenkarussell doch ein Modell braucht: was eine
# Organisation zu einem Gesetz wollte (aus ihrer Stellungnahme) und was eine
# spendende Organisation ist (aus Lobbyregister und Wikipedia). Beides wird
# zweimal geprueft: hier mechanisch (jede Zahl und die tragenden Woerter
# stehen in der Quelle), danach im Faktencheck gegen denselben Auszug.

def _belegt(satz: str, quelle: str, anteil: float = 0.6) -> bool:
    """Jede Zahl des Satzes steht in der Quelle, und die meisten seiner
    Inhaltswoerter auch (auf sechs Buchstaben gekuerzt, damit "fordert"
    und "Forderung" zusammenkommen)."""
    quelle_n = " ".join(quelle.lower().split())
    for zahl in re.findall(r"\d[\d.,]*\d|\d", satz):
        if zahl.rstrip(".,") not in quelle_n:
            return False
    woerter = [w[:6] for w in re.findall(r"[a-zäöüß]{7,}", satz.lower())
               if w not in {"fordert", "kritisiert", "begrüßt", "verlangt",
                            "organisation", "gesetzes", "gesetz"}]
    if not woerter:
        return True
    return sum(w in quelle_n for w in woerter) / len(woerter) >= anteil


LOBBY_PROMPT = """Organisationen haben im Lobbyregister des Bundestages
Lobbyarbeit zum {gesetz} gemeldet. Unten je Organisation ihre eigene
Beschreibung des Vorhabens und, wo vorhanden, ein Auszug ihrer Stellungnahme.

Schreib je Organisation EINEN Satz, hoechstens 110 Zeichen, was sie zu diesem
Gesetz fordert, kritisiert oder begruesst. Beginne mit dem Verb: "Fordert
...", "Kritisiert ...", "Begrüßt ...", "Will ...". Konkret: welche Regel,
welche Zahl, welche Gruppe - aber in Worten, die man ohne Vorwissen
versteht: keine Paragrafen ("§ 71k GEG"), keine Gesetzesabkuerzungen
("CO2KostAufG"), keine Programmkuerzel ohne Erklaerung ("BEG"). Sag, was
die Regel tut ("die Pflicht, Heizkosten fuer Biogas einzeln auszuweisen").
Nur was im Text steht. Keine Wertung, keine Vermutung ueber
Motive. Ist keine klare Position zu diesem Gesetz erkennbar, lass die
Organisation weg. Schreib mit echten Umlauten (ä, ö, ü, ß).

Danach "lager": Teile die Organisationen mit Position in ZWEI Lager, die
sich bei diesem Gesetz gegenueberstehen - nach dem, was sie wollen, nicht
nach ihrer Art. Beispiel GKV-Gesetz: "Wollen Beitragszahler entlasten"
gegen "Wollen hoehere Preise und Verguetungen". Jeder Titel hoechstens 40
Zeichen, beschreibend, ohne Wertung, beginnt mit "Wollen" oder "Gegen".
Jede Organisation hoechstens in einem Lager. Gibt es keinen echten
Gegensatz (alle wollen dasselbe), gib "lager": [].

Antworte NUR mit JSON:
{{"positionen": [{{"nr": 1, "satz": "..."}}],
  "lager": [{{"titel": "...", "nr": [1, 3]}}, {{"titel": "...", "nr": [2]}}]}}

{bloecke}"""


def lobby_positionen(gesetz: str, orgs: list) -> tuple:
    """({nr: satz}, lager) fuer die Organisationen, deren Position belegt ist.

    `lager` sind zwei Gruppen [{"titel", "nr": [...]}], die sich
    gegenueberstehen - oder [], wenn das Modell keinen Gegensatz sieht oder
    ein Lager nach der Belegpruefung leer waere.

    `orgs` sind Dicts mit "name" und "quelle" (Beschreibung plus
    Stellungnahme-Auszug) - genau der Text, gegen den auch der Faktencheck
    prueft."""
    bloecke = "\n\n".join(f"[{i}] {o['name']}\n{o['quelle']}"
                          for i, o in enumerate(orgs, 1))
    try:
        resp = client.messages.create(
            model=config.MODEL_DRAFT, max_tokens=config.DATEN_MAX_TOKENS,
            messages=[{"role": "user", "content": LOBBY_PROMPT.format(
                gesetz=gesetz, bloecke=bloecke)}])
        data = _json_from(_text_block(resp))
    except Exception as exc:
        print(f"    ! Lobby-Positionen nicht ermittelt: {exc}")
        return {}, []
    ergebnis = {}
    for p in data.get("positionen", []) or []:
        try:
            nr = int(p.get("nr"))
            satz = umlaute_reparieren(str(p.get("satz", "")).strip())
            org = orgs[nr - 1]
        except (TypeError, ValueError, IndexError):
            continue
        if not satz or len(satz) > 160:
            print(f"    - Position {org['name']}: zu lang ({len(satz)})")
        # Alltagsworte statt Paragrafen: etwas weniger Woerter decken sich
        # dann mit der Quelle. Die Zahlen muessen weiter alle stimmen.
        elif not _belegt(satz, org["quelle"], anteil=0.5):
            print(f"    - Position {org['name']} nicht belegt: {satz}")
        else:
            ergebnis[nr] = satz
    lager = []
    for l in data.get("lager", []) or []:
        titel = umlaute_reparieren(str(l.get("titel", "")).strip())
        nrn = [n for n in (l.get("nr") or []) if isinstance(n, int) and n in ergebnis]
        if titel and len(titel) <= 50 and nrn:
            lager.append({"titel": titel, "nr": nrn})
    if len(lager) != 2 or set(lager[0]["nr"]) & set(lager[1]["nr"]):
        lager = []
    return ergebnis, lager


GESETZ_KARTE_PROMPT = """Ein beschlossenes Gesetz, unten Titel und
Zusammenfassung aus der Parlamentsdatenbank des Bundestages. Schreib eine
Erklaerkarte fuer einen klugen Fuenfzehnjaehrigen:

- "saetze": GENAU 2 kurze Saetze, je hoechstens 130 Zeichen: was das Gesetz
  regelt und was sich konkret aendert. Ohne Fachsprache, ohne Paragrafen.
- "beispiel": ein konkreter Fall, hoechstens 130 Zeichen. Zahlen NUR, wenn
  sie im Text stehen - erfinde keine.
- "warum": GENAU 2 Gruende, je hoechstens 110 Zeichen. Sie stehen unter der
  Frage "Warum ueberhaupt aendern?": welches Problem gab es, was soll das
  Gesetz bewirken - so, wie der Text es begruendet. Kein Einwand, keine
  Wertung.
Nur was im Text steht. Schreib mit echten Umlauten (ä, ö, ü, ß).

Antworte NUR mit JSON:
{{"saetze": ["...", "..."], "beispiel": "...", "warum": ["...", "..."]}}

Titel: {title}
Zusammenfassung: {text}"""


def gesetz_karte(item: dict) -> dict | None:
    """Begriffskarte "Was das Gesetz aendert" fuer das Lobby-Karussell
    (Abstimmung 25.09.2026: wie Slide 3 bei DIP). Jeder Satz wird gegen den
    DIP-Text geprueft; einmal neu angefordert, dann None."""
    quelle = f"{item['title']} {item['text']}"
    einwand = ""
    for _ in range(2):
        try:
            resp = client.messages.create(
                model=config.MODEL_DRAFT, max_tokens=config.DATEN_MAX_TOKENS,
                messages=[{"role": "user", "content": GESETZ_KARTE_PROMPT.format(
                    title=item["title"], text=item["text"][:4000]) + einwand}])
            karte = umlaute_reparieren(_json_from(_text_block(resp)))
        except Exception as exc:
            print(f"    ! Gesetzeskarte nicht ermittelt: {exc}")
            return None
        saetze = [str(x) for x in karte.get("saetze", [])]
        warum = [str(x) for x in karte.get("warum", [])]
        beispiel = str(karte.get("beispiel", "")).strip()
        alle = saetze + warum + ([beispiel] if beispiel else [])
        # Nur die Zahlen mechanisch: die Karte soll Alltagsworte benutzen
        # ("Aerzte, Kliniken"), der DIP-Text sagt "Leistungserbringer" - eine
        # Wortpruefung verwarf deshalb jede gute Fassung. Den Inhalt prueft
        # der Faktencheck gegen denselben Text.
        falsch = [x for x in alle if len(x) > 150 or not _belegt(x, quelle, anteil=0)]
        if len(saetze) == 2 and len(warum) == 2 and not falsch:
            return {"saetze": saetze, "beispiel": beispiel, "warum": warum}
        print(f"    - Gesetzeskarte verworfen: {falsch or 'Form'}")
        einwand = ("\n\nDein letzter Versuch enthielt Aussagen, die nicht im Text "
                   "stehen, oder war zu lang. Bleib naeher am Text.")
    return None


SPENDER_PROMPT = """Unten Angaben zu der Organisation "{name}": ihr
Eintrag im Lobbyregister des Bundestages und, wenn vorhanden, der Anfang des
Wikipedia-Artikels.

Schreib GENAU 2 kurze Saetze, je hoechstens 150 Zeichen, fuer Leute ohne
Vorwissen: Was ist diese Organisation (Art, Sitz, Groesse) und was macht sie
(Zweck, Themen)? Der erste Satz beginnt mit dem Namen. Nur was in den Angaben
steht; Zahlen nur, wenn sie dort stehen. Nichts darueber, warum sie spendet
oder was sie sich davon verspricht, keine Wertung. Schreib mit echten
Umlauten (ä, ö, ü, ß).

Antworte NUR mit JSON: {{"saetze": ["...", "..."]}}

{quelle}"""


def spender_portraet(name: str, quelle: str) -> list:
    """Zwei belegte Saetze ueber eine spendende Organisation, oder []."""
    einwand = ""
    for _ in range(2):
        try:
            resp = client.messages.create(
                model=config.MODEL_DRAFT, max_tokens=config.DATEN_MAX_TOKENS,
                messages=[{"role": "user", "content": SPENDER_PROMPT.format(
                    name=name, quelle=quelle[:5000]) + einwand}])
            saetze = [umlaute_reparieren(str(s).strip())
                      for s in _json_from(_text_block(resp)).get("saetze", [])]
        except Exception as exc:
            print(f"    ! Spenderportraet nicht ermittelt: {exc}")
            return []
        falsch = [s for s in saetze if len(s) > 170 or not _belegt(s, quelle)]
        if len(saetze) == 2 and not falsch:
            return saetze
        print(f"    - Spenderportraet verworfen: {falsch or saetze}")
        einwand = ("\n\nDein letzter Versuch enthielt Aussagen, die nicht in "
                   "den Angaben stehen, oder war zu lang. Bleib naeher am Text.")
    return []


# --- Umlaute -------------------------------------------------------------
#
# Das Modell driftet in die Umschrift ab: in einem Lauf schrieb dasselbe
# Modell mit demselben Prompt einmal "Heizoel, fuer, Zapfsaeule,
# vernachlaessigbar" und einmal korrekt "Gehaltserhöhung, Freibeträge". Die
# Prompt-Regel unter "Schreibweise:" ist die erste Verteidigung, das hier die
# zweite - auf einer veroeffentlichten Karte sieht "Heizoel" kaputt aus.
#
# Zurueckuebersetzt wird ueber Kontextregeln, nicht ueber eine Wortliste:
# Deutsch baut Komposita, und "Zapfsaeule" steht in keiner Liste. Die Regeln
# sind so geschnitten, dass sie im Zweifel NICHTS tun - ein verpasstes
# "Geuebte" ist harmlos, ein zerstoertes "Steuer" nicht.

# Echte ae/oe/ue, die keinen Umlaut meinen und die keine Kontextregel faengt.
_KEIN_UMLAUT = {
    "aerobic", "aerodynamik", "aerosol", "aeronautik", "maestro", "paella",
    "michael", "raphael", "rafael", "ismael", "israel", "haeckel",
    "poet", "poesie", "poem", "poetisch", "poetin",
    "koexistenz", "koeffizient", "koedukation", "koedieren",
    "goethe", "boeing", "oedipus", "soeben", "soehne",
    "statue", "statuen", "revue", "queue", "silhouette", "duett", "duell",
}

# ss -> ss oder ss -> ss? Das entscheidet die Vokallaenge, nicht der Kontext:
# "dass" und "Masse" sind korrekt, "heisst" und "gross" nicht. Regelbasiert
# ist das nicht zu haben, deshalb hier nur Staemme, die eindeutig sind.
# "Masse" fehlt mit Absicht - es ist ein echtes Wort neben "Masze".
_SZ_STAEMME = [
    ("groess", "größ"), ("gross", "groß"),
    ("heiss", "heiß"), ("schliess", "schließ"),
    ("strass", "straß"), ("massnahm", "maßnahm"),
    ("stoss", "stoß"), ("fuss", "fuß"), ("gruss", "gruß"),
    ("aeusser", "äußer"), ("ausser", "außer"), ("draussen", "draußen"),
]

_PAARE = {"ae": "ä", "oe": "ö", "ue": "ü"}
_VOKALE = set("aeiou")


def _ist_umlaut(wort: str, i: int, paar: str) -> bool:
    """Meint dieses ae/oe/ue an Position i wirklich einen Umlaut?

    Jede Bedingung hier steht fuer einen konkreten Schaden, den die naive
    Ersetzung anrichtet:

    - nach "q": "Quelle" wuerde zu "Qülle", "Konsequenz" zu "Konsequenz".
    - nach einem Vokal: "ue" ist dort das Ende eines Diphthongs plus e -
      "Steuer" wuerde zu "Steür", "Bauer" zu "Baür", "neuen" zu "neün".
      Das ist der gefaehrlichste Fall: "Steuer" ist in einem Politik-Digest
      haeufiger als jedes Wort, das wir reparieren wollen.
    - vor "ll" oder "tt": "aktuell", "eventuell", "Duett".
    - am Wortende: "Statue", "Revue", "Aloe", "neue".
    - "ael" am Wortende: "Michael", "Israel", "Raphael".

    Ein deutsches "ue" fuer "ü" steht praktisch immer hinter einem
    Konsonanten ("fuer", "Buero", "Gebuehr"), deshalb kostet die
    Vokal-Sperre nichts.
    """
    davor = wort[i - 1].lower() if i > 0 else ""
    danach = wort[i + 2:].lower()

    if not danach:                       # Statue, Revue, Aloe, neue
        return False
    if davor in _VOKALE:                 # Steuer, Bauer, neuen, Frauen
        return False
    if paar == "ue" and davor == "q":    # Quelle, Konsequenz, Frequenz
        return False
    if paar == "ue" and danach[:2] in ("ll", "tt"):   # aktuell, Duett
        return False
    if paar == "ae" and danach == "l":   # Michael, Israel, Raphael
        return False
    return True


def _wort_umlaute(wort: str) -> str:
    if wort.lower() in _KEIN_UMLAUT:
        return wort

    gebaut, i = [], 0
    while i < len(wort):
        paar = wort[i:i + 2].lower()
        um = _PAARE.get(paar)
        if um and _ist_umlaut(wort, i, paar):
            gebaut.append(um.upper() if wort[i].isupper() else um)
            i += 2
        else:
            gebaut.append(wort[i])
            i += 1
    return "".join(gebaut)


def umlaute_reparieren(wert):
    """Holt die Umschrift im ganzen Entwurf zurueck nach Deutsch.

    Rekursiv ueber Dicts, Listen und Strings, damit kein Feld vergessen
    wird - die Umschrift trat quer durch alle Slides auf.

    Auf fakten_evidence wirkt das neutral: _normalise bildet Beleg und
    Quelltext ohnehin beide auf ae/oe/ue ab, die Belegquote aendert sich
    dadurch nicht.
    """
    if isinstance(wert, dict):
        return {k: umlaute_reparieren(v) for k, v in wert.items()}
    if isinstance(wert, list):
        return [umlaute_reparieren(v) for v in wert]
    if not isinstance(wert, str):
        return wert

    text = wert
    for alt, neu in _SZ_STAEMME:
        text = re.sub(alt, lambda m: (neu.capitalize() if m.group()[0].isupper()
                                      else neu), text, flags=re.I)
    return re.sub(r"[A-Za-zÄÖÜäöüß]+", lambda m: _wort_umlaute(m.group()), text)


def _einwand_block(einwand: str) -> str:
    """Die Beanstandung des Faktenpruefers als Auftrag fuer den zweiten Versuch.

    Bewusst als Streich-Auftrag formuliert, nicht als Umschreib-Auftrag: die
    naheliegende Reaktion des Modells waere, dieselbe Behauptung vorsichtiger
    zu formulieren. Dann steht sie immer noch da, ist immer noch unbelegt,
    und der zweite Pruefdurchgang kostet nur ein zweites Mal Geld.
    """
    if not einwand.strip():
        return ""
    return f"""
ACHTUNG - ZWEITER VERSUCH. Dein erster Entwurf ist am Faktencheck
gescheitert. Die Beanstandung lautete:

    {einwand.strip()}

Schreib das Karussell neu und werde genau diese Aussage los. Streiche sie
oder ersetze sie durch etwas, das im Quelltext steht. Formuliere sie NICHT
vorsichtiger um - "moeglicherweise", "unter anderem" oder "weitgehend"
machen eine unbelegte Behauptung nicht belegt, sie verstecken sie nur.
Alles andere an deinem Entwurf war in Ordnung; aendere nur, was noetig ist.
"""


def compose(item: dict, recherche: dict, einwand: str = "") -> dict | None:
    """Schreibt die Slides. None, wenn das Thema nichts hergibt.

    `einwand` ist die Beanstandung des Faktenpruefers aus einem ersten
    Versuch. Sie wird dem Prompt angehaengt, damit der zweite Versuch die
    eine strittige Aussage loswird, statt das ganze Karussell zu verlieren.
    """
    zahlen = ", ".join(
        f"{b['label']}: {b['wert']} {b['einheit']}" for b in recherche.get("vorher_nachher", [])
    ) or "keine"

    kk = recherche.get("kaufkraft") or {}
    kaufkraft = (f"{kk['betrag']:g} {kk['einheit']} von {kk['jahr']} haetten heute "
                 f"etwa die Kaufkraft von {kk['heute_etwa']:g} {kk['einheit']} "
                 f"(gerechnet ueber {kk['jahre']} Jahre, Annahme: {kk['annahme']})"
                 if kk else "keine")

    try:
        # Gestreamt: bei max_tokens dieser Groesse laeuft ein normaler Aufruf
        # in den 10-Minuten-Timeout des SDK und wird danach zweimal wiederholt.
        # Der Aufwand bleibt hier bewusst hoch - das ist der Schreibschritt.
        with client.messages.stream(
            # Grosszuegig: das Modell denkt erst nach, und wenn das Budget
            # dabei aufgebraucht ist, kommt gar kein Textblock zurueck.
            model=config.MODEL_DRAFT, max_tokens=config.DRAFT_MAX_TOKENS,
            messages=[{"role": "user", "content": COMPOSE_PROMPT.format(
                source=item["source"], date=item["date"], title=item["title"],
                text=item["text"][:config.PRUEFTEXT_MAX_CHARS],
                erklaerung=recherche.get("erklaerung", "") or "keine",
                zahlen=zahlen, kaufkraft=kaufkraft,
                stand=verfahrensstand(item),
                einwand=_einwand_block(einwand),
                # Fehlt das Feld, bleibt es sachlich: Profil-Karussells und
                # alles, was nicht durch select_topics lief, hat keinen
                # Bereich - und darf dann auch keine Pointe setzen.
                bereich=item.get("bereich") or "unbekannt",
                betroffene=recherche.get("betroffene", "") or "unbekannt",
                alltagswirkung=recherche.get("alltagswirkung", "") or "unbekannt",
                sonderregel=STATISTIK_REGEL if item.get("art") == "statistik" else "",
                min_bars=config.CHART_MIN_BARS, max_bars=config.CHART_MAX_BARS)}],
        ) as stream:
            resp = stream.get_final_message()
        data = _json_from(_text_block(resp))
    except Exception as exc:
        print(f"  ! Komposition unlesbar: {exc}")
        return None

    if data.get("skip"):
        print(f"  - uebersprungen: {item['title'][:50]}")
        return None
    # Vor der Pruefung, nicht erst beim Rendern: so sehen Belegpruefung,
    # Faktencheck und Zwischenstand denselben Text wie spaeter die Karte.
    return umlaute_reparieren(data)


_JAHR = re.compile(r"(?:19|20)\d{2}")


_DATUM = re.compile(r"\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4})")

# Steuerfelder, kein Text: "muster": "4a" wuerde sonst als Zahl 4 gelten und
# einen Beleg fuer die Vier verlangen.
_KEIN_TEXT = {"muster", "symbol"}


def _texte(wert) -> list:
    """Alle Zeichenketten aus einer verschachtelten Modell-Ausgabe.

    `folgen` hat je nach Muster eine andere Form (Tabellenzeilen, Bedingungs-
    listen, zwei Fallkarten). Statt vier Sonderwege einzubauen, wird die
    Struktur eingesammelt, wie sie kommt: was Text ist, wird geprueft. Ein
    neues Feld im Muster ist damit automatisch mitgeprueft und nicht erst,
    wenn es jemandem auffaellt.
    """
    if isinstance(wert, str):
        return [wert]
    if isinstance(wert, dict):
        return [t for k, v in wert.items() if k not in _KEIN_TEXT
                for t in _texte(v)]
    if isinstance(wert, list):
        return [t for v in wert for t in _texte(v)]
    return []


def _sichtbarer_text(slides: dict) -> str:
    """Alles, was auf den Karten zu lesen ist, als ein Text.

    Eigene Funktion, weil zwei Pruefungen genau denselben Umfang brauchen:
    _slide_zahlen sammelt daraus die belegpflichtigen Zahlen, und
    abgeleitete_zahlen sucht darin das Signalwort vor einer gerundeten Zahl.
    Liefe die Hedge-Pruefung auf einem anderen Ausschnitt, koennte eine Zahl
    belegpflichtig sein, ihr "ueber" aber ausserhalb liegen.
    """
    return " ".join([
        slides.get("hook", ""),
        slides.get("titel", ""),
        # Steht auf dem Cover, wenn Variante 1b gezogen wird - eine Zahl darin
        # ist so oeffentlich wie jede andere und unterliegt derselben Pflicht.
        slides.get("cover_frage", "") or "",
        " ".join(slides.get("context", []) or []),
        " ".join(_texte(slides.get("begriff"))),
        (slides.get("sowhat") or {}).get("text", ""),
        " ".join((slides.get("sowhat") or {}).get("schritte", []) or []),
        " ".join(_texte(slides.get("folgen"))),
        ((slides.get("chart") or {}).get("hinweis", "")),
    ])


def _slide_zahlen(slides: dict) -> list:
    """Alle Zahlen aus allen Slides - die muessen belegt sein.

    Wichtig: die Balkenwerte des Diagramms gehoeren ausdruecklich dazu. Das
    Diagramm ist die auffaelligste und ueberzeugendste Slide - eine erfundene
    Zahl faellt dort am meisten ins Gewicht und muss genauso hart geprueft
    werden wie eine im Fliesstext. Dasselbe gilt fuer die Begriffskarte
    (Slide 3) und fuer jedes Muster der Folgen-Slide (Slide 4): dort steht die
    Zahl in Display-Groesse, also so gross wie nirgends sonst.
    """
    text = _sichtbarer_text(slides)
    # Jeder Eintrag ist eine Menge zulaessiger Schreibweisen EINER Zahl -
    # es genuegt, wenn eine davon im Beleg auftaucht (1200 oder 1.200).
    #
    # Jahreszahlen sind ausgenommen: "seit 2023 gilt ..." ist eine Zeitangabe,
    # keine Tatsachenbehauptung ueber eine Groesse. Sie woertlich im Quelltext
    # zu verlangen kippt sonst ein ganzes Karussell wegen eines Nebensatzes.
    # Balkenwerte bleiben voll geprueft - die kommen unten aus chart["balken"]
    # und nicht aus diesem Text, ein Jahr als Messwert faellt also nicht durch.
    #
    # Aus demselben Grund sind ausgeschriebene Daten ausgenommen: die Quelle
    # schreibt "1. Januar 2027", die Karte "01.01.27" - woertlich findet sich
    # das nie, obwohl beides dasselbe Datum meint. Erfunden ist es deshalb
    # nicht ungeprueft: der Faktencheck sieht die Folgen-Slide.
    roh = _DATUM.sub(" ", text)
    zahlen = [{treffer} for treffer in re.findall(r"\d[\d.,]*", roh)
              if not _JAHR.fullmatch(treffer.rstrip(".,"))]

    for balken in (slides.get("chart") or {}).get("balken", []) or []:
        try:
            wert = float(balken.get("wert"))
        except (TypeError, ValueError):
            continue
        if wert.is_integer():
            zahlen.append({str(int(wert)), f"{int(wert):,}".replace(",", ".")})
        else:
            zahlen.append({str(wert), str(wert).replace(".", ",")})
    return zahlen


def recherche_zahlen(recherche: dict) -> set:
    """Alle Schreibweisen der Zahlen, die die Recherche mit Fundstelle belegt.

    Im Fliesstext steht "300.000", in der Recherche 300000.0 - ohne die
    deutsche Schreibweise galt eine sauber belegte Zahl als unbelegt.
    """
    zahlen = set()
    for b in recherche.get("vorher_nachher", []) or []:
        if not b.get("quelle_url"):
            continue
        wert = b["wert"]
        zahlen.add(str(int(wert)) if float(wert).is_integer() else str(wert))
        zahlen.add(str(wert).replace(".", ","))
        if float(wert).is_integer():
            zahlen.add(f"{int(wert):,}".replace(",", "."))

    # Der Kaufkraft-Gegenwert steht in keinem Quelltext - er ist gerechnet.
    # Belegt ist er trotzdem, nur anders als die uebrigen Zahlen: nicht durch
    # eine Fundstelle, sondern dadurch, dass research._kaufkraft ihn aus zwei
    # im Quelltext geprueften Zahlen nach einer offengelegten Annahme
    # ermittelt hat. Deshalb kommt hier genau der berechnete Wert durch und
    # kein anderer - schreibt das Modell eine eigene Zahl in den Balken,
    # faellt sie durch.
    kaufkraft = recherche.get("kaufkraft") or {}
    if kaufkraft.get("heute_etwa"):
        zahlen |= _schreibweisen(kaufkraft["heute_etwa"])
    return zahlen


# Mehr als eine Handvoll selbstgewaehlter Zahlen ist kein Rechenbeispiel mehr,
# sondern eine Hintertuer an der Belegpflicht vorbei.
BEISPIELWERTE_MAX = 6


def beispielwerte(slides: dict) -> set:
    """Die Zahlen, die das Modell als Rechenbeispiel deklariert hat.

    Das Design-System verlangt auf der Begriffskarte ein gerechnetes Beispiel,
    und eine Rechnung braucht einen Ausgangswert ("aus 100 Euro werden
    104,60 Euro"). Solche Zahlen stehen naturgemaess in keiner Quelle - die
    woertliche Pruefung hat daran ganze Karussells scheitern lassen.

    Deshalb duerfen sie hier durch, aber nur deklariert und nur wenige. Ob es
    wirklich Beispiele sind und ob die Rechnung aufgeht, beurteilt der
    Faktencheck: judge_slides bekommt dieselbe Liste vorgelegt.
    """
    werte = set()
    for wert in (slides.get("beispielwerte") or [])[:BEISPIELWERTE_MAX]:
        werte |= _schreibweisen(wert)
    return werte


def _zahl_aus(wert) -> float | None:
    """Die Zahl aus einem Feld, das auch die Anzeigeform tragen kann.

    Das Modell schreibt in "wert" das, was auf der Karte steht - "ueber 70",
    "2,6-fache". Beides ist als Angabe richtig und als float unlesbar. Ein
    strenges float() hat solche Eintraege verworfen, und zwar lautlos: die
    Zahl fiel danach als unbelegt durch, ohne dass der Grund zu sehen war.
    """
    if isinstance(wert, (int, float)):
        return float(wert)
    treffer = re.search(r"\d[\d.]*(?:,\d+)?", str(wert or ""))
    if not treffer:
        return None
    try:
        return float(treffer.group().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _schreibweisen(wert) -> set:
    """Die zulaessigen Schreibweisen einer Zahl (1200, 1.200, 104,60).

    Im Fliesstext steht die deutsche Form, im JSON die englische. Ohne beide
    Formen galt eine sauber belegte Zahl als unbelegt.
    """
    try:
        zahl = float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        return set()
    if zahl.is_integer():
        return {str(int(zahl)), f"{int(zahl):,}".replace(",", ".")}
    return {f"{zahl:g}",
            f"{zahl:g}".replace(".", ","),
            f"{zahl:.2f}".replace(".", ",")}


# Dieselbe Deckelung wie bei den Beispielwerten und aus demselben Grund: eine
# Handvoll Ableitungen ist eine Rechnung, zwanzig sind eine Umgehung.
ABGELEITETE_MAX = 6

# Wie weit eine gerundete Zahl vom gerechneten Ergebnis abweichen darf.
# 71 Jahre als "ueber 70" sind 1,4 Prozent - 71 als "ueber 50" waere Unsinn.
RUNDUNG_TOLERANZ = 0.05

# Signalwoerter vor einer gerundeten Zahl. Die Richtung ist der eigentliche
# Pruefpunkt: "ueber 70" ist richtig, wenn in Wahrheit 71 herauskommt, und
# schlicht falsch, wenn es 69 sind. Ohne diese Unterscheidung waere die
# Aufweichung eine Erlaubnis zum Aufrunden in die gewuenschte Richtung.
_HEDGE_UNTEN = re.compile(          # behauptet weniger, als herauskommt
    r"(ueber|über|mehr als|laenger als|länger als|gut|seit gut)\s*$", re.I)
_HEDGE_OBEN = re.compile(           # behauptet mehr, als herauskommt
    r"(knapp|fast|beinahe|unter|weniger als|bis zu)\s*$", re.I)
_HEDGE_BEIDE = re.compile(          # richtungslos, deckt beides ab
    r"(rund|etwa|circa|ca\.?|ungefaehr|ungefähr|gegen|in etwa)\s*$", re.I)


# Wie viele geltende Ziffern eine gerundete Zahl behalten muss.
#
# Eine Prozentgrenze waere hier das falsche Mass, weil sie an der
# Groessenordnung haengt: dieselbe Rundung auf eine Nachkommastelle weicht
# bei 2,13 um 1,6 Prozent ab und bei 12,3 um 0,4. Geltende Ziffern sind
# skalenfrei und treffen genau die Unterscheidung, um die es geht -
# 2,13464 als "2,1" ist Genauigkeit wegnehmen, als "2" ist es eine
# Behauptung ueber die Groessenordnung.
GELTENDE_ZIFFERN_MIN = 2


def _gerundet_zulaessig(wert: float, ergebnis: float, text: str) -> bool:
    """Darf 'wert' als gerundete Fassung von 'ergebnis' auf die Karte?

    Zwei Arten von Rundung, und sie verlangen Verschiedenes.

    Die erste ist blosses Stellenkuerzen: 2,13464 wird zu "2,13". Der Wert
    ist die exakt gerundete Zahl und weicht um Bruchteile ab - dafuer
    braucht es kein Signalwort, denn er behauptet nichts Zusaetzliches.
    Diese Art fehlte zuerst ganz: die Regel war fuer "ueber 70" gebaut und
    verlangte eine ganze Zahl als Vielfaches von 5, sodass ein sauber auf
    zwei Stellen gerundeter Faktor durchfiel.

    Die zweite ist grobes Runden: 71 wird zu "70". Da verschiebt sich die
    Aussage, deshalb bleiben hier alle drei Bedingungen noetig - kleine
    Abweichung, glatte Zahl, und ein Signalwort, dessen Richtung passt.
    """
    if ergebnis == 0:
        return False

    # Stellenkuerzen: exakt auf n Stellen gerundet, und es bleiben genug
    # geltende Ziffern stehen. Die Rundung selbst garantiert schon, dass die
    # Abweichung hoechstens eine halbe Stelle betraegt - zu pruefen bleibt
    # nur, ob ueberhaupt noch Information uebrig ist.
    for stellen in (0, 1, 2, 3):
        if abs(wert - round(ergebnis, stellen)) > 1e-9 or wert == 0:
            continue
        ziffern = math.floor(math.log10(abs(wert))) + 1 + stellen
        if ziffern >= GELTENDE_ZIFFERN_MIN:
            return True

    if not float(wert).is_integer():
        return False
    if abs(wert - ergebnis) / abs(ergebnis) > RUNDUNG_TOLERANZ:
        return False
    if int(wert) % 5 != 0:
        return False

    # Das Signalwort steht unmittelbar vor der Zahl, nicht irgendwo auf der
    # Karte: "rund" im Nachbarsatz belegt diese Rundung nicht.
    for form in _schreibweisen(wert):
        for treffer in re.finditer(rf"(?<!\d){re.escape(form)}(?!\d)", text):
            davor = text[max(0, treffer.start() - 30):treffer.start()]
            if _HEDGE_BEIDE.search(davor):
                return True
            if wert < ergebnis and _HEDGE_UNTEN.search(davor):
                return True
            if wert > ergebnis and _HEDGE_OBEN.search(davor):
                return True
    return False


def abgeleitete_zahlen(slides: dict, quelltext: str, belegt: set,
                       leise: bool = False) -> set:
    """Zahlen, die das Modell aus belegten Zahlen ausgerechnet hat.

    Der Unterschied zum Rechenbeispiel ist der Grund, warum es diese Funktion
    gibt: ein Beispielwert ist erfunden und kann nur plausibilisiert werden,
    eine Ableitung ist gerechnet und laesst sich nachrechnen. "Seit ueber 70
    Jahren unveraendert" fiel bisher durch, weil die 70 in keiner Quelle
    steht - obwohl 2026 und 1955 beide im Quelltext stehen und die Rechnung
    aufgeht. Hier wird deshalb nicht geglaubt, sondern nachgerechnet.

    Beide Operanden muessen selbst belegt sein. Ohne diese Bedingung waere
    die Ableitung eine Waschanlage: eine erfundene Zahl plus eine erfundene
    Rechnung ergaebe ein "geprueftes" Ergebnis.
    """
    text = _sichtbarer_text(slides)
    freigegeben = set()

    for eintrag in (slides.get("abgeleitete_zahlen") or [])[:ABGELEITETE_MAX]:
        if not isinstance(eintrag, dict):
            continue
        art = str(eintrag.get("rechnung", "")).lower()
        wert = _zahl_aus(eintrag.get("wert"))
        aus = [_zahl_aus(o) for o in eintrag.get("aus") or []]
        if wert is None or not aus or any(o is None for o in aus):
            if not leise:
                print(f"  x Ableitung {eintrag.get('wert')!r}: Zahl nicht lesbar")
            continue

        if not all(zahl_belegt(_schreibweisen(o), quelltext, belegt) for o in aus):
            if not leise:
                print(f"  x Ableitung {eintrag.get('wert')}: Operand selbst unbelegt")
            continue

        # Beide Reihenfolgen gelten. Das Modell listet die Operanden so auf,
        # wie sie in der Quelle stehen - chronologisch "aus": [25, 65] -,
        # meint aber den Faktor 65/25. Die Reihenfolge zu erzwingen haette
        # ein sauber gerechnetes Karussell an einer Formalie scheitern
        # lassen. Die Garantie bleibt dieselbe: der Wert stammt aus belegten
        # Zahlen, ist also nicht erfunden. Ob die Karte ihn richtig
        # bezeichnet ("2,6-fache" und nicht "auf 2,6 Prozent"), beurteilt
        # der Faktencheck - dort liegt Abschnitt G.
        if art == "summe" and len(aus) >= 2:
            kandidaten = [sum(aus)]
        elif art == "differenz" and len(aus) == 2:
            kandidaten = [abs(aus[0] - aus[1])]
        elif art == "anteil" and len(aus) == 2 and all(aus):
            kandidaten = [aus[0] / aus[1] * 100, aus[1] / aus[0] * 100]
        elif art == "faktor" and len(aus) == 2 and all(aus):
            kandidaten = [aus[0] / aus[1], aus[1] / aus[0]]
        else:
            if not leise:
                print(f"  x Ableitung {eintrag.get('wert')}: "
                      f"Rechenart '{art}' unbrauchbar")
            continue

        if any(abs(wert - e) < 1e-9 or _gerundet_zulaessig(wert, e, text)
               for e in kandidaten):
            freigegeben |= _schreibweisen(wert)
        elif not leise:
            moeglich = " oder ".join(f"{e:g}" for e in kandidaten)
            print(f"  x Ableitung geht nicht auf: {art}{aus} = {moeglich}, "
                  f"behauptet {wert:g}")

    return freigegeben


def abgeleitete_eintraege(slides: dict, item: dict, recherche: dict) -> list:
    """Nur die Ableitungen, die die Nachrechnung bestanden haben.

    Der Faktenpruefer bekommt sie mit der Zusicherung vorgelegt, dass die
    Rechnung aufgeht (Abschnitt G). Ohne diese Filterung war die Zusicherung
    falsch: eine verworfene Ableitung blieb im Entwurf stehen und wurde
    mitgeschickt. Gemessen an einem echten Lauf: das Modell hatte eine
    Ableitung deklariert, sie dann aber nirgends auf der Karte verwendet -
    der Pruefer sah die falsche Zusicherung, rechnete nach, widersprach zu
    Recht und verwarf ein fehlerfreies Karussell.

    Verworfene Ableitungen schaden nicht: ihre Zahl ist damit schlicht
    unbelegt und faellt in verify_slides durch, falls sie doch auf einer
    Slide steht.
    """
    frei = abgeleitete_zahlen(slides, item.get("text", ""),
                              recherche_zahlen(recherche or {}), leise=True)
    return [e for e in (slides.get("abgeleitete_zahlen") or [])
            if isinstance(e, dict) and _schreibweisen(_zahl_aus(e.get("wert"))) & frei]


def zahl_belegt(varianten: set, quelltext: str, belegt: set) -> bool:
    """Steht eine dieser Schreibweisen im Quelltext oder in der Recherche?

    Eigene Funktion, weil debug_lauf.py dieselbe Frage beantworten muss. Als
    zweite, knappere Fassung dort hat sie eine sauber belegte Zahl als
    "NIRGENDS" gemeldet, obwohl verify_slides sie zu Recht durchliess - ein
    Pruefbericht, der Fehlalarm gibt, ist schlimmer als keiner.
    """
    if any(v in quelltext for v in varianten):
        return True
    if varianten & belegt:
        return True
    return bool({v.replace(".", ",") for v in varianten} & belegt)


# Ein Fragment, das hierauf endet, ist kein Satzende: im Deutschen tragen
# Ordnungszahlen einen Punkt ("Mittwoch, 23. September"), Abkuerzungen auch.
_SATZ_WEITER = re.compile(
    r"\b(?:\d+|Nr|Abs|Art|Drs|Ziff|Buchst|Mio|Mrd|bzw|ca|evtl|ggf|inkl|sog"
    r"|vgl|betr|Prof|Dr|z|B|u|a|d|h|i|S)\.$")


def saetze(text: str) -> list:
    """Den Belegtext in Saetze zerlegen, ohne an Datumsangaben zu zerbrechen.

    Ein blosses split an [.!?] zerlegt "Der Bundestag beraet am Mittwoch,
    23. September 2026, erstmals ueber ..." in zwei Haelften. Beide sind
    danach kurz, und die kuerzere ist mit 35 Zeichen so kurz, dass die
    Belegquote sie kaum noch bewerten kann. In den Quelltexten eines
    einzigen Laufs standen 36 solcher Datumspunkte.

    Die Zusammenfuehrung ist ausserdem die strengere Pruefung: zwei
    unabhaengig gepruefte Haelften koennen beide woertlich in der Quelle
    stehen und trotzdem falsch zusammengesetzt sein. Ein Satz am Stueck
    schliesst das aus.

    Zwei echte Saetze zu verschmelzen schadet dabei nicht: der Beleg ist ein
    Zitat, aufeinanderfolgende Saetze stehen also auch in der Quelle
    nebeneinander und werden weiterhin am Stueck gefunden.
    """
    teile = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    gebaut = []
    for teil in teile:
        if not teil:
            continue
        if gebaut and _SATZ_WEITER.search(gebaut[-1]):
            gebaut[-1] += " " + teil
        else:
            gebaut.append(teil)
    return gebaut


def mindestblock(norm: str) -> int:
    """Ab welcher Blocklaenge eine Uebereinstimmung zaehlt.

    Eigene Funktion, damit der Pruefbericht denselben Wert nennt, nach dem
    die Pruefung entscheidet - eine zweite Fassung der Formel waere genau
    die Art Fehlalarm, gegen die zahl_belegt() geschrieben wurde.

    Die feste Grenze aus config passt fuer einen Satz von 300 Zeichen. Bei
    einem kurzen Satz ist sie unerreichbar: 16 zusammenhaengende Zeichen von
    35 verlangt zu viel, und wenn die Uebereinstimmung sich auf zwei Stuecke
    verteilt, steht am Ende 0.00 - was nach Halluzination aussieht, aber ein
    Rechenartefakt ist. Deshalb zaehlt bei kurzen Saetzen der Anteil: ein
    Block muss ein Drittel des Satzes ausmachen. Viel Raum zum
    Umformulieren hat ein so kurzer Satz ohnehin nicht, und die
    Zahlenpruefung greift unabhaengig davon.
    """
    return min(config.EVIDENCE_MIN_BLOCK, max(6, len(norm) // 3))


def belegquote(norm: str, quelle: str) -> float:
    """Wie viel des Belegsatzes steht woertlich in der Quelle?

    Gewertet wird die Summe aller Uebereinstimmungen, nicht mehr nur der
    laengste zusammenhaengende Block. Grund: die Bundestag-Seite schiebt
    mitten in ihre Saetze einen Drucksachen-Verweis ein - "... retten"
    ( 21/8115 (Dokument, oeffnet ein neues Fenster) ) vor, der ...". Wer
    korrekt zitiert und den Einschub weglaesst, zerlegt den Satz damit in
    zwei Haelften, und der laengste Block war nur noch eine davon
    (gemessen: 0.61 bei woertlichem Zitat). In den Quelltexten eines
    einzigen Laufs steckte dieser Einschub 34-mal.

    Gezaehlt werden nur Bloecke ab mindestblock() Zeichen. Ohne diese
    Grenze summieren sich die "und", "der", "in" einer freien Paraphrase zu
    einer hohen Quote: eine erfundene Aussage aus lauter Quellvokabular kam
    ungefiltert auf 0.98. Ein Block von 16 zusammenhaengenden Zeichen ist
    kein Zufall mehr, eine Silbe schon.

    difflib liefert die Bloecke in gleicher Reihenfolge in beiden Texten.
    Umgestellte Satzteile zaehlen also nicht doppelt.
    """
    if not norm:
        return 0.0
    if norm in quelle:
        return 1.0
    # autojunk=False ist hier zwingend: difflib haelt ab 200 Elementen alles
    # fuer "junk", was in ueber 1 % der Sequenz vorkommt - bei einem
    # 24.000-Zeichen-Quelltext also jeden gewoehnlichen Buchstaben.
    matcher = difflib.SequenceMatcher(None, norm, quelle, autojunk=False)
    grenze = mindestblock(norm)
    treffer = sum(block.size for block in matcher.get_matching_blocks()
                  if block.size >= grenze)
    return min(1.0, treffer / len(norm))


def evidenz_zahl_erfunden(satz: str, quelltext: str) -> str | None:
    """Die erste Zahl des Belegsatzes, die nicht im Quelltext steht.

    Diese Pruefung haengt unmittelbar an belegquote(): solange nur der
    laengste Block zaehlte, war sie entbehrlich, weil eine ausgetauschte
    Zahl den Satz in der Mitte zerriss und die Quote von selbst einbrach
    (gemessen: 0.67, durchgefallen). Die Summe aller Bloecke ueberspringt
    genau diese eine Stelle - derselbe Satz mit "250 Euro seit 1975" statt
    "102 Euro seit 1955" kam damit auf 0.97 und waere durchgegangen.

    Ein Beleg ist ein Zitat. Eine Zahl, die darin steht und in der Quelle
    nicht, ist deshalb keine Abweichung, sondern eine Faelschung - und zwar
    die gefaehrlichste Sorte, weil der Satz ringsum echt ist.
    """
    for treffer in re.findall(r"\d[\d.,]*", satz):
        varianten = {treffer.rstrip(".,")}
        varianten |= _schreibweisen(treffer.rstrip(".,").replace(".", ""))
        if not zahl_belegt(varianten, quelltext, set()):
            return treffer
    return None


def verify_slides(slides: dict, item: dict, recherche: dict) -> bool:
    """Woertliche Belegpruefung der harten Fakten.

    Geprueft wird gegen den Quelltext unserer amtlichen Quelle. Zahlen, die
    nachweislich aus der Recherche stammen (Vergleichswerte mit Fundstelle),
    sind davon ausgenommen - sie tragen ihre eigene Quellenangabe und werden
    vom Faktencheck beurteilt, nicht woertlich gematcht.

    Drei Ausnahmen von der woertlichen Pflicht, jede mit eigener Absicherung:
    deklarierte Rechenbeispiele (beispielwerte, gedeckelt, gehen an den
    Faktencheck), aus belegten Zahlen ausgerechnete Werte (abgeleitete_zahlen,
    hier nachgerechnet) und Recherche-Zahlen mit Fundstelle.

    Beim Belegsatz selbst gibt es keine Ausnahme: dort zaehlt die Summe aller
    Uebereinstimmungen (belegquote), und zusaetzlich muss jede Zahl im Satz in
    der Quelle stehen (evidenz_zahl_erfunden). Das Paar gehoert zusammen - die
    Summenwertung allein liesse einen echten Satz mit ausgetauschter Zahl mit
    0.97 durch.
    """
    evidence_raw = slides.get("fakten_evidence", "")
    if len(_normalise(evidence_raw)) < 20:
        print(f"  x kein Beleg: {slides.get('titel', '')[:40]}")
        return False

    quelle = _normalise(item.get("text", ""))
    quelltext_roh = item.get("text", "")
    for sentence in saetze(evidence_raw):
        norm = _normalise(sentence)
        if not norm:
            continue
        ratio = belegquote(norm, quelle)
        if ratio < config.EVIDENCE_THRESHOLD:
            print(f"  x Beleg-Satz nicht in Quelle ({ratio:.2f}): {sentence[:60]}")
            return False
        # Untrennbar von der Quote oben: siehe evidenz_zahl_erfunden().
        erfunden = evidenz_zahl_erfunden(sentence, quelltext_roh)
        if erfunden:
            print(f"  x Beleg-Satz nennt Zahl {erfunden}, die nicht in der "
                  f"Quelle steht: {sentence[:60]}")
            return False

    # Jede Zahl muss entweder im Quelltext stehen oder aus der Recherche mit
    # Fundstelle stammen. Alles andere waere eine erfundene Zahl.
    belegt = recherche_zahlen(recherche)
    beispiele = beispielwerte(slides)
    quelltext = item.get("text", "")
    abgeleitet = abgeleitete_zahlen(slides, quelltext, belegt)
    for schreibweisen in _slide_zahlen(slides):
        varianten = {w.rstrip(".,") for w in schreibweisen}
        if zahl_belegt(varianten, quelltext, belegt):
            continue
        # Deklariertes Rechenbeispiel: der Faktencheck prueft es weiter.
        if varianten & beispiele:
            continue
        # Aus belegten Zahlen ausgerechnet und hier bereits nachgerechnet.
        if varianten & abgeleitet:
            continue
        print(f"  x Zahl {sorted(varianten)[0]} weder in Quelle noch in Recherche belegt")
        return False

    return True


def _recherche_belege(recherche: dict) -> str:
    """Die Recherche-Ergebnisse als Belegliste fuer den Faktenpruefer.

    Ohne diesen Block sah der Pruefer nur die amtliche Quelle und musste jeden
    recherchierten Hintergrund fuer unbelegt halten - obwohl research.py ihn
    ausdruecklich an den Faktencheck verweist. Zahlen kommen mit ihrer
    Fundstelle, damit der Pruefer Beleg und Behauptung trennen kann.
    """
    if not recherche:
        return "keine"

    zeilen = []
    if recherche.get("erklaerung"):
        zeilen.append(f"Einordnung: {recherche['erklaerung']}")
    if recherche.get("betroffene"):
        zeilen.append(f"Betroffene: {recherche['betroffene']}")
    if recherche.get("alltagswirkung"):
        zeilen.append(f"Alltagswirkung: {recherche['alltagswirkung']}")
    for b in recherche.get("vorher_nachher", []) or []:
        zeilen.append(f"Vergleichswert {b['label']}: {b['wert']} {b['einheit']} "
                      f"(Fundstelle: {b.get('quelle_url', 'ohne')})")
    kk = recherche.get("kaufkraft") or {}
    if kk:
        zeilen.append(
            f"Kaufkraft: {kk['betrag']:g} {kk['einheit']} von {kk['jahr']} "
            f"haetten heute etwa die Kaufkraft von {kk['heute_etwa']:g} "
            f"{kk['einheit']}. Das ist gerechnet, nicht gemessen - Annahme: "
            f"{kk['annahme']} ueber {kk['jahre']} Jahre. Die Karte darf ihn "
            f"nur als Schaetzung ausgeben und muss die Annahme nennen.")
    return chr(10).join(zeilen) or "keine"


def judge_slides(slides: dict, item: dict,
                 recherche: dict | None = None) -> tuple:
    """KI-Faktencheck fuer Context und So-what (dort gibt es keinen
    woertlichen Beleg, den Code pruefen koennte).

    Liefert (bestanden, einwand). Der Einwand ist der Grund, nicht nur die
    Ablehnung: build_carousels gibt ihn dem Modell fuer EINEN zweiten
    Versuch zurueck. Vorher wurde ein komplettes Karussell samt bezahlter
    Recherche und Entwurf wegen eines einzigen Satzes verworfen - bei einem
    Thema dreimal hintereinander, jedes Mal wegen einer anderen Aussage.

    `recherche` gehoert zwingend dazu, wo es eine gibt: research.py nimmt den
    recherchierten Hintergrund bewusst von der woertlichen Belegpruefung aus
    und verweist ihn hierher. Fehlt er hier, ist er nirgends belegt und faellt
    zwangslaeufig durch - unabhaengig davon, ob er stimmt.
    """
    sowhat = slides.get("sowhat") or {}
    sowhat_text = sowhat.get("text", "")
    if sowhat.get("schritte"):
        sowhat_text += "\nSchritte: " + " | ".join(sowhat["schritte"])

    try:
        resp = client.messages.create(
            # Ja/Nein-Pruefung mit kurzer JSON-Antwort - hier ist langes
            # Nachdenken verschwendete Zeit und verschwendete Output-Tokens.
            model=config.MODEL_JUDGE, max_tokens=config.JUDGE_MAX_TOKENS,
            output_config={"effort": config.EFFORT_JUDGE},
            messages=[{"role": "user", "content": JUDGE_PROMPT.format(
                fakten=item.get("text", "")[:config.PRUEFTEXT_MAX_CHARS],
                recherche=_recherche_belege(recherche or {}),
                stand=verfahrensstand(item),
                titel=slides.get("titel") or "keine",
                hook=slides.get("hook") or "keine",
                context="\n".join(slides.get("context", []) or []),
                art=sowhat.get("art", "keine"),
                sowhat=sowhat_text or "keine",
                # Als JSON, nicht als Fliesstext: das Muster und die Zuordnung
                # von Label zu Wert sind Teil der Aussage, die geprueft wird.
                begriff=json.dumps(slides.get("begriff") or "keine",
                                   ensure_ascii=False),
                folgen=json.dumps(slides.get("folgen") or "keine",
                                  ensure_ascii=False),
                beispielwerte=json.dumps(slides.get("beispielwerte") or "keine",
                                         ensure_ascii=False),
                # Nur die nachgerechneten: siehe abgeleitete_eintraege().
                abgeleitete=json.dumps(
                    abgeleitete_eintraege(slides, item, recherche) or "keine",
                    ensure_ascii=False),
                cover_frage=slides.get("cover_frage") or "keine")}],
        )
        data = _json_from(_text_block(resp))
    except Exception as exc:
        print(f"  ! Faktencheck fehlgeschlagen: {exc}")
        # Kein Einwand, sondern ein Ausfall: daran kann das Modell nichts
        # verbessern, ein zweiter Versuch waere nur ein zweiter Ausfall.
        return False, ""

    if not data.get("ok"):
        problem = str(data.get("problem") or "ohne Begruendung")
        print(f"  x Faktencheck durchgefallen: {problem[:120]}")
        return False, problem
    return True, ""


def build_carousels(items: list, recherche_fn, anzahl: int | None = None,
                    themen: list | None = None) -> list:
    """Kompletter Durchlauf: auswaehlen, recherchieren, schreiben, pruefen.

    `themen` heisst: die Auswahl ist schon getroffen (Destatis waehlt nach
    eigener Regel, siehe destatis_auswahl) - dann wird nur noch geschrieben
    und geprueft. Die Reihenfolge ist die Rangfolge, alles hinter `anzahl`
    ist Reserve.
    """
    anzahl = anzahl or config.CAROUSELS_PER_RUN
    if themen is None:
        print("Themen werden ausgewaehlt ...")
        # Mehr waehlen als gebraucht: faellt ein Thema durch die Pruefung,
        # rueckt ein Ersatz aus DERSELBEN Quelle nach. Vorher kostete ein
        # Durchfaller der Quelle ihren Slot, obwohl noch neun beschlossene
        # Gesetze bereitlagen.
        themen = select_topics(items, anzahl + config.THEMEN_RESERVE)
    if not themen:
        print("  = kein alltagsrelevantes Thema gefunden")
        return []
    for i, t in enumerate(themen):
        rolle = "  +" if i < anzahl else "  ." # "." = Reserve, nur bei Ausfall
        print(f"{rolle} {t['title'][:70]}")

    # Die Themen haengen nicht voneinander ab, und jede Stufe wartet fast nur
    # auf das Netz: die Recherche macht mehrere Websuchen, die anderen Stufen
    # sind Modellaufrufe. Nacheinander addieren sich die Wartezeiten einfach.
    # Reihenfolge der Ausgabe bleibt die der Auswahl, damit der Lauf lesbar
    # bleibt - deshalb Ergebnisse einsammeln und erst am Ende sortieren.
    def _ein_thema(nummer_und_item):
        nummer, item = nummer_und_item
        print(f"Recherche: {item['title'][:55]} ...")
        # Erst den besten verfuegbaren Quelltext holen, dann recherchieren und
        # schreiben: verify_slides() prueft den Beleg-Satz gegen item["text"],
        # ein abgeschnittener RSS-Teaser laesst also auch ein sauber belegtes
        # Karussell durchfallen.
        sources.ensure_volltext(item)
        recherche = recherche_fn(item)

        # Zwei Anlaeufe: faellt der Faktencheck, bekommt das Modell seine
        # Beanstandung zurueck und schreibt einmal neu. Ein Karussell
        # scheitert in der Praxis an einem einzigen Satz, nicht am ganzen
        # Entwurf - und Recherche wie Entwurf sind da laengst bezahlt.
        #
        # Die Belegpruefung ist bewusst NICHT in der Schleife: ein
        # Beleg-Satz, der nicht im Quelltext steht, ist kein
        # Formulierungsproblem, sondern ein Thema, das der Quelltext nicht
        # hergibt. Ein zweiter Versuch waere dort nur ein zweiter Fehlschlag.
        einwand = ""
        for versuch in (1, 2):
            slides = compose(item, recherche, einwand)
            if not slides:
                return nummer, None
            if not verify_slides(slides, item, recherche):
                return nummer, None
            bestanden, einwand = judge_slides(slides, item, recherche)
            if bestanden:
                if versuch == 2:
                    print(f"  ok nach Ueberarbeitung: {slides.get('titel', '')[:48]}")
                else:
                    print(f"  ok {slides.get('titel', '')[:60]}")
                return nummer, {"item": item, "slides": slides,
                                "recherche": recherche}
            if not einwand:
                return nummer, None     # Ausfall, kein Einwand
            if versuch == 1:
                print(f"  ~ zweiter Versuch: {item['title'][:50]}")
        return nummer, None

    # In Saetzen statt alle auf einmal: die Reserve wird nur angefasst, wenn
    # aus dem ersten Satz zu wenig bestanden hat. Alle vier parallel zu
    # starten waere einfacher, wuerde aber jedes Mal vier Recherchen und vier
    # Entwuerfe bezahlen - auch an den Tagen, an denen die ersten beiden
    # durchgehen.
    warteschlange = list(enumerate(themen))
    ergebnisse, versucht = [], 0

    while warteschlange and sum(1 for _, c in ergebnisse if c) < anzahl:
        fehlend = anzahl - sum(1 for _, c in ergebnisse if c)
        satz, warteschlange = warteschlange[:fehlend], warteschlange[fehlend:]
        versucht += len(satz)
        if ergebnisse:
            print(f"Ersatz fuer {len(satz)} ausgefallene(s) Thema/Themen ...")
        print(f"Recherche und Entwurf fuer {len(satz)} Themen (parallel) ...")
        with ThreadPoolExecutor(max_workers=len(satz)) as pool:
            for future in as_completed(pool.submit(_ein_thema, ni)
                                       for ni in satz):
                try:
                    ergebnisse.append(future.result())
                except Exception as exc:
                    print(f"  ! Thema fehlgeschlagen: {exc}")

    fertig = [c for _, c in sorted(ergebnisse, key=lambda x: x[0]) if c]
    print(f"  = {len(fertig)} von {versucht} versuchten Karussells "
          f"bestanden die Pruefung")
    return fertig
