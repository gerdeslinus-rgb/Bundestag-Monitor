"""Alle Pruefungen nacheinander. Kein Modellaufruf, kein Netz, keine Kosten.

    python tests/alle.py

Was hier geprueft wird, ist die Maschinerie hinter der Belegpflicht - also
genau die Stellen, an denen ein Fehler nicht auffaellt, sondern still eine
falsche Karte erzeugt. Zwei Beispiele aus der Entstehung:

- Eine naive Umlaut-Reparatur macht aus "Steuer" ein "Steuer" mit Umlaut.
  In einem Politik-Digest ist das das haeufigste Wort ueberhaupt.
- Die Belegquote zaehlt die Summe aller Uebereinstimmungen. Ein echter
  Quellsatz mit EINER ausgetauschten Ziffer kam damit auf 0.99 - gefangen
  wird er allein von der Zahlenpruefung daneben.

Beides faellt nur auf, wenn jemand die Faelle einzeln durchgeht. Das tut
diese Datei.

pruefe_trennung.py laeuft hier bewusst NICHT mit: es braucht Playwright und
die Webschriften, dauert dadurch deutlich laenger und beurteilt ein Bild,
kein Ja/Nein. Ruf es einzeln auf, wenn du an Schlagzeilen oder Silben-
trennung etwas aenderst.
"""
import os
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)

SUITEN = [
    ("Umlaute", "test_umlaute.py"),
    ("Belegpruefung", "test_belegpruefung.py"),
    ("Satzzerlegung", "test_saetze.py"),
    ("Abgeleitete Zahlen", "test_abgeleitete_zahlen.py"),
    ("Kaufkraft", "test_kaufkraft.py"),
    ("Datenkarussells", "test_datenkarussells.py"),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fehler = []
    for name, datei in SUITEN:
        lauf = subprocess.run([sys.executable, os.path.join(HIER, datei)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=WURZEL)
        letzte = [z for z in (lauf.stdout or "").splitlines() if z.strip()]
        ergebnis = letzte[-1] if letzte else "keine Ausgabe"
        marke = "OK  " if lauf.returncode == 0 else "FEHL"
        print(f"  {marke} {name:<22} {ergebnis}")
        if lauf.returncode != 0:
            fehler.append((name, lauf))

    # Bei einem Fehlschlag die volle Ausgabe zeigen: die Zusammenfassung
    # sagt, DASS etwas kaputt ist, nicht welcher Fall.
    for name, lauf in fehler:
        print(f"\n{'=' * 62}\n{name}\n{'=' * 62}")
        print(lauf.stdout)
        if lauf.stderr.strip():
            print(lauf.stderr)

    print()
    print("ALLE BESTANDEN" if not fehler else f"{len(fehler)} SUITE(N) FEHLGESCHLAGEN")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
