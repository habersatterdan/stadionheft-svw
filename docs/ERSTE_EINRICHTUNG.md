# Erste Einrichtung

Diese Anleitung richtet das Programm einmalig ein. Danach genügt der Knopf in
der Weboberfläche.

Es wird **nichts mehr selbst gebaut** – das fertige Image liegt auf GitHub und
wird nur noch geladen.

!!! info "Voraussetzungen"
    Eine Synology NAS mit **DSM 7.2 oder neuer** (dort heißt das Werkzeug
    *Container Manager*; unter DSM 7.0/7.1 heißt es *Docker* und funktioniert
    genauso). Dazu ein Administrator-Konto auf der NAS.

    Kein SSH nötig, kein Terminal, keine Programmierkenntnisse.

---

## Schritt 1 – Ordner anlegen

In der **File Station** unter `SVW/Stadionheft/` diese Struktur anlegen:

```
SVW/Stadionheft/
├── _Programm/
│   ├── 00_Konfiguration/      ← config.yaml
│   ├── 01_Vorlagen/           ← Vereinswappen (optional)
│   ├── 03_Eingaben/           ← CSV-Dateien als Notfall-Reserve
│   ├── 04_Zwischenergebnisse/ ← Arbeitsordner, legt das Programm selbst an
│   ├── 99_Logs/               ← Protokolle
│   └── docker/                ← hier kommt die docker-compose.yml hinein
└── Saison 26-27/
    └── 05_Ausgaben/           ← hier landen die fertigen PDFs
```

Ordner anlegen: File Station → rechte Maustaste → **Ordner erstellen**.

---

## Schritt 2 – Konfiguration hinterlegen

1. Im Repository die Datei [`config/config.example.yaml`][beispiel] öffnen und
   den Inhalt kopieren.
2. In der File Station nach `_Programm/00_Konfiguration/` gehen.
3. Über **Erstellen → Datei erstellen** eine Datei `config.yaml` anlegen und
   den Inhalt einfügen.
4. Die mit `TODO` markierten Stellen anpassen – vor allem die **Ligen** der
   Mannschaften und die **FuPa-Links**.

[beispiel]: https://github.com/habersatterdan/stadionheft-svw/blob/main/config/config.example.yaml

!!! warning "Die config.yaml gehört auf die NAS, nicht ins Image"
    Sie wird in den Container eingehängt. Dadurch bleibt sie bei jeder
    Aktualisierung erhalten, und Vereinsdaten landen nie auf GitHub.

---

## Schritt 3 – Compose-Datei hinterlegen

Aus dem Repository die Datei [`docker-compose.yml`][compose] kopieren und in
`_Programm/docker/` ablegen.

[compose]: https://github.com/habersatterdan/stadionheft-svw/blob/main/docker-compose.yml

Dann **die Pfade darin prüfen**. Sie müssen genau zu eurer Ablage passen. Wenn
der Ordner `_Programm` nicht direkt unter `SVW/Stadionheft/` liegt, alle Pfade
entsprechend anpassen.

---

## Schritt 4 – Image freischalten

Das Image liegt in der GitHub Container Registry. Weil das Repository privat
ist, ist auch das Image zunächst privat – die NAS käme ohne Anmeldung nicht
heran.

**Einmalig auf GitHub:**

1. Profilbild oben rechts → **Your packages**
2. Paket `stadionheft-svw` anklicken
3. Rechts **Package settings**
4. Ganz unten: **Change visibility → Public** → bestätigen

Das Image enthält nur Programmcode. Keine Vereinsdaten, keine Zugangsdaten,
keine Konfiguration – die liegen alle auf der NAS.

??? question "Lieber privat lassen?"
    Dann braucht die NAS eine Anmeldung. Auf GitHub ein *Personal Access Token*
    mit dem Recht `read:packages` erzeugen und im Container Manager unter
    **Registrierung → Einstellungen → Hinzufügen** eintragen:
    Registry `ghcr.io`, Benutzer = GitHub-Name, Passwort = das Token.

---

??? tip "Alternative: selbst auf der NAS bauen"
    Wer sich nicht mit Paketsichtbarkeit befassen will, lässt die NAS das
    Image selbst bauen. Dann entfällt Schritt 4 komplett.

    1. Auf GitHub den Branch öffnen → **Code** → **Download ZIP**
    2. Das ZIP in der File Station nach `_Programm/docker/` hochladen und dort
       entpacken. Es entsteht ein Ordner
       `stadionheft-svw-claude-stadionheft-fupa-automation-lvyt1e`.
    3. In **diesem** Ordner die `docker-compose.yml` ersetzen: die Zeile
       `image: ghcr.io/...` löschen und stattdessen `build: .` eintragen.
    4. Im Container Manager diesen entpackten Ordner als Projektpfad wählen.

    Die NAS baut dann etwa zehn Minuten. Für eine Aktualisierung wiederholt
    sich das jedes Mal – deshalb ist der Weg über das fertige Image auf Dauer
    bequemer. Umsteigen geht jederzeit: `build: .` wieder gegen die
    `image:`-Zeile tauschen.

---

## Schritt 5 – Projekt anlegen

1. **Container Manager** öffnen
2. Links **Projekt** → **Erstellen**
3. Projektname: `stadionheft`
4. Pfad: den Ordner `_Programm/docker` auswählen
5. Quelle: **Vorhandene docker-compose.yml verwenden**
6. **Weiter** → **Fertig**

Die NAS lädt jetzt das Image (etwa 300 MB, dauert ein paar Minuten) und startet
den Container.

---

## Schritt 6 – Aufrufen

Im Browser: **http://svwnas:8080**

Wenn das nicht geht, statt `svwnas` die IP-Adresse der NAS verwenden – sie
steht in der DSM-Systemsteuerung unter *Netzwerk*.

---

## Schritt 7 – FuPa-Verbindung prüfen

Unten auf der Seite: **„FuPa-Verbindung prüfen"** → Mannschaft wählen → Knopf.

Nach etwa einer halben Minute steht dort, ob Tabelle, Torschützenliste,
Spielerstatistik und Spielplan gefunden wurden. Sind alle vier da, ist alles
fertig eingerichtet.

[→ Was tun, wenn etwas fehlt](fupa.md#wenn-etwas-nicht-gefunden-wird)

---

## Schritt 8 – Probelauf

Zurück auf die Startseite, eine Mannschaft anhaken, **„Seiten jetzt erzeugen"**.

Die PDF sollte danach in `Saison 26-27/05_Ausgaben/<Datum>_Spieltag/` liegen
und sich in der File Station herunterladen lassen.

---

## Aktualisieren

!!! danger "Der eine Stolperstein"
    Docker holt ein Abbild mit dem Namen `latest` **nicht von selbst neu**.
    Liegt lokal schon eines unter dem Namen, wird das weiterverwendet – der
    Container läuft dann mit altem Code, ohne dass irgendwo ein Fehler
    erscheint. „Erstellen" im Container Manager ändert daran nichts.

    Es braucht also immer ein ausdrückliches **Holen**.

### Weg A – Aufgabenplaner (empfohlen)

Das Skript [`skripte/nas_aktualisieren.sh`][skript] holt das Abbild
ausdrücklich, startet den Container neu und schreibt den Programmstand
vorher und nachher nach `99_Logs/aktualisierung.txt`. Schlägt das Holen
fehl, bricht es ab, **bevor** es den laufenden Container anfasst.

Einmalig anlegen:

1. *Systemsteuerung → Aufgabenplaner → Erstellen → Geplante Aufgabe →
   Benutzerdefiniertes Skript*
2. Name: `Stadionheft aktualisieren`, Benutzer: **root**
3. *Zeitplan* → Haken bei „Aktiviert" **entfernen** (soll nur auf Zuruf laufen)
4. *Aufgabeneinstellungen → Benutzerdefiniertes Skript*:
   ```
   sh /volume1/SVW/Stadionheft/_Programm/skripte/nas_aktualisieren.sh
   ```

Ab da ist jede Aktualisierung: Aufgabe markieren → **Ausführen** → nach
zwei Minuten `99_Logs/aktualisierung.txt` lesen.

### Weg B – nur Container Manager, ohne Skript

Funktioniert, weil Docker holen *muss*, wenn lokal nichts mehr da ist:

1. *Projekt* → `stadionheft` → **Aktion → Beenden**
2. Reiter **Abbild** → `ghcr.io/habersatterdan/stadionheft-svw:latest`
   markieren → **Löschen**
3. *Projekt* → `stadionheft` → **Aktion → Erstellen**

[skript]: https://github.com/habersatterdan/stadionheft-svw/blob/main/skripte/nas_aktualisieren.sh

**Wenn selbst gebaut wird:** Das reicht *nicht*. „Erstellen" baut aus dem
Quellcode, der auf der NAS liegt – und der ändert sich davon nicht. Es braucht
erst ein neues ZIP:

1. ZIP herunterladen, alten Quellordner löschen, neu entpacken
2. `docker-compose.yml` im neuen Ordner wieder auf `build: .` umstellen
3. Projekt neu erstellen

!!! tip "Nachsehen, welcher Stand wirklich läuft"
    Am schnellsten: **die Fußzeile der Weboberfläche**. Dort steht hinter
    „Stand:" die Fassung, mit der der Container gerade arbeitet:

    ```
    Hilfe · FuPa-Verbindung prüfen · Stadionheft-Generator ·
    Stand: v0.2.0 · gebaut 30.09.2026 07:24 UTC
    ```

    Dieselbe Zeile steht oben in `pruefen` und im FuPa-Prüfbericht. Ist das
    Datum älter als die letzte Änderung, läuft der Container noch mit dem
    alten Code – dann hat die Aktualisierung nicht gegriffen.

Die `config.yaml` und alle Daten bleiben in beiden Fällen erhalten – sie
liegen außerhalb des Containers.

---

## Ohne Weboberfläche arbeiten

Falls die Oberfläche einmal nicht erreichbar ist, geht alles auch über den
**Aufgabenplaner** der NAS (Systemsteuerung → Aufgabenplaner → Erstellen →
Geplante Aufgabe → Benutzerdefiniertes Skript, Benutzer `root`, Zeitplan
deaktivieren, dann „Ausführen" von Hand):

```bash
# Konfiguration und Ordner prüfen, erzeugt nichts
docker exec stadionheft python -m stadionheft.cli pruefen
```

```bash
# FuPa-Verbindung testen
docker exec stadionheft python -m stadionheft.cli probe-fupa
```

Das Ergebnis des FuPa-Tests liegt danach lesbar in

```
_Programm/04_Zwischenergebnisse/fupa_probe/_bericht.txt
```

```bash
# Seiten für alle aktiven Mannschaften erzeugen
docker exec stadionheft python -m stadionheft.cli erstellen
```

!!! tip "Die Aufgabe darf stehen bleiben"
    Sie ist deaktiviert und läuft nie von selbst. Als Notfallknopf ist sie
    praktisch.

---

## Was danach noch offen ist

| Was | Wo |
|---|---|
| Ligen von Herren 2/3 und Damen 1/2 | `_Programm/00_Konfiguration/config.yaml`, mit `TODO` markiert |
| FuPa-Links prüfen | dieselbe Datei, Feld `fupa_team_url` je Mannschaft |
| Zugriff von unterwegs | [Zugriff von unterwegs](VPN_EINRICHTEN.md) |
| Passwortschutz | `zugang.passwortschutz: true` in der config.yaml |

---

## Wenn etwas klemmt

| Problem | Was tun |
|---|---|
| Seite lädt nicht | Container Manager → Container → läuft `stadionheft`? |
| „manifest unknown" beim Laden | Das Image ist noch privat – siehe Schritt 4 |
| „no such file or directory" | Ein Pfad in der docker-compose.yml stimmt nicht |
| Container startet und stoppt sofort | Container Manager → Container → `stadionheft` → **Protokoll**. Meist ein Tippfehler in der config.yaml |
| Leere Seiten im PDF | [FuPa-Verbindung prüfen](fupa.md) |
