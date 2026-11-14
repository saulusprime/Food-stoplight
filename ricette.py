"""
Ricette CREA: valori che il CREA non pubblica (fruttosio, glucosio,
lattosio, grassi saturi) calcolati dagli ingredienti della ricetta.

Il CREA pubblica per ogni ricetta gli ingredienti con le quantità (colonna
ingredienti, JSON) e i valori misurati o calcolati del piatto, ma spesso
senza il dettaglio degli zuccheri o degli acidi grassi. Dagli ingredienti
(abbinati a mano agli alimenti CREA in dati/ingredienti_crea.csv) si ricava
la *composizione*: quanta parte degli zuccheri è fruttosio, glucosio,
lattosio, quanta parte dei grassi è satura. Le quote si applicano agli
zuccheri e ai grassi del piatto pubblicati dal CREA, così cottura e
perdita d'acqua sono già comprese (EuroFIR, calcolo delle ricette).

Se gli ingredienti senza il dato portano più del 5% degli zuccheri (o dei
grassi) della ricetta, il valore resta non disponibile. Per carne e pesce
senza il glucosio, gli zuccheri (dal glicogeno) contano come glucosio
(classificazioni.glucosio).
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable, Mapping, MutableMapping
from functools import cache
from typing import Any

import calcoli
import classificazioni
import rischi

FILE_INGREDIENTI = classificazioni.CARTELLA_DATI / "ingredienti_crea.csv"

# Ingrediente senza zuccheri né grassi (acqua, sale, spezie in quantità minime)
NESSUNO = "0"

# Quota massima di zuccheri o grassi portata da ingredienti senza dettaglio
QUOTA_IGNOTA_MAX = 0.05

# Densità per le quantità in ml (oli; il resto come l'acqua)
DENSITA_OLI = 0.92

CAMPI_ZUCCHERI = ("fruttosio", "glucosio", "lattosio")
CAMPI_FORNIBILI = (*CAMPI_ZUCCHERI, "grassi_saturi")


@cache
def ingredienti_crea() -> dict[str, str]:
    """
    {nome dell'ingrediente come nelle ricette CREA: codice CREA o "0"}.
    """
    if not FILE_INGREDIENTI.is_file():
        return {}

    with FILE_INGREDIENTI.open(encoding="utf-8", newline="") as f:
        return {
            riga["ingrediente"].strip(): riga["codice_crea"].strip()
            for riga in csv.DictReader(f)
            if (riga.get("ingrediente") or "").strip() and (riga.get("codice_crea") or "").strip()
        }


def leggi_ingredienti(testo: object) -> list[dict[str, Any]]:
    """
    Ingredienti salvati in JSON ([{"nome", "quantita", "unita"}]); [] se mancano o non sono validi.
    """
    if isinstance(testo, list):
        dati: Any = testo
    else:
        try:
            dati = json.loads(str(testo or "[]"))
        except ValueError:
            return []

    if not isinstance(dati, list):
        return []

    validi = []

    for voce in dati:
        if not isinstance(voce, Mapping):
            continue

        nome = str(voce.get("nome") or "").strip()
        quantita = voce.get("quantita")
        unita = str(voce.get("unita") or "").strip().lower()

        if nome and isinstance(quantita, (int, float)) and quantita > 0 and unita in ("g", "ml"):
            validi.append({"nome": nome, "quantita": float(quantita), "unita": unita})

    return validi


def scrivi_ingredienti(ingredienti: Iterable[Mapping[str, Any]]) -> str | None:
    validi = leggi_ingredienti(list(ingredienti))
    return json.dumps(validi, ensure_ascii=False) if validi else None


def leggi_campi(testo: object) -> list[str]:
    """
    Campi calcolati dagli ingredienti, salvati come "fruttosio,glucosio".
    """
    return [c for c in (p.strip() for p in str(testo or "").split(",")) if c in CAMPI_FORNIBILI]


def _grammi(voce: Mapping[str, Any], alimento: Mapping[str, Any] | None) -> float:
    if voce["unita"] == "ml" and alimento and alimento.get("categoria") == "Grassi e Oli":
        return voce["quantita"] * DENSITA_OLI
    return voce["quantita"]


def _quota(parti: list[tuple[float, float | None]]) -> float | None:
    """
    Somma di (peso nel totale, valore o None): quota del valore sul totale
    noto, o None se il totale ignoto supera QUOTA_IGNOTA_MAX.
    """
    # math.fsum: stesso risultato su ogni versione di Python (vedi pasti_pronti._totale)
    noto = math.fsum(peso for peso, valore in parti if valore is not None)
    ignoto = math.fsum(peso for peso, valore in parti if valore is None)

    if noto <= 0 or ignoto / (noto + ignoto) > QUOTA_IGNOTA_MAX:
        return None

    return math.fsum(valore for _, valore in parti if valore is not None) / noto


def composizione(
    ingredienti: Iterable[Mapping[str, Any]], alimenti: Mapping[str, Mapping[str, Any]],
) -> dict[str, float | None]:
    """
    Quote dagli ingredienti: {"fruttosio": parte degli zuccheri, ...,
    "grassi_saturi": parte dei grassi}; None dove i dati non bastano.
    """
    abbinati = ingredienti_crea()
    zuccheri: dict[str, list[tuple[float, float | None]]] = {c: [] for c in CAMPI_ZUCCHERI}
    grassi: list[tuple[float, float | None]] = []

    for voce in ingredienti:
        codice = abbinati.get(voce["nome"])

        if codice == NESSUNO:
            continue

        alimento = alimenti.get(codice) if codice else None
        peso = _grammi(voce, alimento)

        if alimento is None:
            # Ingrediente non abbinato: zuccheri e grassi ignoti, pesati con la quantità
            for parti in zuccheri.values():
                parti.append((peso, None))
            grassi.append((peso, None))
            continue

        z = alimento.get("zuccheri")

        if z is None:
            z = alimento.get("carboidrati")   # al massimo tutti i carboidrati

        if z is None or z > 0:
            for campo, parti in zuccheri.items():
                valore = classificazioni.glucosio(alimento) if campo == "glucosio" else alimento.get(campo)
                parti.append((peso * (z if z is not None else 100) / 100,
                              None if valore is None or z is None else peso * valore / 100))

        g = alimento.get("grassi")

        if g is None or g > 0:
            saturi = alimento.get("grassi_saturi")
            grassi.append((peso * (g if g is not None else 100) / 100,
                           None if saturi is None or g is None else peso * saturi / 100))

    risultato = {campo: _quota(parti) for campo, parti in zuccheri.items()}
    risultato["grassi_saturi"] = _quota(grassi)
    return risultato


def completa(ricetta: MutableMapping[str, Any], alimenti: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """
    Riempie i campi mancanti della ricetta (fruttosio, glucosio, lattosio,
    grassi saturi) dagli ingredienti e ricalcola derivati, FODMAP misurati e
    rischi. Restituisce i campi calcolati.
    """
    ingredienti = leggi_ingredienti(ricetta.get("ingredienti"))

    if not ingredienti:
        return []

    gia = set(leggi_campi(ricetta.get("campi_ricetta")))
    quote = composizione(ingredienti, alimenti)
    calcolati = []

    for campo, quota in quote.items():
        base = ricetta.get("grassi" if campo == "grassi_saturi" else "zuccheri")

        if quota is None or base is None or (ricetta.get(campo) is not None and campo not in gia):
            continue

        ricetta[campo] = round(min(quota, 1) * base, 2)
        calcolati.append(campo)

    if calcolati:
        ricetta["campi_ricetta"] = ",".join(c for c in CAMPI_FORNIBILI if c in calcolati)

        for campo, livello in classificazioni.fodmap(dict(ricetta)).items():
            if livello is not None:
                ricetta[campo] = livello

        calcoli.completa_energia(ricetta, set(calcolati), nuovo=False)
        rischi.assegna(ricetta)

    return calcolati


def completa_tutte(alimenti: Mapping[str, MutableMapping[str, Any]]) -> int:
    """
    Calcola i campi delle ricette in {codice CREA: alimento}; due passaggi,
    perché un ingrediente può essere a sua volta una ricetta (es. besciamella).
    Restituisce il numero di ricette con almeno un campo calcolato.
    """
    ricette = [a for a in alimenti.values() if a.get("ingredienti")]
    completate = set()

    for _passaggio in range(2):
        for ricetta in ricette:
            if completa(ricetta, alimenti):
                completate.add(ricetta.get("codice_crea"))

    return len(completate)
