"""
Pasti pronti: ricette italiane convertite negli alimenti dell'app, con i
grammi di ogni ingrediente.

I dati sono in dati/pasti_pronti.csv (una riga per ricetta: nome, portata,
porzioni, fonte) e dati/pasti_pronti_ingredienti.csv (una riga per
ingrediente: testo della fonte, codice CREA dell'alimento, grammi crudi per
l'intera ricetta, resa in cottura). «flask pasti-importa» li carica nelle
tabelle pasti_pronti e pasti_pronti_ingredienti; ogni ricetta diventa anche
un piatto della categoria «Piatti e ricette», con i valori per 100 g
calcolati qui (fonti.aggiorna_pasti_pronti li scrive).

Calcolo delle ricette (EuroFIR): si sommano i nutrienti degli ingredienti
crudi e si dividono per il peso del piatto cotto, cioè la somma dei grammi
per la resa di ciascun ingrediente (pasta e riso assorbono acqua, carni e
verdure ne perdono). L'alcol del vino in cottura si riduce al 35% (USDA,
Table of Nutrient Retention Factors, Release 6, 2007: 30 minuti di
cottura). Il sale aggiunto non è conteggiato: tra gli alimenti CREA non c'è.

Un valore resta non disponibile se gli ingredienti senza quel dato portano
più del 5% del totale (dello stesso riferimento usato per le ricette CREA:
zuccheri per fruttosio, glucosio e lattosio, grassi per saturi e colesterolo).
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import nutrienti
from classificazioni import CARTELLA_DATI, glucosio
from lingue import N_

FILE_PASTI = CARTELLA_DATI / "pasti_pronti.csv"
FILE_INGREDIENTI = CARTELLA_DATI / "pasti_pronti_ingredienti.csv"

CATEGORIA = "Piatti e ricette"

PORTATE = (
    ("antipasto", N_("Antipasti")),
    ("primo", N_("Primi piatti")),
    ("secondo", N_("Secondi piatti")),
    ("contorno", N_("Contorni")),
)
CHIAVI_PORTATE = tuple(chiave for chiave, _etichetta in PORTATE)

# Fonti delle ricette: si riprendono solo nome, porzioni, ingredienti e
# quantità, con il collegamento alla pagina originale
FONTI = {
    "Wikibooks": {
        "nome": "Wikibooks, Libro di cucina",
        "licenza": "CC BY-SA 4.0",
        "url_licenza": "https://creativecommons.org/licenses/by-sa/4.0/deed.it",
    },
    "Buttalapasta": {
        "nome": "Buttalapasta",
        "licenza": N_("riuso consentito citando la fonte"),
        "url_licenza": "https://www.buttalapasta.it/disclaimer/",
    },
}

# Il piatto si distingue così da un alimento con lo stesso nome (es. una ricetta CREA)
SUFFISSO_OMONIMO = "(pasto pronto)"

RITENZIONE_ALCOL = 0.35
KCAL_ALCOL = 7.0
QUOTA_IGNOTA_MAX = 0.05
PORZIONI_MAX = 12

# Campi per 100 g che si sommano dagli ingredienti
CAMPI_SOMMA = ("kcal", "fibre", "fruttosio", *nutrienti.CAMPI_NUTRIENTI)

# Riferimento per la quota ignota: un ingrediente senza zuccheri non porta
# fruttosio, uno senza grassi non porta saturi né colesterolo
RIFERIMENTO = {
    "fruttosio": "zuccheri",
    "glucosio": "zuccheri",
    "lattosio": "zuccheri",
    "zuccheri": "carboidrati",
    "grassi_saturi": "grassi",
    "colesterolo": "grassi",
}

# Nelle tabelle l'alcol manca per gli alimenti che non ne hanno
ZERO_SE_MANCA = {"alcol"}

CODICE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

Ricetta = dict[str, Any]


class ErroreDati(ValueError):
    """
    File dei pasti pronti non validi; errori è l'elenco dei problemi.
    """

    def __init__(self, errori: list[str]) -> None:
        super().__init__("; ".join(errori[:5]))
        self.errori = errori


class IngredientiMancanti(LookupError):
    """
    Codici CREA degli ingredienti che non corrispondono a nessun alimento.
    """

    def __init__(self, codici: list[str]) -> None:
        super().__init__(", ".join(codici))
        self.codici = codici


# ---------------------------------------------------------------
# LETTURA DEI FILE
# ---------------------------------------------------------------

def _numero(testo: str | None) -> float | None:
    testo = (testo or "").strip().replace(",", ".")
    return float(testo) if testo else None


def leggi_dati(file_pasti: Path = FILE_PASTI, file_ingredienti: Path = FILE_INGREDIENTI) -> list[Ricetta]:
    """
    Ricette con i loro ingredienti, nell'ordine dei file. Solleva ErroreDati
    con tutti i problemi trovati (codici doppi, portate o numeri non validi,
    ricette senza ingredienti o ingredienti senza ricetta).
    """
    errori: list[str] = []
    ricette: dict[str, Ricetta] = {}

    with file_pasti.open(encoding="utf-8", newline="") as f:
        for riga_n, riga in enumerate(csv.DictReader(f), start=2):
            codice = (riga.get("codice") or "").strip()
            dove = f"{file_pasti.name}, riga {riga_n}"

            if not CODICE_RE.match(codice):
                errori.append(f"{dove}: codice non valido «{codice}»")
                continue

            if codice in ricette:
                errori.append(f"{dove}: codice ripetuto «{codice}»")
                continue

            portata = (riga.get("portata") or "").strip()
            fonte = (riga.get("fonte") or "").strip()
            nome = (riga.get("nome") or "").strip()

            try:
                porzioni = int(riga.get("porzioni") or "")
            except ValueError:
                porzioni = 0

            if portata not in CHIAVI_PORTATE:
                errori.append(f"{dove}: portata non valida «{portata}»")
            if fonte not in FONTI:
                errori.append(f"{dove}: fonte non valida «{fonte}»")
            if not nome:
                errori.append(f"{dove}: nome mancante")
            if not 0 < porzioni <= 50:
                errori.append(f"{dove}: porzioni non valide")

            ricette[codice] = {
                "codice": codice,
                "nome": nome,
                "portata": portata,
                "porzioni": porzioni,
                "fonte": fonte,
                "url_fonte": (riga.get("url") or "").strip() or None,
                "note": (riga.get("note") or "").strip() or None,
                "ingredienti": [],
            }

    with file_ingredienti.open(encoding="utf-8", newline="") as f:
        for riga_n, riga in enumerate(csv.DictReader(f), start=2):
            codice = (riga.get("codice") or "").strip()
            dove = f"{file_ingredienti.name}, riga {riga_n}"
            ricetta = ricette.get(codice)

            if ricetta is None:
                errori.append(f"{dove}: ricetta inesistente «{codice}»")
                continue

            try:
                grammi = _numero(riga.get("grammi"))
                resa = _numero(riga.get("resa"))
            except ValueError:
                errori.append(f"{dove}: grammi o resa non numerici")
                continue

            codice_crea = (riga.get("codice_crea") or "").strip() or None
            ingrediente = (riga.get("ingrediente") or "").strip()

            if not ingrediente:
                errori.append(f"{dove}: ingrediente senza testo")
            if grammi is not None and grammi < 0:
                errori.append(f"{dove}: grammi negativi")
            if resa is not None and resa <= 0:
                errori.append(f"{dove}: resa non valida")
            if codice_crea and grammi is None:
                errori.append(f"{dove}: alimento senza grammi")

            ricetta["ingredienti"].append({
                "ingrediente": ingrediente,
                "codice_crea": codice_crea,
                "grammi": grammi,
                "resa": resa if resa is not None else 1.0,
                "nota": (riga.get("nota") or "").strip() or None,
            })

    for codice, ricetta in ricette.items():
        if not any(voce["codice_crea"] for voce in ricetta["ingredienti"]):
            errori.append(f"ricetta «{codice}» senza ingredienti abbinati")

    if errori:
        raise ErroreDati(errori)

    return list(ricette.values())


# ---------------------------------------------------------------
# CALCOLO DEL PIATTO
# ---------------------------------------------------------------

def _totale(parti: list[tuple[float, float | None]]) -> float | None:
    """
    parti: (peso nel riferimento, contributo o None). Somma dei contributi
    noti estesa alla parte ignota, o None se questa supera QUOTA_IGNOTA_MAX.
    """
    # math.fsum e non sum: dalla 3.12 sum somma i float in modo diverso e un valore
    # a metà tra due arrotondamenti cambierebbe con la versione di Python
    noto = math.fsum(peso for peso, valore in parti if valore is not None)
    ignoto = math.fsum(peso for peso, valore in parti if valore is None)

    if noto + ignoto <= 0:
        return 0.0

    if ignoto / (noto + ignoto) > QUOTA_IGNOTA_MAX:
        return None

    somma = math.fsum(valore for _, valore in parti if valore is not None)
    return somma * (noto + ignoto) / noto if noto > 0 else 0.0


def voci_alimenti(
    ricetta: Ricetta, alimenti: Mapping[str, Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], float, float]]:
    """
    [(alimento, grammi crudi, resa)] degli ingredienti abbinati; solleva
    IngredientiMancanti se un codice non corrisponde a nessun alimento.
    """
    mancanti = sorted({
        voce["codice_crea"] for voce in ricetta["ingredienti"]
        if voce["codice_crea"] and voce["codice_crea"] not in alimenti
    })

    if mancanti:
        raise IngredientiMancanti(mancanti)

    return [
        (alimenti[voce["codice_crea"]], float(voce["grammi"] or 0), float(voce["resa"] or 1))
        for voce in ricetta["ingredienti"]
        if voce["codice_crea"]
    ]


def peso_cotto(ricetta: Ricetta) -> float:
    """
    Peso del piatto finito: grammi per resa di tutti gli ingredienti con un
    peso, anche quelli contati solo come peso (acqua, brodo).
    """
    return math.fsum(float(voce["grammi"] or 0) * float(voce["resa"] or 1) for voce in ricetta["ingredienti"])


def _indice_glicemico(voci: Iterable[tuple[Mapping[str, Any], float, float]]) -> float | None:
    """
    Indice glicemico del piatto: media degli indici pesata sui carboidrati
    disponibili di ciascun ingrediente (FAO/OMS 1998, pasti misti).
    """
    parti = []

    for alimento, grammi, _resa in voci:
        disponibili = nutrienti.carboidrati_disponibili(dict(alimento))
        peso = grammi * (disponibili if disponibili is not None else 100) / 100

        if peso <= 0:
            continue

        indice = alimento.get("indice_glicemico")
        parti.append((peso, None if indice is None else peso * float(indice)))

    if not parti:
        return None

    totale = _totale(parti)
    carboidrati = math.fsum(peso for peso, _ in parti)
    return round(totale / carboidrati) if totale is not None and carboidrati > 0 else None


def calcola(ricetta: Ricetta, alimenti: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """
    Valori per 100 g del piatto cotto, porzione in grammi e dati descrittivi,
    pronti per fonti.completa. alimenti: {codice CREA: alimento}.
    """
    voci = voci_alimenti(ricetta, alimenti)
    totali: dict[str, float | None] = {}

    for campo in CAMPI_SOMMA:
        rif = RIFERIMENTO.get(campo)
        parti = []

        for alimento, grammi, _resa in voci:
            # Per carne e pesce senza glucosio, gli zuccheri (dal glicogeno)
            valore = glucosio(alimento) if campo == "glucosio" else alimento.get(campo)

            if valore is None and campo in ZERO_SE_MANCA:
                valore = 0.0

            if rif:
                base = alimento.get(rif)

                if base is not None and base <= 0:
                    continue   # senza zuccheri (o grassi) non porta questo campo

                peso = grammi * (base if base is not None else 100) / 100
            else:
                peso = grammi

            parti.append((peso, None if valore is None else grammi * float(valore) / 100))

        totali[campo] = _totale(parti)

    alcol = totali.get("alcol")

    if alcol:
        perso = alcol * (1 - RITENZIONE_ALCOL)
        totali["alcol"] = alcol - perso

        if totali.get("kcal") is not None:
            totali["kcal"] = max(float(totali["kcal"] or 0) - perso * KCAL_ALCOL, 0.0)

    peso = peso_cotto(ricetta)
    fattore = 100 / peso if peso > 0 else 0
    fonte = FONTI.get(ricetta["fonte"], {})

    valori: dict[str, Any] = {
        campo: (None if totale is None else round(totale * fattore, 2))
        for campo, totale in totali.items()
    }
    valori.update({
        "alimento": ricetta["nome"],
        "categoria": CATEGORIA,
        "porzione": round(peso / ricetta["porzioni"]) if ricetta["porzioni"] else None,
        "indice_glicemico": _indice_glicemico(voci),
        "fonte_nutrienti": f"Calcolato dagli ingredienti; ricetta: {fonte.get('nome', ricetta['fonte'])}",
        "url_fonte": ricetta.get("url_fonte"),
    })
    return valori


def nome_piatto(nome: str, altri_nomi: set[str]) -> str:
    """
    Nome del piatto in tabella: quello della ricetta, con SUFFISSO_OMONIMO se
    un altro alimento (non un pasto pronto) si chiama già così.
    """
    return f"{nome} {SUFFISSO_OMONIMO}" if nome.casefold() in altri_nomi else nome


def per_porzione(ricetta: Ricetta, porzioni: float = 1) -> list[dict[str, Any]]:
    """
    Ingredienti abbinati con i grammi per il numero di porzioni indicato
    (crudi, come si pesano), nell'ordine della ricetta.
    """
    fattore = porzioni / ricetta["porzioni"]
    return [
        {**voce, "grammi_porzione": round(float(voce["grammi"] or 0) * fattore, 1)}
        for voce in ricetta["ingredienti"]
        if voce["codice_crea"] and voce["grammi"]
    ]
