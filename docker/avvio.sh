#!/bin/sh
# Avvio del container: prepara /data, crea l'amministratore iniziale se richiesto,
# poi esegue il comando (gunicorn) come utente "app" senza privilegi.
set -e

mkdir -p "$(dirname "$DATABASE_PATH")" "$BACKUP_DIR"

# Primo avvio con un volume vuoto: si parte dal database incluso nell'immagine
if [ ! -f "$DATABASE_PATH" ]; then
    cp "$(dirname "$0")/../alimenti.db" "$DATABASE_PATH"
    echo " * Database iniziale copiato in $DATABASE_PATH"
fi

come_app() {
    if [ "$(id -u)" = "0" ]; then
        # I dischi montati (Render, volumi Docker) possono appartenere a root
        chown -R app:app "$(dirname "$DATABASE_PATH")" "$BACKUP_DIR"
        exec_come="setpriv --reuid=app --regid=app --init-groups"
    else
        exec_come=""
    fi
}

come_app

# ADMIN_USERNAME e ADMIN_PASSWORD (facoltative): amministratore del primo deploy,
# creato solo se non ne esiste già uno
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
    $exec_come flask --app app crea-admin-iniziale
fi

exec $exec_come "$@"
