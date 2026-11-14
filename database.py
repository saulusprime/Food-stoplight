"""
Connessioni ai tre database SQLite e migrazioni versionate.

- alimenti.db  dati nutrizionali (versionato in git)
- utenti.db    utenti e hash delle password (escluso da git)
- diario.db    diario alimentare personale (escluso da git)

Ogni database tiene la propria versione in PRAGMA user_version. All'avvio
si applicano in ordine le migrazioni mancanti, tutte in un'unica transazione
(se una fallisce il database resta com'era). Le migrazioni non si modificano
dopo il rilascio: un cambio di schema è sempre una migrazione nuova in coda.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

import analisi
import profilo

Migrazione = tuple[int, str, Callable[[sqlite3.Connection], None]]


def connetti(percorso: str) -> sqlite3.Connection:
    conn = sqlite3.connect(percorso)
    conn.row_factory = sqlite3.Row
    return conn


def connetti_alimenti(percorso: str) -> sqlite3.Connection:
    """
    Connessione ad alimenti.db con le funzioni SQL punteggio(r1..r5)
    (punteggio sintetico 0-100) e per_te(r, ...) (semaforo per te, 0-3, dai
    rischi del profilo), usabili in SELECT, WHERE e ORDER BY.
    """
    conn = connetti(percorso)
    conn.create_function(
        "punteggio", len(analisi.CAMPI_RISCHIO), analisi.calcola_punteggio, deterministic=True
    )
    conn.create_function("per_te", -1, profilo.punti_per_te, deterministic=True)
    return conn


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


# ---------------------------------------------------------------
# ALIMENTI
# ---------------------------------------------------------------

# Schema della versione 1, fissato: le versioni successive lo modificano con nuove migrazioni
_ALIMENTI_V1 = {
    "alimento": "TEXT NOT NULL",
    "categoria": "TEXT",
    "kcal": "REAL DEFAULT 0",
    "tef_kcal": "REAL DEFAULT 0",
    "tef_percent": "REAL DEFAULT 0",
    "kcal_nette": "REAL DEFAULT 0",
    "fruttosio": "REAL DEFAULT 0",
    "fibre": "REAL DEFAULT 0",
    "rapporto": "REAL DEFAULT 0",
    "rischio_diabete": "TEXT",
    "rischio_colesterolo": "TEXT",
    "rischio_malassorbimento": "TEXT",
    "rischio_metabolico": "TEXT",
    "rischio_tumorale": "TEXT",
    "aggiornato_il": "TEXT",
    "proteine": "REAL",
    "carboidrati": "REAL",
    "zuccheri": "REAL",
    "grassi": "REAL",
    "grassi_saturi": "REAL",
    "colesterolo": "REAL",
    "vitamina_a": "REAL",
    "vitamina_c": "REAL",
    "vitamina_d": "REAL",
    "vitamina_e": "REAL",
    "vitamina_b12": "REAL",
    "folati": "REAL",
    "calcio": "REAL",
    "ferro": "REAL",
    "magnesio": "REAL",
    "potassio": "REAL",
    "sodio": "REAL",
    "zinco": "REAL",
    "indice_glicemico": "REAL",
    "nova": "INTEGER",
    "fodmap_fruttani": "TEXT",
    "fodmap_gos": "TEXT",
    "fodmap_lattosio": "TEXT",
    "fodmap_fruttosio": "TEXT",
    "fodmap_polioli": "TEXT",
    "fonte_nutrienti": "TEXT",
    "url_fonte": "TEXT",
    "fdc_id": "INTEGER",
    # Colonne storiche di update.py, rimosse dalla versione 2
    "fonte_kcal": "TEXT",
    "fonte_tef": "TEXT",
    "note": "TEXT",
}


def _alimenti_1_schema_di_base(conn: sqlite3.Connection) -> None:
    """
    Crea la tabella, oppure porta allo schema di base un database creato da
    versioni precedenti di app.py o update.py aggiungendo le colonne mancanti.
    """
    colonne = ",\n".join(f"{nome} {tipo}" for nome, tipo in _ALIMENTI_V1.items())
    conn.execute(f"CREATE TABLE IF NOT EXISTS alimenti (id INTEGER PRIMARY KEY AUTOINCREMENT, {colonne})")

    esistenti = _colonne(conn, "alimenti")

    for nome, tipo in _ALIMENTI_V1.items():
        if nome not in esistenti:
            # ALTER TABLE non accetta NOT NULL senza default: alimento c'è sempre
            conn.execute(f"ALTER TABLE alimenti ADD COLUMN {nome} {tipo.replace(' NOT NULL', '')}")


def _alimenti_2_rimuovi_fonti_storiche(conn: sqlite3.Connection) -> None:
    """
    fonte_kcal e fonte_tef di update.py sono sostituite da fonte_nutrienti e url_fonte:
    un eventuale contenuto passa nelle note prima di eliminare le colonne.
    """
    for colonna, etichetta in (("fonte_kcal", "Fonte Kcal"), ("fonte_tef", "Fonte TEF")):
        conn.execute(
            f"""
            UPDATE alimenti
            SET note = TRIM(COALESCE(note || char(10), '') || '{etichetta}: ' || {colonna})
            WHERE TRIM(COALESCE({colonna}, '')) <> ''
            """
        )
        conn.execute(f"ALTER TABLE alimenti DROP COLUMN {colonna}")


def _alimenti_3_fonti_e_zuccheri(conn: sqlite3.Connection) -> None:
    """
    Codici delle fonti (CREA, codice a barre di Open Food Facts), porzione
    tipica, zuccheri semplici e alcol per i rischi calcolati, campi presi da
    USDA (quelli che la sincronizzazione aggiorna) e storico delle sincronizzazioni.
    """
    for nome, tipo in (
        ("codice_crea", "TEXT"),
        ("codice_barre", "TEXT"),
        ("porzione", "REAL"),
        ("glucosio", "REAL"),
        ("lattosio", "REAL"),
        ("alcol", "REAL"),
        ("campi_usda", "TEXT"),
    ):
        conn.execute(f"ALTER TABLE alimenti ADD COLUMN {nome} {tipo}")

    conn.execute("CREATE INDEX IF NOT EXISTS alimenti_codice_crea ON alimenti (codice_crea)")
    conn.execute("CREATE INDEX IF NOT EXISTS alimenti_fdc_id ON alimenti (fdc_id)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sincronizzazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fonte TEXT NOT NULL,
            iniziata_il TEXT NOT NULL,
            finita_il TEXT,
            esito TEXT NOT NULL DEFAULT 'in corso'
                CHECK (esito IN ('in corso', 'riuscita', 'fallita')),
            aggiornati INTEGER NOT NULL DEFAULT 0,
            messaggio TEXT
        )
    """)


def _alimenti_4_cofid_e_ricette(conn: sqlite3.Connection) -> None:
    """
    Valori presi dalla tabella britannica CoFID (codice e campi) e ricette CREA:
    ingredienti (JSON) e campi calcolati dagli ingredienti.
    """
    for nome in ("codice_cofid", "campi_cofid", "campi_ricetta", "ingredienti"):
        conn.execute(f"ALTER TABLE alimenti ADD COLUMN {nome} TEXT")


def _alimenti_5_pasti_pronti(conn: sqlite3.Connection) -> None:
    """
    Pasti pronti: ricette con gli ingredienti presi tra gli alimenti (codice
    CREA, grammi crudi dell'intera ricetta, resa in cottura). alimento_id è il
    piatto calcolato dagli ingredienti, nella tabella alimenti.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pasti_pronti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codice TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            portata TEXT NOT NULL
                CHECK (portata IN ('antipasto', 'primo', 'secondo', 'contorno')),
            porzioni INTEGER NOT NULL CHECK (porzioni > 0),
            fonte TEXT NOT NULL,
            url_fonte TEXT,
            note TEXT,
            alimento_id INTEGER,
            aggiornato_il TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pasti_pronti_ingredienti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pasto_id INTEGER NOT NULL REFERENCES pasti_pronti (id) ON DELETE CASCADE,
            ordine INTEGER NOT NULL,
            ingrediente TEXT NOT NULL,
            codice_crea TEXT,
            grammi REAL CHECK (grammi IS NULL OR grammi >= 0),
            resa REAL NOT NULL DEFAULT 1 CHECK (resa > 0),
            nota TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS pasti_pronti_ingredienti_pasto ON pasti_pronti_ingredienti (pasto_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS pasti_pronti_alimento ON pasti_pronti (alimento_id)")


def _alimenti_6_ciqual(conn: sqlite3.Connection) -> None:
    """
    Valori presi dalla tabella francese Ciqual (codice e campi), come per CoFID.
    """
    for nome in ("codice_ciqual", "campi_ciqual"):
        conn.execute(f"ALTER TABLE alimenti ADD COLUMN {nome} TEXT")


# ---------------------------------------------------------------
# UTENTI E DIARIO
# ---------------------------------------------------------------

def _utenti_1_schema_di_base(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            ruolo TEXT NOT NULL DEFAULT 'visitatore'
                CHECK (ruolo IN ('admin', 'visitatore')),
            creato_il TEXT
        )
    """)


def _utenti_2_profilo(conn: sqlite3.Connection) -> None:
    """
    Profilo personale: condizioni scelte dall'utente («diabete,fruttosio»),
    per il semaforo per te. Si elimina con l'utente.
    """
    conn.execute("ALTER TABLE utenti ADD COLUMN condizioni TEXT NOT NULL DEFAULT ''")


def _diario_1_schema_di_base(conn: sqlite3.Connection) -> None:
    # valori: copia in JSON dei valori per 100 g al momento dell'inserimento,
    # così il diario resta valido anche se l'alimento cambia o viene eliminato
    conn.execute("""
        CREATE TABLE IF NOT EXISTS diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utente_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            pasto TEXT NOT NULL
                CHECK (pasto IN ('colazione', 'pranzo', 'cena', 'spuntino')),
            alimento_id INTEGER,
            alimento TEXT NOT NULL,
            grammi REAL NOT NULL CHECK (grammi > 0),
            valori TEXT NOT NULL,
            creato_il TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS diario_utente_data ON diario (utente_id, data)")


MIGRAZIONI: dict[str, list[Migrazione]] = {
    "alimenti": [
        (1, "Schema di base (energia, rischi, nutrienti, FODMAP, NOVA, fonte)", _alimenti_1_schema_di_base),
        (2, "Rimuove fonte_kcal e fonte_tef (sostituite da fonte_nutrienti)", _alimenti_2_rimuovi_fonti_storiche),
        (3, "Codici CREA e a barre, porzione, glucosio, lattosio, alcol, sincronizzazioni",
         _alimenti_3_fonti_e_zuccheri),
        (4, "Valori da CoFID e ricette calcolate dagli ingredienti", _alimenti_4_cofid_e_ricette),
        (5, "Pasti pronti: ricette con ingredienti e grammi", _alimenti_5_pasti_pronti),
        (6, "Valori da Ciqual", _alimenti_6_ciqual),
    ],
    "utenti": [
        (1, "Schema di base", _utenti_1_schema_di_base),
        (2, "Profilo personale: condizioni per il semaforo per te", _utenti_2_profilo),
    ],
    "diario": [
        (1, "Schema di base", _diario_1_schema_di_base),
    ],
}


# ---------------------------------------------------------------
# ESECUZIONE
# ---------------------------------------------------------------

def versione(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def ultima_versione(nome: str) -> int:
    return MIGRAZIONI[nome][-1][0]


def stato(percorso: str, nome: str) -> tuple[int, int]:
    """
    (versione attuale, ultima versione disponibile).
    """
    conn = sqlite3.connect(percorso)

    try:
        return versione(conn), ultima_versione(nome)
    finally:
        conn.close()


def migra(percorso: str, nome: str, prima_di_migrare: Callable[[], object] | None = None) -> list[str]:
    """
    Applica le migrazioni mancanti e restituisce le descrizioni di quelle eseguite.
    prima_di_migrare viene chiamata (es. per un backup) solo se il database
    contiene già delle tabelle e c'è qualcosa da migrare.
    """
    conn = sqlite3.connect(percorso, isolation_level=None)

    try:
        if versione(conn) >= ultima_versione(nome):
            return []

        ha_tabelle = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]

        if ha_tabelle and prima_di_migrare is not None:
            prima_di_migrare()

        # BEGIN IMMEDIATE: con più processi (gunicorn) uno solo migra, gli altri
        # attendono e poi trovano la versione già aggiornata
        conn.execute("BEGIN IMMEDIATE")
        eseguite = []

        try:
            attuale = versione(conn)

            for numero, descrizione, funzione in MIGRAZIONI[nome]:
                if numero > attuale:
                    funzione(conn)
                    conn.execute(f"PRAGMA user_version = {int(numero)}")
                    eseguite.append(f"{nome} {numero}: {descrizione}")

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        return eseguite
    finally:
        conn.close()
