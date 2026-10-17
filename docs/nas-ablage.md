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

## Das gesamte Heft (zweiter Knopf)

Eingeschaltet mit `heft.gesamt_aktiv: true`. Ablauf:

1. **Knopf 1:** FuPa-Seiten erzeugen und „Auf NAS ablegen“. Dabei landen die
   Spieldaten im Unterordner `_daten` der Ausgabe.
2. **Von Hand** in den Ausgabe-Ordner legen:
   * `Titelbild.jpg` (ersetzt das aus der Vorlage),
   * `Vorwort.txt`, `Vorwort.docx` oder `Vorwort.pdf`,
   * Berichte, Bilder usw. in den jeweiligen Mannschaftsordner.
3. **„Gesamtes Heft bauen …“** auf der Startseite, Ausgabe wählen.

Aufbau wie im Heft der Layouterin:

1. Deckblatt (mit dem Titelbild aus dem Ausgabe-Ordner), Vorwort
   (`Vorwort…` oder `Grußwort…`, Word wird im Heftlayout gesetzt)
2. Werbung aus `Allgemein/Werbung/1 vorne`
3. je Mannschaft: Trennseite mit dem **Zwischenbild aus `00 Vorlage/<Mannschaft>`**
   (dort austauschen), dann ihre Dateien (PDF-Artikel als „Spielbericht“),
   dann die FuPa-Seiten; danach weitere Ordner wie „Jugend“
4. Werbung aus `2 hinten`
5. Kontaktlisten (`Allgemein/Ansprechpartner.txt`, `Kontakte_Jugend*.docx`),
   Impressum (`Allgemein/Impressum.pdf`)
6. Rückseite aus `3 Rückseite`

Innerhalb eines Werbe-Ordners bestimmt der Dateiname die Reihenfolge (am
besten mit Nummer vorne: `01 …`, `02 …`). Querformate und Logos sind halbe
Seiten – zwei hintereinander teilen sich eine Seite. Leerseiten (vor den
Kontaktlisten) füllen auf eine durch 4 teilbare Seitenzahl auf. Gibt es die
drei Unterordner nicht, wird die Werbung zwischen die Mannschaften verteilt.

Das Heft (`<Datum>_WaB_Druck.pdf`) und `Heftplan.txt` landen im
Ausgabe-Ordner. **Reihenfolge ändern:** `Heftplan.txt` bearbeiten und erneut
bauen – dann gilt genau diese Reihenfolge. Neu planen: Datei löschen oder
„Heftplan neu erstellen“ anhaken.

Dateiarten: PDF, JPG/PNG, Word (`.docx`; `.doc`/`.odt` über `heft.umwandler_url`), Text.
**Synology-Office-Dateien (`.odoc`) gehen nicht** – in DSM als PDF oder
`.docx` exportieren.

## Neue Saison

1. In der Konfiguration `saison` umstellen (z. B. `"2027/2028"`). FuPa-Adressen
   und Saisonordner mit `{saison_slug}`/`{saison_kurz}` stellen sich mit um;
   die Ligen bitte prüfen.
2. Seite **„NAS-Ordner“** → **„Saisonordner anlegen“**: legt den Ordner an und
   übernimmt `00 Vorlage` und `Allgemein` aus der Vorsaison.
