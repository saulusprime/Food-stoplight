"""
Ambiente e funzioni di supporto dei test.

L'app legge la configurazione all'import, quindi le variabili d'ambiente si
impostano qui, prima di importarla: i test lavorano solo su copie dei
database in una cartella temporanea, mai su quelli del progetto.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

PROGETTO = Path(__file__).resolve().parent.parent
LAVORO = Path(tempfile.mkdtemp(prefix="food-stoplight-test-"))
ORIGINALE = LAVORO / "alimenti_originale.db"
DB = LAVORO / "alimenti.db"
UTENTI_DB = LAVORO / "utenti.db"
DIARIO_DB = LAVORO / "diario.db"
BACKUP_DIR = LAVORO / "backup"
IMPORT_DIR = LAVORO / "import"

shutil.copy(PROGETTO / "alimenti.db", ORIGINALE)
shutil.copy(ORIGINALE, DB)

os.environ.update({
    "APP_ENV": "sviluppo",
    "APP_DEBUG": "false",
    "FLASK_SECRET_KEY": "chiave-di-prova-" + "x" * 32,
    "DATABASE_PATH": str(DB),
    "UTENTI_DB_PATH": str(UTENTI_DB),
    "DIARIO_DB_PATH": str(DIARIO_DB),
    "BACKUP_DIR": str(BACKUP_DIR),
    "IMPORT_DIR": str(IMPORT_DIR),
    "ACCESSO_PUBBLICO": "true",
    "PROXY_ATTENDIBILI": "0",
})
sys.path.insert(0, str(PROGETTO))

from werkzeug.security import generate_password_hash  # noqa: E402

import app as applicazione  # noqa: E402

PASSWORD = "password-di-prova"
UTENTI = (("admin_t", "admin"), ("anna_t", "visitatore"), ("bruno_t", "visitatore"))

# Le password si calcolano una volta sola (scrypt è lento di proposito)
_HASH = generate_password_hash(PASSWORD)


def prepara_utenti() -> None:
    conn = sqlite3.connect(UTENTI_DB)
    conn.execute("DELETE FROM utenti")
    conn.executemany(
        "INSERT INTO utenti (username, password_hash, ruolo, creato_il) VALUES (?, ?, ?, '')",
        [(nome, _HASH, ruolo) for nome, ruolo in UTENTI],
    )
    conn.commit()
    conn.close()


def accedi(app: Any, username: str) -> Any:
    cliente = app.test_client()
    risposta = cliente.post("/login", data={"username": username, "password": PASSWORD})
    assert risposta.status_code == 302, risposta.data
    return cliente


# ---------------------------------------------------------------
# Funzioni di supporto
# ---------------------------------------------------------------

def sql(query: str, parametri: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute(query, parametri).fetchall()
    finally:
        conn.close()


def conta(query: str = "SELECT COUNT(*) FROM alimenti", parametri: tuple[Any, ...] = ()) -> int:
    return int(sql(query, parametri)[0][0])


def id_di(nome: str) -> int:
    righe = sql("SELECT id FROM alimenti WHERE alimento = ? ORDER BY id", (nome,))
    assert righe, f"alimento {nome!r} non trovato"
    return int(righe[0]["id"])


def messaggi(cliente: Any) -> list[str]:
    """
    Messaggi flash in attesa nella sessione del client.
    """
    with cliente.session_transaction() as sessione:
        return [testo for _, testo in sessione.get("_flashes", [])]


def carica(cliente: Any, nome: str, dati: bytes, url: str = "/importa", **campi: str) -> Any:
    return cliente.post(
        url,
        data={"file": (io.BytesIO(dati), nome), **campi},
        content_type="multipart/form-data",
    )


def piano_in_attesa(
    cliente: Any, modalita: str = "aggiorna"
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    """
    (file letto, voci, riepilogo) dell'import in attesa nella sessione del client.
    """
    import json

    with cliente.session_transaction() as sessione:
        token = sessione["import_token"]

    with applicazione.app.app_context():
        percorso = applicazione.percorso_import(token)
        assert percorso is not None

        with open(percorso, encoding="utf-8") as f:
            letto = json.load(f)

        conn = applicazione.get_db()

        try:
            voci = applicazione.importazione.pianifica(conn, letto, modalita)
        finally:
            conn.close()

    return letto, voci, applicazione.importazione.riepilogo(voci)


def solo_testo(html: bytes) -> str:
    """
    Testo visibile di una pagina, con gli spazi compattati (per cercare frasi).
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.decode()))
