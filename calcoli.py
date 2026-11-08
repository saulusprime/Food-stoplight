"""
Calcoli condivisi da web app (form e import), update.py e autogen.py:
lettura dei numeri scritti a mano o nei file, arrotondamento, energia
dai macronutrienti, effetto termico (TEF), Kcal nette e rapporto
fruttosio/fibre.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, MutableMapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Energia per grammo di macronutriente (fattori di Atwater)
KCAL_PER_GRAMMO = {"proteine": 4.0, "carboidrati": 4.0, "grassi": 9.0}

# Effetto termico: quota dell'energia di ciascun macronutriente spesa per digerirlo
# (gli stessi coefficienti con cui autogen.py ha calcolato i TEF del database)
TEF_MACRONUTRIENTI = {"proteine": 0.25, "carboidrati": 0.10, "grassi": 0.05}

MACRONUTRIENTI = tuple(KCAL_PER_GRAMMO)

# Valori da trattare come cella vuota
VALORI_ASSENTI = {"", "-", "–", "—", "na", "n/a", "nd", "n/d", "n.d.", "null", "none"}


# ---------------------------------------------------------------
# NUMERI
# ---------------------------------------------------------------

def leggi_numero(testo: object) -> tuple[float | None, bool]:
    """
    (valore, valido): valore None se la cella è vuota o assente (valido=True)
    oppure se non è un numero (valido=False). Accetta virgola o punto decimale,
    separatore delle migliaia, % e unità di misura in coda ("5,9 g").
    """
    pulito = str(testo if testo is not None else "").strip().replace(" ", "").replace(" ", "")

    if pulito.lower() in VALORI_ASSENTI or pulito.lower() in ("inf", "infinity", "∞"):
        return None, True

    pulito = pulito.rstrip("%")

    if "," in pulito and "." in pulito:
        # Il separatore decimale è l'ultimo dei due: 1.234,5 oppure 1,234.5
        if pulito.rfind(",") > pulito.rfind("."):
            pulito = pulito.replace(".", "").replace(",", ".")
        else:
            pulito = pulito.replace(",", "")
    else:
        pulito = pulito.replace(",", ".")

    corrispondenza = re.fullmatch(r"(-?\d+(?:\.\d+)?|-?\.\d+)(?:[a-zA-Zµ]{1,4})?", pulito)

    if not corrispondenza:
        return None, False

    valore = float(corrispondenza.group(1))
    return (valore, True) if math.isfinite(valore) else (None, True)


def arrotonda(valore: float, cifre: int) -> float:
    """
    Arrotondamento "alla pari per eccesso" come ROUND() di SQLite
    (con cui è stato normalizzato il database): 2,8125 -> 2,813,
    dove round() di Python darebbe 2,812.
    """
    passo = Decimal(1).scaleb(-cifre)
    return float(Decimal(repr(float(valore))).quantize(passo, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------
# ENERGIA
# ---------------------------------------------------------------

def kcal_da_macronutrienti(
    proteine: float | None, carboidrati: float | None, grassi: float | None
) -> float | None:
    """
    Kcal stimate dai macronutrienti (4 / 4 / 9 Kcal per grammo); None se mancano tutti.
    """
    grammi = {"proteine": proteine, "carboidrati": carboidrati, "grassi": grassi}

    if all(valore is None for valore in grammi.values()):
        return None

    return sum((valore or 0) * KCAL_PER_GRAMMO[nome] for nome, valore in grammi.items())


def tef_da_macronutrienti(
    kcal: float, proteine: float | None, carboidrati: float | None, grassi: float | None
) -> tuple[float, float] | None:
    """
    (TEF in Kcal, TEF in %) stimati dalla ripartizione dell'energia tra i
    macronutrienti: la percentuale è la media dei coefficienti pesata sulle
    Kcal di ciascun macronutriente. None se i macronutrienti non danno energia.
    """
    energia = {
        nome: (valore or 0) * KCAL_PER_GRAMMO[nome]
        for nome, valore in (("proteine", proteine), ("carboidrati", carboidrati), ("grassi", grassi))
    }
    totale = sum(energia.values())

    if totale <= 0:
        return None

    percentuale = sum(energia[nome] / totale * TEF_MACRONUTRIENTI[nome] for nome in energia) * 100
    tef_kcal = min(kcal * percentuale / 100, kcal)
    return arrotonda(tef_kcal, 2), arrotonda(percentuale, 2)


def rapporto_fruttosio_fibre(fruttosio: float | None, fibre: float | None) -> float | None:
    """
    Fruttosio diviso fibre, 0 se le fibre sono 0 o mancano, None se il fruttosio non è noto.
    """
    if fruttosio is None:
        return None

    if not fibre or fibre <= 0:
        return 0.0

    return arrotonda((fruttosio or 0) / fibre, 3)


def completa_energia(valori: MutableMapping[str, Any], forniti: Collection[str], nuovo: bool) -> None:
    """
    Completa sul posto i campi derivati di un alimento, come il form e l'import:

    - Kcal mancanti: stimate dai macronutrienti;
    - TEF (Kcal) <-> TEF (%): uno dall'altro; se mancano entrambi, stimati dai
      macronutrienti; se cambiano solo le Kcal, il TEF (Kcal) segue la percentuale;
    - Kcal nette = Kcal - TEF (Kcal);
    - rapporto fruttosio/fibre, sempre ricalcolato.

    forniti: campi con un valore scritto da chi inserisce i dati (per un
    aggiornamento, solo quelli che cambiano). Un campo derivato si ricalcola
    solo se è cambiato qualcosa da cui dipende, così una riga identica al
    database resta invariata.
    """
    forniti = set(forniti)
    macro_forniti = bool(set(MACRONUTRIENTI) & forniti)
    proteine, carboidrati, grassi = (valori.get(nome) for nome in MACRONUTRIENTI)

    if not valori.get("kcal") and "kcal" not in forniti and (nuovo or macro_forniti):
        stima = kcal_da_macronutrienti(proteine, carboidrati, grassi)

        if stima:
            valori["kcal"] = arrotonda(stima, 1)
            forniti.add("kcal")

    kcal = float(valori.get("kcal") or 0)
    tef_percent = float(valori.get("tef_percent") or 0)

    if "tef_kcal" in forniti and "tef_percent" not in forniti:
        valori["tef_percent"] = arrotonda(float(valori["tef_kcal"] or 0) / kcal * 100, 2) if kcal else 0.0
    elif "tef_percent" in forniti and "tef_kcal" not in forniti:
        valori["tef_kcal"] = arrotonda(kcal * tef_percent / 100, 2)
    elif not {"tef_kcal", "tef_percent"} & forniti:
        stima_tef = tef_da_macronutrienti(kcal, proteine, carboidrati, grassi) if kcal else None

        if stima_tef and not tef_percent and (nuovo or macro_forniti):
            valori["tef_kcal"], valori["tef_percent"] = stima_tef
            forniti.add("tef_kcal")
        elif "kcal" in forniti and tef_percent:
            valori["tef_kcal"] = arrotonda(kcal * tef_percent / 100, 2)

    if "kcal_nette" not in forniti and (nuovo or {"kcal", "tef_kcal", "tef_percent"} & forniti):
        valori["kcal_nette"] = arrotonda(kcal - float(valori.get("tef_kcal") or 0), 2)

    if nuovo or {"fruttosio", "fibre", "rapporto"} & forniti:
        valori["rapporto"] = rapporto_fruttosio_fibre(valori.get("fruttosio"), valori.get("fibre"))
