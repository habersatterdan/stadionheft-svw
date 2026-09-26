# Seiten erzeugen

Das ist der Vorgang, den ihr vor jedem Heimspiel macht. Er dauert eine Minute.

---

## Schritt für Schritt

### 1. Seite öffnen

Im Browser: **http://svwnas:8080**

Das geht vom Handy, vom Tablet und von jedem Rechner im Vereinsnetz – es muss
nichts installiert werden. Von unterwegs braucht es eine Verbindung ins
Vereinsnetz ([→ Zugriff von unterwegs](VPN_EINRICHTEN.md)).

### 2. Mannschaften anhaken

Alle sind vorausgewählt. Wer nicht ins Heft soll, wird abgehakt.

### 3. Auf „Seiten jetzt erzeugen" klicken

Jetzt passiert Folgendes, sichtbar im Protokoll darunter:

- Für jede Mannschaft werden die Daten von FuPa geholt
- Aus dem Spielplan wird der nächste Gegner bestimmt
- Zu diesem Gegner werden ebenfalls die Zahlen geholt
- Die Seiten werden gesetzt und zu einer PDF je Mannschaft zusammengefügt

Pro Mannschaft dauert das wenige Sekunden.

### 4. Dateien herunterladen

Oben steht, wie viele Dateien entstanden sind und **wann die Daten geholt
wurden**. Darunter:

- **„Alle Dateien herunterladen (ZIP)"** – der Normalfall. Ein Klick, alles
  drin, dazu eine `UEBERSICHT.txt`, die erklärt, was in welcher Datei steckt.
- Jede Datei einzeln, falls nur eine gebraucht wird.

Die Dateien liegen außerdem auf der NAS unter

```
SVW/Stadionheft/Saison 26-27/05_Ausgaben/<Datum>_Spieltag/
```

### 5. Weitergeben

Das ZIP an die Person schicken, die das Heft zusammenbaut. Mehr braucht sie
nicht – [was sie damit macht, steht hier](uebergabe.md).

---

## Die Dateinamen

```
2026-10-04_Herren_1_gegen_SG_Alerheim.pdf
```

Aufbau: **Datum des Spiels** (so sortieren sich die Dateien von selbst
richtig), **Mannschaft**, **Gegner**. Man sieht ohne Öffnen, was drin ist.

---

## Wenn eine Warnung erscheint

Gelbe Kästen unter dem Ergebnis sind **Hinweise, keine Fehler** – die Dateien
sind trotzdem fertig. Typische Fälle:

| Meldung | Bedeutung |
|---|---|
| „Für *Damen 1* ist noch keine Liga eingetragen" | Kosmetik: Auf der Trennseite fehlt die Ligabezeichnung. Ein Administrator trägt sie nach. |
| „Zu *SG Alerheim* kamen keine Zahlen an" | Die Gegnerseiten bleiben leer. Der Rest stimmt. |
| „Von FuPa konnte die Tabelle nicht gelesen werden" | Diese Seite bleibt leer. Über **FuPa-Verbindung prüfen** lässt sich nachsehen, woran es liegt. |
| „möglicherweise veraltet" | FuPa war nicht erreichbar, es wurden ältere Daten verwendet. **Vor dem Druck prüfen.** |

Ausführlich: [Wenn etwas nicht klappt](fehler.md)

---

## Weitere Einstellungen

Hinter dem aufklappbaren Bereich „Weitere Einstellungen" – im Normalfall nicht
nötig:

**Spieltag** – Freitext, landet in der Übersicht im ZIP.

**Dein Name** – erscheint nur im Protokoll. Praktisch, wenn mehrere Leute
Dateien erzeugen.

**Woher kommen die Daten?** – normalerweise FuPa. „Beispieldaten" ist zum
Ausprobieren der Oberfläche, ohne dass echte Zahlen geholt werden.

**Zwischenspeicher übergehen** – holt jede Seite wirklich neu. Der
Zwischenspeicher hält ohnehin nur 15 Minuten; das braucht man nur, wenn ein
Ergebnis gerade eben in FuPa nachgetragen wurde und sofort im Heft stehen soll.

---

## Ohne Weboberfläche

Falls die Oberfläche einmal nicht erreichbar ist, geht es auch über den
Aufgabenplaner der NAS:

```bash
docker exec stadionheft python -m stadionheft.cli erstellen --mannschaften herren1
```

Alle aktiven Mannschaften auf einmal: `--mannschaften` einfach weglassen.
Frisch abrufen: `--frisch` anhängen.
