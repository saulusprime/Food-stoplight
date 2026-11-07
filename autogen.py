"""
autogen.py — genera il dataset 1000_foods_complete.csv:

1. alimenti reali da USDA FoodData Central (dataset Foundation e SR Legacy);
2. alimenti integrativi con valori casuali verosimili per categoria, fino a
   circa 1000 righe (sono dati sintetici: nomi ripetuti con valori diversi).

    python autogen.py
    python autogen.py --output dataset.csv --seed 42 --per-categoria 115

TEF, Kcal nette e rapporto fruttosio/fibre si calcolano con calcoli.py,
come nella web app. Il CSV si importa da «Importa» o con update.py.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
from collections.abc import Sequence
from typing import Any

import requests

import calcoli

URL_ELENCO = "https://api.nal.usda.gov/fdc/v1/foods/list"

INTESTAZIONI = [
    "Alimento", "Categoria", "Kcal", "TEF (Kcal)", "TEF (%)", "Kcal Nette", "Fruttosio (g)",
    "Fibre (g)", "Rapporto F/F", "Rischio Diabete", "Rischio Colesterolo",
    "Rischio Malassorbimento", "Rischio Metabolico", "Rischio Tumorale",
]

# TEF di ripiego quando i macronutrienti non danno energia
TEF_PREDEFINITO = 0.10

PAROLE_CATEGORIA = (
    ("Frutta", ("apple", "banana", "orange", "berry", "fruit", "juice")),
    ("Verdura", ("vegetable", "broccoli", "carrot", "spinach", "tomato")),
    ("Latticini e Uova", ("milk", "cheese", "yogurt", "butter", "cream", "egg")),
    ("Carne", ("beef", "pork", "chicken", "turkey", "meat", "steak")),
    ("Pesce", ("fish", "salmon", "tuna", "shrimp", "cod", "crab")),
    ("Cereali", ("bread", "rice", "pasta", "wheat", "oat", "cereal", "corn")),
    ("Legumi/Frutta Secca", ("bean", "pea", "lentil", "soy", "peanut", "almond", "walnut", "seed")),
    ("Grassi e Oli", ("oil", "fat", "shortening", "lard")),
    ("Dolci e Snack", ("candy", "cake", "cookie", "sugar", "syrup", "jam", "chocolate", "snack")),
    ("Bevande", ("wine", "beer", "liquor", "alcohol", "drink", "soda", "coffee", "tea")),
)

ALIMENTI_BASE = {
    "Frutta": ["Mela", "Pera", "Banana", "Arancia", "Uva", "Fragola", "Kiwi", "Pesca", "Albicocca", "Ciliegie"],
    "Verdura": ["Carota", "Zucchina", "Spinaci", "Broccoli", "Cavolfiore", "Pomodoro", "Cetriolo", "Peperone",
                "Melanzana", "Sedano"],
    "Cereali": ["Riso bianco", "Riso integrale", "Pasta", "Pane integrale", "Avena", "Farro", "Orzo", "Mais",
                "Quinoa", "Grano saraceno"],
    "Carne": ["Petto di pollo", "Manzo magro", "Maiale", "Tacchino", "Agnello", "Salsiccia", "Salame",
              "Prosciutto crudo", "Bresaola", "Hamburger"],
    "Pesce": ["Salmone", "Tonno", "Merluzzo", "Trota", "Sgombro", "Gamberetti", "Vongole", "Polpo", "Orata",
              "Branzino"],
    "Latticini e Uova": ["Latte intero", "Latte scremato", "Yogurt greco", "Parmigiano", "Mozzarella",
                         "Uovo intero", "Albume", "Burro", "Ricotta", "Formaggio fresco"],
    "Dolci e Snack": ["Cioccolato fondente", "Biscotti", "Torta al cioccolato", "Miele", "Marmellata",
                      "Patatine fritte", "Merendina", "Caramelle", "Gelato", "Croissant"],
}

VARIANTI = ("", "cotto", "crudo", "bio", "industriale", "fresco")

# Intervalli per categoria: kcal, proteine, grassi, carboidrati, fibre, fruttosio, saturi, colesterolo, zuccheri
Intervallo = tuple[float, float]
INTERVALLI: dict[str, tuple[Intervallo, ...]] = {
    "Frutta": ((30, 90), (0.5, 1.5), (0.1, 0.5), (10, 20), (1, 4), (2, 8), (0, 0), (0, 0), (8, 15)),
    "Verdura": ((10, 40), (1, 3), (0.1, 0.5), (2, 8), (1.5, 4), (0.5, 2), (0, 0), (0, 0), (1, 4)),
    "Cereali": ((120, 380), (3, 12), (1, 4), (25, 75), (1, 10), (0, 0), (0, 2), (0, 0), (0, 3)),
    "Carne": ((100, 350), (15, 28), (2, 25), (0, 2), (0, 0), (0, 0), (1, 10), (30, 100), (0, 0)),
    "Pesce": ((70, 250), (15, 25), (1, 15), (0, 0), (0, 0), (0, 0), (0.5, 4), (30, 80), (0, 0)),
    "Latticini e Uova": ((50, 400), (3, 30), (0, 35), (0, 15), (0, 0), (0, 1), (0, 20), (10, 200), (0, 10)),
    "Dolci e Snack": ((200, 600), (2, 10), (5, 35), (30, 80), (0, 3), (0, 10), (2, 15), (0, 50), (10, 40)),
}


def nutriente(nutrienti_usda: Sequence[dict[str, Any]], numero: int) -> float:
    for n in nutrienti_usda:
        if n.get("number") == str(numero):
            return float(n.get("amount") or 0)

    return 0.0


def categoria_da_descrizione(descrizione: str) -> str:
    testo = descrizione.lower()

    for categoria, parole in PAROLE_CATEGORIA:
        if any(parola in testo for parola in parole):
            return categoria

    return "Altri Alimenti"


def _livello(punteggio: int) -> str:
    if punteggio >= 3:
        return "Alto"

    if punteggio == 2:
        return "Medio"

    if punteggio == 1:
        return "Basso"

    return "Trascurabile"


def calcola_rischi(
    kcal: float, saturi: float, fibre: float, fruttosio: float, zuccheri: float, colesterolo: float
) -> tuple[str, str, str, str, str]:
    """
    Livelli dei 5 rischi (diabete, colesterolo, malassorbimento, metabolico, tumorale)
    da soglie su zuccheri, fibre, grassi saturi, colesterolo e fruttosio.
    """
    diabete = (2 if zuccheri > 15 else 1 if zuccheri > 10 else 0) + (1 if fibre < 2 else -1 if fibre > 5 else 0)
    colesterolo_punti = (2 if saturi > 5 else 0) + (2 if colesterolo > 100 else 1 if colesterolo > 50 else 0)
    malassorbimento = 2 if fruttosio > 5 and fibre < 2 else 1 if fruttosio > 3 else 0
    metabolico = (2 if kcal > 250 and zuccheri > 10 else 0) + (1 if saturi > 5 else 0)
    tumorale = (2 if saturi > 7 else 1 if saturi > 4 else 0) + (1 if zuccheri > 15 else 0)  # soglie OMS/WCRF

    return (
        _livello(diabete),
        _livello(colesterolo_punti),
        _livello(malassorbimento),
        _livello(metabolico),
        _livello(tumorale),
    )


def riga(
    nome: str, categoria: str, kcal: float, proteine: float, grassi: float, carboidrati: float,
    fibre: float, fruttosio: float, saturi: float, colesterolo: float, zuccheri: float,
) -> list[Any]:
    stima = calcoli.tef_da_macronutrienti(kcal, proteine, carboidrati, grassi)
    tef_kcal, tef_percent = stima if stima else (kcal * TEF_PREDEFINITO, TEF_PREDEFINITO * 100)

    return [
        nome, categoria, round(kcal, 1), round(tef_kcal, 1), round(tef_percent, 1), round(kcal - tef_kcal, 1),
        round(fruttosio, 1), round(fibre, 1), calcoli.rapporto_fruttosio_fibre(fruttosio, fibre),
        *calcola_rischi(kcal, saturi, fibre, fruttosio, zuccheri, colesterolo),
    ]


def scarica_usda(api_key: str, dimensione: int = 200) -> list[dict[str, Any]]:
    parametri: dict[str, Any] = {
        "api_key": api_key, "dataType": ["Foundation", "SR Legacy"], "pageSize": dimensione, "pageNumber": 1,
    }
    risposta = requests.get(URL_ELENCO, params=parametri, timeout=15)
    risposta.raise_for_status()
    dati: list[dict[str, Any]] = risposta.json()
    return dati


def righe_usda(alimenti_usda: Sequence[dict[str, Any]]) -> list[list[Any]]:
    righe = []

    for alimento in alimenti_usda:
        descrizione = alimento.get("description", "Unknown")
        valori = alimento.get("foodNutrients", [])

        kcal = nutriente(valori, 208) or nutriente(valori, 268) / 4.184  # Kcal, altrimenti da kJ

        righe.append(riga(
            descrizione, categoria_da_descrizione(descrizione), kcal,
            proteine=nutriente(valori, 203), grassi=nutriente(valori, 204), carboidrati=nutriente(valori, 205),
            fibre=nutriente(valori, 291), fruttosio=nutriente(valori, 287), saturi=nutriente(valori, 606),
            colesterolo=nutriente(valori, 601), zuccheri=nutriente(valori, 269),
        ))

    return righe


def righe_integrative(per_categoria: int, generatore: random.Random) -> list[list[Any]]:
    righe = []

    for categoria, nomi in ALIMENTI_BASE.items():
        intervalli = INTERVALLI[categoria]

        for _ in range(per_categoria):
            nome = f"{generatore.choice(nomi)} {generatore.choice(VARIANTI)}".strip()
            kcal_min, kcal_max = intervalli[0]
            kcal = float(generatore.randint(int(kcal_min), int(kcal_max)))
            proteine, grassi, carboidrati, fibre, fruttosio, saturi, colesterolo, zuccheri = (
                generatore.uniform(minimo, massimo) for minimo, massimo in intervalli[1:]
            )
            righe.append(riga(nome, categoria, kcal, proteine, grassi, carboidrati, fibre, fruttosio,
                              saturi, colesterolo, zuccheri))

    return righe


def salva(righe: Sequence[Sequence[Any]], percorso: str) -> None:
    with open(percorso, "w", encoding="utf-8", newline="") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(INTESTAZIONI)
        scrittore.writerows(righe)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera il dataset di alimenti (USDA + integrativi).")
    parser.add_argument("--output", default="1000_foods_complete.csv", help="File CSV da scrivere")
    parser.add_argument("--seed", type=int, default=None, help="Seme casuale per risultati ripetibili")
    parser.add_argument("--per-categoria", type=int, default=115, help="Alimenti integrativi per categoria")
    parser.add_argument("--api-key", default=os.environ.get("USDA_API_KEY", "DEMO_KEY"),
                        help="Chiave USDA FoodData Central (variabile USDA_API_KEY)")
    args = parser.parse_args(argv)

    righe: list[list[Any]] = []

    try:
        righe = righe_usda(scarica_usda(args.api_key))
    except requests.RequestException as exc:
        print(f"Errore connessione API USDA: {exc}")

    righe += righe_integrative(args.per_categoria, random.Random(args.seed))
    salva(righe, args.output)
    print(f"Generazione completata: {len(righe)} alimenti in '{args.output}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
