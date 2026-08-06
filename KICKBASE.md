# Kickbase-Berater

Eine kleine Anwendung für den eigenen Server, die dabei hilft, in Kickbase
bessere Entscheidungen zu treffen. Sie holt sich regelmäßig die Daten deiner
Liga, wertet sie aus und sagt dir für jeden Spieler, **ob du ihn kaufen,
halten oder verkaufen solltest – und warum**.

> Der Berater liest nur. Er bietet nicht, kauft nicht und verkauft nicht.
> Jede Entscheidung triffst weiterhin du selbst in der Kickbase-App.

Diese Anwendung ist ein eigenständiges Projekt und hat mit dem
Stadionheft-Generator im selben Repository nichts zu tun außer dem Ablageort.

---

## Inhalt

* [In fünf Minuten ausprobieren](#in-fünf-minuten-ausprobieren)
* [Dauerhaft im Heimlabor betreiben](#dauerhaft-im-heimlabor-betreiben)
* [Was die App anzeigt](#was-die-app-anzeigt)
* [Wie die Empfehlung entsteht](#wie-die-empfehlung-entsteht)
* [Auf den eigenen Spielstil einstellen](#auf-den-eigenen-spielstil-einstellen)
* [Kommandozeile](#kommandozeile)
* [Datenquellen](#datenquellen)
* [Sicherheit und Datenschutz](#sicherheit-und-datenschutz)
* [Grenzen – was der Berater nicht kann](#grenzen--was-der-berater-nicht-kann)
* [Aufbau des Programms](#aufbau-des-programms)
* [Wenn etwas nicht klappt](#wenn-etwas-nicht-klappt)

---

## In fünf Minuten ausprobieren

Ohne Kickbase-Konto, ohne Container – der Berater startet im Demomodus mit
erfundenen, aber realistisch aufgebauten Beispieldaten:

```bash
pip install -r requirements-kickbase.txt
python -m kickbase.cli abruf     # erzeugt die Beispieldaten
python -m kickbase.cli web       # http://127.0.0.1:8090
```

Das genügt, um zu sehen, wie die Oberfläche aussieht und wie die Empfehlungen
begründet werden. Alles, was du dort siehst, ist erfunden – ein gelber Kasten
oben auf jeder Seite weist darauf hin.

Mit echten Daten:

```bash
export KICKBASE_EMAIL="du@example.org"
export KICKBASE_PASSWORT="dein-kickbase-passwort"
python -m kickbase.cli abruf
python -m kickbase.cli team
```

---

## Dauerhaft im Heimlabor betreiben

Der Normalfall: ein Container, der von allein alle sechs Stunden neue Daten
holt.

**1. Zugangsdaten hinterlegen.** Eine Datei `.env` neben der
`docker-compose.kickbase.yml` anlegen (die Datei ist bereits in `.gitignore`
eingetragen und landet nie im Repository):

```bash
KICKBASE_EMAIL=du@example.org
KICKBASE_PASSWORT=dein-kickbase-passwort
KICKBASE_WEB_PASSWORT=passwort-fuer-die-weboberflaeche
```

**2. Starten:**

```bash
docker compose -f docker-compose.kickbase.yml up -d --build
```

**3. Aufrufen:** `http://<adresse-deines-servers>:8090`

Beim ersten Start ist die Oberfläche noch leer – der erste Abruf beginnt
15 Sekunden nach dem Start und dauert je nach Ligagröße ein bis drei Minuten.
Mit dem Knopf **„Daten jetzt holen"** lässt er sich jederzeit anstoßen.

### Was gesichert werden muss

Nur der Ordner `daten/kickbase/`. Darin liegt eine einzige SQLite-Datei mit
allen Spielern und – über die Wochen wachsend – deiner eigenen
Marktwerthistorie. Diese Historie kann Kickbase dir nicht zurückgeben, wenn
sie verloren geht.

### Auf einer Synology NAS

Container Manager → Projekt → Erstellen → Ordner mit der
`docker-compose.kickbase.yml` auswählen. Die Umgebungsvariablen unter
„Umgebung" eintragen, **nicht** in die Compose-Datei schreiben. Der
Berater läuft im Container als normaler Benutzer, nicht als root.

---

## Was die App anzeigt

| Seite | Wofür |
|---|---|
| **Mein Team** | Dein Kader mit Note und Empfehlung, ganz oben Ausfälle und Verkaufsvorschläge. Der schnelle Blick vor dem Spieltag. |
| **Transfermarkt** | Alles, was in deiner Liga gerade zum Verkauf steht – bewertet **gegen den Angebotspreis**, nicht gegen den Marktwert. |
| **Kaufkandidaten** | Alle Spieler der Liga nach Note sortiert, filterbar nach Position, Höchstpreis und Einsatzfähigkeit. |
| **Spielerseite** | Marktwertverlauf, alle sieben Kennzahlen mit Begründung, die letzten Spieltage. |
| **Wie wird gerechnet?** | Die komplette Rechenlogik im Klartext, mit deinen eingestellten Gewichten. |

Unter `/bericht.json` liegt derselbe Stand maschinenlesbar – praktisch, wenn
du dir die Verkaufsvorschläge per Skript in Home Assistant, ntfy oder Telegram
schicken lassen willst.

---

## Wie die Empfehlung entsteht

Sieben Kennzahlen, jede zwischen **-100** (klar dagegen) und **+100** (klar
dafür), jede mit einem Satz Begründung:

| Kennzahl | Gewicht | Was sie misst |
|---|---|---|
| **Verfügbarkeit** | 1,6 | Fit, angeschlagen, verletzt, gesperrt. Wer nicht spielt, punktet nicht. |
| **Form** | 1,4 | Punkte der letzten fünf Spieltage (jüngere zählen stärker) gegen den eigenen Saisonschnitt. |
| **Einsatzzeit** | 1,2 | Stammspieler oder Ergänzung. Drei Spiele ohne Einsatz sind ein Alarmzeichen, bevor die Punkte einbrechen. |
| **Marktwerttrend** | 1,0 | Veränderung über 7 und 30 Tage. |
| **Preis-Leistung** | 0,9 | Punkte je Million, verglichen mit dem Median derselben Position. |
| **Nächste Gegner** | 0,6 | Tabellenplatz der nächsten zwei Gegner plus Heimvorteil. |
| **Bewertungsniveau** | 0,5 | Wo steht der Marktwert in seiner eigenen Spanne? Nahe am Hoch ist Einkauf teuer, Verkauf attraktiv. |

Der mit den Gewichten gemittelte Durchschnitt ergibt die **Gesamtnote**:

| Note | Empfehlung |
|---|---|
| ab +35 | Kaufen |
| +15 bis +35 | Beobachten |
| -15 bis +15 | Halten |
| -35 bis -15 | Verkauf prüfen |
| unter -35 | Verkaufen |

### Vorrangregeln

Manche Umstände darf kein Durchschnitt wegrechnen. Diese Regeln deckeln die
Note – sie wirken ausschließlich nach unten:

* **Verletzt oder in Reha** → höchstens -45
* **Gesperrt** → höchstens -20
* **Nicht im Kader** → höchstens -35
* **Angeschlagen** → höchstens +20, **im Aufbautraining** → höchstens +5
* **Drei Spiele ohne Einsatz** → höchstens -30
* **Angebotspreis über 25 % vom Marktwert** → höchstens +10
* **Weniger als drei gewertete Spiele** → Note wird halbiert

Ohne diese Regeln würde ein Langzeitverletzter mit starken Zahlen aus der
gesunden Zeit als Kauf durchgehen.

---

## Auf den eigenen Spielstil einstellen

`config/kickbase.example.yaml` nach `config/kickbase.yaml` kopieren und die
Gewichte anpassen. Drei bewährte Ausrichtungen:

**Du spielst auf schnelle Marktwertgewinne:**

```yaml
analyse:
  gewichte:
    marktwerttrend: 1.6
    bewertungsniveau: 1.0
    gegnerstaerke: 0.3
```

**Du willst vor allem Punkte am Spieltag:**

```yaml
analyse:
  form_spieltage: 3
  gewichte:
    form: 2.0
    einsatzzeit: 1.6
    gegnerstaerke: 1.0
    marktwerttrend: 0.5
```

**Du kaufst langfristig und günstig:**

```yaml
analyse:
  form_spieltage: 8
  gewichte:
    preis_leistung: 1.8
    bewertungsniveau: 1.2
    marktwerttrend: 0.4
```

Nach dem Ändern den Container neu starten. Die neuen Gewichte stehen dann
auch auf der Seite „Wie wird gerechnet?".

---

## Kommandozeile

```bash
kickbase abruf                              # Daten holen
kickbase team                               # eigener Kader
kickbase team -v                            # mit allen Begründungen
kickbase markt                              # Transfermarkt der Liga
kickbase kandidaten --position 4 --hoechstpreis 12 --nur-fit
kickbase spieler Musiala                    # ID oder Namensteil
kickbase web --host 0.0.0.0 --port 8090
```

Ohne Installation genauso über `python -m kickbase.cli …`.

Wer den Abruf lieber über Cron steuert, setzt in der Konfiguration
`abruf.automatisch: false` und trägt ein:

```cron
30 5 * * * cd /pfad/zum/projekt && python -m kickbase.cli abruf
```

---

## Datenquellen

**Kickbase** (Schnittstelle der App, Version 4) – Marktwerte,
Marktwertverlauf, Punkte, Einsatzzeiten, Spielerstatus, dein Kader, der
Transfermarkt deiner Liga. Die Schnittstelle ist nicht offiziell
dokumentiert; die Feldnamen können sich ohne Ankündigung ändern. Der Berater
liest deshalb jedes Feld unter mehreren möglichen Namen – ein umbenanntes
Feld führt zu einer Lücke, nicht zum Absturz. Abgefragt werden ausschließlich
deine eigenen Daten mit deinen eigenen Zugangsdaten, mit Pausen zwischen den
Anfragen.

**OpenLigaDB** – Spielplan und Tabelle der Bundesliga, frei zugänglich, ohne
Schlüssel und ohne Anmeldung. Liefert die Kennzahl „Nächste Gegner".

**Eigene Datenbank** – bei jedem Abruf wird der Tagesmarktwert gespeichert.
Nach ein paar Wochen hast du eine lückenlose eigene Reihe, unabhängig davon,
wie weit Kickbase gerade zurückliefert.

**Verletzungsseiten** *(ab Werk ausgeschaltet)* – optionale Klartextmeldungen
von Fußballseiten. Bewusst kein seitenspezifischer Parser: der Berater liest
den Text der Seite und sucht satzweise nach den Namen der Spieler, die er
ohnehin kennt. Steht im selben Satz ein Verletzungsbegriff, gilt das als
Meldung. Vorher wird die `robots.txt` gefragt; verbietet sie den Abruf, wird
die Seite übersprungen. Vor dem Einschalten bitte prüfen, ob die
Nutzungsbedingungen der Seite das automatische Auslesen erlauben. **Der
Kickbase-Status bleibt in jedem Fall die maßgebliche Quelle** – diese
Zusatzmeldungen sind Beiwerk.

---

## Sicherheit und Datenschutz

* Zugangsdaten stehen **nie** in einer Konfigurationsdatei, sondern in
  Umgebungsvariablen (`KICKBASE_EMAIL`, `KICKBASE_PASSWORT`).
* Alle Daten bleiben auf deinem Server. Es gibt keinen Cloud-Dienst, keine
  Telemetrie und keinen Aufruf nach außen außer zu Kickbase und OpenLigaDB.
* Die Oberfläche hat ab Werk **keinen** Zugangsschutz – das ist für das eigene
  Heimnetz gedacht. Sobald sie von außen erreichbar sein soll:
  `web.passwortschutz: true` setzen und `KICKBASE_WEB_PASSWORT` füllen.
  Basic Authentication schützt aber nur hinter HTTPS. Der sicherste Weg
  bleibt ein VPN.
* Der Berater schreibt nichts an Kickbase zurück. Es gibt im ganzen Programm
  keinen Aufruf, der ein Gebot abgibt oder einen Spieler auf den Markt stellt.

---

## Grenzen – was der Berater nicht kann

Ehrlichkeit ist hier wichtiger als Marketing:

* Er kennt **keine Pressekonferenzen, keine Trainerentscheidungen und keine
  Gerüchte**. Wer am Freitag in der PK aus der Startelf gestrichen wird,
  steht hier am Samstag noch als Stammspieler.
* Er gibt **keine Punkteprognose** für einzelne Spiele ab. Kickbase-Punkte
  hängen stark vom Spielverlauf ab; jede Einzelspiel-Vorhersage wäre
  Scheingenauigkeit.
* Zu **Saisonbeginn, nach Winterpausen und bei Neuzugängen** ist die
  Datengrundlage dünn. Dann steht bei den Kennzahlen „zu wenig Daten" – das
  ist gewollt und ehrlicher als eine erfundene Zahl.
* Marktwerte in Kickbase reagieren **verzögert**. Der Marktwerttrend
  bestätigt eine Entwicklung, er sagt sie nicht voraus.
* Es ist ein **Punktesystem, kein Modell**. Es lernt nicht dazu. Dafür kannst
  du jede einzelne Zahl nachvollziehen und selbst korrigieren – was im Alltag
  meist mehr wert ist.

---

## Aufbau des Programms

```
kickbase/
├── config.py            Konfiguration, Standardwerte, Prüfungen
├── models.py            Datenmodelle; einzige Stelle mit Kickbase-Kürzeln
├── speicher.py          SQLite: Spieler, Marktwerthistorie, Abrufprotokoll
├── dienst.py            Ablauf: Abruf, Lagebericht, Hintergrundplaner
├── cli.py               Kommandozeile
├── quellen/
│   ├── http.py          Wiederholungen, Cache, klare Fehler
│   ├── kickbase_api.py  Kickbase-Schnittstelle v4
│   ├── openligadb.py    Spielplan und Tabelle
│   ├── verletzungen.py  Optionale Zusatzmeldungen
│   └── demo.py          Beispieldaten ohne Konto
├── analyse/
│   ├── kennzahlen.py    Die sieben Kennzahlen
│   └── bewertung.py     Gewichtung, Vorrangregeln, Empfehlung
└── web/                 Flask-Oberfläche, Diagramme ohne Fremdbibliothek
```

Grundsätze, die sich durch den ganzen Code ziehen:

1. **Abruf und Anzeige sind getrennt.** Die Oberfläche liest nur aus der
   Datenbank. Kein Klick löst eine Anfrage an Kickbase aus, und die Seiten
   funktionieren auch, wenn gerade nichts erreichbar ist.
2. **Jede Zahl trägt ihre Begründung.** Die entsteht bei der Berechnung, nicht
   nachträglich – deshalb gibt es kein „Kaufen!" ohne Erklärung.
3. **Teilausfälle sind erlaubt.** Fällt OpenLigaDB aus, fehlt eine Kennzahl.
   Fällt der Marktwertverlauf aus, bleibt der Rest nutzbar.
4. **Wenige Abhängigkeiten.** Flask, Jinja2, PyYAML, requests. Kein pandas,
   kein numpy, keine Diagrammbibliothek – die Diagramme sind selbst gerechnetes
   SVG, damit die Seite auch ohne Internetzugang vollständig aussieht.

Tests:

```bash
python -m pytest tests/kickbase -q
```

---

## Wenn etwas nicht klappt

| Meldung | Ursache und Abhilfe |
|---|---|
| „Die Anmeldung bei Kickbase ist fehlgeschlagen" | E-Mail oder Passwort falsch. In der Kickbase-App prüfen, ob die Anmeldung dort funktioniert. |
| „Zu diesem Konto wurde keine Liga gefunden" | Das Konto ist in keiner aktiven Liga. Oder: `kickbase.liga_id` zeigt auf eine Liga, in der du nicht spielst – das Protokoll listet beim Start alle gefundenen Ligen mit ihrer ID auf. |
| „Kein Spielplan gespeichert" | OpenLigaDB war beim letzten Abruf nicht erreichbar. Die Kennzahl „Nächste Gegner" bleibt dann wirkungslos, alles andere läuft weiter. |
| „Noch kein Marktwertverlauf gespeichert" | Normal beim ersten Start. Nach einigen Tagen mit täglichem Abruf steht die Kennzahl zur Verfügung. |
| Container startet, zeigt aber nur eine Fehlerseite | Fehler in `config/kickbase.yaml`. Die Seite nennt die Ursache im Klartext; nach der Korrektur den Container neu starten. |
| Alles ist leer | Es wurde noch nie abgerufen. Knopf „Daten jetzt holen" drücken oder `kickbase abruf` aufrufen. |

Ausführliches Protokoll: `logs/kickbase.log`, oder `protokoll.level: DEBUG`
in der Konfiguration setzen.
