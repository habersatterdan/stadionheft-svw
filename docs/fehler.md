# Wenn etwas nicht klappt

Die Meldungen sind absichtlich in normalem Deutsch geschrieben und nennen
immer einen nächsten Schritt. Hier die häufigsten.

---

## Hinweise – kein Grund zur Sorge

Diese erscheinen **unter einem fertigen Heft**. Es ist nichts kaputt.

??? note "„Die Datei … fehlt – die zugehörige Seite bleibt leer.""
    Für eine Mannschaft fehlt eine CSV-Datei. Das Heft ist fertig, nur diese
    eine Seite hat keinen Inhalt.

    **Zu tun:** Datei in `03_Eingaben` ergänzen, siehe
    [Inhalte pflegen](inhalte-pflegen.md). Oder die Seite in der Konfiguration
    für diese Mannschaft abschalten.

??? note "„Anzeige … ist seit dem … abgelaufen""
    Eine befristete Anzeige hat ihr Enddatum überschritten und wurde bewusst
    weggelassen. Genau so soll es sein.

    **Zu tun:** Nichts – oder die Datei löschen, wenn sie nicht mehr gebraucht
    wird. Siehe [Werbung verwalten](werbung.md).

??? note "„Der Gegnerkader stammt aus der allgemeinen Datei …""
    Die Spielerliste des Gegners kommt aus einer Datei, die nicht
    gegnerspezifisch ist. Sie könnte noch zum letzten Gegner gehören.

    **Zu tun:** Seite „Vorstellung Gegner" im PDF prüfen. Dauerhafte Lösung:
    eine Datei je Gegner anlegen.

??? note "„Das Heft hat N Seiten. Für Rückendrahtheftung …""
    Geheftete Hefte brauchen meist eine durch vier teilbare Seitenzahl.

    **Zu tun:** Mit der Druckerei klären oder eine Anzeige bzw. Seite ergänzen.

??? note "„Für … ist noch keine Liga eingetragen""
    In der Konfiguration steht bei dieser Mannschaft noch „TODO".

    **Zu tun:** Administrator bitten, die Liga einzutragen.

---

## Fehler – das Heft wurde nicht erstellt

??? failure "„FuPa ist im Moment nicht erreichbar.""
    Keine Verbindung zu fupa.net. Meist vorübergehend.

    **Zu tun:** Ein paar Minuten warten und erneut versuchen. Wenn es bleibt:
    bei „Woher kommen die Daten?" auf *Aus den CSV-Dateien* umstellen. Dann
    wird mit den zuletzt gepflegten Zahlen gearbeitet.

??? failure "„FuPa hat den automatischen Abruf abgelehnt (403/429).""
    FuPa hat den Zugriff abgewiesen – meist, weil zu oft hintereinander
    abgefragt wurde.

    **Zu tun:** Eine Stunde warten. In der Zwischenzeit mit den CSV-Dateien
    arbeiten. Tritt es dauerhaft auf, einen Administrator informieren.

??? failure "„Die Daten konnten nicht gelesen werden.""
    FuPa antwortet, aber anders als erwartet – vermutlich wurde dort etwas
    umgestellt.

    **Zu tun:** Auf CSV-Dateien umstellen und einen Administrator informieren.
    Der prüft die [FuPa-Anbindung](fupa.md) neu.

??? failure "„Die Datei ‚…' wurde nicht gefunden.""
    Eine als verpflichtend eingetragene Werbe- oder Vorlagendatei fehlt. Der
    vollständige Pfad steht in der Meldung.

    **Zu tun:** Datei an die genannte Stelle legen.

??? failure "„Für … wurden keine Eingabedateien gefunden.""
    Für diese Mannschaft gibt es überhaupt keine CSV-Dateien.

    **Zu tun:** Entweder die Dateien anlegen oder die Mannschaft diesmal nicht
    anhaken.

??? failure "„Die Synology NAS ist nicht erreichbar.""
    Das Heft **ist fertig** – nur das Ablegen auf der NAS hat nicht geklappt.

    **Zu tun:** PDF über den Knopf herunterladen und von Hand ablegen. Der
    lokale Pfad steht in der Meldung.

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

1. **Bist du im richtigen Netz?** Von unterwegs geht es nur über VPN.
2. **Läuft die NAS?** Andere Dienste ausprobieren, z. B. die Dateistation.
3. **Läuft der Container?** Administrator bitten, im Container Manager
   nachzusehen.

---

## Etwas stimmt inhaltlich nicht

| Beobachtung | Ursache |
|---|---|
| Falscher Gegner auf dem Titel | Spielplan prüfen – fehlt die Partie oder stimmt das Datum nicht? |
| Zahlen sind veraltet | Stand-Datum unter der Tabelle ansehen. Bei CSV-Betrieb müssen die Zahlen von Hand aktualisiert werden. |
| Gegnerkader passt nicht | Datei je Gegner anlegen, siehe [Inhalte pflegen](inhalte-pflegen.md) |
| Titelseite ohne Foto | `titelbild.jpg` fehlt in `03_Eingaben` |
| Vorwort ist das alte | `vorwort.md` wurde nicht aktualisiert |

---

## Nichts hilft?

Im Protokoll steht mehr: auf der NAS unter `Stadionheft/99_Logs/`. Bei einer
Meldung in der Oberfläche lässt sich außerdem *„Technische Details"*
aufklappen. Beides hilft einem Administrator bei der Suche.
