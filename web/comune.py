"""
Funzioni condivise dalle pagine: connessioni ai database (dalla
configurazione dell'app attiva), query sugli alimenti, data e ora per i
salvataggi, file da scaricare, alimento scelto da un campo di ricerca,
ricalcolo delle ricette dopo una modifica.
"""

from __future__ import annotations

import io
import re
import sqlite3
import unicodedata
from collections.abc import Mapping
from datetime import datetime

from flask import (
    Response,
    current_app,
    request,
    send_file,
)
from flask_babel import gettext as _

import archivio
import backup
import database
import fonti
import lingue
from archivio import Alimento

# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    return database.connetti_alimenti(current_app.config["DATABASE_PATH"])


def get_db_utenti() -> sqlite3.Connection:
    """
    Gli utenti stanno in un database separato (utenti.db, escluso da git):
    alimenti.db è versionato e non deve contenere credenziali.
    """
    return database.connetti(current_app.config["UTENTI_DB_PATH"])


def get_db_diario() -> sqlite3.Connection:
    """
    Il diario alimentare è personale: database separato (diario.db, escluso da git).
    """
    return database.connetti(current_app.config["DIARIO_DB_PATH"])


# Query sugli alimenti (in archivio.py, condivise con l'API)
get_alimento = archivio.get_alimento
get_alimenti = archivio.get_alimenti
get_stats = archivio.get_stats
SORT_EXPRESSIONS = archivio.SORT_EXPRESSIONS


def leggi_filtri() -> tuple[archivio.Filtri, str, str]:
    return archivio.leggi_filtri(request.args)



def aggiorna_ricette() -> None:
    """
    Dopo una modifica dei dati: ricette ricalcolate dagli ingredienti (un
    ingrediente può essere cambiato o eliminato).
    """
    conn = get_db()

    try:
        if fonti.ricalcola_ricette(conn, adesso_testo()):
            conn.commit()
    finally:
        conn.close()



def adesso_testo() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



def invia_file(dati: bytes, nome: str, mimetype: str) -> Response:
    """
    Risposta di download per un file generato in memoria.
    """
    risposta = send_file(
        io.BytesIO(dati),
        mimetype=mimetype,
        as_attachment=True,
        download_name=nome,
        max_age=0,
    )
    risposta.headers["Cache-Control"] = "no-store"
    return risposta



def nome_file_sicuro(testo: str | None, alternativa: str) -> str:
    """
    "Pane integrale (100%)" -> "pane-integrale-100" per i nomi dei file scaricati.
    """
    ascii_ = unicodedata.normalize("NFKD", testo or "").encode("ascii", "ignore").decode()
    nome = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60]
    return nome or alternativa



# Alimento scelto da un campo di ricerca: "Nome · Categoria · 52 Kcal · #123"
ID_IN_TESTO_RE = re.compile(r"#(\d+)\s*$")


def trova_alimento_da_modulo(form: Mapping[str, str]) -> tuple[Alimento | None, str | None]:
    """
    (alimento, errore) dal campo alimento_id, dal testo "Nome · Categoria · #id"
    scelto nella ricerca, oppure da un nome esatto se non è ambiguo.
    """
    testo_id = (form.get("alimento_id") or "").strip()
    testo = (form.get("cerca") or "").strip()

    if not testo_id:
        corrispondenza = ID_IN_TESTO_RE.search(testo)
        testo_id = corrispondenza.group(1) if corrispondenza else ""

    if testo_id.isdigit():
        item = get_alimento(int(testo_id))
        return (item, None) if item else (None, _("Alimento non trovato."))

    if not testo:
        return None, _("Scegli un alimento dall'elenco.")

    righe = archivio.ids_per_nome(testo)

    if len(righe) == 1:
        return get_alimento(righe[0]), None

    if righe:
        return None, _("Ci sono %(n)d alimenti «%(testo)s»: scegline uno dall'elenco.", n=len(righe), testo=testo)

    return None, _("Nessun alimento «%(testo)s»: scegline uno dall'elenco.", testo=testo)


def init_db(backup_prima: bool = True) -> list[str]:
    """
    Applica le migrazioni mancanti ai tre database e restituisce quelle eseguite.
    Prima di migrare un alimenti.db esistente ne salva un backup.
    """
    config = current_app.config

    def copia_di_sicurezza() -> None:
        if backup_prima:
            backup.crea(config["DATABASE_PATH"], config["BACKUP_DIR"], "migrazione")

    eseguite = database.migra(config["UTENTI_DB_PATH"], "utenti")
    eseguite += database.migra(config["DIARIO_DB_PATH"], "diario")
    eseguite += database.migra(config["DATABASE_PATH"], "alimenti", prima_di_migrare=copia_di_sicurezza)
    return eseguite


def filtro_numero(valore: float | None, decimali: int | None = None, lingua: str | None = None) -> str:
    """
    Numero con la virgola decimale in italiano (il punto in inglese);
    senza decimali indicati usa la forma compatta (%g).
    """
    if valore is None:
        return "–"

    testo = f"{valore:g}" if decimali is None else f"{valore:.{decimali}f}"

    if lingua is None:
        return lingue.decimale(testo)

    return testo.replace(".", ",") if lingua == "it" else testo
