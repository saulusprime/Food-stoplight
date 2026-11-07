# Food-stoplight: immagine di produzione (gunicorn, dati su /data)
#
#   docker build -t food-stoplight .
#   docker run -p 8000:8000 -e FLASK_SECRET_KEY=... -v dati:/data food-stoplight

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=produzione \
    DATABASE_PATH=/data/alimenti.db \
    UTENTI_DB_PATH=/data/utenti.db \
    DIARIO_DB_PATH=/data/diario.db \
    BACKUP_DIR=/data/backup \
    IMPORT_DIR=/tmp/food-stoplight-import \
    PORT=8000 \
    GUNICORN_WORKERS=2

WORKDIR /app

# Utente senza privilegi: l'avvio sistema i permessi di /data e poi passa a lui
RUN useradd --create-home --uid 10001 app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker/avvio.sh && mkdir -p /data

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/salute', timeout=4)"

ENTRYPOINT ["/app/docker/avvio.sh"]

# --preload: l'app (e le migrazioni del database) si carica una volta sola, prima dei worker
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS} --threads 4 --preload --timeout 60 --access-logfile - app:app"]
