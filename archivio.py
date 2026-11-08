"""
Lettura e scrittura degli alimenti: query con filtri e ordinamento,
singolo alimento, statistiche, opzioni dei filtri. Usato dalle pagine web
(app.py) e dall'API JSON (api.py); il percorso del database arriva dalla
configurazione dell'app attiva.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from flask import current_app

import analisi
import database
import importazione
import lingue
import ricerca
from lingue import N_

Alimento = dict[str, Any]

# Colonne lette da ogni query sugli alimenti, punteggio calcolato compreso
PUNTEGGIO_SQL = "punteggio(" + ", ".join(analisi.CAMPI_RISCHIO) + ")"
SELECT_ALIMENTI = f"SELECT *, {PUNTEGGIO_SQL} AS punteggio FROM alimenti"

# Livello di rischio come numero (Trascurabile 0 ... Alto 3, altri valori NULL)
LIVELLO_SQL = (
    "CASE LOWER(TRIM(COALESCE({campo}, '')))"
    + "".join(f" WHEN '{liv['chiave']}' THEN {liv['punti']}" for liv in analisi.LIVELLI)
    + " END"
)

# Espressioni di ordinamento: i valori NULL (dato mancante, rischio non
# classificato) vanno sempre in fondo, in entrambe le direzioni
SORT_EXPRESSIONS = {
    "alimento": "LOWER(alimento)",
    "categoria": "NULLIF(LOWER(TRIM(COALESCE(categoria, ''))), '')",
    "punteggio": PUNTEGGIO_SQL,
    **{
        campo: campo
        for campo in (
            "kcal", "kcal_nette", "tef_kcal", "tef_percent",
            "fruttosio", "fibre", "rapporto", "zuccheri", "grassi_saturi", "sodio",
        )
    },
    **{campo: LIVELLO_SQL.format(campo=campo) for campo in analisi.CAMPI_RISCHIO},
}

# Ordinamento per pertinenza alla ricerca: solo come primo criterio, con un testo cercato
PERTINENZA = "pertinenza"
ORDINAMENTI_MAX = 3

# Filtri di uguaglianza (menu della home), con le etichette per i file esportati
FILTRI_UGUALI = {
    "categoria": "Categoria",
    **{campo: f"Rischio {etichetta.lower()}" for campo, etichetta in analisi.RISCHI},
}

# Filtri a intervallo (da / fino a), per 100 g: campo -> etichetta
CAMPI_INTERVALLO = {
    "kcal": N_("Kcal"),
    "zuccheri": N_("Zuccheri (g)"),
    "fruttosio": N_("Fruttosio (g)"),
    "fibre": N_("Fibre (g)"),
    "grassi_saturi": N_("Grassi saturi (g)"),
    "sodio": N_("Sodio (mg)"),
    "rapporto": N_("Rapporto F/F"),
    "punteggio": N_("Punteggio"),
}

LIMITI = (("min", ">=", "da"), ("max", "<=", "fino a"))

# Alimenti «sicuri»: tutti e cinque i rischi classificati, al massimo Basso
LIVELLI_SICURI = tuple(liv["chiave"] for liv in analisi.LIVELLI if liv["punti"] <= 1)

# Tutti i parametri di filtro della home (e di export e API), con le etichette per i file esportati
ETICHETTE_FILTRI = {
    "q": "Ricerca",
    **FILTRI_UGUALI,
    "sicuri": "Solo alimenti sicuri",
    **{
        f"{campo}_{limite}": f"{etichetta} {parola}"
        for campo, etichetta in CAMPI_INTERVALLO.items()
        for limite, _operatore, parola in LIMITI
    },
}

Filtri = dict[str, str]


def get_db() -> sqlite3.Connection:
    return database.connetti_alimenti(current_app.config["DATABASE_PATH"])


def _numero_filtro(testo: object) -> str:
    """
    Limite di un filtro a intervallo, come testo normalizzato ("2.5"), o "" se non valido.
    """
    try:
        valore = float(str(testo or "").strip().replace(",", "."))
    except ValueError:
        return ""

    return f"{valore:g}" if math.isfinite(valore) and valore >= 0 else ""


def _valori(args: Mapping[str, str], nome: str) -> list[str]:
    """
    Valori di un parametro: ripetuto (?sort=a&sort=b, dai menu) o separato da virgole.
    """
    getlist = getattr(args, "getlist", None)
    valori = getlist(nome) if getlist else [args.get(nome) or ""]

    if len(valori) == 1:
        return [v.strip() for v in valori[0].split(",")]

    return [v.strip() for v in valori]


def ordinamenti(campi: list[str], direzioni: list[str], ricerca: bool) -> list[tuple[str, str]]:
    """
    Criteri di ordinamento validi, (campo, "asc"/"desc"), al massimo
    ORDINAMENTI_MAX e senza ripetizioni. Senza criteri: per pertinenza se
    c'è un testo cercato, altrimenti per nome.
    """
    scelti: list[tuple[str, str]] = []

    for i, campo in enumerate(campi):
        direzione = direzioni[i].lower() if i < len(direzioni) else ""

        if campo == PERTINENZA:
            valido = ricerca and not scelti
            direzione = "desc"
        else:
            valido = campo in SORT_EXPRESSIONS

        if valido and campo not in (c for c, _ in scelti):
            scelti.append((campo, direzione if direzione in ("asc", "desc") else "asc"))

    if not scelti:
        scelti = [(PERTINENZA, "desc")] if ricerca else [("alimento", "asc")]

    return scelti[:ORDINAMENTI_MAX]


def leggi_filtri(args: Mapping[str, str]) -> tuple[Filtri, str, str]:
    """
    (filtri, sort, direction) dalla query string, già validati. sort e
    direction possono avere più criteri separati da virgole («categoria,kcal»
    con «asc,desc»).
    """
    filtri = {campo: (args.get(campo) or "").strip() for campo in FILTRI_UGUALI}
    q = " ".join((args.get("q") or "").split())[: ricerca.LUNGHEZZA_MASSIMA]
    sicuri = (args.get("sicuri") or "").strip().lower() in ("1", "on", "true", "si", "sì")

    filtri = {
        "q": q,
        **filtri,
        "sicuri": "1" if sicuri else "",
        **{
            nome: _numero_filtro(args.get(nome))
            for nome in ETICHETTE_FILTRI
            if nome.endswith(("_min", "_max"))
        },
    }

    criteri = ordinamenti(_valori(args, "sort"), _valori(args, "dir"), bool(q))
    sort = ",".join(campo for campo, _ in criteri)
    direction = ",".join(direzione for _, direzione in criteri)

    return filtri, sort, direction


def get_alimenti(
    filtri: Mapping[str, str] | None = None,
    sort: str = "alimento",
    direction: str = "asc",
) -> list[Alimento]:
    """
    Alimenti filtrati e ordinati: categoria e rischi uguali (maiuscole
    indifferenti), «sicuri», intervalli di valori, ricerca nel nome
    (ricerca.py). sort e direction come da leggi_filtri.
    """
    filtri = filtri or {}
    q = (filtri.get("q") or "").strip()
    criteri = ordinamenti(sort.split(","), direction.split(","), bool(q))

    clausole = []
    parametri: list[Any] = []

    for campo in FILTRI_UGUALI:
        valore = filtri.get(campo, "")

        if valore:
            clausole.append(f"LOWER(COALESCE({campo}, '')) = LOWER(?)")
            parametri.append(valore)

    if filtri.get("sicuri"):
        segnaposti = ", ".join("?" for _ in LIVELLI_SICURI)

        for campo in analisi.CAMPI_RISCHIO:
            clausole.append(f"LOWER(TRIM(COALESCE({campo}, ''))) IN ({segnaposti})")
            parametri.extend(LIVELLI_SICURI)

    for campo in CAMPI_INTERVALLO:
        espressione = SORT_EXPRESSIONS[campo]

        for limite, operatore, _parola in LIMITI:
            valore = _numero_filtro(filtri.get(f"{campo}_{limite}"))

            if valore:
                clausole.append(f"({espressione}) IS NOT NULL AND ({espressione}) {operatore} ?")
                parametri.append(float(valore))

    sql = SELECT_ALIMENTI

    if clausole:
        sql += " WHERE " + " AND ".join(clausole)

    ordine = [
        f"({SORT_EXPRESSIONS[campo]}) IS NULL, ({SORT_EXPRESSIONS[campo]}) {direzione.upper()}"
        for campo, direzione in criteri
        if campo != PERTINENZA
    ]
    sql += " ORDER BY " + ", ".join([*ordine, "LOWER(alimento) ASC", "id ASC"])

    conn = get_db()

    try:
        alimenti = [dict(riga) for riga in conn.execute(sql, parametri).fetchall()]
    finally:
        conn.close()

    if not q:
        return alimenti

    trovati = ricerca.cerca(alimenti, q)

    if criteri[0][0] == PERTINENZA:
        trovati.sort(key=lambda coppia: -coppia[1])

    return [alimento for alimento, _punti in trovati]


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
            for campo in FILTRI_UGUALI
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
