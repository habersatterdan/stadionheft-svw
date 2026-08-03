# ---------------------------------------------------------------------------
# Stadionheft-Generator
#
# Gedacht fuer den Betrieb im Container Manager der Synology NAS.
# WeasyPrint braucht Pango/Cairo als Systembibliotheken -- die sind hier fest
# eingebaut, damit auf der NAS nichts nachinstalliert werden muss.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Berlin

# Systempakete fuer WeasyPrint + Schriften.
# fonts-dejavu-core   : garantierte Grundschrift
# fonts-open-sans     : dem in der Vorlage verwendeten Segoe UI sehr aehnlich
#                       und frei lizenziert (Segoe UI selbst darf nicht
#                       mitgeliefert werden -- siehe docs/KONZEPT.md)
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libffi8 \
        libjpeg62-turbo \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-open-sans \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

COPY stadionheft/ ./stadionheft/
COPY config/ ./config/
COPY pyproject.toml README.md ./

# Arbeitsordner; auf der NAS werden hier Volumes eingehaengt.
RUN mkdir -p /app/daten/01_vorlagen /app/daten/02_werbung /app/daten/03_eingaben \
             /app/daten/04_zwischenergebnisse /app/daten/05_ausgaben /app/logs

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/').read()" || exit 1

# Ein Arbeitsprozess mit mehreren Threads reicht voellig -- im Verein
# erstellt praktisch nie mehr als eine Person gleichzeitig ein Heft.
# Das Timeout ist grosszuegig, weil ein Lauf mit vielen Mannschaften und
# langsamer FuPa-Antwort durchaus eine Minute dauern kann.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", \
     "--timeout", "300", "stadionheft.web.wsgi:app"]
