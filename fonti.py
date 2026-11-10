"""
Alimenti dalle fonti esterne: CREA (con i nutrienti mancanti da CoFID, USDA
e, per le ricette, dagli ingredienti), Open Food Facts e USDA FoodData Central.

Ogni alimento costruito da una fonte passa da completa(): classificazioni
documentate (NOVA, FODMAP, indice glicemico), energia derivata (TEF, Kcal
nette, rapporto F/F) e livelli di rischio calcolati.

Per i valori che il CREA non pubblica, in quest'ordine:
1. CoFID 2021 (dati/crea_cofid.csv): profilo degli zuccheri di prodotti
   europei e grassi saturi come percentuale degli acidi grassi (cofid.py);
   il profilo si applica agli zuccheri totali del CREA, altrimenti a quelli
   USDA, altrimenti a quelli CoFID;
2. USDA FoodData Central (dati/crea_usda.csv): gli altri campi mancanti;
3. ricette CREA: fruttosio, glucosio, lattosio e saturi dagli ingredienti
   (ricette.py), calcolati dopo aver costruito tutti gli alimenti.
Gli abbinamenti sono scelti alimento per alimento.
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

import calcoli
import classificazioni
import cofid
import crea
import importazione
import openfoodfacts
import ricette
import rischi
import usda

FILE_ABBINAMENTI = classificazioni.CARTELLA_DATI / "crea_usda.csv"

# Zuccheri semplici: se gli zuccheri totali sono 0, sono 0 anche loro
ZUCCHERI_SEMPLICI = ("fruttosio", "glucosio", "lattosio")

# Campi derivati o di sistema che non vengono dalle fonti
CAMPI_DERIVATI = ("tef_kcal", "tef_percent", "kcal_nette", "rapporto")

# Categorie USDA (foodCategory) -> categorie dell'app
CATEGORIE_USDA = {
    "Fruits and Fruit Juices": "Frutta",
    "Vegetables and Vegetable Products": "Verdura",
    "Dairy and Egg Products": "Latticini e Uova",
    "Beef Products": "Carne",
    "Pork Products": "Carne",
    "Lamb, Veal, and Game Products": "Carne",
    "Poultry Products": "Carne",
    "Sausages and Luncheon Meats": "Carne",
    "Finfish and Shellfish Products": "Pesce",
    "Cereal Grains and Pasta": "Cereali",
    "Baked Products": "Cereali",
    "Breakfast Cereals": "Cereali",
    "Legumes and Legume Products": "Legumi/Frutta Secca",
    "Nut and Seed Products": "Legumi/Frutta Secca",
    "Fats and Oils": "Grassi e Oli",
    "Sweets": "Dolci e Snack",
    "Snacks": "Dolci e Snack",
    "Beverages": "Bevande",
    "Meals, Entrees, and Side Dishes": "Piatti e ricette",
    "Soups, Sauces, and Gravies": "Piatti e ricette",
}


class ErroreFonte(Exception):
    pass


# ---------------------------------------------------------------
# ABBINAMENTI CREA -> USDA
# ---------------------------------------------------------------

@cache
def abbinamenti() -> dict[str, int]:
    """
    {codice CREA: FDC ID} da dati/crea_usda.csv.
    """
    if not FILE_ABBINAMENTI.is_file():
        return {}

    with FILE_ABBINAMENTI.open(encoding="utf-8", newline="") as f:
        return {
            riga["codice_crea"]: int(riga["fdc_id"])
            for riga in csv.DictReader(f)
            if riga.get("codice_crea") and (riga.get("fdc_id") or "").isdigit()
        }


# ---------------------------------------------------------------
# COSTRUZIONE DEGLI ALIMENTI
# ---------------------------------------------------------------

def completa(valori: dict[str, Any], altri: Mapping[str, float | None] | None = None) -> dict[str, Any]:
    """
    Alimento completo per il database: tutti i campi (vuoti = non disponibili),
    classificazioni, energia derivata e rischi.
    """
    v: dict[str, Any] = dict(importazione.VUOTO)
    v.update({campo: valore for campo, valore in valori.items() if campo in importazione.CAMPI})

    for campo, valore in classificazioni.classifica(v, dict(altri or {})).items():
        if v.get(campo) is None:
            v[campo] = valore

    forniti = {campo for campo, valore in valori.items() if valore is not None and campo not in CAMPI_DERIVATI}
    calcoli.completa_energia(v, forniti, nuovo=True)
    rischi.assegna(v)
    return v


def scala_zuccheri(da_usda: dict[str, float], zuccheri: float | None) -> dict[str, float]:
    """
    Fruttosio, glucosio e lattosio USDA riportati agli zuccheri totali
    dell'alimento: si tiene la proporzione di ciascuno sugli zuccheri
    dell'alimento USDA (es. fichi freschi CREA con il profilo dei fichi
    secchi USDA). Senza zuccheri confrontabili restano i valori USDA.
    """
    zuccheri_usda = da_usda.get("zuccheri")

    if not zuccheri or not zuccheri_usda or zuccheri_usda <= 0:
        return da_usda

    fattore = zuccheri / zuccheri_usda
    scalati = dict(da_usda)

    for campo in ZUCCHERI_SEMPLICI:
        if da_usda.get(campo) is not None:
            scalati[campo] = round(min(da_usda[campo] * fattore, zuccheri), 2)

    return scalati


def regole_zuccheri(valori: dict[str, Any], categoria_crea: str, nome: str) -> None:
    """
    Zuccheri semplici noti per composizione (solo dove mancano): senza zuccheri
    sono 0; negli alimenti di origine animale non c'è fruttosio né lattosio;
    nel latte e nei latticini non zuccherati gli zuccheri sono lattosio.
    """
    if valori.get("zuccheri") is None and valori.get("carboidrati") == 0:
        valori["zuccheri"] = 0.0

    zuccheri = valori.get("zuccheri")

    if zuccheri == 0:
        for campo in ZUCCHERI_SEMPLICI:
            valori.setdefault(campo, 0.0)
    elif categoria_crea in crea.CATEGORIE_ANIMALI:
        valori.setdefault("fruttosio", 0.0)
        valori.setdefault("lattosio", 0.0)
    elif categoria_crea in crea.CATEGORIE_LATTICINI and not classificazioni.LATTICINI_DOLCI_RE.search(nome):
        valori.setdefault("fruttosio", 0.0)

        if zuccheri is not None:
            valori.setdefault("lattosio", float(zuccheri))


def da_cofid(valori: dict[str, Any], scheda: Mapping[str, Any]) -> tuple[list[str], set[str]]:
    """
    Valori mancanti dall'alimento CoFID abbinato alla scheda CREA: profilo
    degli zuccheri e grassi saturi. Restituisce (campi presi, campi riservati):
    i riservati non si prendono da USDA, perché un profilo degli zuccheri
    mescolato da due fonti non sarebbe coerente.
    """
    gruppi = cofid.abbinamenti().get(scheda["codice"], {})
    presi: list[str] = []
    riservati: set[str] = set()
    usati: list[str] = []

    zuccheri = cofid.alimenti().get(gruppi.get(cofid.ZUCCHERI, ""))

    if zuccheri and valori.get("zuccheri") is None:
        # Né il CREA né USDA pubblicano gli zuccheri totali: quelli CoFID
        totale = cofid.zuccheri_totali(zuccheri, valori.get("carboidrati"))

        if totale is not None:
            valori["zuccheri"] = totale
            presi.append("zuccheri")
            riservati.add("zuccheri")

    if zuccheri and any(valori.get(c) is None for c in cofid.CAMPI_ZUCCHERI):
        profilo = cofid.profilo_zuccheri(zuccheri, valori.get("zuccheri"))

        for campo, valore in profilo.items():
            if valori.get(campo) is None:
                riservati.add(campo)

                if valore is not None:
                    valori[campo] = valore
                    presi.append(campo)

        if profilo or "zuccheri" in presi:
            usati.append(zuccheri["codice"])

    saturi = cofid.alimenti().get(gruppi.get(cofid.SATURI, ""))

    if saturi and valori.get("grassi_saturi") is None:
        valore = cofid.saturi(saturi, valori.get("grassi"), crea.fattore_acidi_grassi(dict(scheda)))

        if valore is not None:
            valori["grassi_saturi"] = valore
            presi.append("grassi_saturi")
            riservati.add("grassi_saturi")
            usati.append(saturi["codice"])

    if presi:
        valori["codice_cofid"] = ",".join(dict.fromkeys(usati))
        valori["campi_cofid"] = ",".join(c for c in cofid.CAMPI_FORNIBILI if c in presi)

    return presi, riservati


def da_crea(scheda: Mapping[str, Any], alimento_usda: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """
    Alimento da una scheda CREA; i nutrienti che il CREA non pubblica si
    prendono dall'alimento CoFID abbinato (elencati in campi_cofid), poi da
    quello USDA (in campi_usda). Le ricette portano con sé gli ingredienti.
    """
    valori = crea.valori(dict(scheda))
    regole_zuccheri(valori, scheda["categoria"], scheda["nome"])
    fonti = [crea.FONTE]
    da_usda = usda.valori(alimento_usda) if alimento_usda else {}
    presi: set[str] = set()

    if valori.get("zuccheri") is None and da_usda.get("zuccheri") is not None:
        # Zuccheri totali da USDA prima di CoFID, perché il profilo CoFID si applichi a questi
        valori["zuccheri"] = da_usda["zuccheri"]
        presi.add("zuccheri")

    presi_cofid, riservati = da_cofid(valori, scheda)

    if presi_cofid:
        fonti.extend(cofid.descrizione(cofid.alimenti()[c]) for c in cofid.leggi_codici(valori["codice_cofid"]))

    if alimento_usda:
        da_usda = scala_zuccheri(da_usda, valori.get("zuccheri"))

        for campo in usda.CAMPI_FORNIBILI:
            if campo not in riservati and valori.get(campo) is None and da_usda.get(campo) is not None:
                valori[campo] = da_usda[campo]
                presi.add(campo)

        if valori.get("grassi_saturi") is not None and valori.get("grassi") is not None:
            valori["grassi_saturi"] = min(valori["grassi_saturi"], valori["grassi"])

        valori["fdc_id"] = int(alimento_usda["fdcId"])
        valori["campi_usda"] = ",".join(c for c in usda.CAMPI_FORNIBILI if c in presi) or None

        if presi:
            fonti.append(usda.descrizione(alimento_usda))

    valori["fonte_nutrienti"] = "; ".join(fonti)
    valori["ingredienti"] = ricette.scrivi_ingredienti(scheda.get("ingredienti") or [])

    altri = {
        chiave: scheda["valori"].get(etichetta)
        for etichetta, chiave in crea.ALTRI.items()
        if chiave in ("fos", "raffinosio")
    }

    return completa(valori, altri)


def da_openfoodfacts(prodotto: Mapping[str, Any]) -> dict[str, Any]:
    return completa(openfoodfacts.valori(prodotto))


def da_usda(alimento_usda: Mapping[str, Any]) -> dict[str, Any]:
    """
    Alimento solo USDA (nome inglese della banca dati): tutti i nutrienti da USDA.
    """
    fdc_id = int(alimento_usda["fdcId"])
    categoria = alimento_usda.get("foodCategory")

    if isinstance(categoria, Mapping):
        categoria = categoria.get("description")

    valori: dict[str, Any] = {
        **usda.valori(alimento_usda),
        "alimento": str(alimento_usda.get("description") or fdc_id),
        "categoria": CATEGORIE_USDA.get(str(categoria or ""), crea.CATEGORIA_PREDEFINITA),
        "fdc_id": fdc_id,
        "fonte_nutrienti": usda.descrizione(alimento_usda),
        "url_fonte": usda.url_scheda(fdc_id),
    }

    return completa(valori)


def cerca(fonte: str, codice: str, api_key: str | None = None) -> dict[str, Any]:
    """
    Alimento da una fonte per il form: "crea" (codice CREA), "off" (codice a
    barre) o "usda" (FDC ID). Solleva ErroreFonte con un messaggio da mostrare.
    """
    codice = (codice or "").strip()

    try:
        if fonte == "crea":
            codice = codice.upper()

            if not crea.CODICE_RE.match(codice):
                raise ErroreFonte("Codice CREA non valido: servono 6 caratteri (es. 007000).")

            schede, errori = crea.scarica_schede([codice])

            if not schede:
                raise ErroreFonte(errori[0] if errori else f"Scheda CREA {codice} non trovata.")

            fdc_id = abbinamenti().get(codice)
            alimento_usda = None

            if fdc_id:
                alimento_usda = usda.scarica(api_key or usda.CHIAVE_DEMO, [fdc_id]).get(fdc_id)

            return da_crea(schede[0], alimento_usda)

        if fonte == "off":
            return da_openfoodfacts(openfoodfacts.scarica(codice))

        if fonte == "usda":
            if not codice.isdigit():
                raise ErroreFonte("FDC ID non valido: serve un numero.")

            trovato = usda.scarica(api_key or usda.CHIAVE_DEMO, [int(codice)]).get(int(codice))

            if not trovato:
                raise ErroreFonte(f"Alimento USDA {codice} non trovato.")

            return da_usda(trovato)
    except (crea.ErroreCrea, openfoodfacts.ErroreOpenFoodFacts, usda.ErroreUsda) as exc:
        raise ErroreFonte(str(exc)) from None

    raise ErroreFonte(f"Fonte sconosciuta: {fonte}")


# ---------------------------------------------------------------
# SCRITTURA NEL DATABASE
# ---------------------------------------------------------------

def _diversi(nuovo: Mapping[str, Any], vecchio: Mapping[str, Any]) -> list[str]:
    return [c for c in importazione.CAMPI if importazione._diverso(nuovo.get(c), vecchio.get(c), c)]


def scrivi(conn: sqlite3.Connection, alimenti: Iterable[dict[str, Any]], adesso: str,
           chiave: str = "codice_crea") -> dict[str, int]:
    """
    Inserisce o aggiorna (stesso codice della fonte) gli alimenti; non fa commit.
    Restituisce i conteggi {nuovi, aggiornati, invariati}.
    """
    esistenti = {
        r[chiave]: dict(r)
        for r in conn.execute(f"SELECT id, {', '.join(importazione.CAMPI)} FROM alimenti WHERE {chiave} IS NOT NULL")
    }
    colonne = (*importazione.CAMPI, "aggiornato_il")
    conteggi = {"nuovi": 0, "aggiornati": 0, "invariati": 0}

    for alimento in alimenti:
        precedente = esistenti.get(alimento.get(chiave))

        if precedente is None:
            conn.execute(
                f"INSERT INTO alimenti ({', '.join(colonne)}) VALUES ({', '.join('?' for _ in colonne)})",
                [alimento.get(c) for c in importazione.CAMPI] + [adesso],
            )
            conteggi["nuovi"] += 1
        elif _diversi(alimento, precedente):
            conn.execute(
                f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in colonne)} WHERE id = ?",
                [alimento.get(c) for c in importazione.CAMPI] + [adesso, precedente["id"]],
            )
            conteggi["aggiornati"] += 1
        else:
            conteggi["invariati"] += 1

    return conteggi


def importa_crea(
    conn: sqlite3.Connection,
    codici: Iterable[str],
    adesso: str,
    api_key: str | None = None,
    cache_pagine: Path | None = None,
    sostituisci: bool = False,
    avanzamento: Callable[[str], object] | None = None,
) -> dict[str, Any]:
    """
    Importa (o aggiorna) gli alimenti CREA indicati, con i valori USDA degli
    abbinamenti. Con sostituisci elimina prima gli alimenti senza codice CREA.
    Non fa commit. Restituisce conteggi ed errori.
    """
    def avvisa(testo: str) -> None:
        if avanzamento:
            avanzamento(testo)

    schede, errori = crea.scarica_schede(
        codici, cache=cache_pagine,
        avanzamento=lambda n, totale: avvisa(f"CREA {n}/{totale}") if n % 50 == 0 or n == totale else None,
    )

    ids = [abbinamenti()[s["codice"]] for s in schede if s["codice"] in abbinamenti()]
    dati_usda: dict[int, dict[str, Any]] = {}

    if ids:
        try:
            dati_usda = usda.scarica(api_key or usda.CHIAVE_DEMO, ids,
                                     avanzamento=lambda n, totale: avvisa(f"USDA {n}/{totale}"))
        except usda.ErroreUsda as exc:
            errori.append(f"USDA: {exc} (fruttosio e altri valori USDA non aggiornati)")

    alimenti = [da_crea(s, dati_usda.get(abbinamenti().get(s["codice"], 0))) for s in schede]

    eliminati = 0

    if sostituisci and alimenti:
        eliminati = conn.execute("DELETE FROM alimenti WHERE codice_crea IS NULL").rowcount

    conteggi = scrivi(conn, alimenti, adesso)
    ricalcolate = ricalcola_ricette(conn, adesso)
    return {**conteggi, "eliminati": eliminati, "errori": errori, "letti": len(schede), "ricette": ricalcolate}


def sincronizza_usda(
    conn: sqlite3.Connection, api_key: str, adesso: str,
    avanzamento: Callable[[str], object] | None = None,
) -> int:
    """
    Aggiorna da USDA i campi presi da USDA degli alimenti con FDC ID e
    ricalcola derivati, FODMAP misurati e rischi. Non fa commit.
    Restituisce il numero di alimenti aggiornati.
    """
    righe = usda.righe_da_sincronizzare(conn)

    if not righe:
        return 0

    dati = usda.scarica(
        api_key, [r["fdc_id"] for r in righe],
        avanzamento=lambda n, totale: avanzamento(f"USDA {n}/{totale}") if avanzamento else None,
    )
    aggiornati = []

    for riga in righe:
        alimento_usda = dati.get(int(riga["fdc_id"]))

        if not alimento_usda:
            continue

        v = dict(riga)
        campi = usda.campi_da_aggiornare(riga)
        nuovi = usda.valori(alimento_usda)

        if "zuccheri" not in campi:
            # Zuccheri da un'altra fonte (CREA): fruttosio e glucosio in proporzione
            nuovi = scala_zuccheri(nuovi, v.get("zuccheri"))

        cambiati = set()

        for campo in campi:
            if campo in nuovi and importazione._diverso(nuovi[campo], v.get(campo), campo):
                v[campo] = nuovi[campo]
                cambiati.add(campo)

        if not cambiati:
            continue

        for campo, livello in classificazioni.fodmap(v).items():
            if livello is not None:
                v[campo] = livello

        calcoli.completa_energia(v, cambiati, nuovo=False)
        rischi.assegna(v)
        aggiornati.append(v)

    colonne = (*importazione.CAMPI, "aggiornato_il")

    for v in aggiornati:
        conn.execute(
            f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in colonne)} WHERE id = ?",
            [v.get(c) for c in importazione.CAMPI] + [adesso, v["id"]],
        )

    # Gli ingredienti possono essere cambiati: si ricalcolano le ricette
    if aggiornati:
        ricalcola_ricette(conn, adesso)

    return len(aggiornati)


def ricalcola_ricette(conn: sqlite3.Connection, adesso: str) -> int:
    """
    Ricalcola dagli ingredienti i campi delle ricette CREA (fruttosio,
    glucosio, lattosio, grassi saturi che il CREA non pubblica), con
    derivati e rischi; non fa commit. Restituisce le ricette cambiate.
    """
    righe = {r["codice_crea"]: dict(r) for r in conn.execute("SELECT * FROM alimenti WHERE codice_crea IS NOT NULL")}
    prima = {codice: dict(r) for codice, r in righe.items() if r.get("ingredienti")}
    ricette.completa_tutte(righe)
    colonne = (*importazione.CAMPI, "aggiornato_il")
    cambiate = 0

    for codice, vecchia in prima.items():
        nuova = righe[codice]

        if _diversi(nuova, vecchia):
            conn.execute(
                f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in colonne)} WHERE id = ?",
                [nuova.get(c) for c in importazione.CAMPI] + [adesso, nuova["id"]],
            )
            cambiate += 1

    return cambiate


def ricalcola_rischi(conn: sqlite3.Connection, adesso: str) -> int:
    """
    Ricalcola i livelli di rischio di tutti gli alimenti; non fa commit.
    """
    cambiati = 0

    for riga in conn.execute("SELECT * FROM alimenti").fetchall():
        v = dict(riga)
        prima = {c: v.get(c) for c in rischi.REGOLE}
        rischi.assegna(v)

        if any((v[c] or "") != (prima[c] or "") for c in rischi.REGOLE):
            conn.execute(
                f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in rischi.REGOLE)}, aggiornato_il = ? WHERE id = ?",
                [v[c] for c in rischi.REGOLE] + [adesso, v["id"]],
            )
            cambiati += 1

    return cambiati
