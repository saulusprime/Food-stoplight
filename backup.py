"""
Backup e ripristino del database degli alimenti.

Le copie si fanno con l'API di backup di SQLite, che produce un file
coerente anche mentre l'app sta usando il database. I backup automatici
(prima di ogni import e di ogni ripristino) finiscono in BACKUP_DIR;
utenti.db non viene mai incluso, perché contiene le credenziali.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Backup conservati nella cartella: oltre, si eliminano i più vecchi
BACKUP_CONSERVATI = 20

INTESTAZIONE_SQLITE = b"SQLite format 3\x00"

MOTIVI = {
    "manuale": "Manuale",
    "import": "Prima di un import",
    "ripristino": "Prima di un ripristino",
    "usda": "Prima dei nutrienti USDA",
    "migrazione": "Prima di una migrazione dello schema",
}

NOME_RE = re.compile(r"^alimenti_(\d{8}-\d{6})(?:-(\d+))?_([a-z]+)\.db$")


class ErroreBackup(Exception):
    """
    File non valido come backup: il messaggio è per l'utente.
    """


def _uri_sola_lettura(percorso: str) -> str:
    return Path(percorso).resolve().as_uri() + "?mode=ro"


def istantanea(db_path: str) -> bytes:
    """
    Contenuto completo del database come bytes, per il download.
    """
    sorgente = sqlite3.connect(db_path)
    memoria = sqlite3.connect(":memory:")

    try:
        sorgente.backup(memoria)
        return memoria.serialize()
    finally:
        memoria.close()
        sorgente.close()


def crea(db_path: str, cartella: str, motivo: str, pota_vecchi: bool = True) -> str:
    """
    Salva una copia del database nella cartella dei backup e restituisce il nome del file.
    """
    if motivo not in MOTIVI:
        raise ValueError(f"Motivo di backup non valido: {motivo}")

    os.makedirs(cartella, exist_ok=True)

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    nome = f"alimenti_{marca}_{motivo}.db"
    progressivo = 2

    while os.path.exists(os.path.join(cartella, nome)):
        nome = f"alimenti_{marca}-{progressivo}_{motivo}.db"
        progressivo += 1

    destinazione = os.path.join(cartella, nome)
    sorgente = sqlite3.connect(db_path)
    copia = sqlite3.connect(destinazione)

    try:
        sorgente.backup(copia)
    finally:
        copia.close()
        sorgente.close()

    if pota_vecchi:
        pota(cartella)

    return nome


def pota(cartella: str, conserva: int = BACKUP_CONSERVATI) -> None:
    """
    Elimina i backup più vecchi oltre il numero da conservare.
    """
    nomi = sorted(
        (nome for nome in os.listdir(cartella) if NOME_RE.match(nome)),
        key=_ordine,
        reverse=True,
    )

    for nome in nomi[conserva:]:
        os.remove(os.path.join(cartella, nome))


def _parti(nome: str) -> tuple[str, str | None, str]:
    """
    (marca temporale, progressivo, motivo) di un nome di backup valido.
    """
    corrispondenza = NOME_RE.match(nome)

    if corrispondenza is None:
        raise ValueError(f"Nome di backup non valido: {nome}")

    marca, progressivo, motivo = corrispondenza.groups()
    return marca, progressivo, motivo


def _ordine(nome: str) -> tuple[str, int]:
    marca, progressivo, _ = _parti(nome)
    return marca, int(progressivo or 1)


def percorso(cartella: str, nome: str) -> str | None:
    """
    Percorso di un backup esistente nella cartella, None se il nome non è valido.
    Il controllo sul nome impedisce di uscire dalla cartella (../).
    """
    if not NOME_RE.match(nome or ""):
        return None

    completo = os.path.join(cartella, nome)
    return completo if os.path.isfile(completo) else None


def elenco(cartella: str) -> list[dict[str, Any]]:
    """
    Backup presenti, dal più recente: nome, data, motivo, dimensione, numero di alimenti.
    """
    if not os.path.isdir(cartella):
        return []

    risultato = []

    for nome in sorted(
        (n for n in os.listdir(cartella) if NOME_RE.match(n)), key=_ordine, reverse=True
    ):
        marca, _, motivo = _parti(nome)
        completo = os.path.join(cartella, nome)

        try:
            alimenti = verifica(completo)
        except ErroreBackup:
            alimenti = None

        risultato.append({
            "nome": nome,
            "data": datetime.strptime(marca, "%Y%m%d-%H%M%S"),
            "motivo": MOTIVI.get(motivo, motivo),
            "dimensione": os.path.getsize(completo),
            "alimenti": alimenti,
        })

    return risultato


def verifica(file_db: str) -> int:
    """
    Controlla che il file sia un database di Food-stoplight integro
    e restituisce il numero di alimenti; altrimenti solleva ErroreBackup.
    """
    with open(file_db, "rb") as f:
        if f.read(16) != INTESTAZIONE_SQLITE:
            raise ErroreBackup("Il file non è un database SQLite.")

    try:
        conn = sqlite3.connect(_uri_sola_lettura(file_db), uri=True)
    except sqlite3.Error:
        raise ErroreBackup("Il database non si apre.") from None

    try:
        # Lo schema arriva da un file caricato: niente funzioni negli oggetti dello schema
        conn.execute("PRAGMA trusted_schema = OFF")

        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ErroreBackup("Il database è danneggiato.")

        oggetti = conn.execute("SELECT type, name FROM sqlite_master").fetchall()

        if any(tipo in ("trigger", "view") for tipo, _ in oggetti):
            raise ErroreBackup(
                "Il database contiene trigger o viste: non è un backup di Food-stoplight."
            )

        if ("table", "alimenti") not in oggetti:
            raise ErroreBackup("Nel database manca la tabella «alimenti».")

        colonne = {riga[1] for riga in conn.execute("PRAGMA table_info(alimenti)")}

        if not {"id", "alimento"} <= colonne:
            raise ErroreBackup("La tabella «alimenti» non ha le colonne attese.")

        return conn.execute("SELECT COUNT(*) FROM alimenti").fetchone()[0]
    except sqlite3.Error as exc:
        raise ErroreBackup(f"Il database non è leggibile ({exc}).") from None
    finally:
        conn.close()


def ripristina(file_db: str, db_path: str) -> None:
    """
    Sostituisce il contenuto del database con quello del file (già verificato).
    """
    sorgente = sqlite3.connect(_uri_sola_lettura(file_db), uri=True)
    destinazione = sqlite3.connect(db_path)

    try:
        sorgente.backup(destinazione)
    finally:
        destinazione.close()
        sorgente.close()
