"""
Macro e micronutrienti da USDA FoodData Central per gli alimenti
del database che vengono da USDA (abbinati per nome esatto).

Usa lo stesso elenco di autogen.py (dataset Foundation e SR Legacy).
La chiave pubblica DEMO_KEY basta per un aggiornamento occasionale
(poche richieste l'ora); per un uso regolare serve una chiave gratuita:
https://fdc.nal.usda.gov/api-key-signup
"""

from __future__ import annotations

import sqlite3
from typing import Any

import requests

import nutrienti

URL_ELENCO = "https://api.nal.usda.gov/fdc/v1/foods/list"
URL_SCHEDA = "https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients"
DATASET = ("Foundation", "SR Legacy")

# Conversione dalle unità USDA a quelle dei campi (fattore moltiplicativo)
CONVERSIONI = {
    ("g", "g"): 1, ("mg", "mg"): 1, ("µg", "µg"): 1,
    ("g", "mg"): 1000, ("mg", "µg"): 1000,
    ("mg", "g"): 0.001, ("µg", "mg"): 0.001,
}

UNITA_USDA = {"G": "g", "MG": "mg", "UG": "µg", "µG": "µg", "MCG": "µg"}


class ErroreUsda(Exception):
    pass


def scarica(api_key: str, pagine: int = 1, dimensione: int = 200, timeout: float = 30) -> list[dict[str, Any]]:
    """
    Alimenti dell'elenco USDA con i loro nutrienti (formato abridged).
    """
    alimenti = []

    for pagina in range(1, pagine + 1):
        try:
            parametri: dict[str, Any] = {
                    "api_key": api_key,
                    "dataType": list(DATASET),
                    "pageSize": dimensione,
                    "pageNumber": pagina,
            }
            risposta = requests.get(URL_ELENCO, params=parametri, timeout=timeout)
        except requests.RequestException as exc:
            raise ErroreUsda(f"USDA non raggiungibile: {exc}") from None

        if risposta.status_code == 429:
            raise ErroreUsda("Limite di richieste USDA raggiunto: riprova più tardi o usa una chiave personale.")

        if risposta.status_code != 200:
            raise ErroreUsda(f"USDA ha risposto {risposta.status_code}: {risposta.text[:200]}")

        blocco = risposta.json()

        if not blocco:
            break

        alimenti.extend(blocco)

    return alimenti


def valori(alimento_usda: dict[str, Any]) -> dict[str, float]:
    """
    {campo: valore} dei nutrienti presenti, convertiti nelle unità dei campi.
    I nutrienti assenti non compaiono: restano "non disponibili".
    """
    per_codice = {}

    for n in alimento_usda.get("foodNutrients", []):
        codice = str(n.get("number") or "")

        if codice and n.get("amount") is not None:
            per_codice[codice] = n

    risultato = {}

    for campo, _, unita, decimali, codice in nutrienti.NUTRIENTI:
        n = per_codice.get(codice)

        if not n:
            continue

        unita_usda = UNITA_USDA.get(str(n.get("unitName") or "").upper())
        fattore = CONVERSIONI.get((unita_usda, unita)) if unita_usda else None

        if fattore is None:
            continue

        risultato[campo] = round(float(n["amount"]) * fattore, max(decimali, 2) + 1)

    return risultato


def pianifica(
    conn: sqlite3.Connection, alimenti_usda: list[dict[str, Any]], sovrascrivi: bool = False
) -> list[dict[str, Any]]:
    """
    Lista di aggiornamenti {id, alimento, fdc_id, valori} per le righe del database
    il cui nome coincide con una descrizione USDA. Senza sovrascrivi si
    compilano solo i campi vuoti.
    """
    per_nome: dict[str, dict[str, Any]] = {}

    for a in alimenti_usda:
        per_nome.setdefault((a.get("description") or "").strip().casefold(), a)

    campi = (*nutrienti.CAMPI_NUTRIENTI, *nutrienti.CAMPI_FONTE)
    righe = conn.execute(f"SELECT id, alimento, {', '.join(campi)} FROM alimenti").fetchall()

    piano = []

    for riga in righe:
        trovato = per_nome.get((riga["alimento"] or "").strip().casefold())

        if not trovato:
            continue

        nuovi: dict[str, Any] = dict(valori(trovato))
        nuovi.update({
            "fdc_id": trovato.get("fdcId"),
            "fonte_nutrienti": f"USDA FoodData Central · {trovato.get('dataType', '')}".strip(" ·"),
            "url_fonte": URL_SCHEDA.format(fdc_id=trovato.get("fdcId")),
        })

        if not sovrascrivi:
            nuovi = {campo: valore for campo, valore in nuovi.items() if riga[campo] is None}

        if nuovi:
            piano.append({
                "id": riga["id"], "alimento": riga["alimento"], "fdc_id": trovato.get("fdcId"), "valori": nuovi,
            })

    return piano


def applica(conn: sqlite3.Connection, piano: list[dict[str, Any]], adesso: str) -> None:
    for voce in piano:
        campi = list(voce["valori"])
        conn.execute(
            f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in campi)}, aggiornato_il = ? WHERE id = ?",
            [voce["valori"][c] for c in campi] + [adesso, voce["id"]],
        )
