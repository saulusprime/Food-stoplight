"""
Prodotti confezionati da Open Food Facts per codice a barre (EAN/UPC):
https://world.openfoodfacts.org

I dati sono pubblicati con licenza Open Database License (ODbL): chi li
riusa deve citare la fonte, come fa ogni alimento importato (fonte e link
alla scheda del prodotto). Valori per 100 g dalla tabella nutrizionale
dell'etichetta; il gruppo NOVA è quello calcolato da Open Food Facts
dagli ingredienti.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import requests

URL_PRODOTTO = "https://world.openfoodfacts.org/api/v2/product/{codice}.json"
URL_SCHEDA = "https://world.openfoodfacts.org/product/{codice}"
FONTE = "Open Food Facts (ODbL)"
CAMPI_RICHIESTI = (
    "code,product_name,product_name_it,generic_name_it,brands,categories_tags,nova_group,serving_quantity,nutriments"
)
INTESTAZIONI_HTTP = {"User-Agent": "Food-stoplight/1.0 (+https://github.com/saulusprime/Food-stoplight)"}

CODICE_RE = re.compile(r"^\d{8,14}$")

# Nutrienti per 100 g: chiave Open Food Facts -> (campo, fattore verso l'unità del campo)
NUTRIENTI = {
    "energy-kcal_100g": ("kcal", 1),
    "proteins_100g": ("proteine", 1),
    "carbohydrates_100g": ("carboidrati", 1),
    "sugars_100g": ("zuccheri", 1),
    "fructose_100g": ("fruttosio", 1),
    "glucose_100g": ("glucosio", 1),
    "lactose_100g": ("lattosio", 1),
    "fat_100g": ("grassi", 1),
    "saturated-fat_100g": ("grassi_saturi", 1),
    "cholesterol_100g": ("colesterolo", 1000),
    "fiber_100g": ("fibre", 1),
    "sodium_100g": ("sodio", 1000),
    "vitamin-a_100g": ("vitamina_a", 1_000_000),
    "vitamin-c_100g": ("vitamina_c", 1000),
    "vitamin-d_100g": ("vitamina_d", 1_000_000),
    "vitamin-e_100g": ("vitamina_e", 1000),
    "vitamin-b12_100g": ("vitamina_b12", 1_000_000),
    "vitamin-b9_100g": ("folati", 1_000_000),
    "calcium_100g": ("calcio", 1000),
    "iron_100g": ("ferro", 1000),
    "magnesium_100g": ("magnesio", 1000),
    "potassium_100g": ("potassio", 1000),
    "zinc_100g": ("zinco", 1000),
}

# Alcol: Open Food Facts lo indica in % vol; densità dell'etanolo 0,789 g/ml
DENSITA_ALCOL = 0.789

# Categorie di Open Food Facts -> categorie dell'app (la prima che corrisponde)
CATEGORIE = (
    ("en:alcoholic-beverages", "Bevande"),
    ("en:beverages", "Bevande"),
    ("en:meals", "Piatti e ricette"),
    ("en:cheeses", "Latticini e Uova"),
    ("en:dairies", "Latticini e Uova"),
    ("en:eggs", "Latticini e Uova"),
    ("en:fishes", "Pesce"),
    ("en:seafood", "Pesce"),
    ("en:meats", "Carne"),
    ("en:fats", "Grassi e Oli"),
    ("en:vegetable-oils", "Grassi e Oli"),
    ("en:legumes", "Legumi/Frutta Secca"),
    ("en:nuts", "Legumi/Frutta Secca"),
    ("en:sweet-snacks", "Dolci e Snack"),
    ("en:salty-snacks", "Dolci e Snack"),
    ("en:snacks", "Dolci e Snack"),
    ("en:desserts", "Dolci e Snack"),
    ("en:confectioneries", "Dolci e Snack"),
    ("en:fruits", "Frutta"),
    ("en:vegetables", "Verdura"),
    ("en:cereals-and-potatoes", "Cereali"),
    ("en:breads", "Cereali"),
)

CATEGORIA_PREDEFINITA = "Altri Alimenti"


class ErroreOpenFoodFacts(Exception):
    pass


def scarica(codice: str, timeout: float = 20) -> dict[str, Any]:
    """
    Prodotto (dizionario "product" dell'API) per codice a barre.
    """
    codice = codice.strip()

    if not CODICE_RE.match(codice):
        raise ErroreOpenFoodFacts("Codice a barre non valido: servono da 8 a 14 cifre.")

    try:
        risposta = requests.get(
            URL_PRODOTTO.format(codice=codice),
            params={"fields": CAMPI_RICHIESTI},
            headers=INTESTAZIONI_HTTP,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ErroreOpenFoodFacts(f"Open Food Facts non raggiungibile: {exc}") from None

    if risposta.status_code == 404:
        raise ErroreOpenFoodFacts(f"Prodotto {codice} non trovato su Open Food Facts.")

    if risposta.status_code != 200:
        raise ErroreOpenFoodFacts(f"Open Food Facts ha risposto {risposta.status_code}.")

    dati = risposta.json()

    if dati.get("status") != 1 or not dati.get("product"):
        raise ErroreOpenFoodFacts(f"Prodotto {codice} non trovato su Open Food Facts.")

    prodotto: dict[str, Any] = dati["product"]
    prodotto.setdefault("code", codice)
    return prodotto


def categoria_app(tag: list[str] | None) -> str:
    presenti = set(tag or [])
    return next((categoria for chiave, categoria in CATEGORIE if chiave in presenti), CATEGORIA_PREDEFINITA)


def _numero(valore: object) -> float | None:
    try:
        numero = float(valore)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

    return numero if numero >= 0 else None


def valori(prodotto: Mapping[str, Any]) -> dict[str, Any]:
    """
    Campi dell'app per un prodotto (solo i valori presenti nell'etichetta).
    """
    nutrimenti = prodotto.get("nutriments") or {}
    risultato: dict[str, Any] = {}

    for chiave, (campo, fattore) in NUTRIENTI.items():
        valore = _numero(nutrimenti.get(chiave))

        if valore is not None:
            risultato[campo] = round(valore * fattore, 3)

    alcol = _numero(nutrimenti.get("alcohol_100g"))

    if alcol is not None:
        risultato["alcol"] = round(alcol * DENSITA_ALCOL, 2)

    nome = (prodotto.get("product_name_it") or prodotto.get("product_name")
            or prodotto.get("generic_name_it") or "").strip()
    marca = str(prodotto.get("brands") or "").split(",")[0].strip()

    if marca and marca.casefold() not in nome.casefold():
        nome = f"{nome} ({marca})" if nome else marca

    codice = str(prodotto.get("code") or "")
    nova = prodotto.get("nova_group")
    porzione = _numero(prodotto.get("serving_quantity"))

    risultato.update({
        "alimento": nome or codice,
        "categoria": categoria_app(prodotto.get("categories_tags")),
        "codice_barre": codice,
        "nova": int(nova) if nova in (1, 2, 3, 4, "1", "2", "3", "4") else None,
        "porzione": porzione if porzione and porzione > 0 else None,
        "fonte_nutrienti": FONTE,
        "url_fonte": URL_SCHEDA.format(codice=codice),
    })

    return risultato
