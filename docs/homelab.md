# Im Homelab betreiben

Das Programm läuft überall, wo Docker läuft – nicht nur auf der Synology. Diese
Seite ist für den Fall, dass es stattdessen (oder zusätzlich) auf einem eigenen
Server laufen soll.

---

## Das Kürzeste

```bash
mkdir -p ~/stadionheft/{config,eingaben,arbeit,ausgaben,logs}

# Beispielkonfiguration holen und anpassen
curl -o ~/stadionheft/config/config.yaml \
  https://raw.githubusercontent.com/habersatterdan/stadionheft-svw/main/config/config.example.yaml

docker run -d --name stadionheft --restart unless-stopped \
  -p 8080:8080 -e TZ=Europe/Berlin \
  -v ~/stadionheft/config:/app/config \
  -v ~/stadionheft/eingaben:/app/daten/03_eingaben \
  -v ~/stadionheft/arbeit:/app/daten/04_zwischenergebnisse \
  -v ~/stadionheft/ausgaben:/app/daten/05_ausgaben \
  -v ~/stadionheft/logs:/app/logs \
  ghcr.io/habersatterdan/stadionheft-svw:latest
```

Danach: `http://<server>:8080`

---

## Mit Compose

```yaml
services:
  stadionheft:
    image: ghcr.io/habersatterdan/stadionheft-svw:latest
    container_name: stadionheft
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      TZ: Europe/Berlin
      # Nur wenn zugang.passwortschutz in der config.yaml aktiv ist:
      # STADIONHEFT_PASSWORT: ${STADIONHEFT_PASSWORT}
    volumes:
      - ./config:/app/config
      - ./eingaben:/app/daten/03_eingaben
      - ./arbeit:/app/daten/04_zwischenergebnisse
      - ./ausgaben:/app/daten/05_ausgaben
      - ./logs:/app/logs
```

Aktualisieren: `docker compose pull && docker compose up -d`

!!! warning "`up -d` allein holt nichts Neues"
    Liegt lokal schon ein Abbild mit dem Namen `latest`, verwendet Docker
    genau dieses weiter – ohne Fehlermeldung, ohne Hinweis. Das `pull` davor
    ist deshalb nicht optional.

    Ob es geklappt hat, steht **in der Fußzeile der Weboberfläche**:
    dort erscheint hinter „Stand:" die Fassung, mit der der Container gerade
    läuft. Dieselbe Angabe liefert
    `docker exec stadionheft python -m stadionheft.cli stand`.

---

## Prozessorarten

Das Image wird für **linux/amd64** und **linux/arm64** gebaut. Es läuft damit
auf gewöhnlichen Servern ebenso wie auf einem Raspberry Pi 4/5 oder einem
ARM-Server. Docker wählt die passende Fassung von selbst.

Bedarf: etwa 300 MB Platte, 300–500 MB Arbeitsspeicher während eines Laufs.

---

## Die Dateien auf die NAS bringen

Wenn das Programm im Homelab läuft, die fertigen PDFs aber auf der NAS liegen
sollen, gibt es zwei Wege.

### Weg A – NAS-Freigabe einhängen (empfohlen)

Die Freigabe auf dem Server mounten und als Ausgabeordner verwenden:

```yaml
    volumes:
      - /mnt/svwnas/Stadionheft/Saison 26-27/05_Ausgaben:/app/daten/05_ausgaben
```

Aus Sicht des Programms ist das ein ganz normaler Ordner. Nichts weiter
einzustellen.

### Weg B – SMB aus dem Programm heraus

In der `config.yaml`:

```yaml
nas:
  aktiv: true
  modus: "smb"
  smb:
    host: "svwnas"
    freigabe: "SVW"
    benutzer: "stadionheft"
    passwort_umgebungsvariable: "NAS_PASSWORT"
    zielordner: "Stadionheft/Saison 26-27/05_Ausgaben"
```

Das Passwort **nicht** in die Datei schreiben, sondern als Umgebungsvariable
setzen:

```yaml
    environment:
      NAS_PASSWORT: ${NAS_PASSWORT}
```

Dafür wird zusätzlich `smbprotocol` gebraucht – das Image bringt es nicht mit,
weil der normale Betrieb es nicht braucht. Weg A ist der einfachere.

---

## Regelmäßig automatisch erzeugen

Wenn die Seiten ohne Knopfdruck entstehen sollen, zum Beispiel jeden Freitag
um 18 Uhr:

```
0 18 * * 5  docker exec stadionheft python -m stadionheft.cli erstellen --frisch
```

Die Dateien landen dann von selbst im Ausgabeordner. Der Knopf in der
Oberfläche bleibt daneben nutzbar.

!!! warning "Nicht öfter als nötig"
    Jeder Lauf holt je Mannschaft mehrere Seiten von fupa.net. Einmal pro
    Woche ist angemessen, stündlich wäre unhöflich.

---

## Erreichbarkeit

Das Programm hat **keine eigene Verschlüsselung und standardmäßig keinen
Login**. Es gehört hinter einen Reverse Proxy oder ins interne Netz.

Mit Passwortschutz (in der `config.yaml`):

```yaml
zugang:
  passwortschutz: true
  benutzer: "svw"
  passwort_umgebungsvariable: "STADIONHEFT_PASSWORT"
```

Das ist HTTP-Basic-Auth – ausreichend gegen versehentliche Zugriffe, kein
Ersatz für HTTPS. Wer es aus dem Internet erreichbar macht, setzt einen Proxy
mit TLS davor (Caddy, Traefik, nginx).

Der Pfad `/gesundheit` antwortet immer ohne Anmeldung – für Healthchecks und
Monitoring.
