"""Weboberflaeche (Flask).

Bewusst klein gehalten: eine Seite mit dem Formular, eine Fortschrittsseite,
ein Download. Kein Login, keine Datenbank, kein JavaScript-Framework -- die
Anwendung laeuft im Vereinsnetz bzw. auf der NAS und soll auch in fuenf Jahren
noch von jemandem repariert werden koennen, der Python nur grundlegend kennt.

Die eigentliche Arbeit macht ``stadionheft.build``. Diese Schicht kuemmert sich
nur um Formular, Fortschrittsanzeige und verstaendliche Fehlermeldungen.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, url_for)

from .. import programmstand
from ..build import dateien_erstellen
from ..config import Konfiguration
from ..errors import StadionheftFehler
from ..logging_setup import LaufProtokoll, einrichten, logger


@dataclass
class Lauf:
    """Zustand eines Laufs (fuer die Fortschrittsanzeige)."""

    id: str
    gestartet: datetime = field(default_factory=datetime.now)
    fertig: bool = False
    erfolgreich: bool = False
    ergebnis: dict | None = None
    fehler: dict | None = None
    protokoll: list[dict] = field(default_factory=list)
    benutzer: str = ""
    #: Ablage auf der NAS per Knopf (nur nas.modus = filestation)
    nas: dict = field(default_factory=dict)
    #: Von Hand hochgeladenes Titelbild (geht mit auf die NAS)
    titelbild: str = ""
    #: Von Hand hochgeladene Zeitungsberichte je Mannschaft (Schluessel -> Datei)
    berichte: dict = field(default_factory=dict)

    def als_dict(self) -> dict:
        return {
            "id": self.id,
            "fertig": self.fertig,
            "erfolgreich": self.erfolgreich,
            "ergebnis": self.ergebnis,
            "fehler": self.fehler,
            "protokoll": self.protokoll[-200:],
        }


def app_erzeugen(konfiguration: Konfiguration | None = None) -> Flask:
    k = konfiguration or Konfiguration.laden()
    einrichten(k.pfad(k.get("protokoll.ordner"), "logs"),
               str(k.get("protokoll.level", "INFO")))

    app = Flask(__name__)
    app.config["KONFIGURATION"] = k
    # Titelbild + Zeitungsberichte vom Handy in einer Anfrage; jede Datei
    # wird zusaetzlich einzeln begrenzt.
    app.config["MAX_CONTENT_LENGTH"] = ANFRAGE_MAX_BYTES

    @app.errorhandler(413)
    def zu_gross(_fehler):
        return render_template(
            "fehler.html", titel="Datei zu groß",
            meldung=f"Titelbild und Zeitungsberichte dürfen zusammen höchstens "
                    f"{ANFRAGE_MAX_BYTES // 1_000_000} MB groß sein.",
            hinweis="Bitte ein kleineres Bild wählen (am Handy z. B. per "
                    "Teilen → verkleinern).", technisch=""), 413

    from .zugang import einrichten as zugang_einrichten
    zugang_einrichten(app, k)

    @app.get("/gesundheit")
    def gesundheit():
        """Fuer den Healthcheck des Containers -- bewusst ohne Anmeldung."""
        return {"status": "ok"}

    # Jede Vorlage -- auch die Fehlerseiten -- braucht die Konfiguration
    # fuer Kopf- und Fusszeile.
    @app.context_processor
    def standard_kontext():
        # Der Programmstand steht in der Fusszeile jeder Seite. Grund: Auf der
        # NAS ist die haeufigste Stoerung, dass der Container noch mit altem
        # Code laeuft -- das sieht man sonst nirgends, weil nichts fehlschlaegt.
        return {"konfiguration": k, "programmstand": programmstand()}

    laeufe: dict[str, Lauf] = {}
    sperre = threading.Lock()

    def _filestation_aktiv() -> bool:
        return bool(k.get("nas.aktiv", False)) and k.get("nas.modus") == "filestation"

    # -- Seiten -------------------------------------------------------------

    @app.get("/")
    def start():
        from ..storage.nas import NasAblage
        from ..vorabpruefung import vorab_pruefen

        nas_ok, nas_meldung = NasAblage(k).erreichbar()
        # Ohne Probeseite: Die Startseite soll sofort da sein. Den
        # vollstaendigen Durchlauf gibt es auf der eigenen Pruefseite.
        lage = vorab_pruefen(k, probeseite=False)
        return render_template(
            "start.html",
            konfiguration=k,
            mannschaften=k.aktive_mannschaften(),
            modus=k.get("datenquelle.modus", "api"),
            cache_minuten=k.get("datenquelle.cache.gueltigkeit_minuten", 15),
            nas_aktiv=bool(k.get("nas.aktiv", False)),
            nas_ok=nas_ok,
            nas_meldung=nas_meldung,
            # Die fehlende Liga steht schon bei der Mannschaft selbst. Noch
            # einmal als Kasten obendrueber macht die Seite nur voll und
            # gewoehnt daran, Hinweise zu ueberlesen.
            warnungen=[w for w in k.warnungen
                       if "keine Liga eingetragen" not in w],
            lage=lage,
            quelle_je_mannschaft={m.schluessel: m for m in lage.mannschaften},
            bericht_mannschaften=_bericht_mannschaften(k),
        )

    @app.get("/vorab")
    def vorab():
        """Die vollstaendige Vorab-Pruefung, mit Probeseite."""
        from ..vorabpruefung import als_text, vorab_pruefen

        lage = vorab_pruefen(k)
        return render_template("vorab.html", konfiguration=k, lage=lage,
                               text=als_text(k, lage))

    @app.post("/erstellen")
    def erstellen():
        auswahl = request.form.getlist("mannschaften")
        if not auswahl:
            return render_template(
                "fehler.html",
                titel="Keine Mannschaft ausgewählt",
                meldung="Bitte mindestens eine Mannschaft anhaken.",
                hinweis="", technisch=""), 400

        lauf = Lauf(id=uuid.uuid4().hex[:12],
                    benutzer=request.form.get("benutzer", "").strip())
        titelbild = None
        hochgeladen = request.files.get("titelbild")
        if hochgeladen and hochgeladen.filename:
            inhalt = hochgeladen.read()
            endung = _bildendung(inhalt)
            if not endung or len(inhalt) > TITELBILD_MAX_BYTES:
                return render_template(
                    "fehler.html", titel="Titelbild nicht lesbar",
                    meldung="Das Titelbild muss ein JPG- oder PNG-Bild sein.",
                    hinweis="Am Handy klappt es mit einem Foto aus der Galerie.",
                    technisch=hochgeladen.filename), 400
            # Genau so benannt, wie es im Ausgabe-Ordner liegen soll -- daran
            # erkennt es "Gesamtes Heft bauen" spaeter wieder.
            ordner = k.arbeits_ordner / "titelbilder" / lauf.id
            ordner.mkdir(parents=True, exist_ok=True)
            titelbild = ordner / f"Titelbild{endung}"
            titelbild.write_bytes(inhalt)
            lauf.titelbild = str(titelbild)
        for m in _bericht_mannschaften(k):
            hochgeladen = request.files.get(f"bericht_{m.schluessel}")
            if not hochgeladen or not hochgeladen.filename:
                continue
            inhalt = hochgeladen.read()
            endung = _berichtendung(inhalt)
            if not endung or len(inhalt) > TITELBILD_MAX_BYTES:
                return render_template(
                    "fehler.html", titel="Zeitungsbericht nicht lesbar",
                    meldung=f"Der Zeitungsbericht für {m.anzeigename} muss ein "
                            f"PDF oder ein JPG-/PNG-Bild sein (höchstens "
                            f"{TITELBILD_MAX_BYTES // 1_000_000} MB).",
                    hinweis="Am Handy klappt ein Foto oder Scan der Zeitungsseite.",
                    technisch=hochgeladen.filename), 400
            # Liegt spaeter im Ordner der Mannschaft -- "Gesamtes Heft bauen"
            # setzt ihn dort als Spielbericht vor die FuPa-Seiten.
            ordner = k.arbeits_ordner / "berichte" / lauf.id / m.schluessel
            ordner.mkdir(parents=True, exist_ok=True)
            bericht = ordner / f"Zeitungsbericht {m.anzeigename}{endung}"
            bericht.write_bytes(inhalt)
            lauf.berichte[m.schluessel] = str(bericht)
        with sperre:
            laeufe[lauf.id] = lauf

        argumente = {
            "titelbild": titelbild,
            "mannschaften": auswahl,
            "spieltag": request.form.get("spieltag", "").strip(),
            "datenquelle": request.form.get("quelle") or None,
            "erzeugt_von": lauf.benutzer or "Weboberfläche",
            "frisch": request.form.get("frisch") == "ja",
        }

        threading.Thread(target=_lauf_ausfuehren, args=(k, lauf, argumente),
                         daemon=True).start()
        return redirect(url_for("fortschritt", lauf_id=lauf.id))

    @app.get("/lauf/<lauf_id>")
    def fortschritt(lauf_id: str):
        lauf = laeufe.get(lauf_id)
        if not lauf:
            abort(404)
        return render_template("lauf.html", lauf=lauf, konfiguration=k,
                               nas_ablage=_filestation_aktiv())

    @app.get("/lauf/<lauf_id>/status")
    def status(lauf_id: str):
        lauf = laeufe.get(lauf_id)
        if not lauf:
            return jsonify({"fehlt": True}), 404
        return jsonify(lauf.als_dict())

    @app.get("/lauf/<lauf_id>/download")
    def download(lauf_id: str):
        """Alle Dateien als ZIP -- ein Klick statt fuenf."""
        lauf = laeufe.get(lauf_id)
        if not lauf or not lauf.ergebnis:
            abort(404)
        pfad = Path(lauf.ergebnis.get("archiv") or "")
        if not str(pfad) or not pfad.exists():
            abort(404)
        return send_file(pfad, as_attachment=True, download_name=pfad.name)

    @app.get("/lauf/<lauf_id>/datei/<int:nummer>")
    def datei(lauf_id: str, nummer: int):
        """Eine einzelne Mannschaftsdatei."""
        lauf = laeufe.get(lauf_id)
        if not lauf or not lauf.ergebnis:
            abort(404)
        dateien = lauf.ergebnis.get("dateien") or []
        if not 0 <= nummer < len(dateien):
            abort(404)
        pfad = Path(dateien[nummer]["pfad"])
        if not pfad.exists():
            abort(404)
        return send_file(pfad, as_attachment=True, download_name=pfad.name)

    # -- Ablage auf der NAS per Knopfdruck (File Station) --------------------

    def _ablage_dateien(lauf: Lauf) -> list[tuple[str, Path]]:
        dateien = [(d.get("schluessel", ""), Path(d["pfad"]))
                   for d in (lauf.ergebnis or {}).get("dateien") or []]
        # Die Spieldaten des Laufs gehen mit: Daraus setzt "Gesamtes Heft
        # bauen" spaeter Deckblatt und FuPa-Seiten neu (mit Balken).
        snapshot = (lauf.ergebnis or {}).get("snapshot")
        if snapshot and Path(snapshot).exists():
            dateien.append(("ordner:_daten", Path(snapshot)))
        # Ein hochgeladenes Titelbild liegt danach im Ausgabe-Ordner -- und
        # ersetzt dort das aus der Vorlage (auch fuers Gesamtheft).
        if lauf.titelbild and Path(lauf.titelbild).exists():
            dateien.append(("", Path(lauf.titelbild)))
        for schluessel, bericht in lauf.berichte.items():
            if Path(bericht).exists():
                dateien.append((schluessel, Path(bericht)))
        return dateien

    @app.get("/lauf/<lauf_id>/nas/vorschlag")
    def nas_vorschlag(lauf_id: str):
        """Was beim Klick passieren wuerde -- ohne etwas anzulegen."""
        from ..storage.filestation import (FileStation, ordnername_vorschlagen,
                                           zielordner_fuer)

        lauf = laeufe.get(lauf_id)
        if not lauf or not lauf.ergebnis or not _filestation_aktiv():
            abort(404)
        saison = k.nas_saison_ordner
        termine = []
        for d in lauf.ergebnis.get("dateien") or []:
            try:
                termine.append(datetime.strptime(d.get("anstoss", ""), "%d.%m.%Y"))
            except ValueError:
                pass
        ziele = [{"datei": pfad.name,
                  "ordner": zielordner_fuer(k, schluessel) if schluessel else ""}
                 for schluessel, pfad in _ablage_dateien(lauf)]
        antwort = {"saison_ordner": saison,
                   "vorlage": k.get("nas.filestation.vorlage_ordner", ""),
                   "ziele": ziele, "vorhandene": [], "vorschlag": "",
                   "fehler": "", "status": lauf.nas}
        try:
            with FileStation.aus_konfiguration(k) as fs:
                antwort["vorhandene"] = sorted(
                    f["name"] for f in fs.auflisten(saison) if f.get("isdir"))
        except StadionheftFehler as fehler:
            antwort["fehler"] = fehler.benutzer_text
        antwort["vorschlag"] = ordnername_vorschlagen(
            antwort["vorhandene"], min(termine) if termine else None,
            str(k.get("nas.filestation.ordnername",
                      "{nummer:02d} Ausgabe {datum:%d%m%y}")))
        return jsonify(antwort)

    @app.post("/lauf/<lauf_id>/nas")
    def nas_ablegen(lauf_id: str):
        lauf = laeufe.get(lauf_id)
        if not lauf or not lauf.ergebnis or not _filestation_aktiv():
            abort(404)
        ordnername = (request.form.get("ordnername")
                      or (request.get_json(silent=True) or {}).get("ordnername")
                      or "")
        with sperre:
            if lauf.nas.get("laeuft"):
                return jsonify({"fehler": "Die Ablage läuft bereits."}), 409
            vorher = lauf.nas.get("bericht") or {}
            if vorher.get("erfolgreich"):
                return jsonify({"fehler": "Dieses Heft liegt bereits auf der NAS."}), 409
            # Derselbe Name wie beim abgebrochenen Versuch: dort weitermachen,
            # statt an "gibt es schon" zu scheitern. Nur innerhalb dieses
            # Laufs -- einen fremden Ordner fasst die Ablage nie an.
            fortsetzen = bool(vorher.get("angelegt")) and \
                " ".join(ordnername.split()) == lauf.nas.get("ordnername")
            lauf.nas = {"laeuft": True, "ordnername": " ".join(ordnername.split())}
        threading.Thread(target=_ablage_ausfuehren,
                         args=(k, lauf, ordnername, _ablage_dateien(lauf), fortsetzen),
                         daemon=True).start()
        return jsonify({"gestartet": True})

    @app.get("/lauf/<lauf_id>/nas/status")
    def nas_status(lauf_id: str):
        lauf = laeufe.get(lauf_id)
        if not lauf:
            return jsonify({"fehlt": True}), 404
        return jsonify(lauf.nas)

    @app.get("/nas")
    def nas_ordner():
        """Liest Saison- und Vorlage-Ordner direkt von der NAS -- zum Pruefen
        der Einstellungen ohne DSM."""
        from ..storage.filestation import FileStation

        lage = {"aktiv": _filestation_aktiv(), "fehler": "", "freigaben": [],
                "saison": [], "vorlage": [],
                "saison_ordner": k.nas_saison_ordner,
                "vorlage_ordner": str(k.get("nas.filestation.vorlage_ordner", ""))}
        if lage["aktiv"]:
            try:
                with FileStation.aus_konfiguration(k) as fs:
                    lage["adresse"] = fs.adresse
                    lage["freigaben"] = [f["path"] for f in fs._roh(
                        {"api": "SYNO.FileStation.List", "version": "2",
                         "method": "list_share"}).get("shares") or []]
                    saison = lage["saison_ordner"].rstrip("/")
                    eltern, _, name = saison.rpartition("/")
                    if not any(f["name"] == name
                               for f in fs.auflisten(eltern or "/")):
                        lage["saison_fehlt"] = True
                    else:
                        lage["saison"] = fs.auflisten(saison)
                    if lage["vorlage_ordner"] and any(
                            f["name"] == lage["vorlage_ordner"] for f in lage["saison"]):
                        lage["vorlage"] = fs.auflisten(
                            f"{saison}/{lage['vorlage_ordner']}")
            except StadionheftFehler as fehler:
                lage["fehler"] = fehler.benutzer_text
        lage["saison_meldung"] = request.args.get("saison", "")
        lage["saison_fehler"] = request.args.get("meldung", "")
        return render_template("nas.html", konfiguration=k, lage=lage)

    # -- Neue Saison ----------------------------------------------------------

    @app.post("/nas/saison")
    def nas_saison_anlegen():
        from ..storage.filestation import saison_anlegen

        if not _filestation_aktiv():
            abort(404)
        bericht = saison_anlegen(k).als_dict()
        return redirect(url_for("nas_ordner", saison="ok" if bericht["erfolgreich"]
                                else "fehler", meldung=bericht["fehler"]))

    # -- Zweiter Knopf: das gesamte Heft --------------------------------------

    hefte: dict[str, Lauf] = {}

    def _gesamtheft_aktiv() -> bool:
        return _filestation_aktiv() and bool(k.get("heft.gesamt_aktiv", False))

    @app.get("/heft")
    def heft_seite():
        from ..gesamtheft import ausgaben_auflisten

        if not _gesamtheft_aktiv():
            abort(404)
        ausgaben, fehler = [], ""
        try:
            ausgaben = ausgaben_auflisten(k)
        except StadionheftFehler as ausnahme:
            fehler = ausnahme.benutzer_text
        return render_template("heft.html", konfiguration=k, ausgaben=ausgaben,
                               fehler=fehler, lauf=None)

    @app.post("/heft")
    def heft_bauen():
        if not _gesamtheft_aktiv():
            abort(404)
        name = request.form.get("ausgabe", "").strip()
        if not name:
            return redirect(url_for("heft_seite"))
        with sperre:
            if any(not h.fertig for h in hefte.values()):
                return render_template(
                    "fehler.html", titel="Es wird schon ein Heft gebaut",
                    meldung="Bitte warten, bis der laufende Bau fertig ist.",
                    hinweis="", technisch=""), 409
            lauf = Lauf(id=uuid.uuid4().hex[:12])
            hefte[lauf.id] = lauf
        threading.Thread(target=_heft_ausfuehren,
                         args=(k, lauf, name, request.form.get("neu") == "ja"),
                         daemon=True).start()
        return redirect(url_for("heft_fortschritt", lauf_id=lauf.id))

    @app.get("/heft/<lauf_id>")
    def heft_fortschritt(lauf_id: str):
        lauf = hefte.get(lauf_id)
        if not lauf:
            abort(404)
        return render_template("heft.html", konfiguration=k, ausgaben=[],
                               fehler="", lauf=lauf)

    @app.get("/heft/<lauf_id>/status")
    def heft_status(lauf_id: str):
        lauf = hefte.get(lauf_id)
        if not lauf:
            return jsonify({"fehlt": True}), 404
        zustand = lauf.als_dict()
        zustand["aktuell"] = lauf.nas.get("aktuell", "")
        return jsonify(zustand)

    @app.get("/heft/<lauf_id>/download")
    def heft_download(lauf_id: str):
        lauf = hefte.get(lauf_id)
        if not lauf or not lauf.ergebnis:
            abort(404)
        pfad = Path(lauf.ergebnis.get("pdf") or "")
        if not str(pfad) or not pfad.exists():
            abort(404)
        return send_file(pfad, as_attachment=True, download_name=pfad.name)

    @app.context_processor
    def heft_kontext():
        return {"gesamtheft_aktiv": _gesamtheft_aktiv()}

    @app.get("/hilfe")
    def hilfe():
        return render_template("hilfe.html", konfiguration=k)

    # -- FuPa-Verbindung pruefen -------------------------------------------
    # Bewusst als Knopf in der Oberflaeche und nicht nur als Befehl auf der
    # Kommandozeile: Der Test ist der eine Schritt, der den automatischen
    # Datenabruf freischaltet -- dafuer soll niemand ein Terminal oeffnen
    # muessen.

    @app.get("/fupa-test")
    def fupa_test():
        return render_template("fupa_test.html", konfiguration=k,
                               mannschaften=k.aktive_mannschaften(),
                               bericht=None)

    @app.post("/fupa-test")
    def fupa_test_starten():
        from ..sources.fupa_api import probe_fupa

        auswahl = request.form.get("mannschaft") or None
        try:
            bericht = probe_fupa(k, auswahl)
            fehler = None
        except StadionheftFehler as ausnahme:
            logger().error("FuPa-Test fehlgeschlagen: %s", ausnahme.technisch)
            bericht, fehler = None, ausnahme.as_dict()

        return render_template("fupa_test.html", konfiguration=k,
                               mannschaften=k.aktive_mannschaften(),
                               bericht=bericht, fehler=fehler)

    @app.get("/fupa-test/download")
    def fupa_test_download():
        """Packt die Rohantworten als ZIP -- die Datei, die zur Auswertung
        weitergegeben wird."""
        import io
        import zipfile

        ordner = Path(k.arbeits_ordner) / "fupa_probe"
        if not ordner.is_dir():
            abort(404)

        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
            # Auch die Rohantworten: Wenn nichts erkannt wurde, sind sie
            # das Einzige, woran sich der Aufbau der Seite ablesen laesst.
            for muster in ("*.json", "*.html", "*.txt"):
                for datei in sorted(ordner.glob(muster)):
                    archiv.write(datei, arcname=datei.name)
        puffer.seek(0)
        return send_file(puffer, mimetype="application/zip", as_attachment=True,
                         download_name="fupa_probe.zip")

    # -- Fehlerbehandlung ---------------------------------------------------

    @app.errorhandler(404)
    def nicht_gefunden(_fehler):
        return render_template(
            "fehler.html", titel="Seite nicht gefunden",
            meldung="Diese Adresse gibt es nicht (mehr).",
            hinweis="Vermutlich wurde die Anwendung zwischenzeitlich neu gestartet.",
            technisch=""), 404

    @app.errorhandler(StadionheftFehler)
    def bekannter_fehler(fehler: StadionheftFehler):
        logger().error("%s", fehler.technisch)
        return render_template(
            "fehler.html", titel="Es ist ein Fehler aufgetreten",
            meldung=fehler.benutzer_text, hinweis=fehler.hinweis or "",
            technisch=fehler.technisch), 500

    return app


TITELBILD_MAX_BYTES = 30_000_000
ANFRAGE_MAX_BYTES = 150_000_000


def _bericht_mannschaften(k: Konfiguration) -> list:
    """Mannschaften mit Upload-Feld fuer den Zeitungsbericht.

    ``heft.zeitungsberichte`` waehlt sie aus (leer = alle aktiven). Nur
    Mannschaften mit eigenem NAS-Ordner -- der Bericht gehoert dorthin.
    """
    wahl = k.get("heft.zeitungsberichte") or []
    ordner = k.get("nas.filestation.mannschaftsordner", {}) or {}
    return [m for m in k.aktive_mannschaften()
            if (not wahl or m.schluessel in wahl) and ordner.get(m.schluessel)]


def _berichtendung(inhalt: bytes) -> str:
    """PDF, JPG oder PNG -- am Inhalt erkannt."""
    if inhalt[:5] == b"%PDF-":
        return ".pdf"
    return _bildendung(inhalt)


def _bildendung(inhalt: bytes) -> str:
    """Erkennt JPG/PNG am Inhalt, nicht am Dateinamen."""
    if inhalt[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if inhalt[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return ""


def _lauf_ausfuehren(k: Konfiguration, lauf: Lauf, argumente: dict) -> None:
    """Laeuft im Hintergrund-Thread und fuellt ``lauf`` mit dem Ergebnis."""
    with LaufProtokoll() as protokoll:
        lauf.protokoll = protokoll.zeilen
        try:
            ergebnis = dateien_erstellen(k, **argumente)
            lauf.ergebnis = ergebnis.als_dict()
            lauf.erfolgreich = True
        except StadionheftFehler as fehler:
            logger().error("Lauf abgebrochen: %s", fehler.technisch)
            lauf.fehler = fehler.as_dict()
        except Exception as fehler:  # noqa: BLE001
            logger().exception("Unerwarteter Fehler beim Erzeugen der Dateien")
            lauf.fehler = {
                "typ": type(fehler).__name__,
                "meldung": "Im Programm ist ein unerwarteter Fehler aufgetreten.",
                "hinweis": "Bitte einen Administrator informieren. Details "
                           "stehen im Protokoll unter logs/.",
                "technisch": str(fehler),
            }
        finally:
            lauf.fertig = True


def _ablage_ausfuehren(k: Konfiguration, lauf: Lauf, ordnername: str,
                       dateien: list[tuple[str, Path]], fortsetzen: bool) -> None:
    """Hintergrund-Thread hinter dem Knopf 'Auf NAS ablegen'."""
    from ..storage.filestation import ablage_ausfuehren

    def melden(text: str) -> None:
        lauf.nas["aktuell"] = text

    try:
        bericht = ablage_ausfuehren(k, ordnername, dateien, fortsetzen=fortsetzen,
                                    melden=melden).als_dict()
    except StadionheftFehler as fehler:
        bericht = {"erfolgreich": False, "ordner": "", "schritte": [],
                   "fehler": " ".join(t for t in (fehler.benutzer_text,
                                                  fehler.hinweis) if t)}
    except Exception as fehler:  # noqa: BLE001
        logger().exception("Unerwarteter Fehler bei der NAS-Ablage")
        bericht = {"erfolgreich": False, "ordner": "", "schritte": [],
                   "fehler": f"Unerwarteter Fehler: {fehler}"}
    lauf.nas = {"laeuft": False, "fertig": True,
                "ordnername": " ".join(ordnername.split()), "bericht": bericht}


def _heft_ausfuehren(k: Konfiguration, lauf: Lauf, name: str, neu: bool) -> None:
    """Hintergrund-Thread hinter 'Gesamtes Heft bauen'."""
    from ..gesamtheft import gesamtheft_bauen

    def melden(text: str) -> None:
        lauf.nas["aktuell"] = text

    with LaufProtokoll() as protokoll:
        lauf.protokoll = protokoll.zeilen
        try:
            lauf.ergebnis = gesamtheft_bauen(k, name, neu_planen=neu,
                                             melden=melden).als_dict()
            lauf.erfolgreich = True
        except StadionheftFehler as fehler:
            logger().error("Heftbau abgebrochen: %s", fehler.technisch)
            lauf.fehler = fehler.as_dict()
        except Exception as fehler:  # noqa: BLE001
            logger().exception("Unerwarteter Fehler beim Heftbau")
            lauf.fehler = {"typ": type(fehler).__name__,
                           "meldung": "Im Programm ist ein unerwarteter Fehler "
                                      "aufgetreten.",
                           "hinweis": "Details stehen im Protokoll.",
                           "technisch": str(fehler)}
        finally:
            lauf.fertig = True
