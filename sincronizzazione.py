"""
Sincronizzazione periodica con USDA FoodData Central.

L'app stessa la esegue ogni USDA_SINCRONIZZA_GIORNI giorni (0 = spenta),
solo con una chiave personale in USDA_API_KEY: su Render il disco dei dati
è collegato solo al servizio web, quindi un cron job separato non lo
vedrebbe. Ogni processo dell'app (i worker di gunicorn) controlla una volta
l'ora se è il momento; un file di blocco accanto al database fa sì che ne
parta una sola alla volta. Prima di scrivere si fa un backup.

Lo storico è nella tabella sincronizzazioni di alimenti.db.
"""

from __future__ import annotations

import contextlib
import logging
import os
import random
import sqlite3
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import backup
import database
import fonti
import usda
from lingue import N_

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: nessun blocco tra processi
    fcntl = None  # type: ignore[assignment]

FONTE = "usda"

# Esiti salvati nello storico (mostrati tradotti)
ESITI = (N_("in corso"), N_("riuscita"), N_("fallita"))
INTERVALLO_CONTROLLO = 3600  # secondi tra due controlli
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

log = logging.getLogger(__name__)

_avviata_nel_processo: int | None = None
_blocco_thread = threading.Lock()


class GiaInCorso(Exception):
    pass


def _adesso() -> str:
    return datetime.now().strftime(FORMATO_DATA)


@contextlib.contextmanager
def _blocco(db_path: str) -> Iterator[None]:
    """
    Blocco esclusivo tra processi e thread (flock su un file accanto al
    database: ogni apertura è indipendente); GiaInCorso se è già preso.
    """
    percorso = f"{db_path}.sincronizzazione.lock"

    with open(percorso, "a+") as f:
        if fcntl is not None:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise GiaInCorso() from None

        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_UN)


def in_corso(db_path: str) -> bool:
    try:
        with _blocco(db_path):
            return False
    except GiaInCorso:
        return True


def esegui(db_path: str, cartella_backup: str, api_key: str) -> dict[str, Any]:
    """
    Sincronizza subito: backup, aggiornamento, riga nello storico.
    GiaInCorso se un'altra sincronizzazione è in corso.
    """
    with _blocco(db_path):
        conn = database.connetti_alimenti(db_path)

        try:
            # Righe "in corso" rimaste da un processo interrotto
            conn.execute(
                "UPDATE sincronizzazioni SET esito = 'fallita', finita_il = ?, messaggio = 'Interrotta' "
                "WHERE esito = 'in corso'", (_adesso(),),
            )
            id_riga = conn.execute(
                "INSERT INTO sincronizzazioni (fonte, iniziata_il) VALUES (?, ?)", (FONTE, _adesso())
            ).lastrowid
            conn.commit()

            try:
                if not usda.chiave_valida(api_key):
                    raise usda.ErroreUsda("Serve una chiave USDA personale in USDA_API_KEY (non DEMO_KEY).")

                nome_backup = backup.crea(db_path, cartella_backup, "usda")
                aggiornati = fonti.sincronizza_usda(conn, api_key, _adesso())
                conn.execute(
                    "UPDATE sincronizzazioni SET esito = 'riuscita', finita_il = ?, aggiornati = ?, messaggio = ? "
                    "WHERE id = ?", (_adesso(), aggiornati, f"Backup: {nome_backup}", id_riga),
                )
                conn.commit()
                return {"esito": "riuscita", "aggiornati": aggiornati, "backup": nome_backup}
            except Exception as exc:
                conn.rollback()
                conn.execute(
                    "UPDATE sincronizzazioni SET esito = 'fallita', finita_il = ?, messaggio = ? WHERE id = ?",
                    (_adesso(), str(exc)[:500], id_riga),
                )
                conn.commit()

                if not isinstance(exc, usda.ErroreUsda):
                    log.exception("Sincronizzazione USDA fallita")

                return {"esito": "fallita", "messaggio": str(exc)}
        finally:
            conn.close()


def ultime(db_path: str, n: int = 5) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sincronizzazioni WHERE fonte = ? ORDER BY id DESC LIMIT ?", (FONTE, n)
        )]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def prossima(db_path: str, giorni: int) -> datetime | None:
    """
    Quando tocca la prossima sincronizzazione automatica (None se spenta).
    """
    if giorni <= 0:
        return None

    riuscite = [r for r in ultime(db_path, 20) if r["esito"] == "riuscita"]

    if not riuscite:
        return datetime.now()

    return datetime.strptime(riuscite[0]["iniziata_il"], FORMATO_DATA) + timedelta(days=giorni)


def stato(db_path: str, api_key: str, giorni: int) -> dict[str, Any]:
    chiave = usda.chiave_valida(api_key)
    return {
        "chiave": chiave,
        "giorni": giorni,
        "automatica": chiave and giorni > 0,
        "in_corso": in_corso(db_path),
        "ultime": ultime(db_path),
        "prossima": prossima(db_path, giorni) if chiave else None,
    }


def avvia_in_background(db_path: str, cartella_backup: str, api_key: str) -> bool:
    """
    Avvia la sincronizzazione in un thread; False se ce n'è già una in corso.
    """
    if in_corso(db_path):
        return False

    def lavoro() -> None:
        with contextlib.suppress(GiaInCorso):
            esegui(db_path, cartella_backup, api_key)

    threading.Thread(target=lavoro, name="sincronizzazione-usda", daemon=True).start()
    return True


def _ciclo(db_path: str, cartella_backup: str, api_key: str, giorni: int) -> None:
    # Attesa iniziale casuale: i worker non controllano tutti nello stesso istante
    time.sleep(random.uniform(60, 300))

    while True:
        try:
            scadenza = prossima(db_path, giorni)

            if scadenza is not None and scadenza <= datetime.now():
                with contextlib.suppress(GiaInCorso):
                    esito = esegui(db_path, cartella_backup, api_key)
                    log.info("Sincronizzazione USDA automatica: %s", esito)
        except Exception:
            log.exception("Controllo della sincronizzazione USDA non riuscito")

        time.sleep(INTERVALLO_CONTROLLO)


def avvia_automatica(db_path: str, cartella_backup: str, api_key: str, giorni: int) -> bool:
    """
    Avvia (una volta per processo) il controllo periodico; False se non serve
    (sincronizzazione spenta o senza chiave personale).
    """
    global _avviata_nel_processo

    if giorni <= 0 or not usda.chiave_valida(api_key):
        return False

    with _blocco_thread:
        if _avviata_nel_processo == os.getpid():
            return True

        _avviata_nel_processo = os.getpid()

    threading.Thread(
        target=_ciclo, args=(db_path, cartella_backup, api_key, giorni),
        name="sincronizzazione-usda-automatica", daemon=True,
    ).start()
    return True
