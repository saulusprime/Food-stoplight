"""
Ciqual 2025: Table de composition nutritionnelle des aliments (Anses,
Licence Ouverte / Open Licence 2.0 Etalab).

Come CoFID (cofid.py), serve per i valori che il CREA non pubblica, presi da
un alimento scelto a mano (dati/crea_ciqual.csv), dove CoFID non ha un
alimento comparabile o non ne ha i dati: è la tabella francese, con molti
alimenti e piatti della cucina mediterranea e frattaglie analizzate.
- profilo degli zuccheri: fruttosio, glucosio e lattosio in proporzione agli
  zuccheri totali dell'alimento Ciqual, riportati agli zuccheri del CREA (se
  il CREA non li pubblica, a quelli USDA o, in mancanza, a quelli Ciqual, al
  massimo i carboidrati del CREA);
- grassi saturi in proporzione ai grassi: quota dei saturi sui grassi
  dell'alimento Ciqual, applicata ai grassi del CREA.

Valori Ciqual: «-» non disponibile, «traces» 0, «< x» sotto il limite di
quantificazione. Sotto il limite si usa una stima prudente per il rischio
malassorbimento: il fruttosio vale il limite, ma non più degli zuccheri
non spiegati dagli altri zuccheri misurati; glucosio e lattosio valgono 0; i
grassi saturi valgono il limite.

In dati/ciqual.csv ci sono solo gli alimenti Ciqual usati; si rigenera dal
file Excel ufficiale con «flask ciqual-estrai».
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

import classificazioni

FONTE = "Anses, Table de composition nutritionnelle des aliments Ciqual 2025"
LICENZA = "Licence Ouverte / Open Licence 2.0 (Etalab)"
URL = "https://ciqual.anses.fr/"
URL_DATI = "https://doi.org/10.57745/RDMHWY"
URL_LICENZA = "https://www.etalab.gouv.fr/licence-ouverte-open-licence/"

# Codici Ciqual: numeri (alim_code), es. 24006 o 7719
CODICE_RE = re.compile(r"^\d{3,6}$")

FILE_DATI = classificazioni.CARTELLA_DATI / "ciqual.csv"
FILE_ABBINAMENTI = classificazioni.CARTELLA_DATI / "crea_ciqual.csv"

# Gruppi di campi che si possono prendere da Ciqual (come CoFID)
ZUCCHERI = "zuccheri"
SATURI = "saturi"
GRUPPI = (ZUCCHERI, SATURI)
CAMPI_ZUCCHERI = ("fruttosio", "glucosio", "lattosio")
CAMPI_FORNIBILI = ("zuccheri", *CAMPI_ZUCCHERI, "grassi_saturi")

# Inizio dell'intestazione nel foglio «composition nutritionnelle» (le
# intestazioni vanno a capo: «Sucres\n(g\n100 g)») -> colonne di dati/ciqual.csv
COLONNE_EXCEL = {
    "alim_code": "codice",
    "alim_nom_fr": "nome",
    "Sucres": "zuccheri",
    "Fructose": "fruttosio",
    "Galactose": "galattosio",
    "Glucose": "glucosio",
    "Lactose": "lattosio",
    "Maltose": "maltosio",
    "Saccharose": "saccarosio",
    "Lipides": "grassi",
    "AG saturés": "saturi",
}
COLONNE = tuple(COLONNE_EXCEL.values())
NUMERICHE = COLONNE[2:]

# Zuccheri semplici misurati, per il fruttosio sotto il limite
ZUCCHERI_SEMPLICI = ("glucosio", "galattosio", "lattosio", "maltosio", "saccarosio")


def valore(testo: object) -> tuple[float | None, bool]:
    """
    (numero, sotto il limite di quantificazione) da un valore Ciqual:
    «0,3» -> (0.3, False), «< 0,2» -> (0.2, True), «traces» -> (0.0, False),
    «-» o vuoto -> (None, False).
    """
    pulito = " ".join(str(testo if testo is not None else "").split()).lower()
    sotto = pulito.startswith("<")

    if sotto:
        pulito = pulito[1:].strip()

    if pulito == "traces":
        return 0.0, False

    try:
        return float(pulito.replace(",", ".")), sotto
    except ValueError:
        return None, False


def normalizza(testo: object) -> str:
    """
    Valore come in dati/ciqual.csv: spazi compattati, punto decimale («< 0.2»).
    """
    pulito = " ".join(str(testo if testo is not None else "").split())
    return re.sub(r"(\d),(\d)", r"\1.\2", pulito)


@cache
def alimenti() -> dict[str, dict[str, Any]]:
    """
    {codice Ciqual: valori come nel file (testo)} da dati/ciqual.csv.
    """
    if not FILE_DATI.is_file():
        return {}

    with FILE_DATI.open(encoding="utf-8", newline="") as f:
        return {
            riga["codice"]: {colonna: riga.get(colonna) or "" for colonna in COLONNE}
            for riga in csv.DictReader(f)
            if riga.get("codice")
        }


@cache
def abbinamenti() -> dict[str, dict[str, str]]:
    """
    {codice CREA: {gruppo di campi: codice Ciqual}} da dati/crea_ciqual.csv
    (una riga per gruppo, come per CoFID).
    """
    if not FILE_ABBINAMENTI.is_file():
        return {}

    with FILE_ABBINAMENTI.open(encoding="utf-8", newline="") as f:
        risultato: dict[str, dict[str, str]] = {}

        for riga in csv.DictReader(f):
            gruppo = (riga.get("campi") or "").strip()

            if riga.get("codice_crea") and riga.get("codice_ciqual") and gruppo in GRUPPI:
                risultato.setdefault(riga["codice_crea"], {})[gruppo] = riga["codice_ciqual"].strip()

        return risultato


def leggi_codici(testo: object) -> list[str]:
    """
    Codici Ciqual salvati come "24006" o "24006,7719" (solo quelli validi).
    """
    return [c for c in (p.strip() for p in str(testo or "").split(",")) if CODICE_RE.match(c)]


def leggi_campi(testo: object) -> list[str]:
    """
    Campi presi da Ciqual salvati come "fruttosio,glucosio" (solo quelli validi).
    """
    return [c for c in (p.strip() for p in str(testo or "").split(",")) if c in CAMPI_FORNIBILI]


def zuccheri_totali(alimento: Mapping[str, Any], carboidrati: float | None) -> float | None:
    """
    Zuccheri totali dell'alimento Ciqual, per un alimento CREA che non li
    pubblica: al massimo i carboidrati del CREA (non sotto il limite).
    """
    zuccheri, sotto = valore(alimento.get("zuccheri"))

    if zuccheri is None or sotto:
        return None

    return round(min(zuccheri, carboidrati) if carboidrati is not None else zuccheri, 2)


def composizione_zuccheri(alimento: Mapping[str, Any]) -> dict[str, float | None] | None:
    """
    Fruttosio, glucosio e lattosio dell'alimento Ciqual (g/100 g) con la stima
    prudente per i valori sotto il limite; None senza zuccheri totali positivi
    o senza fruttosio e glucosio.
    """
    totale, totale_sotto = valore(alimento.get("zuccheri"))

    if totale is None or totale_sotto or totale <= 0:
        return None

    letti = {campo: valore(alimento.get(campo)) for campo in ("fruttosio", *ZUCCHERI_SEMPLICI)}

    if letti["fruttosio"][0] is None or letti["glucosio"][0] is None:
        return None

    misurati = sum(numero for campo, (numero, sotto) in letti.items()
                   if campo != "fruttosio" and numero is not None and not sotto)
    fruttosio, fruttosio_sotto = letti["fruttosio"]
    assert fruttosio is not None

    if fruttosio_sotto:
        # Al massimo il limite, e non più degli zuccheri non spiegati dagli altri
        fruttosio = min(fruttosio, max(totale - misurati, 0.0))

    def altro(campo: str) -> float | None:
        numero, sotto = letti[campo]
        return 0.0 if sotto else numero

    return {"totale": totale, "fruttosio": fruttosio, "glucosio": altro("glucosio"), "lattosio": altro("lattosio")}


def profilo_zuccheri(alimento: Mapping[str, Any], zuccheri: float | None) -> dict[str, float | None]:
    """
    Fruttosio, glucosio e lattosio per gli zuccheri totali indicati, con le
    proporzioni dell'alimento Ciqual. Senza zuccheri confrontabili: niente.
    """
    composizione = composizione_zuccheri(alimento)

    if zuccheri is None or composizione is None:
        return {}

    totale = composizione["totale"]
    assert totale is not None
    risultato: dict[str, float | None] = {}

    for campo in CAMPI_ZUCCHERI:
        parte = composizione[campo]
        risultato[campo] = None if parte is None else round(min(parte / totale, 1) * zuccheri, 2)

    return risultato


def saturi(alimento: Mapping[str, Any], grassi: float | None) -> float | None:
    """
    Grassi saturi (g/100 g) dai grassi totali, con la quota dei saturi sui
    grassi dell'alimento Ciqual (saturi sotto il limite: il limite).
    """
    grassi_ciqual, grassi_sotto = valore(alimento.get("grassi"))
    saturi_ciqual, _sotto = valore(alimento.get("saturi"))

    if grassi is None or saturi_ciqual is None or grassi_ciqual is None or grassi_sotto or grassi_ciqual <= 0:
        return None

    return round(min(grassi * saturi_ciqual / grassi_ciqual, grassi), 2)


def descrizione(alimento: Mapping[str, Any]) -> str:
    return f"Ciqual 2025 · {alimento['codice']} {alimento['nome']}"


def _colonna(intestazione: object) -> str | None:
    testo = " ".join(str(intestazione or "").split())
    return next((colonna for inizio, colonna in COLONNE_EXCEL.items()
                 if testo == inizio or testo.startswith(inizio + " ") or testo.startswith(inizio + ",")), None)


def estrai_excel(percorso: Path, codici: Iterable[str]) -> list[dict[str, Any]]:
    """
    Righe per dati/ciqual.csv dal file Excel ufficiale di Ciqual 2025 (foglio
    «composition nutritionnelle»), solo per i codici indicati, con i valori
    come nel file (punto decimale).
    """
    from openpyxl import load_workbook

    voluti = set(codici)
    libro = load_workbook(percorso, read_only=True, data_only=True)

    try:
        righe = libro["composition nutritionnelle"].iter_rows(values_only=True)
        indici: dict[str, int] = {}

        for i, intestazione in enumerate(next(righe)):
            colonna = _colonna(intestazione)

            if colonna and colonna not in indici:
                indici[colonna] = i

        mancanti = set(COLONNE) - set(indici)

        if mancanti:
            raise ValueError(f"Colonne Ciqual non trovate: {', '.join(sorted(mancanti))}")

        estratti = []

        for riga in righe:
            codice = normalizza(riga[indici["codice"]])

            if codice in voluti:
                estratti.append({colonna: normalizza(riga[i]) for colonna, i in indici.items()})

        return sorted(estratti, key=lambda r: int(r["codice"]))
    finally:
        libro.close()


def scrivi_dati(righe: Iterable[Mapping[str, Any]], percorso: Path = FILE_DATI) -> None:
    with percorso.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.DictWriter(f, fieldnames=COLONNE)
        scrittore.writeheader()
        scrittore.writerows(righe)

    alimenti.cache_clear()
