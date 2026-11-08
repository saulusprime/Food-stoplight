"""
Valori da USDA FoodData Central (dominio pubblico, CC0) per FDC ID:
https://fdc.nal.usda.gov

Negli alimenti CREA USDA completa i nutrienti che il CREA non pubblica
(soprattutto fruttosio e glucosio), presi dall'alimento USDA corrispondente;
quali campi vengono da USDA è scritto in campi_usda, ed è quello che la
sincronizzazione periodica aggiorna. Un alimento senza campi_usda ma con
FDC ID prende da USDA tutti i nutrienti.

La sincronizzazione richiede una chiave personale gratuita
(https://fdc.nal.usda.gov/api-key-signup): DEMO_KEY basta solo per
qualche ricerca occasionale dal form.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import requests

import nutrienti

URL_ALIMENTI = "https://api.nal.usda.gov/fdc/v1/foods"
URL_SCHEDA = "https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients"
CHIAVE_DEMO = "DEMO_KEY"
FONTE = "USDA FoodData Central"

# Alimenti per richiesta (limite dell'API)
LOTTO = 20

# Conversione dalle unità USDA a quelle dei campi (fattore moltiplicativo)
CONVERSIONI = {
    ("g", "g"): 1, ("mg", "mg"): 1, ("µg", "µg"): 1, ("kcal", "kcal"): 1,
    ("g", "mg"): 1000, ("mg", "µg"): 1000,
    ("mg", "g"): 0.001, ("µg", "mg"): 0.001,
}

UNITA_USDA = {"G": "g", "MG": "mg", "UG": "µg", "µG": "µg", "MCG": "µg", "KCAL": "kcal"}

# Campi dell'app: (unità, decimali, codici USDA in ordine di preferenza)
CAMPI: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "kcal": ("kcal", 1, ("208", "958", "957")),
    "fruttosio": ("g", 2, ("212",)),
    "fibre": ("g", 2, ("291",)),
    "zuccheri": ("g", 1, ("269", "269.3")),
    **{
        campo: (unita, decimali, (codice,))
        for campo, _, unita, decimali, codice in nutrienti.NUTRIENTI
        if campo not in ("zuccheri", "carboidrati")
    },
}

# Campi che USDA può fornire (i carboidrati diventano disponibili: meno le fibre)
CAMPI_FORNIBILI = (*CAMPI, "carboidrati")


class ErroreUsda(Exception):
    pass


def chiave_valida(api_key: str | None) -> bool:
    """
    Chiave personale (non vuota e diversa da DEMO_KEY): serve per la sincronizzazione.
    """
    return bool(api_key) and api_key != CHIAVE_DEMO


def scarica(
    api_key: str,
    fdc_ids: Iterable[int],
    timeout: float = 30,
    avanzamento: Callable[[int, int], object] | None = None,
) -> dict[int, dict[str, Any]]:
    """
    {fdc_id: alimento USDA} (formato abridged), a lotti di 20.
    """
    ids = list(dict.fromkeys(int(i) for i in fdc_ids))
    risultato: dict[int, dict[str, Any]] = {}

    for inizio in range(0, len(ids), LOTTO):
        lotto = ids[inizio:inizio + LOTTO]

        try:
            risposta = requests.post(
                URL_ALIMENTI,
                params={"api_key": api_key},
                json={"fdcIds": lotto, "format": "abridged"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise ErroreUsda(f"USDA non raggiungibile: {exc}") from None

        if risposta.status_code == 429:
            raise ErroreUsda("Limite di richieste USDA raggiunto: riprova più tardi o usa una chiave personale.")

        if risposta.status_code == 403:
            raise ErroreUsda("Chiave USDA non valida (USDA_API_KEY).")

        if risposta.status_code != 200:
            raise ErroreUsda(f"USDA ha risposto {risposta.status_code}: {risposta.text[:200]}")

        for alimento in risposta.json() or []:
            if alimento.get("fdcId"):
                risultato[int(alimento["fdcId"])] = alimento

        if avanzamento:
            avanzamento(min(inizio + LOTTO, len(ids)), len(ids))

    return risultato


def valori(alimento_usda: Mapping[str, Any]) -> dict[str, float]:
    """
    {campo: valore} dei nutrienti presenti, convertiti nelle unità dei campi.
    I nutrienti assenti non compaiono: restano "non disponibili".
    """
    per_codice: dict[str, Mapping[str, Any]] = {}

    for n in alimento_usda.get("foodNutrients", []):
        codice = str(n.get("number") or n.get("nutrient", {}).get("number") or "")
        quantita = n.get("amount")

        if codice and quantita is not None:
            per_codice.setdefault(codice, {**n, "amount": quantita})

    risultato: dict[str, float] = {}

    for campo, (unita, decimali, codici) in CAMPI.items():
        n = next((per_codice[c] for c in codici if c in per_codice), None)

        if n is None:
            continue

        nome_unita = n.get("unitName") or n.get("nutrient", {}).get("unitName") or ""
        unita_usda = UNITA_USDA.get(str(nome_unita).upper())
        fattore = CONVERSIONI.get((unita_usda, unita)) if unita_usda else None

        if fattore is None:
            continue

        risultato[campo] = round(float(n["amount"]) * fattore, max(decimali, 2) + 1)

    if "205" in per_codice:
        totali = float(per_codice["205"]["amount"])
        risultato["carboidrati"] = round(max(totali - risultato.get("fibre", 0.0), 0.0), 2)

    return risultato


def descrizione(alimento_usda: Mapping[str, Any]) -> str:
    tipo = alimento_usda.get("dataType") or ""
    return f"{FONTE} · {tipo}".strip(" ·")


def url_scheda(fdc_id: int | str) -> str:
    return URL_SCHEDA.format(fdc_id=fdc_id)


def leggi_campi(testo: object) -> list[str]:
    """
    Campi da USDA salvati come "fruttosio,glucosio" (solo quelli validi).
    """
    return [c for c in (p.strip() for p in str(testo or "").split(",")) if c in CAMPI_FORNIBILI]


def campi_da_aggiornare(riga: Mapping[str, Any]) -> list[str]:
    """
    Campi che la sincronizzazione aggiorna per un alimento con FDC ID.
    """
    campi = leggi_campi(riga.get("campi_usda"))
    return campi if campi else list(CAMPI_FORNIBILI)


def righe_da_sincronizzare(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM alimenti WHERE fdc_id IS NOT NULL ORDER BY id")]
