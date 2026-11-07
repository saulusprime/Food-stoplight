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

Migrazione = tuple[int, str, Callable[[sqlite3.Connection], None]]


def connetti(percorso: str) -> sqlite3.Connection:
    conn = sqlite3.connect(percorso)
    conn.row_factory = sqlite3.Row
    return conn


def connetti_alimenti(percorso: str) -> sqlite3.Connection:
    """
    Connessione ad alimenti.db con la funzione SQL punteggio(r1..r5)
    (punteggio sintetico 0-100, usabile in SELECT e ORDER BY).
    """
    conn = connetti(percorso)
    conn.create_function(
        "punteggio", len(analisi.CAMPI_RISCHIO), analisi.calcola_punteggio, deterministic=True
    )
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
    ],
    "utenti": [
        (1, "Schema di base", _utenti_1_schema_di_base),
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
