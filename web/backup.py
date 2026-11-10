"""
Backup e ripristino del database degli alimenti (solo amministratori).
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from flask_babel import ngettext

import backup
from web.accesso import solo_admin
from web.comune import (
    get_stats,
    init_db,
    invia_file,
)
from web.import_export import cartella_import

bp = Blueprint("backup", __name__)


# ---------------------------------------------------------------
# BACKUP E RIPRISTINO
# ---------------------------------------------------------------

MIMETYPE_SQLITE = "application/vnd.sqlite3"


@bp.route("/backup")
@solo_admin
def pagina() -> ResponseReturnValue:
    return render_template(
        "backup.html",
        backups=backup.elenco(current_app.config["BACKUP_DIR"]),
        totale_alimenti=get_stats()[0],
        conservati=backup.BACKUP_CONSERVATI,
        max_mb=current_app.config["MAX_UPLOAD_MB"],
    )


@bp.route("/backup/scarica")
@solo_admin
def scarica() -> ResponseReturnValue:
    dati = backup.istantanea(current_app.config["DATABASE_PATH"])
    return invia_file(dati, f"alimenti_{datetime.now():%Y%m%d-%H%M%S}.db", MIMETYPE_SQLITE)


@bp.route("/backup/scarica/<nome>")
@solo_admin
def scarica_salvato(nome: str) -> ResponseReturnValue:
    percorso = backup.percorso(current_app.config["BACKUP_DIR"], nome)

    if not percorso:
        abort(404)

    with open(percorso, "rb") as f:
        return invia_file(f.read(), nome, MIMETYPE_SQLITE)


@bp.route("/backup/crea", methods=["POST"])
@solo_admin
def crea() -> ResponseReturnValue:
    nome = backup.crea(current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], "manuale")
    flash(_("Backup salvato: %(nome)s.", nome=nome), "success")
    return redirect(url_for("backup.pagina"))


def esegui_ripristino(file_db: str, etichetta: str) -> None:
    try:
        alimenti = backup.verifica(file_db)
    except backup.ErroreBackup as exc:
        flash(_("Ripristino non eseguito: %(motivo)s", motivo=exc), "danger")
        return

    cartella = current_app.config["BACKUP_DIR"]

    # La potatura dei vecchi backup si fa dopo: il file da ripristinare
    # potrebbe essere proprio il più vecchio della cartella
    nome_backup = backup.crea(current_app.config["DATABASE_PATH"], cartella, "ripristino", pota_vecchi=False)
    backup.ripristina(file_db, current_app.config["DATABASE_PATH"])
    backup.pota(cartella)

    # Un backup di una versione precedente si porta allo schema attuale
    # (il database da sostituire è già nel backup appena creato)
    init_db(backup_prima=False)

    flash(
        ngettext(
            "Database ripristinato da %(origine)s: %(num)d alimento. Il database precedente è nel backup %(backup)s.",
            "Database ripristinato da %(origine)s: %(num)d alimenti. Il database precedente è nel backup %(backup)s.",
            alimenti, origine=etichetta, backup=nome_backup,
        ),
        "success"
    )


@bp.route("/backup/ripristina", methods=["POST"])
@solo_admin
def ripristina() -> ResponseReturnValue:
    file = request.files.get("file")

    if not file or not file.filename:
        flash(_("Seleziona il file del database da ripristinare."), "danger")
        return redirect(url_for("backup.pagina"))

    if request.form.get("conferma") != "1":
        flash(_("Per ripristinare spunta la casella di conferma."), "danger")
        return redirect(url_for("backup.pagina"))

    temporaneo = os.path.join(cartella_import(), f"ripristino-{secrets.token_hex(8)}.db")
    file.save(temporaneo)

    try:
        esegui_ripristino(temporaneo, os.path.basename(file.filename.replace("\\", "/")))
    finally:
        os.remove(temporaneo)

    return redirect(url_for("backup.pagina"))


@bp.route("/backup/ripristina/<nome>", methods=["POST"])
@solo_admin
def ripristina_salvato(nome: str) -> ResponseReturnValue:
    percorso = backup.percorso(current_app.config["BACKUP_DIR"], nome)

    if not percorso:
        abort(404)

    esegui_ripristino(percorso, nome)
    return redirect(url_for("backup.pagina"))
