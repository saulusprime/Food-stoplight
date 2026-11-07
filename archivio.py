"""
Lettura e scrittura degli alimenti: query con filtri e ordinamento,
singolo alimento, statistiche, opzioni dei filtri. Usato dalle pagine web
(app.py) e dall'API JSON (api.py); il percorso del database arriva dalla
configurazione dell'app attiva.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from flask import current_app

import analisi
import database
import importazione
import lingue

Alimento = dict[str, Any]

# Colonne lette da ogni query sugli alimenti, punteggio calcolato compreso
SELECT_ALIMENTI = (
    "SELECT *, punteggio(" + ", ".join(analisi.CAMPI_RISCHIO) + ") AS punteggio FROM alimenti"
)

SORT_EXPRESSIONS = {
    "alimento": "LOWER(alimento)",
    "categoria": "LOWER(COALESCE(categoria, ''))",
    "kcal": "COALESCE(kcal, 0)",
    "tef_kcal": "COALESCE(tef_kcal, 0)",
    "tef_percent": "COALESCE(tef_percent, 0)",
    "kcal_nette": "COALESCE(kcal_nette, 0)",
    "fruttosio": "COALESCE(fruttosio, 0)",
    "fibre": "COALESCE(fibre, 0)",
    "rapporto": "COALESCE(rapporto, 0)",
    **{campo: f"LOWER(COALESCE({campo}, ''))" for campo in analisi.CAMPI_RISCHIO},
    "punteggio": "COALESCE(punteggio(" + ", ".join(analisi.CAMPI_RISCHIO) + "), -1)",
}

# Parametri di filtro della home (e di export e API), con le etichette per i file esportati
ETICHETTE_FILTRI = {
    "categoria": "Categoria",
    **{campo: f"Rischio {etichetta.lower()}" for campo, etichetta in analisi.RISCHI},
}

Filtri = dict[str, str]


def get_db() -> sqlite3.Connection:
    return database.connetti_alimenti(current_app.config["DATABASE_PATH"])


def leggi_filtri(args: Mapping[str, str]) -> tuple[Filtri, str, str]:
    """
    (filtri, sort, direction) dalla query string, già validati.
    """
    filtri = {campo: (args.get(campo) or "").strip() for campo in ETICHETTE_FILTRI}

    sort = (args.get("sort") or "alimento").strip()
    if sort not in SORT_EXPRESSIONS:
        sort = "alimento"

    direction = (args.get("dir") or "asc").strip().lower()
    if direction not in ("asc", "desc"):
        direction = "asc"

    return filtri, sort, direction


def get_alimenti(
    filtri: Mapping[str, str] | None = None,
    sort: str = "alimento",
    direction: str = "asc",
    cerca: str = "",
) -> list[Alimento]:
    """
    Alimenti filtrati (uguaglianza senza maiuscole per categoria e rischi,
    testo contenuto nel nome per cerca) e ordinati.
    """
    sort_expr = SORT_EXPRESSIONS.get(sort, SORT_EXPRESSIONS["alimento"])
    dir_sql = "DESC" if direction.lower() == "desc" else "ASC"

    clausole = []
    parametri: list[str] = []

    for campo in ETICHETTE_FILTRI:
        valore = (filtri or {}).get(campo, "")

        if valore:
            clausole.append(f"LOWER(COALESCE({campo}, '')) = LOWER(?)")
            parametri.append(valore)

    if cerca.strip():
        clausole.append("instr(LOWER(alimento), LOWER(?)) > 0")
        parametri.append(cerca.strip())

    sql = SELECT_ALIMENTI

    if clausole:
        sql += " WHERE " + " AND ".join(clausole)

    sql += f" ORDER BY {sort_expr} {dir_sql}, LOWER(alimento) ASC, id ASC"

    conn = get_db()

    try:
        return [dict(riga) for riga in conn.execute(sql, parametri).fetchall()]
    finally:
        conn.close()


def get_alimento(alimento_id: int) -> Alimento | None:
    conn = get_db()

    try:
        riga = conn.execute(f"{SELECT_ALIMENTI} WHERE id = ?", (alimento_id,)).fetchone()
    finally:
        conn.close()

    return dict(riga) if riga else None


def get_alimenti_per_id(ids: list[int]) -> dict[int, Alimento]:
    if not ids:
        return {}

    conn = get_db()

    try:
        righe = conn.execute(
            f"{SELECT_ALIMENTI} WHERE id IN ({', '.join('?' for _ in ids)})", ids
        ).fetchall()
    finally:
        conn.close()

    return {riga["id"]: dict(riga) for riga in righe}


def salva_alimento(valori: Mapping[str, Any], alimento_id: int | None = None) -> int:
    """
    Inserisce (alimento_id None) o aggiorna un alimento con tutti i campi; restituisce l'id.
    """
    campi = (*importazione.CAMPI, "aggiornato_il")
    dati = [valori.get(campo) for campo in importazione.CAMPI]
    dati.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    conn = get_db()

    try:
        if alimento_id is None:
            cursore = conn.execute(
                f"INSERT INTO alimenti ({', '.join(campi)}) VALUES ({', '.join('?' for _ in campi)})",
                dati,
            )
            alimento_id = int(cursore.lastrowid or 0)
        else:
            conn.execute(
                f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in campi)} WHERE id = ?",
                [*dati, alimento_id],
            )

        conn.commit()
    finally:
        conn.close()

    return alimento_id


def elimina_alimento(alimento_id: int) -> bool:
    conn = get_db()

    try:
        eliminati = conn.execute("DELETE FROM alimenti WHERE id = ?", (alimento_id,)).rowcount
        conn.commit()
    finally:
        conn.close()

    return eliminati > 0


def get_stats() -> tuple[int, int]:
    """
    (totale alimenti, alimenti con dati TEF).
    """
    conn = get_db()

    try:
        totale = conn.execute("SELECT COUNT(*) FROM alimenti").fetchone()[0]
        con_tef = conn.execute(
            "SELECT COUNT(*) FROM alimenti WHERE COALESCE(tef_kcal, 0) > 0 OR COALESCE(tef_percent, 0) > 0"
        ).fetchone()[0]
    finally:
        conn.close()

    return int(totale), int(con_tef)


def categorie() -> list[tuple[str, int]]:
    """
    (categoria, numero di alimenti), in ordine alfabetico.
    """
    conn = get_db()

    try:
        righe = conn.execute("""
            SELECT categoria, COUNT(*) AS n
            FROM alimenti
            WHERE TRIM(COALESCE(categoria, '')) <> ''
            GROUP BY categoria
            ORDER BY LOWER(categoria)
        """).fetchall()
    finally:
        conn.close()

    return [(riga["categoria"], int(riga["n"])) for riga in righe]


def elenco_per_ricerca() -> list[Alimento]:
    """
    Alimenti per il campo di ricerca (datalist) di pasto e diario.
    """
    conn = get_db()

    try:
        righe = conn.execute(
            "SELECT id, alimento, categoria, kcal FROM alimenti ORDER BY LOWER(alimento), id"
        ).fetchall()
    finally:
        conn.close()

    return [dict(riga) for riga in righe]


def ids_per_nome(nome: str) -> list[int]:
    conn = get_db()

    try:
        righe = conn.execute(
            "SELECT id FROM alimenti WHERE LOWER(alimento) = LOWER(?)", (nome,)
        ).fetchall()
    finally:
        conn.close()

    return [int(riga["id"]) for riga in righe]


Opzione = dict[str, str]


def _opzioni(predefinite: list[tuple[str, str]], valori: list[str]) -> list[Opzione]:
    """
    Opzioni di un menu: prima quelle predefinite (valore, etichetta),
    poi gli altri valori presenti nel database.
    """
    opzioni = [{"value": valore, "label": etichetta} for valore, etichetta in predefinite]
    visti = {valore.lower() for valore, _ in predefinite}

    for valore in valori:
        valore = str(valore).strip()

        if valore and valore.lower() not in visti:
            opzioni.append({"value": valore, "label": valore})
            visti.add(valore.lower())

    return opzioni


def get_filter_options() -> dict[str, list[Opzione]]:
    """
    Opzioni dei filtri per categoria e per ciascun rischio: la scala a 4 livelli
    (analisi.LIVELLI) più eventuali altri valori presenti nel database.
    """
    conn = get_db()

    try:
        distinti = {
            campo: [
                riga[0]
                for riga in conn.execute(
                    f"SELECT DISTINCT {campo} FROM alimenti "
                    f"WHERE TRIM(COALESCE({campo}, '')) <> '' ORDER BY {campo}"
                ).fetchall()
            ]
            for campo in ETICHETTE_FILTRI
        }
    finally:
        conn.close()

    livelli = [(liv["etichetta"], f"{liv['emoji']} {lingue.traduci(liv['etichetta'])}") for liv in analisi.LIVELLI]

    return {
        "categoria": [
            {**opzione, "label": lingue.traduci(opzione["label"])}
            for opzione in _opzioni([], distinti["categoria"])
        ],
        **{campo: _opzioni(livelli, distinti[campo]) for campo in analisi.CAMPI_RISCHIO},
    }
