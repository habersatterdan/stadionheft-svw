# Wenn etwas nicht klappt

Die Meldungen sind absichtlich in normalem Deutsch geschrieben und nennen
immer einen nächsten Schritt. Hier die häufigsten.

---

## Hinweise – kein Grund zur Sorge

Diese erscheinen **unter fertigen Dateien**. Es ist nichts kaputt.

??? note "„Von FuPa konnte die Tabelle / die Torschützenliste / … nicht gelesen werden""
    Ein Teil der Daten kam nicht an. Die betreffende Seite bleibt leer, alles
    andere ist fertig.

    **Zu tun:** Unten auf **„FuPa-Verbindung prüfen"** klicken. Dort steht
    Adresse für Adresse, was zurückkam. Meist hilft ein zweiter Versuch ein
    paar Minuten später.

??? note "„Zu … kamen keine Zahlen an – die Gegnerseiten bleiben leer""
    Die eigene Mannschaft ist vollständig, nur zum Gegner gab es nichts.

    **Zu tun:** Oft hat der Gegner bei FuPa selbst noch keine Daten gepflegt.
    Wenn es dauerhaft bleibt, kann ein Administrator den FuPa-Link des Gegners
    fest hinterlegen – siehe [FuPa-Anbindung](fupa.md#wenn-etwas-nicht-gefunden-wird).

??? note "„… liefert FuPa im Spielplan keinen Team-Bezeichner""
    Das Programm konnte die Seite des Gegners nicht finden, weil FuPa im
    Spielplan keinen Verweis darauf mitliefert.

    **Zu tun:** Administrator bitten, den Link in der `config.yaml` unter
    `datenquelle.fupa.gegner` einzutragen. Einmal pro Gegner, dann ist Ruhe.

??? note "„Der Gegnerkader stammt aus der allgemeinen Datei …""
    Nur im CSV-Betrieb. Die Spielerliste könnte noch zum letzten Gegner
    gehören.

    **Zu tun:** Die Gegnerseite im PDF prüfen. Dauerhafte Lösung: eine Datei
    je Gegner anlegen, siehe [CSV-Reserve](csv-reserve.md).

??? note "„Für … ist noch keine Liga eingetragen""
    In der Konfiguration steht bei dieser Mannschaft noch „TODO". Auf der
    Trennseite fehlt dadurch die Ligabezeichnung.

    **Zu tun:** Administrator bitten, die Liga einzutragen.

??? note "„Es wurde automatisch auf 'manuell' umgeschaltet""
    FuPa hat nichts geliefert, deshalb wurden die CSV-Dateien verwendet.

    **Zu tun:** Prüfen, ob die Zahlen stimmen – CSV-Dateien sind nur so
    aktuell wie ihre letzte Pflege. [CSV-Reserve](csv-reserve.md)

---

## Rot im PDF: „Achtung – möglicherweise veraltet"

Steht dieser Kasten unten auf den Seiten, war FuPa beim Erzeugen nicht
erreichbar und es wurden **ältere Daten aus dem Zwischenspeicher** verwendet.
Daneben steht, von wann sie sind.

**Zu tun:** Später noch einmal erzeugen. Ins Heft sollten diese Seiten nur,
wenn die Zeit drängt – und dann mit dem Wissen, dass der Stand nicht der von
heute ist.

---

## Fehler – es sind keine Dateien entstanden

??? failure "„FuPa ist im Moment nicht erreichbar.""
    Keine Verbindung zu fupa.net. Meist vorübergehend.

    **Zu tun:** Ein paar Minuten warten und erneut versuchen. Wenn es bleibt:
    unter „Weitere Einstellungen" bei *Woher kommen die Daten?* auf
    *Aus den CSV-Dateien* umstellen.

??? failure "„FuPa hat den automatischen Abruf abgelehnt (403/429).""
    FuPa hat den Zugriff abgewiesen – meist, weil zu oft hintereinander
    abgefragt wurde.

    **Zu tun:** Eine Stunde warten. In der Zwischenzeit mit den CSV-Dateien
    arbeiten. Tritt es dauerhaft auf, einen Administrator informieren.

??? failure "„Für … fehlt ein gültiger FuPa-Link.""
    In der Konfiguration steht bei dieser Mannschaft keine brauchbare Adresse.

    **Zu tun:** Administrator bitten, `fupa_team_url` zu prüfen. Erwartet wird
    eine Adresse der Form `https://www.fupa.net/team/<name>-<saison>`.

??? failure "„Für … wurden keine Eingabedateien gefunden.""
    Im CSV-Betrieb: Für diese Mannschaft gibt es überhaupt keine Dateien.

    **Zu tun:** Entweder die Dateien anlegen oder die Mannschaft diesmal nicht
    anhaken.

??? failure "„Die Konfiguration enthält Fehler: …""
    In `config.yaml` stimmt etwas nicht. Jeder Punkt wird einzeln aufgeführt.

    **Zu tun:** Administrator informieren. Meist ist es eine verrutschte
    Einrückung.

??? failure "„Einrichtung nicht abgeschlossen""
    Das Programm läuft, findet aber keine Konfiguration.

    **Zu tun:** Administrator informieren – es fehlt die `config.yaml` im
    Ordner `00_Konfiguration`.

---

## Die Seite lädt gar nicht

1. **Bist du im richtigen Netz?** Von unterwegs geht es nur über VPN oder
   Tailscale – siehe [Zugriff von unterwegs](VPN_EINRICHTEN.md).
2. **Läuft die NAS?** Andere Dienste ausprobieren, z. B. die File Station.
3. **Läuft der Container?** Administrator bitten, im Container Manager
   nachzusehen.

---

## Etwas stimmt inhaltlich nicht

| Beobachtung | Ursache |
|---|---|
| Falscher Gegner | Steht das Spiel in FuPa? Hat es das richtige Datum? Maßgeblich ist immer das Datum, nicht die Reihenfolge. |
| Zahlen sind veraltet | Auf jeder Seite unten steht der Abrufzeitpunkt. Stimmt er, sind es FuPas Zahlen von genau dann. |
| Formkurve fehlt | Die Ergebnisse stehen bei FuPa noch nicht drin. Ohne Ergebnis kein S/U/N. |
| Saisonbilanz bleibt leer | Dasselbe: Sie wird aus den gespielten Partien gerechnet. |
| Tabelle zweimal im Heft | Das ist gewollt, wenn der Gegner in einer anderen Liga spielt (Pokal). |
| Gegnerkader passt nicht | Im CSV-Betrieb: Datei je Gegner anlegen, siehe [CSV-Reserve](csv-reserve.md) |

---

## Nichts hilft?

Im Protokoll steht mehr: auf der NAS unter `_Programm/99_Logs/`. Bei einer
Meldung in der Oberfläche lässt sich außerdem *„Technische Details"*
aufklappen.

Für FuPa-Probleme ist die aussagekräftigste Datei

```
_Programm/04_Zwischenergebnisse/fupa_probe/_bericht.txt
```

Sie entsteht beim Klick auf **„FuPa-Verbindung prüfen"** und nennt zu jeder
Adresse, was zurückkam.

---

## Quellen prüfen – ganz ohne Container

Wenn nicht einmal klar ist, ob eine Webseite die gesuchten Daten überhaupt
ausliefert, hilft `skripte/quellen_pruefen.sh`. Das Skript braucht weder das
Programm noch Docker – nur `curl`.

**So wird es angestoßen:**

1. Datei nach `_Programm/skripte/quellen_pruefen.sh` legen
2. *Systemsteuerung → Aufgabenplaner → Erstellen → Geplante Aufgabe →
   Benutzerdefiniertes Skript*
3. Benutzer: `root`, Befehl:
   `sh /volume1/SVW/Stadionheft/_Programm/skripte/quellen_pruefen.sh`
4. Aufgabe markieren → **Ausführen**

**Das Ergebnis** steht in `_Programm/99_Logs/quellen_pruefen.txt`, die
abgeholten Seiten selbst in `_Programm/99_Logs/quellen/`.

Zu jeder Adresse meldet der Bericht:

| Zeile im Bericht | Bedeutung |
|---|---|
| `*** KALENDER gefunden, 24 Termine ***` | Treffer. Diese Adresse gehört unter `datenquelle.fupa.zusatz_adressen`. |
| `enthaelt __NEXT_DATA__ (1 x)` | Die Seite bringt eingebettetes JSON mit – das Programm kann es lesen. |
| `nennt 'Wörnitzstein' (2 x)` bei 200 KB Seite | Die Daten stehen **nicht** in der Seite; der Browser holt sie nach. Diese Adresse bringt nichts. |
| `HTTP 404` | Gibt es nicht. |
| `HTTP 403` | Vorhanden, aber gesperrt. |

Welche Adressen geprüft werden, steht im Skript oben unter `ADRESSEN` –
eine Zeile je Adresse, Name und URL durch `|` getrennt. Weitere lassen sich
dort einfach anhängen.
