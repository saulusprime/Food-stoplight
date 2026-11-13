"""Migrazioni versionate dei database, backup e ripristino."""

import shutil
import sqlite3

import pytest

import backup
import database
from tests.aiuti import DB, PROGETTO


def colonne(percorso, tabella="alimenti"):
    conn = sqlite3.connect(percorso)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({tabella})")}
    finally:
        conn.close()


def test_database_nuovo_arriva_all_ultima_versione(tmp_path):
    percorso = str(tmp_path / "nuovo.db")
    chiamate = []
    eseguite = database.migra(percorso, "alimenti", prima_di_migrare=lambda: chiamate.append(1))
    assert len(eseguite) == database.ultima_versione("alimenti")
    assert chiamate == []  # niente backup per un database vuoto
    assert database.stato(percorso, "alimenti") == (5, 5)
    assert "fonte_kcal" not in colonne(percorso)
    assert {"note", "vitamina_c", "fdc_id", "rischio_diabete", "codice_cofid", "ingredienti"} <= colonne(percorso)


def test_migrazioni_idempotenti(tmp_path):
    percorso = str(tmp_path / "x.db")
    database.migra(percorso, "alimenti")
    assert database.migra(percorso, "alimenti") == []


def test_database_storico_di_update_py(tmp_path):
    """
    Schema delle prime versioni di update.py: niente rischi diabete/colesterolo,
    colonne fonte_kcal e fonte_tef con un valore da conservare nelle note.
    """
    percorso = str(tmp_path / "storico.db")
    conn = sqlite3.connect(percorso)
    conn.execute("""CREATE TABLE alimenti (id INTEGER PRIMARY KEY AUTOINCREMENT, alimento TEXT NOT NULL,
                    categoria TEXT, kcal REAL, proteine REAL, fonte_kcal TEXT, fonte_tef TEXT, note TEXT)""")
    conn.execute("INSERT INTO alimenti (alimento, kcal, fonte_kcal, note) VALUES ('Mela', 52, 'CREA', 'bio')")
    conn.commit()
    conn.close()

    chiamate = []
    database.migra(percorso, "alimenti", prima_di_migrare=lambda: chiamate.append(1))

    assert chiamate == [1]
    assert {"rischio_diabete", "rischio_colesterolo", "vitamina_c"} <= colonne(percorso)
    assert not {"fonte_kcal", "fonte_tef"} & colonne(percorso)
    conn = sqlite3.connect(percorso)
    assert conn.execute("SELECT alimento, kcal, note FROM alimenti").fetchone() == ("Mela", 52.0, "bio\nFonte Kcal: CREA")
    conn.close()


def test_migrazione_fallita_non_lascia_mezzo_schema(tmp_path, monkeypatch):
    percorso = str(tmp_path / "x.db")

    def guasta(conn):
        conn.execute("CREATE TABLE temporanea (x)")
        raise RuntimeError("guasto")

    monkeypatch.setitem(database.MIGRAZIONI, "alimenti", [
        *database.MIGRAZIONI["alimenti"], (3, "Guasta", guasta),
    ])

    with pytest.raises(RuntimeError):
        database.migra(percorso, "alimenti")

    conn = sqlite3.connect(percorso)
    assert database.versione(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] == 0
    conn.close()


def test_database_del_progetto_aggiornato():
    """
    alimenti.db versionato in git è già all'ultima versione dello schema.
    """
    assert database.stato(str(PROGETTO / "alimenti.db"), "alimenti") == (5, 5)


# ---------------------------------------------------------------
# Backup
# ---------------------------------------------------------------

def test_crea_elenca_pota(tmp_path):
    cartella = str(tmp_path / "backup")
    nomi = [backup.crea(str(DB), cartella, "manuale") for _ in range(3)]
    assert len(set(nomi)) == 3
    elenco = backup.elenco(cartella)
    assert [b["nome"] for b in elenco] == list(reversed(nomi))
    assert elenco[0]["alimenti"] == 1100
    backup.pota(cartella, conserva=1)
    assert [b["nome"] for b in backup.elenco(cartella)] == [nomi[-1]]


def test_istantanea_valida(tmp_path):
    copia = tmp_path / "copia.db"
    copia.write_bytes(backup.istantanea(str(DB)))
    assert backup.verifica(str(copia)) == 1100


@pytest.mark.parametrize("nome", ["../alimenti.db", "alimenti_x.db", "utenti.db", "", "alimenti_20260101-000000_boh.db/.."])
def test_percorso_rifiuta_nomi_non_validi(tmp_path, nome):
    assert backup.percorso(str(tmp_path), nome) is None


def prepara(tmp_path, sql=None, contenuto=None):
    percorso = tmp_path / "caricato.db"

    if contenuto is not None:
        percorso.write_bytes(contenuto)
    else:
        shutil.copy(DB, percorso)
        conn = sqlite3.connect(percorso)
        conn.execute(sql)
        conn.commit()
        conn.close()

    return str(percorso)


@pytest.mark.parametrize(("sql", "contenuto", "messaggio"), [
    (None, b"testo qualunque", "non è un database SQLite"),
    ("CREATE TRIGGER t AFTER INSERT ON alimenti BEGIN DELETE FROM alimenti; END", None, "trigger"),
    ("CREATE VIEW v AS SELECT 1", None, "viste"),
    ("ALTER TABLE alimenti RENAME TO prodotti", None, "manca la tabella"),
])
def test_verifica_rifiuta(tmp_path, sql, contenuto, messaggio):
    with pytest.raises(backup.ErroreBackup, match=messaggio):
        backup.verifica(prepara(tmp_path, sql, contenuto))


def test_ripristina(tmp_path):
    sorgente = tmp_path / "piccolo.db"
    database.migra(str(sorgente), "alimenti")
    conn = sqlite3.connect(sorgente)
    conn.execute("INSERT INTO alimenti (alimento) VALUES ('Solo questo')")
    conn.commit()
    conn.close()

    backup.ripristina(str(sorgente), str(DB))
    conn = sqlite3.connect(DB)
    assert conn.execute("SELECT alimento FROM alimenti").fetchall() == [("Solo questo",)]
    conn.close()
