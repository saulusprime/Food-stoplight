"""
CoFID: McCance and Widdowson's Composition of Foods Integrated Dataset 2021
(Public Health England, Open Government Licence v3.0).

Serve per i valori che il CREA non pubblica, presi da un alimento simile
scelto a mano (dati/crea_cofid.csv):
- profilo degli zuccheri: fruttosio, glucosio e lattosio in proporzione agli
  zuccheri totali dell'alimento CoFID, riportati agli zuccheri del CREA
  (prodotti europei, senza lo sciroppo di mais dei prodotti USA); se il CREA
  non pubblica gli zuccheri totali si usano quelli USDA o, in mancanza,
  quelli CoFID (al massimo i carboidrati del CREA);
- grassi saturi come percentuale degli acidi grassi, lo stesso formato del
  CREA, convertiti con i grassi totali del CREA; dove CoFID dà solo i saturi
  per 100 g, in proporzione ai grassi dell'alimento CoFID.

In dati/cofid.csv ci sono solo gli alimenti CoFID usati; si rigenera dal
file Excel ufficiale con «flask cofid-estrai».
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

import classificazioni

FONTE = "McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID) 2021"
LICENZA = "Open Government Licence v3.0"
URL = "https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid"
URL_LICENZA = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

# Codici CoFID: gruppo e numero, es. 11-1145 o 13-076
CODICE_RE = re.compile(r"^\d{2}-\d{1,4}[A-Za-z]?$")

FILE_DATI = classificazioni.CARTELLA_DATI / "cofid.csv"
FILE_ABBINAMENTI = classificazioni.CARTELLA_DATI / "crea_cofid.csv"

# Gruppi di campi che si possono prendere da CoFID
ZUCCHERI = "zuccheri"
SATURI = "saturi"
GRUPPI = (ZUCCHERI, SATURI)
CAMPI_ZUCCHERI = ("fruttosio", "glucosio", "lattosio")
CAMPI_GRUPPO = {ZUCCHERI: CAMPI_ZUCCHERI, SATURI: ("grassi_saturi",)}
CAMPI_FORNIBILI = ("zuccheri", *CAMPI_ZUCCHERI, "grassi_saturi")

# Colonne del foglio «1.3 Proximates» -> colonne di dati/cofid.csv
COLONNE_EXCEL = {
    "Food Code": "codice",
    "Food Name": "nome",
    "Total sugars (g)": "zuccheri",
    "Glucose (g)": "glucosio",
    "Fructose (g)": "fruttosio",
    "Sucrose (g)": "saccarosio",
    "Maltose (g)": "maltosio",
    "Lactose (g)": "lattosio",
    "Fat (g)": "grassi",
    "Satd FA /100g FA (g)": "saturi_su_acidi",
    "Satd FA /100g fd (g)": "saturi",
}
COLONNE = tuple(COLONNE_EXCEL.values())
NUMERICHE = COLONNE[2:]


def numero(valore: object) -> float | None:
    """
    Valore CoFID: "Tr" (tracce) vale 0, "N" (non analizzato) o vuoto None.
    """
    testo = str(valore if valore is not None else "").strip()

    if testo.lower() == "tr":
        return 0.0

    try:
        return float(testo)
    except ValueError:
        return None


@cache
def alimenti() -> dict[str, dict[str, Any]]:
    """
    {codice CoFID: valori} da dati/cofid.csv.
    """
    if not FILE_DATI.is_file():
        return {}

    with FILE_DATI.open(encoding="utf-8", newline="") as f:
        return {
            riga["codice"]: {
                "codice": riga["codice"],
                "nome": riga["nome"],
                **{campo: numero(riga.get(campo)) for campo in NUMERICHE},
            }
            for riga in csv.DictReader(f)
            if riga.get("codice")
        }


@cache
def abbinamenti() -> dict[str, dict[str, str]]:
    """
    {codice CREA: {gruppo di campi: codice CoFID}} da dati/crea_cofid.csv (una
    riga per gruppo: zuccheri e saturi possono venire da alimenti diversi).
    """
    if not FILE_ABBINAMENTI.is_file():
        return {}

    with FILE_ABBINAMENTI.open(encoding="utf-8", newline="") as f:
        risultato: dict[str, dict[str, str]] = {}

        for riga in csv.DictReader(f):
            gruppo = (riga.get("campi") or "").strip()

            if riga.get("codice_crea") and riga.get("codice_cofid") and gruppo in GRUPPI:
                risultato.setdefault(riga["codice_crea"], {})[gruppo] = riga["codice_cofid"].strip()

        return risultato


def leggi_codici(testo: object) -> list[str]:
    """
    Codici CoFID salvati come "11-1145" o "11-1145,13-076" (solo quelli validi).
    """
    return [c for c in (p.strip() for p in str(testo or "").split(",")) if CODICE_RE.match(c)]


def zuccheri_totali(alimento: Mapping[str, Any], carboidrati: float | None) -> float | None:
    """
    Zuccheri totali dell'alimento CoFID, per un alimento CREA che non li
    pubblica: al massimo i carboidrati del CREA.
    """
    zuccheri = alimento.get("zuccheri")

    if zuccheri is None:
        return None

    return round(min(zuccheri, carboidrati) if carboidrati is not None else zuccheri, 2)


def profilo_zuccheri(alimento: Mapping[str, Any], zuccheri: float | None) -> dict[str, float | None]:
    """
    Fruttosio, glucosio e lattosio per gli zuccheri totali indicati, con le
    proporzioni dell'alimento CoFID. Senza zuccheri confrontabili: niente.
    """
    totale = alimento.get("zuccheri")

    if zuccheri is None or not totale or totale <= 0:
        return {}

    if alimento.get("fruttosio") is None or alimento.get("glucosio") is None:
        return {}

    return {
        campo: None if alimento.get(campo) is None else round(min(alimento[campo] / totale, 1) * zuccheri, 2)
        for campo in CAMPI_ZUCCHERI
    }


def saturi(alimento: Mapping[str, Any], grassi: float | None, fattore: float) -> float | None:
    """
    Grassi saturi (g/100 g) dai grassi totali, dal fattore di conversione in
    acidi grassi (FAO/INFOODS, lo stesso del CREA) e dalla percentuale CoFID.
    Senza la percentuale: con la quota dei saturi sui grassi dell'alimento
    CoFID (saturi per 100 g diviso grassi per 100 g).
    """
    if grassi is None:
        return None

    percentuale = alimento.get("saturi_su_acidi")

    if percentuale is not None:
        return round(min(grassi * fattore * percentuale / 100, grassi), 2)

    saturi_cofid = alimento.get("saturi")
    grassi_cofid = alimento.get("grassi")

    if saturi_cofid is None or not grassi_cofid or grassi_cofid <= 0:
        return None

    return round(min(grassi * saturi_cofid / grassi_cofid, grassi), 2)


def descrizione(alimento: Mapping[str, Any]) -> str:
    return f"CoFID 2021 · {alimento['codice']} {alimento['nome']}"


def leggi_campi(testo: object) -> list[str]:
    """
    Campi presi da CoFID salvati come "fruttosio,glucosio" (solo quelli validi).
    """
    return [c for c in (p.strip() for p in str(testo or "").split(",")) if c in CAMPI_FORNIBILI]


def estrai_excel(percorso: Path, codici: Iterable[str]) -> list[dict[str, Any]]:
    """
    Righe per dati/cofid.csv dal file Excel ufficiale di CoFID 2021 (foglio
    «1.3 Proximates»), solo per i codici indicati, con i valori come nel file.
    """
    from openpyxl import load_workbook

    voluti = set(codici)
    libro = load_workbook(percorso, read_only=True, data_only=True)

    try:
        righe = libro["1.3 Proximates"].iter_rows(values_only=True)
        intestazione = [str(c).strip() if c is not None else "" for c in next(righe)]
        indici = {COLONNE_EXCEL[nome]: i for i, nome in enumerate(intestazione) if nome in COLONNE_EXCEL}
        mancanti = set(COLONNE) - set(indici)

        if mancanti:
            raise ValueError(f"Colonne CoFID non trovate: {', '.join(sorted(mancanti))}")

        estratti = []

        for riga in righe:
            codice = str(riga[indici["codice"]] or "").strip()

            if codice in voluti:
                estratti.append({
                    colonna: "" if riga[i] is None else str(riga[i]).strip()
                    for colonna, i in indici.items()
                })

        return sorted(estratti, key=lambda r: r["codice"])
    finally:
        libro.close()


def scrivi_dati(righe: Iterable[Mapping[str, Any]], percorso: Path = FILE_DATI) -> None:
    with percorso.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.DictWriter(f, fieldnames=COLONNE)
        scrittore.writeheader()
        scrittore.writerows(righe)

    alimenti.cache_clear()
