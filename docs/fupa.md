# FuPa-Anbindung

Tabelle, Torschützenliste, Spielerstatistik und Spielplan werden automatisch
von fupa.net geholt – für die eigene Mannschaft **und für den nächsten
Gegner**. Damit entfällt die Pflege der CSV-Dateien.

Das ist seit der aktuellen Fassung die **Voreinstellung**. Es muss dafür nichts
eingestellt werden.

Diese Seite richtet sich an Administratoren.

---

## Ausgangslage: ehrlich betrachtet

**FuPa bietet keine offizielle, dokumentierte Schnittstelle an.** Die Website
lädt ihre Inhalte zwar über interne JSON-Aufrufe nach, aber diese sind:

* nicht dokumentiert
* nicht zugesichert
* jederzeit ohne Ankündigung änderbar

Der naheliegende Weg – eine feste Adresse anrufen und feste Feldnamen erwarten –
funktioniert deshalb genau so lange, bis FuPa etwas umstellt. Das Programm geht
darum einen anderen Weg.

---

## Was FuPa erlaubt – und was nicht

Zwei Dateien sagen das, und sie sagen Unterschiedliches.

**`api.fupa.net/robots.txt`:**

```
User-agent: *
Allow: /*.ics$
Disallow: /
```

Die JSON-Schnittstelle ist also gesperrt. Das Programm hält sich daran und
ruft `api.fupa.net` gar nicht erst auf – **mit einer Ausnahme**:
Kalenderdateien sind ausdrücklich freigegeben. Das ist keine Lücke, sondern
Absicht: Kalender sind zum Abonnieren gedacht.

**`www.fupa.net/robots.txt`** enthält überhaupt keine Gruppe `User-agent: *`.
Geregelt sind dort nur einzelne Werbe- und Suchmaschinen-Crawler. Für einen
Abruf wie unseren gilt damit keine Einschränkung – die öffentlichen Teamseiten
dürfen gelesen werden.

### Der Kalender ist der saubere Weg für den Spielplan

Eine Kalenderdatei (`.ics`) enthält alle Termine einer Mannschaft: Datum,
Uhrzeit, Paarung, Spielort – und bei manchen Vereinen auch das nachgetragene
Ergebnis. Daraus ergeben sich:

* der **nächste Gegner** samt Anstoß und Spielort,
* die **Formkurve** der letzten fünf Spiele.

Das Programm erkennt eine Kalenderdatei am Inhalt (`BEGIN:VCALENDAR`) und
liest sie ohne Zusatzbibliothek (`stadionheft/sources/ics_daten.py`). Der
Spielplan läuft danach durch dieselbe Erkennung wie alle anderen Daten.

!!! warning "Die Kalenderadresse muss einmal gefunden werden"
    Unter welcher Adresse FuPa den Kalender ausliefert, ist nicht
    dokumentiert. Das Programm probiert mehrere naheliegende Schreibweisen
    durch. Führt keine zum Ziel, hilft `skripte/quellen_pruefen.sh`
    (siehe [Fehler suchen](fehler.md)): Es holt alle Kandidaten roh ab und
    meldet, welche mit einem Kalender antwortet. Die richtige Adresse kommt
    dann unter `datenquelle.fupa.zusatz_adressen` in die Konfiguration.

    Alternativ: die Mannschaftsseite auf fupa.net im Browser öffnen und nach
    „Kalender abonnieren" suchen. Die Adresse dahinter ist die gesuchte.

Tabelle, Torschützen und Spielerstatistik stehen **nicht** im Kalender. Die
kommen von der Teamseite – oder, solange das nicht trägt, aus den CSV-Dateien
(siehe [CSV als Rückfalllösung](csv-reserve.md)).

---

## Wie der Abruf funktioniert

Das Programm **rät nicht, es sucht**. In drei Schritten:

### 1. Mehrere Adressen durchprobieren

Für jede Mannschaft steht eine Liste von Adressen bereit – in dieser
Reihenfolge:

1. die in `config.yaml` eingetragenen Endpunkte
2. die **Teamseite der Mannschaft** (`fupa_team_url`) – die verlässlichste
   Adresse überhaupt, denn die hat der Verein selbst eingetragen
3. selbst ergänzte Adressen aus `zusatz_adressen`
4. eine eingebaute Liste weiterer Kandidaten – zuerst die **Kalenderdateien**
   (ausdrücklich erlaubt), dann Unterseiten (`/tabelle`, `/spielplan`,
   `/kader`, `/statistiken` …)

Sobald alle vier Datenteile beisammen sind, hört das Programm auf. In der Regel
genügt **eine einzige** Seite.

Adressmuster, die in einem Lauf schon einmal nichts geliefert haben, werden bei
den folgenden Mannschaften übersprungen. Ein Heft mit fünf Mannschaften holt
sonst dieselben Fehlschläge zehnmal – unnötige Last für FuPa und unnötige
Wartezeit.

### 2. Die Daten aus der Seite holen

Antwortet eine Adresse mit einer **Kalenderdatei**, wird daraus der Spielplan
gelesen. Antwortet sie mit JSON, wird das direkt verwendet. Antwortet sie mit
HTML – also mit einer ganz normalen Webseite –, sucht das Programm die
JSON-Blöcke, die in der Seite eingebettet sind. Moderne Websites liefern ihre
Daten genau so aus (`__NEXT_DATA__`, `window.__NUXT__` und Ähnliches).

**Das ist der entscheidende Punkt:** Die Adresse der öffentlichen Teamseite ist
bekannt und stabil. Sie muss nicht erraten werden.

### 3. Erkennen, was was ist

Aus allem gefundenen JSON sucht das Programm heraus, was wie eine Tabelle, eine
Torschützenliste, eine Spielerstatistik oder ein Spielplan **aussieht** – an der
Struktur, nicht an den Feldnamen:

* Eine **Tabelle** hat mehrere Zeilen mit Mannschaftsname, Punkten, Siegen,
  Niederlagen und Toren.
* Eine **Torschützenliste** hat Spielernamen und Tore, aber keine
  Einsatzminuten.
* Eine **Spielerstatistik** hat Spielernamen *mit* Minuten und Karten.
* Ein **Spielplan** hat Paarungen mit einem Datum.

Ob das Feld `points` oder `punkte` heißt, ob der Vereinsname direkt drinsteht
oder in einem verschachtelten `team`-Objekt: alles egal. Kommen mehrere
Kandidaten in Frage, gewinnt die vollständigste Liste.

!!! note "Warum dieser Umweg"
    Weil er hält. Eine feste Feldzuordnung müsste nach jeder Umstellung bei FuPa
    von Hand nachgezogen werden – und bis das jemand merkt, steht im Heft nichts
    oder Falsches.

### 4. Dasselbe noch einmal für den Gegner

Im Spielplan, den Schritt 3 gerade erkannt hat, steht nicht nur, **gegen wen**
als nächstes gespielt wird, sondern meist auch der technische Bezeichner des
Gegners – als Kürzel, als volle Adresse oder als Nummer. Das Programm nimmt
ihn mit und läuft damit dieselbe Suche ein zweites Mal.

Ergebnis: Tabelle, Torschützenliste, Spielerstatistik und Spielplan des
Gegners, ohne dass irgendwo ein Gegnername gepflegt werden müsste.

Spielt der Gegner in **derselben Liga**, sind Tabelle und Torschützenliste für
beide dieselben – dann stehen sie nur einmal im Heft, mit beiden Vereinen
hervorgehoben. Nur bei einem Gegner aus einer anderen Liga (Pokal) kommen
zusätzliche Seiten dazu.

---

## Verbindung prüfen

In der Fußzeile der Oberfläche steht **„FuPa-Verbindung prüfen"**. Die Seite
klappert alle Adressen ab und zeigt für jede an, was zurückkam und was sich
daraus lesen ließ.

Der Test **liest nur** – es wird nichts verändert. Er dauert etwa eine halbe
Minute.

Oben steht die Bilanz:

| Ergebnis | Bedeutung |
|---|---|
| **Alle vier Datenteile gefunden** | Es ist nichts zu tun |
| **Ein Teil gefunden** | Was fehlt, bleibt im Heft leer und muss per CSV gepflegt werden |
| **Nichts gefunden** | FuPa ist nicht erreichbar, oder die Seiten sind anders aufgebaut als erwartet |

Darunter steht Adresse für Adresse, was passiert ist. Der Knopf **„Ergebnis
herunterladen (ZIP)"** liefert die Rohantworten – die braucht, wer der Sache
nachgehen will.

Dasselbe im Terminal:

```bash
docker exec stadionheft python -m stadionheft.cli probe-fupa --mannschaft herren1
```

---

## Wenn etwas nicht gefunden wird

Erst prüfen, ob die Teamseite überhaupt stimmt: Die `fupa_team_url` der
Mannschaft im Browser öffnen. Zeigt sie die richtige Mannschaft in der
richtigen Saison?

Wenn ja, lässt sich eine zusätzliche Adresse nachtragen, ohne am Programm etwas
zu ändern:

1. FuPa-Teamseite im Browser öffnen
2. Taste `F12` drücken (Entwicklerwerkzeuge)
3. Reiter **Netzwerk** wählen, Filter **Fetch/XHR**
4. Seite mit `F5` neu laden
5. In der Liste stehen die tatsächlich benutzten Adressen

Diese in `config.yaml` eintragen – `{slug}` wird durch den Team-Bezeichner
ersetzt:

```yaml
datenquelle:
  fupa:
    zusatz_adressen:
      - "https://api.fupa.net/v2/teams/{slug}/statistics"
```

Danach den Test noch einmal laufen lassen.

### Wenn nur die Gegnerseiten leer bleiben

Dann liefert FuPa im Spielplan keinen Bezeichner für diesen Gegner. Seine
Teamseite lässt sich von Hand hinterlegen – der Schlüssel ist der Vereinsname
genau so, wie er im Spielplan steht:

```yaml
datenquelle:
  fupa:
    gegner:
      "SG Alerheim": "https://www.fupa.net/team/sg-alerheim-2026-27"
      "TSV Meitingen": "https://www.fupa.net/team/tsv-meitingen-2026-27"
```

Einmal pro Ligagegner eingetragen, gilt das für die ganze Saison.

Ganz abschalten lässt sich der Gegnerabruf auch:

```yaml
datenquelle:
  fupa:
    gegner_abrufen: false
```

---

## Einstellungen

```yaml
datenquelle:
  modus: "api"              # Voreinstellung
  fallback_modus: "manuell" # wenn nichts kommt: CSV-Dateien

  fupa:
    zusatz_adressen: []     # eigene Adressen, siehe oben
    max_abrufe: 12          # Obergrenze je Mannschaft
    gegner_abrufen: true    # auch die Zahlen des Gegners holen
    gegner: {}              # Notnagel: Teamseiten von Hand hinterlegen

  cache:
    gueltigkeit_minuten: 15 # bewusst kurz - das Heft soll den Stand von
                            # jetzt zeigen, nicht den von heute Morgen
```

`fallback_modus` greift in **zwei** Fällen: wenn FuPa gar nicht erreichbar ist,
und wenn der Abruf zwar durchläuft, aber nichts liefert. Ein Heft mit lauter
leeren Statistikseiten wäre sonst formal ein Erfolg – und fällt erst im Druck
auf.

---

## Faires Verhalten

Das Programm verhält sich bewusst zurückhaltend:

* Sprechender User-Agent **mit Kontaktadresse** – kein anonymer Zugriff
* `robots.txt` wird gelesen und respektiert
* Konfigurierbare Pause zwischen Anfragen (Standard 1,5 Sekunden)
* Wiederholung mit wachsender Wartezeit bei Netzfehlern
* Zwischenspeicher: dieselbe Adresse wird innerhalb von zwei Stunden nicht
  erneut abgerufen
* Der Abruf **hört auf**, sobald alles gefunden ist – meist nach einer Seite
* Höchstens `max_abrufe` Seiten je Mannschaft (Standard 12)
* Insgesamt eine Handvoll Abrufe alle zwei Wochen

Weist FuPa den Zugriff ab (403 oder 429), meldet das Programm das im Klartext
und schaltet um. Es versucht **nicht**, eine Sperre zu umgehen.

---

## Rechtliches in Kürze

Ausführlich im [Umsetzungskonzept](KONZEPT.md#10-rechtliche-und-technische-einschrankungen).
Die Kurzfassung:

* **Zahlen sind nicht urheberrechtlich geschützt.** Dass das Programm die
  Werte neu setzt statt Bildschirmfotos zu übernehmen, ist rechtlich sauberer
  als die bisherige Praxis.
* **Spielerfotos werden bewusst nicht übernommen.**
* **Quellenangabe** steht auf jeder Datenseite: „Quelle: fupa.net" mit
  Stand-Datum.
* **Nutzungsbedingungen** von FuPa untersagen automatisierte Abfragen
  möglicherweise. Das ist eine vertragliche Frage, keine strafrechtliche.

!!! tip "Der einfachste Weg aus der Grauzone"
    FuPa kurz anschreiben: „Wir sind der SV Wörnitzstein-Berg und möchten für
    unser Stadionheft alle zwei Wochen Tabelle und Statistik unserer eigenen
    Mannschaften automatisch abrufen – ist das in Ordnung?"

    Eine schriftliche Zusage klärt alles. Regionalportale stehen
    Vereinsprojekten erfahrungsgemäß offen gegenüber.

---

## Alternativen

| Weg | Bewertung |
|---|---|
| **Offizieller Export von FuPa** | Beste Lösung, falls es einen Vereinszugang gibt – bitte prüfen |
| **BFV-Daten** | Die Originalquelle. Prüfenswert, ob der Verband Vereinen Zugang bietet |
| **Manuelle CSV-Eingabe** | Funktioniert immer, rechtlich unbedenklich, etwa 10 Minuten je Mannschaft |
| **Copy-Paste nach Excel** | Praktischer Mittelweg, deutlich schneller als Abtippen |
