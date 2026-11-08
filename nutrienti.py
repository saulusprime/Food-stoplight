"""
Dati nutrizionali oltre a energia, fruttosio e fibre: macronutrienti,
micronutrienti, indice e carico glicemico, FODMAP e grado di
processazione (NOVA).

Qui stanno le definizioni dei campi (etichetta, unità, decimali, codice
USDA), usate da database, form, scheda, import ed export, e i calcoli
per porzione, per pasto e per giornata.

Convenzione: nei nuovi campi None significa "dato non disponibile",
0 è un valore misurato.

I carboidrati sono quelli disponibili (senza le fibre), come nelle
etichette europee e nelle tabelle CREA; da USDA, che li calcola per
differenza comprese le fibre, si sottraggono le fibre.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import analisi
from analisi import Alimento, Livello
from lingue import N_

# (alimento, grammi) di un pasto o di una giornata
Voce = tuple[Alimento, float]

# ---------------------------------------------------------------
# CAMPI
# (campo, etichetta, unità, decimali, codice del nutriente in USDA FoodData Central)
# ---------------------------------------------------------------

MACRO = (
    ("proteine", N_("Proteine"), "g", 1, "203"),
    ("carboidrati", N_("Carboidrati"), "g", 1, "205"),
    ("zuccheri", N_("di cui zuccheri"), "g", 1, "269"),
    ("glucosio", N_("di cui glucosio"), "g", 2, "211"),
    ("lattosio", N_("di cui lattosio"), "g", 2, "213"),
    ("grassi", N_("Grassi"), "g", 1, "204"),
    ("grassi_saturi", N_("di cui saturi"), "g", 1, "606"),
    ("colesterolo", N_("Colesterolo"), "mg", 0, "601"),
    ("alcol", N_("Alcol"), "g", 1, "221"),
)

MICRO = (
    ("vitamina_a", N_("Vitamina A"), "µg", 0, "320"),
    ("vitamina_c", N_("Vitamina C"), "mg", 1, "401"),
    ("vitamina_d", N_("Vitamina D"), "µg", 1, "328"),
    ("vitamina_e", N_("Vitamina E"), "mg", 1, "323"),
    ("vitamina_b12", N_("Vitamina B12"), "µg", 2, "418"),
    ("folati", N_("Folati"), "µg", 0, "435"),
    ("calcio", N_("Calcio"), "mg", 0, "301"),
    ("ferro", N_("Ferro"), "mg", 1, "303"),
    ("magnesio", N_("Magnesio"), "mg", 0, "304"),
    ("potassio", N_("Potassio"), "mg", 0, "306"),
    ("sodio", N_("Sodio"), "mg", 0, "307"),
    ("zinco", N_("Zinco"), "mg", 1, "309"),
)

NUTRIENTI = MACRO + MICRO
CAMPI_NUTRIENTI = tuple(n[0] for n in NUTRIENTI)
PER_CAMPO = {n[0]: n for n in NUTRIENTI}

FODMAP = (
    ("fodmap_fruttani", N_("Fruttani")),
    ("fodmap_gos", N_("GOS (galatto-oligosaccaridi)")),
    ("fodmap_lattosio", N_("Lattosio")),
    ("fodmap_fruttosio", N_("Fruttosio in eccesso")),
    ("fodmap_polioli", N_("Polioli (sorbitolo, mannitolo)")),
)

CAMPI_FODMAP = tuple(campo for campo, _ in FODMAP)

# Semaforo FODMAP come nelle tabelle Monash: verde, giallo, rosso
LIVELLI_FODMAP = (
    {"etichetta": N_("Basso"), "stato": "good", "ordine": 0},
    {"etichetta": N_("Medio"), "stato": "warning", "ordine": 1},
    {"etichetta": N_("Alto"), "stato": "critical", "ordine": 2},
)

_FODMAP_PER_ETICHETTA = {liv["etichetta"]: liv for liv in LIVELLI_FODMAP}

SINONIMI_FODMAP = {
    "basso": "Basso", "low": "Basso", "verde": "Basso", "green": "Basso",
    "medio": "Medio", "moderato": "Medio", "moderate": "Medio", "giallo": "Medio",
    "ambra": "Medio", "amber": "Medio", "arancione": "Medio",
    "alto": "Alto", "high": "Alto", "rosso": "Alto", "red": "Alto", "elevato": "Alto",
}

NOVA = {
    1: {"gruppo": 1, "etichetta": N_("Non trasformati o minimamente trasformati"), "stato": "good"},
    2: {"gruppo": 2, "etichetta": N_("Ingredienti culinari trasformati"), "stato": "warning"},
    3: {"gruppo": 3, "etichetta": N_("Alimenti trasformati"), "stato": "serious"},
    4: {"gruppo": 4, "etichetta": N_("Ultra-trasformati"), "stato": "critical"},
}

CAMPI_FONTE = ("fonte_nutrienti", "url_fonte", "fdc_id", "codice_crea", "codice_barre", "campi_usda")

# Porzione tipica quando la fonte non ne indica una
PORZIONE_PREDEFINITA = 100.0


# Tutti i nuovi campi (None = non disponibile)
CAMPI_NUMERICI_NULLABILI = (*CAMPI_NUTRIENTI, "indice_glicemico", "nova", "fdc_id", "porzione")
CAMPI_TESTO_NULLABILI = (
    *CAMPI_FODMAP, "fonte_nutrienti", "url_fonte", "codice_crea", "codice_barre", "campi_usda", "note",
)
CAMPI_NULLABILI = (*CAMPI_NUMERICI_NULLABILI, *CAMPI_TESTO_NULLABILI)

# Valori per 100 g che cambiano con la porzione
CAMPI_PER_PORZIONE = ("kcal", "tef_kcal", "kcal_nette", "fruttosio", "fibre", *CAMPI_NUTRIENTI)

ETICHETTE = {
    **{n[0]: n[1] for n in NUTRIENTI},
    "zuccheri": N_("Zuccheri"),
    "glucosio": N_("Glucosio"),
    "lattosio": N_("Lattosio"),
    "grassi_saturi": N_("Grassi saturi"),
    "indice_glicemico": N_("Indice glicemico"),
    "nova": N_("NOVA"),
    "fodmap_fruttani": N_("FODMAP fruttani"),
    "fodmap_gos": N_("FODMAP GOS"),
    "fodmap_lattosio": N_("FODMAP lattosio"),
    "fodmap_fruttosio": N_("FODMAP fruttosio in eccesso"),
    "fodmap_polioli": N_("FODMAP polioli"),
    "fonte_nutrienti": N_("Fonte nutrienti"),
    "url_fonte": N_("URL fonte"),
    "fdc_id": N_("FDC ID"),
    "codice_crea": N_("Codice CREA"),
    "codice_barre": N_("Codice a barre"),
    "campi_usda": N_("Campi da USDA"),
    "porzione": N_("Porzione tipica (g)"),
    "note": N_("Note"),
}

# Porzione: limiti accettati dal calcolatore, dal pasto e dal diario
GRAMMI_MIN = 1
GRAMMI_MAX = 2000

PASTI = (
    ("colazione", N_("Colazione")),
    ("pranzo", N_("Pranzo")),
    ("cena", N_("Cena")),
    ("spuntino", N_("Spuntino")),
)

URL_RE = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)


# ---------------------------------------------------------------
# LIVELLI E CLASSIFICAZIONI
# ---------------------------------------------------------------

def livello_fodmap(valore: object) -> Livello | None:
    """
    Livello FODMAP canonico ({etichetta, stato, ordine}) oppure None.
    Accetta anche emoji davanti e i colori del semaforo (verde, giallo, rosso).
    """
    testo = re.sub(r"^[\W_]+|[\W_]+$", "", str(valore or "")).lower()
    testo = re.sub(r"\s*fodmap$", "", testo)
    etichetta = SINONIMI_FODMAP.get(testo)
    return _FODMAP_PER_ETICHETTA.get(etichetta) if etichetta else None


def fodmap_complessivo(item: Alimento) -> Livello | None:
    """
    Livello FODMAP più alto tra le categorie classificate, None se nessuna lo è.
    """
    livelli = [liv for liv in (livello_fodmap(item.get(campo)) for campo in CAMPI_FODMAP) if liv is not None]
    return max(livelli, key=lambda liv: liv["ordine"]) if livelli else None


def leggi_nova(valore: object) -> int | None:
    """
    Gruppo NOVA 1-4 da "4", "NOVA 4", "4 - Ultra-trasformati"...; None altrimenti.
    """
    if valore is None:
        return None

    if isinstance(valore, (int, float)):
        return int(valore) if valore in (1, 2, 3, 4) else None

    corrispondenza = re.search(r"(?<!\d)([1-4])(?!\d)", str(valore))
    return int(corrispondenza.group(1)) if corrispondenza else None


def gruppo_nova(item: Alimento) -> dict[str, Any] | None:
    gruppo = leggi_nova(item.get("nova"))
    return NOVA.get(gruppo) if gruppo else None


def livello_indice_glicemico(indice: float | None) -> dict[str, str] | None:
    """
    Soglie usuali: fino a 55 basso, 56-69 medio, da 70 alto.
    """
    if indice is None:
        return None

    if indice <= 55:
        return {"etichetta": N_("Basso"), "stato": "good"}

    if indice < 70:
        return {"etichetta": N_("Medio"), "stato": "warning"}

    return {"etichetta": N_("Alto"), "stato": "critical"}


def livello_carico_glicemico(carico: float | None) -> dict[str, str] | None:
    """
    Soglie per porzione: fino a 10 basso, 11-19 medio, da 20 alto.
    """
    if carico is None:
        return None

    if carico <= 10:
        return {"etichetta": N_("Basso"), "stato": "good"}

    if carico < 20:
        return {"etichetta": N_("Medio"), "stato": "warning"}

    return {"etichetta": N_("Alto"), "stato": "critical"}


def carboidrati_disponibili(item: Alimento) -> float | None:
    """
    Carboidrati disponibili (senza fibre: sono già così nel campo carboidrati);
    None se non sono noti.
    """
    carboidrati = item.get("carboidrati")
    return None if carboidrati is None else max(float(carboidrati), 0.0)


def porzione(item: Alimento) -> float:
    """
    Porzione tipica in grammi (dalla fonte), altrimenti 100 g.
    """
    grammi = item.get("porzione")
    return float(grammi) if grammi and grammi > 0 else PORZIONE_PREDEFINITA


def carico_glicemico(item: Alimento, grammi: float = 100) -> float | None:
    """
    Carico glicemico = indice glicemico × carboidrati disponibili della porzione ÷ 100.
    """
    indice = item.get("indice_glicemico")
    disponibili = carboidrati_disponibili(item)

    if indice is None or disponibili is None:
        return None

    return round(indice * disponibili * grammi / 100 / 100, 1)


# ---------------------------------------------------------------
# PORZIONI, PASTI E GIORNATE
# ---------------------------------------------------------------

def leggi_grammi(valore: object, predefinito: float | None = None) -> float | None:
    """
    Grammi di una porzione (virgola o punto), nei limiti ammessi; altrimenti il predefinito.
    """
    try:
        grammi = float(str(valore).strip().replace(",", "."))
    except (TypeError, ValueError):
        return predefinito

    if not GRAMMI_MIN <= grammi <= GRAMMI_MAX:
        return predefinito

    return round(grammi, 1)


def per_porzione(item: Alimento, grammi: float) -> dict[str, float | None]:
    """
    Valori riferiti alla porzione: i campi per 100 g scalati, None restano None.
    """
    fattore = grammi / 100

    return {
        campo: (None if item.get(campo) is None else item[campo] * fattore)
        for campo in CAMPI_PER_PORZIONE
    }


def totali(voci: Sequence[Voce]) -> tuple[dict[str, float], dict[str, int]]:
    """
    voci: lista di (alimento, grammi). Somma i valori delle porzioni e conta,
    campo per campo, gli alimenti per cui il dato manca.
    """
    somme = dict.fromkeys(CAMPI_PER_PORZIONE, 0.0)
    mancanti = dict.fromkeys(CAMPI_PER_PORZIONE, 0)

    for alimento, grammi in voci:
        porzione = per_porzione(alimento, grammi)

        for campo, valore in porzione.items():
            if valore is None:
                mancanti[campo] += 1
            else:
                somme[campo] += valore

    somme["grammi"] = sum(grammi for _, grammi in voci)
    return somme, mancanti


def profilo_rischio(voci: Sequence[Voce]) -> dict[str, Any]:
    """
    Profilo di rischio di un pasto o di una giornata: per ogni rischio la media
    dei punti dei livelli (0-3) pesata sulle Kcal che ciascun alimento apporta.
    Se nessun alimento ha Kcal si pesa sui grammi. Gli alimenti senza
    quel livello non contano per quel rischio.
    """
    pesi_kcal = [(alimento.get("kcal") or 0) * grammi / 100 for alimento, grammi in voci]
    su_kcal = sum(pesi_kcal) > 0
    pesi = pesi_kcal if su_kcal else [grammi for _, grammi in voci]

    rischi: list[dict[str, Any]] = []

    for campo, etichetta in analisi.RISCHI:
        somma = 0.0
        peso_totale = 0.0
        contributi = []

        for (alimento, _), peso in zip(voci, pesi, strict=True):
            liv = analisi.livello(alimento.get(campo))

            if liv is None or peso <= 0:
                continue

            somma += liv["punti"] * peso
            peso_totale += peso
            contributi.append((liv["punti"] * peso, alimento.get("alimento")))

        if peso_totale == 0:
            rischi.append({"campo": campo, "etichetta": etichetta, "punti": None,
                           "livello": analisi.NON_CLASSIFICATO, "principale": None})
            continue

        punti = somma / peso_totale
        principale = max(contributi)[1] if contributi and max(contributi)[0] > 0 else None

        rischi.append({
            "campo": campo,
            "etichetta": etichetta,
            "punti": round(punti, 2),
            "livello": analisi.LIVELLI[min(int(punti + 0.5), len(analisi.LIVELLI) - 1)],
            "principale": principale,
        })

    noti = [r["punti"] for r in rischi if r["punti"] is not None]
    punteggio = round(100 * (1 - (sum(noti) / len(noti)) / analisi.PUNTI_MAX)) if noti else None

    return {
        "rischi": rischi,
        "punteggio": punteggio,
        "livello": analisi.livello_punteggio(punteggio),
        "pesato_su": N_("Kcal") if su_kcal else N_("grammi"),
    }


# ---------------------------------------------------------------
# SUGGERIMENTI
# ---------------------------------------------------------------

SUGGERIMENTI_MAX = 5


def alternative(item: Alimento, alimenti: list[Alimento], n: int = SUGGERIMENTI_MAX) -> list[Alimento]:
    """
    Alimenti della stessa categoria con punteggio più alto: prima i migliori,
    a parità quelli con Kcal più vicine. Esclude gli omonimi.
    """
    punteggio = item.get("punteggio")
    categoria = (item.get("categoria") or "").strip().casefold()
    nome = (item.get("alimento") or "").strip().casefold()

    if punteggio is None or not categoria:
        return []

    kcal = item.get("kcal") or 0

    candidati = [
        a for a in alimenti
        if a["id"] != item.get("id")
        and (a.get("categoria") or "").strip().casefold() == categoria
        and (a.get("alimento") or "").strip().casefold() != nome
        and a.get("punteggio") is not None
        and a["punteggio"] > punteggio
    ]

    candidati.sort(key=lambda a: (
        -a["punteggio"],
        abs((a.get("kcal") or 0) - kcal),
        (a.get("alimento") or "").casefold(),
    ))

    # Un solo risultato per nome (il database contiene omonimi con valori diversi)
    visti = set()
    scelti = []

    for a in candidati:
        chiave = a["alimento"].strip().casefold()

        if chiave in visti:
            continue

        visti.add(chiave)
        scelti.append({**a, "guadagno": a["punteggio"] - punteggio})

        if len(scelti) == n:
            break

    return scelti
