# Deckblatt und Ablage auf der NAS

## Das Deckblatt

Jeder Lauf erzeugt zusätzlich eine Datei `<Datum>_Deckblatt.pdf`:

1. **Titelseite:** Titelbild, „Wir begrüßen unsere Gäste“ mit allen
   **Heimspielen** der gewählten Mannschaften, nach Tag und Uhrzeit sortiert.
   Auswärtsspiele stehen nicht darauf.
2. **Ansprechpartner:** die Liste aus `config.yaml` → `deckblatt.ansprechpartner`.

Das Titelbild kommt aus dem Vorlage-Ordner auf der NAS (`Titelbild.jpeg`,
`.jpg` oder `.png`). Ist dort keins, nimmt das Programm `titelbild.*` aus dem
Eingabeordner. Fehlt beides, steht ein Platzhalter da und das Programm weist
darauf hin.

Ausschalten: `deckblatt.aktiv: false`.

## Ablage per File Station (auch über QuickConnect)

Für eine NAS, die nur über QuickConnect erreichbar ist (`nas.modus:
"filestation"`). Abgelegt wird **nicht automatisch**, sondern nach dem
Ansehen auf Knopfdruck:

1. Heft erzeugen, ZIP oder einzelne Dateien ansehen.
2. Unter **„Auf die NAS legen“** steht ein Vorschlag für den Ordnernamen,
   z. B. `09 Ausgabe 301026` (nächste Nummer, Datum des ersten Spiels). Er
   lässt sich frei ändern.
3. **„Auf NAS ablegen“** legt den Ordner im Saisonordner an, kopiert den
   Inhalt des Vorlage-Ordners hinein und lädt jede Mannschaftsdatei in ihren
   Unterordner (`nas.filestation.mannschaftsordner`). Das Deckblatt kommt in
   den Hauptordner.
4. Zum Schluss prüft das Programm, ob jede Datei vollständig angekommen ist.

Über QuickConnect dauert das einige Minuten. Bricht es ab, genügt ein
erneuter Klick mit demselben Namen: Der angefangene Ordner wird fortgesetzt.
Einen Ordner, den es schon gab, fasst das Programm nie an.

Die Seite **„NAS-Ordner“** (Link auf der Startseite) liest Saisonordner und
Vorlage direkt von der NAS – zum Prüfen der Einstellungen, ohne DSM zu öffnen.

### Einrichten

* Eigener DSM-Benutzer nur für das Programm: kein Administrator, nur die
  Anwendung File Station, Schreibrecht nur auf den Stadionheft-Ordner, ohne
  Zwei-Faktor-Anmeldung.
* Das Passwort steht **nie** in der `config.yaml`, sondern in der
  Umgebungsvariablen `NAS_PASSWORT`.
* Im Saisonordner einen Ordner `00 Vorlage` anlegen – mit genau den Dateien,
  die in jede Ausgabe gehören (Titelbild, Liga-Übersichten je Mannschaft).
