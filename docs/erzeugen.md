# Seiten erzeugen

Das ist der Vorgang, den ihr vor jedem Heimspiel macht. Er dauert eine Minute.

---

## Schritt für Schritt

### 1. Seite öffnen

Im Browser: **http://svwnas:8080** (im Homelab: **https://stadionheft.haberlab.local**)

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

### 5. Auf die NAS legen (wenn eingerichtet)

Ist die Ablage per File Station eingerichtet, steht unter dem Ergebnis
**„Auf die NAS legen“**:

1. Ordnernamen prüfen – vorgeschlagen ist die nächste Nummer mit dem Datum
   des ersten Spiels, z. B. `09 Ausgabe 301026`.
2. **„Auf NAS ablegen“** klicken und die Seite offen lassen. Über QuickConnect
   dauert das ein paar Minuten; der Fortschritt steht darunter.

Das Programm legt den Ordner im Saisonordner an, kopiert den Inhalt von
`00 Vorlage` hinein (Titelbild, Zwischenbilder) und legt jede Mannschaftsdatei
in ihren Ordner, das Deckblatt in den Hauptordner.

### 6. Weitergeben

Das ZIP an die Person schicken, die das Heft zusammenbaut. Mehr braucht sie
nicht – [was sie damit macht, steht hier](uebergabe.md).

---

## Das gesamte Heft bauen (zweiter Knopf)

Statt alles von Hand zusammenzubauen, kann das Programm das komplette Heft
aus dem Ausgabe-Ordner der NAS bauen:

1. Ausgabe wie oben anlegen (Schritt 1–5).
2. In den Ausgabe-Ordner auf der NAS legen:
   * **`Titelbild.jpg`** (ersetzt das aus der Vorlage),
   * **das Grußwort** als `Grußwort….docx` oder `Vorwort….docx` (Word),
   * **Zeitungsartikel** als PDF in den Ordner der Mannschaft.
3. Auf der Startseite **„Gesamtes Heft bauen …“** → Ausgabe wählen →
   **„Heft bauen“**. Nach einigen Minuten liegt das fertige Heft
   (`<Datum>_WaB_Druck.pdf`) im Ausgabe-Ordner und lässt sich herunterladen.
4. **Reihenfolge ändern:** Im Ordner liegt jetzt `Heftplan.txt`. Zeilen
   verschieben oder löschen, dann noch einmal „Heft bauen“ – es gilt genau
   diese Reihenfolge.

Werbung, Kontaktlisten und Impressum kommen aus dem Ordner `Allgemein` der
Saison. Was wo liegt und wie man es pflegt:
[Deckblatt, NAS-Ablage, Gesamtheft, neue Saison](nas-ablage.md).

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
