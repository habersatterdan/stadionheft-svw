# Erste Einrichtung – Schritt für Schritt

Diese Anleitung führt dich einmal komplett durch. **Kein SSH, keine
Kommandozeile** – alles über die DSM-Oberfläche im Browser, auch von
unterwegs.

Dauer: etwa 30 Minuten, davon 15 Minuten Warten auf den Container-Build.

!!! info "Passt genau auf eure NAS"
    Geschrieben für die **SVWNAS (DS720+)** und die vorhandene Ablage
    `SVW/Stadionheft`. Andere Pfade nur, wenn ausdrücklich erwähnt.

---

## Vorab: Brauche ich SSH?

**Nein.** Alles hier geht über den Browser.

SSH über das Internet wäre auch keine gute Idee: Dafür müsstest du Port 22
im Router freigeben, und dieser Port wird im Internet permanent von
automatisierten Angriffen abgeklopft. Wenn du später doch einmal eine
Kommandozeile brauchst, dann bitte **nur über VPN**, nicht offen freigegeben.

---

## Schritt 1: Prüfen, ob das DSM-Update durch ist

DSM öffnen (über QuickConnect oder im Heimnetz) →
**Systemsteuerung → Info-Center**

Bei **DSM-Version** muss **7.2** oder höher stehen.

??? question "Steht dort noch 7.1?"
    Dann läuft das Update noch oder wurde noch nicht gestartet:
    **Systemsteuerung → Aktualisieren und Wiederherstellen → DSM-Aktualisierung**

    Vor dem Update: Datensicherung prüfen. Das Update dauert 10–20 Minuten,
    die NAS startet dabei neu.

---

## Schritt 2: Container Manager installieren

**Paket-Zentrum** öffnen → oben nach `Container Manager` suchen →
**Installieren**

Dauert ein bis zwei Minuten. Danach erscheint „Container Manager" im
Hauptmenü.

---

## Schritt 3: Startpaket hochladen und entpacken

Du hast von mir die Datei **`SVWNAS_Startpaket.zip`** bekommen. Darin sind
schon fertig enthalten:

* die komplette Ordnerstruktur
* die Konfiguration, passend zu euren Pfaden
* alle 14 Werbeanzeigen aus dem alten Heft, einzeln und benannt
* Kontaktlisten, Impressum und Rücktitel als Seiten
* das Vereinswappen
* die Beispieldaten für Herren 1

So kommt es auf die NAS:

1. **File Station** öffnen
2. Links zu **SVW → Stadionheft** navigieren
3. Oben auf **Upload → Upload – Überspringen** klicken
4. Die Datei `SVWNAS_Startpaket.zip` auswählen und hochladen (12 MB)
5. Nach dem Upload: **Rechtsklick auf die ZIP-Datei → Extrahieren →
   Hierher extrahieren**
6. Die ZIP-Datei danach löschen

Danach liegt in `SVW/Stadionheft` ein neuer Ordner **`_Programm`**.

!!! warning "Wo genau landet `_Programm`?"
    Es muss direkt in `SVW/Stadionheft` liegen, also
    `SVW/Stadionheft/_Programm`. Landet es versehentlich eine Ebene tiefer
    (z. B. `SVW/Stadionheft/app/_Programm`), dann entweder den Ordner
    `_Programm` eine Ebene nach oben ziehen – oder in `docker-compose.yml`
    alle Pfade entsprechend anpassen.

!!! success "Was dabei nicht passiert"
    Deine bestehenden Ordner – `Saison 22 23` bis `Saison 26-27`,
    `Fupa-Export`, `Beregnungseinbau` – werden **nicht angefasst**. Es kommt
    nur ein Ordner dazu.

---

## Schritt 4: Ausgabeordner anlegen

Die fertigen Hefte sollen dort landen, wo sie bisher lagen.

**File Station** → **SVW → Stadionheft → Saison 26-27** →
oben **Create → Ordner erstellen** → Name: `05_Ausgaben`

---

## Schritt 5: Programm auf die NAS bringen

Euer Repository ist privat – die NAS kann es also nicht selbst
herunterladen. Deshalb der Umweg über eine ZIP-Datei. Das ist einmalig
und dauert zwei Minuten.

1. Im Browser https://github.com/habersatterdan/stadionheft-svw öffnen
2. Oben rechts der grüne Knopf **Code** → **Download ZIP**
3. In der **File Station** links auf **docker** klicken
   (die Freigabe gibt es bereits)
4. **Create → Ordner erstellen** → Name: `stadionheft`
5. In diesen Ordner wechseln und die heruntergeladene ZIP hochladen
6. **Rechtsklick → Extrahieren → Hierher extrahieren**

Nach dem Entpacken liegt dort ein Unterordner mit einem langen Namen wie
`stadionheft-svw-main` oder `stadionheft-svw-claude-...`. **Das ist in
Ordnung** – du musst nichts verschieben. Merk dir nur den Namen; im
nächsten Schritt wählst du genau diesen Ordner aus.

Darin müssen `Dockerfile`, `docker-compose.yml` und der Ordner
`stadionheft` liegen.

7. Die ZIP-Datei löschen (wird nicht mehr gebraucht)

---

## Schritt 6: Projekt im Container Manager anlegen

**Container Manager** öffnen → links **Projekt** → **Erstellen**

| Feld | Eingabe |
|---|---|
| Projektname | `stadionheft` |
| Pfad | **Festlegen** → den entpackten Ordner auswählen (der mit dem langen Namen) |
| Quelle | Container Manager erkennt die vorhandene `docker-compose.yml` und schlägt sie vor – bestätigen |

Dann **Weiter → Weiter → Fertig**.

Jetzt baut die NAS das Programm. **Das dauert beim ersten Mal 10–15
Minuten** – im Fenster laufen viele Meldungen durch, das ist normal.
Warten, bis unten **„Läuft"** bzw. **„running"** steht.

??? warning "Fehlermeldung „port is already allocated""
    Port 8080 ist auf der NAS schon belegt. In `docker-compose.yml` die
    **linke** Zahl ändern, z. B. `"8095:8080"`. Die rechte Zahl bleibt 8080.
    Die App ist dann unter Port 8095 erreichbar.

??? warning "Der Build bricht ab"
    Meist zu wenig Arbeitsspeicher oder Plattenplatz. Andere Container
    vorübergehend stoppen und erneut versuchen. Die DS720+ hat 2 GB RAM –
    das reicht, aber nicht mit vielen Containern gleichzeitig.

??? tip "Später: Updates einspielen"
    Bei einer neuen Version: neue ZIP herunterladen, Inhalt von
    `docker/stadionheft` ersetzen, dann im Container Manager beim Projekt
    auf **Erstellen** (Build) klicken. Konfiguration und Daten bleiben
    erhalten – die liegen außerhalb in `_Programm`.

---

## Schritt 7: Aufrufen

Im Browser:

```
http://svwnas:8080
```

Klappt das nicht, die IP verwenden – zu finden unter
**Systemsteuerung → Netzwerk → Netzwerkschnittstelle**, z. B.
`http://192.168.178.42:8080`

**Du solltest jetzt sehen:** „Stadionheft erstellen" mit den fünf
Mannschaften zur Auswahl.

### Sofort ausprobieren

Haken bei **Herren 1** → **Stadionheft erstellen** → warten →
**PDF herunterladen**

Es sollte ein Heft mit 24 Seiten entstehen, Gegner **SG Alerheim**.

---

## Schritt 8: Feste IP vergeben

Damit sich die Adresse nie ändert und Lesezeichen dauerhaft funktionieren:

Im **Router** (FRITZ!Box: Heimnetz → Netzwerk → SVWNAS bearbeiten) den Haken
setzen bei *„Diesem Netzwerkgerät immer die gleiche IPv4-Adresse zuweisen"*.

---

## Schritt 9: Zugriff für die anderen

### Im Vereins-WLAN

Nichts weiter nötig. Adresse weitergeben, fertig. Am Handy lohnt sich
*„Zum Home-Bildschirm hinzufügen"*.

### Von unterwegs – der sichere Weg

Über **VPN**. Eigene Schritt-für-Schritt-Anleitung:
**[VPN einrichten](VPN_EINRICHTEN.md)**

Kurz: DDNS einrichten, VPN Server installieren, WireGuard aktivieren, einen
einzigen UDP-Port im Router freigeben, je Gerät ein Profil per QR-Code.

Wer sich per VPN verbindet, erreicht die App wie zu Hause – und alles andere
auf der NAS gleich mit.

!!! danger "Nicht einfach den Port im Router freigeben"
    Die App hat im Auslieferungszustand keine Anmeldung. Wer die Adresse
    kennt, könnte Hefte erzeugen und eure Daten sehen.

    Soll es ohne VPN gehen, brauchst du **beides**:

    1. **Reverse Proxy mit HTTPS** – DSM → Anmeldeportal → Reverse Proxy,
       dazu ein Let's-Encrypt-Zertifikat
    2. **Passwortschutz einschalten** – in `config.yaml`:
       ```yaml
       zugang:
         passwortschutz: true
         benutzername: "svw"
         passwort_umgebungsvariable: "STADIONHEFT_PASSWORT"
       ```
       Das Passwort selbst im Container Manager unter **Umgebung** setzen,
       nicht in die Datei schreiben.

    QuickConnect hilft hier übrigens nicht – es leitet nur DSM-eigene
    Dienste weiter, keine Container-Ports.

---

## Was danach noch offen ist

| Was | Wo |
|---|---|
| Ligen von Herren 2/3 und Damen 1/2 | `_Programm/00_Konfiguration/config.yaml`, mit `TODO` markiert |
| Vorwort | `_Programm/03_Eingaben/vorwort.md` |
| Titelbild | `_Programm/03_Eingaben/titelbild.jpg` |
| Spielpläne der anderen Mannschaften | `_Programm/03_Eingaben/<mannschaft>_spielplan.csv` |
| FuPa automatisch anbinden | in der App unten auf **„FuPa-Verbindung prüfen"** |

---

## Wenn etwas klemmt

| Problem | Was tun |
|---|---|
| Seite lädt nicht | Container Manager → Container → läuft `stadionheft`? |
| „Einrichtung nicht abgeschlossen" | `config.yaml` liegt nicht in `_Programm/00_Konfiguration` |
| Container startet und stoppt sofort | Container Manager → Protokoll ansehen |
| Heft wird erzeugt, ist aber nicht in `05_Ausgaben` | Ordner aus Schritt 4 fehlt |
| Werbung fehlt im Heft | Liegen die PDFs in `02_Werbung/vorne` bzw. `hinten`? |

Protokolle liegen auf der NAS unter `_Programm/99_Logs/`.
