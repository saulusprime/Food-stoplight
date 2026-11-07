"""
Dati nutrizionali oltre a energia, fruttosio e fibre: macronutrienti,
micronutrienti, indice e carico glicemico, FODMAP e grado di
processazione (NOVA).

Qui stanno le definizioni dei campi (etichetta, unità, decimali, codice
USDA), usate da database, form, scheda, import ed export, e i calcoli
per porzione, per pasto e per giornata.

Convenzione: nei nuovi campi None significa "dato non disponibile",
0 è un valore misurato.
"""

import re

import analisi

# ---------------------------------------------------------------
# CAMPI
# (campo, etichetta, unità, decimali, codice del nutriente in USDA FoodData Central)
# ---------------------------------------------------------------

MACRO = (
    ("proteine", "Proteine", "g", 1, "203"),
    ("carboidrati", "Carboidrati", "g", 1, "205"),
    ("zuccheri", "di cui zuccheri", "g", 1, "269"),
    ("grassi", "Grassi", "g", 1, "204"),
    ("grassi_saturi", "di cui saturi", "g", 1, "606"),
    ("colesterolo", "Colesterolo", "mg", 0, "601"),
)

MICRO = (
    ("vitamina_a", "Vitamina A", "µg", 0, "320"),
    ("vitamina_c", "Vitamina C", "mg", 1, "401"),
    ("vitamina_d", "Vitamina D", "µg", 1, "328"),
    ("vitamina_e", "Vitamina E", "mg", 1, "323"),
    ("vitamina_b12", "Vitamina B12", "µg", 2, "418"),
    ("folati", "Folati", "µg", 0, "435"),
    ("calcio", "Calcio", "mg", 0, "301"),
    ("ferro", "Ferro", "mg", 1, "303"),
    ("magnesio", "Magnesio", "mg", 0, "304"),
    ("potassio", "Potassio", "mg", 0, "306"),
    ("sodio", "Sodio", "mg", 0, "307"),
    ("zinco", "Zinco", "mg", 1, "309"),
)

NUTRIENTI = MACRO + MICRO
CAMPI_NUTRIENTI = tuple(n[0] for n in NUTRIENTI)
PER_CAMPO = {n[0]: n for n in NUTRIENTI}

FODMAP = (
    ("fodmap_fruttani", "Fruttani"),
    ("fodmap_gos", "GOS (galatto-oligosaccaridi)"),
    ("fodmap_lattosio", "Lattosio"),
    ("fodmap_fruttosio", "Fruttosio in eccesso"),
    ("fodmap_polioli", "Polioli (sorbitolo, mannitolo)"),
)

CAMPI_FODMAP = tuple(campo for campo, _ in FODMAP)

# Semaforo FODMAP come nelle tabelle Monash: verde, giallo, rosso
LIVELLI_FODMAP = (
    {"etichetta": "Basso", "stato": "good", "ordine": 0},
    {"etichetta": "Medio", "stato": "warning", "ordine": 1},
    {"etichetta": "Alto", "stato": "critical", "ordine": 2},
)

_FODMAP_PER_ETICHETTA = {liv["etichetta"]: liv for liv in LIVELLI_FODMAP}

SINONIMI_FODMAP = {
    "basso": "Basso", "low": "Basso", "verde": "Basso", "green": "Basso",
    "medio": "Medio", "moderato": "Medio", "moderate": "Medio", "giallo": "Medio",
    "ambra": "Medio", "amber": "Medio", "arancione": "Medio",
    "alto": "Alto", "high": "Alto", "rosso": "Alto", "red": "Alto", "elevato": "Alto",
}

NOVA = {
    1: {"gruppo": 1, "etichetta": "Non trasformati o minimamente trasformati", "stato": "good"},
    2: {"gruppo": 2, "etichetta": "Ingredienti culinari trasformati", "stato": "warning"},
    3: {"gruppo": 3, "etichetta": "Alimenti trasformati", "stato": "serious"},
    4: {"gruppo": 4, "etichetta": "Ultra-trasformati", "stato": "critical"},
}

CAMPI_FONTE = ("fonte_nutrienti", "url_fonte", "fdc_id")


def _nome_fodmap(etichetta):
    """
    "GOS (galatto-oligosaccaridi)" -> "GOS", "Fruttani" -> "fruttani".
    """
    nome = etichetta.split(" (")[0]
    return nome if nome.isupper() else nome.lower()

# Tutti i nuovi campi (None = non disponibile)
CAMPI_NUMERICI_NULLABILI = (*CAMPI_NUTRIENTI, "indice_glicemico", "nova", "fdc_id")
CAMPI_TESTO_NULLABILI = (*CAMPI_FODMAP, "fonte_nutrienti", "url_fonte")
CAMPI_NULLABILI = (*CAMPI_NUMERICI_NULLABILI, *CAMPI_TESTO_NULLABILI)

# Colonne SQL da aggiungere alla tabella alimenti
COLONNE_SQL = {
    **{campo: "REAL" for campo in CAMPI_NUTRIENTI},
    "indice_glicemico": "REAL",
    "nova": "INTEGER",
    **{campo: "TEXT" for campo in CAMPI_FODMAP},
    "fonte_nutrienti": "TEXT",
    "url_fonte": "TEXT",
    "fdc_id": "INTEGER",
}

# Valori per 100 g che cambiano con la porzione
CAMPI_PER_PORZIONE = ("kcal", "tef_kcal", "kcal_nette", "fruttosio", "fibre", *CAMPI_NUTRIENTI)

ETICHETTE = {
    **{n[0]: n[1] for n in NUTRIENTI},
    "zuccheri": "Zuccheri",
    "grassi_saturi": "Grassi saturi",
    "indice_glicemico": "Indice glicemico",
    "nova": "NOVA",
    **{campo: f"FODMAP {_nome_fodmap(etichetta)}" for campo, etichetta in FODMAP},
    "fonte_nutrienti": "Fonte nutrienti",
    "url_fonte": "URL fonte",
    "fdc_id": "FDC ID",
}

# Porzione: limiti accettati dal calcolatore, dal pasto e dal diario
GRAMMI_MIN = 1
GRAMMI_MAX = 2000

PASTI = (
    ("colazione", "Colazione"),
    ("pranzo", "Pranzo"),
    ("cena", "Cena"),
    ("spuntino", "Spuntino"),
)

URL_RE = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)


# ---------------------------------------------------------------
# LIVELLI E CLASSIFICAZIONI
# ---------------------------------------------------------------

def livello_fodmap(valore):
    """
    Livello FODMAP canonico ({etichetta, stato, ordine}) oppure None.
    Accetta anche emoji davanti e i colori del semaforo (verde, giallo, rosso).
    """
    testo = re.sub(r"^[\W_]+|[\W_]+$", "", str(valore or "")).lower()
    testo = re.sub(r"\s*fodmap$", "", testo)
    etichetta = SINONIMI_FODMAP.get(testo)
    return _FODMAP_PER_ETICHETTA.get(etichetta) if etichetta else None


def fodmap_complessivo(item):
    """
    Livello FODMAP più alto tra le categorie classificate, None se nessuna lo è.
    """
    livelli = [livello_fodmap(item.get(campo)) for campo in CAMPI_FODMAP]
    livelli = [liv for liv in livelli if liv]
    return max(livelli, key=lambda liv: liv["ordine"]) if livelli else None


def leggi_nova(valore):
    """
    Gruppo NOVA 1-4 da "4", "NOVA 4", "4 - Ultra-trasformati"...; None altrimenti.
    """
    if valore is None:
        return None

    if isinstance(valore, (int, float)):
        return int(valore) if valore in (1, 2, 3, 4) else None

    corrispondenza = re.search(r"(?<!\d)([1-4])(?!\d)", str(valore))
    return int(corrispondenza.group(1)) if corrispondenza else None


def gruppo_nova(item):
    gruppo = leggi_nova(item.get("nova"))
    return NOVA.get(gruppo) if gruppo else None


def livello_indice_glicemico(indice):
    """
    Soglie usuali: fino a 55 basso, 56-69 medio, da 70 alto.
    """
    if indice is None:
        return None

    if indice <= 55:
        return {"etichetta": "Basso", "stato": "good"}

    if indice < 70:
        return {"etichetta": "Medio", "stato": "warning"}

    return {"etichetta": "Alto", "stato": "critical"}


def livello_carico_glicemico(carico):
    """
    Soglie per porzione: fino a 10 basso, 11-19 medio, da 20 alto.
    """
    if carico is None:
        return None

    if carico <= 10:
        return {"etichetta": "Basso", "stato": "good"}

    if carico < 20:
        return {"etichetta": "Medio", "stato": "warning"}

    return {"etichetta": "Alto", "stato": "critical"}


def carboidrati_disponibili(item):
    """
    Carboidrati meno fibre (i carboidrati USDA sono calcolati per differenza
    e comprendono le fibre); None se i carboidrati non sono noti.
    """
    carboidrati = item.get("carboidrati")

    if carboidrati is None:
        return None

    return max(carboidrati - (item.get("fibre") or 0), 0.0)


def carico_glicemico(item, grammi=100):
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

def leggi_grammi(valore, predefinito=None):
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


def per_porzione(item, grammi):
    """
    Valori riferiti alla porzione: i campi per 100 g scalati, None restano None.
    """
    fattore = grammi / 100

    return {
        campo: (None if item.get(campo) is None else item[campo] * fattore)
        for campo in CAMPI_PER_PORZIONE
    }


def totali(voci):
    """
    voci: lista di (alimento, grammi). Somma i valori delle porzioni e conta,
    campo per campo, gli alimenti per cui il dato manca.
    """
    somme = {campo: 0.0 for campo in CAMPI_PER_PORZIONE}
    mancanti = {campo: 0 for campo in CAMPI_PER_PORZIONE}

    for alimento, grammi in voci:
        porzione = per_porzione(alimento, grammi)

        for campo, valore in porzione.items():
            if valore is None:
                mancanti[campo] += 1
            else:
                somme[campo] += valore

    somme["grammi"] = sum(grammi for _, grammi in voci)
    return somme, mancanti


def profilo_rischio(voci):
    """
    Profilo di rischio di un pasto o di una giornata: per ogni rischio la media
    dei punti dei livelli (0-3) pesata sulle Kcal che ciascun alimento apporta.
    Se nessun alimento ha Kcal si pesa sui grammi. Gli alimenti senza
    quel livello non contano per quel rischio.
    """
    pesi_kcal = [(alimento.get("kcal") or 0) * grammi / 100 for alimento, grammi in voci]
    su_kcal = sum(pesi_kcal) > 0
    pesi = pesi_kcal if su_kcal else [grammi for _, grammi in voci]

    rischi = []

    for campo, etichetta in analisi.RISCHI:
        somma = 0.0
        peso_totale = 0.0
        contributi = []

        for (alimento, _), peso in zip(voci, pesi):
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
        "pesato_su": "Kcal" if su_kcal else "grammi",
    }


# ---------------------------------------------------------------
# SUGGERIMENTI
# ---------------------------------------------------------------

SUGGERIMENTI_MAX = 5


def alternative(item, alimenti, n=SUGGERIMENTI_MAX):
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
