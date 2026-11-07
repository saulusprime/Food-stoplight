"""
Analisi dei dati per la visualizzazione:
livelli di rischio, punteggio sintetico, medaglie "top alimenti"
e dati già pronti per i grafici della home e della scheda alimento.
"""

import math

# ---------------------------------------------------------------
# LIVELLI DI RISCHIO
# Scala a 4 livelli, come nelle matrici di rischio:
# verde -> giallo -> arancio -> rosso. "stato" è il nome del colore
# (variabili CSS --stato-good, --stato-warning, ... in static/css/app.css).
# ---------------------------------------------------------------

LIVELLI = (
    {"chiave": "trascurabile", "etichetta": "Trascurabile", "punti": 0, "stato": "good", "emoji": "🟢"},
    {"chiave": "basso", "etichetta": "Basso", "punti": 1, "stato": "warning", "emoji": "🟡"},
    {"chiave": "medio", "etichetta": "Medio", "punti": 2, "stato": "serious", "emoji": "🟠"},
    {"chiave": "alto", "etichetta": "Alto", "punti": 3, "stato": "critical", "emoji": "🔴"},
)

PUNTI_MAX = LIVELLI[-1]["punti"]

# Valori alternativi accettati (vecchia scala del rischio tumorale, import CSV)
SINONIMI = {
    "protettivo": "trascurabile",
    "neutro": "trascurabile",
    "elevato": "alto",
    "aumentato": "alto",
}

_PER_CHIAVE = {liv["chiave"]: liv for liv in LIVELLI}

# Valore assente o non riconosciuto
NON_CLASSIFICATO = {
    "chiave": "nd",
    "etichetta": "Non classificato",
    "punti": None,
    "stato": "nd",
    "emoji": "⚪",
}

RISCHI = (
    ("rischio_diabete", "Diabete"),
    ("rischio_colesterolo", "Colesterolo"),
    ("rischio_malassorbimento", "Malassorbimento"),
    ("rischio_metabolico", "Metabolico"),
    ("rischio_tumorale", "Tumorale"),
)

CAMPI_RISCHIO = tuple(campo for campo, _ in RISCHI)


def livello(valore):
    """
    Livello canonico di un valore di rischio (dict di LIVELLI) oppure None.
    """
    chiave = str(valore or "").strip().lower()
    chiave = SINONIMI.get(chiave, chiave)
    return _PER_CHIAVE.get(chiave)


def stato(valore):
    """
    Nome del colore di stato per un valore di rischio ("good" ... "critical", "nd").
    """
    liv = livello(valore)
    return liv["stato"] if liv else NON_CLASSIFICATO["stato"]


# ---------------------------------------------------------------
# PUNTEGGIO SINTETICO 0-100
# 100 = tutti i rischi trascurabili, 0 = tutti alti.
# Media dei punti dei livelli noti (0-3), riportata su 0-100.
# ---------------------------------------------------------------

def calcola_punteggio(*valori):
    punti = [liv["punti"] for liv in map(livello, valori) if liv]

    if not punti:
        return None

    media = sum(punti) / len(punti)
    return round(100 * (1 - media / PUNTI_MAX))


def livello_punteggio(punteggio):
    """
    Livello corrispondente alla media dei rischi da cui deriva il punteggio:
    > 83 Trascurabile, 51-83 Basso, 17-50 Medio, <= 16 Alto.
    """
    if punteggio is None:
        return NON_CLASSIFICATO

    media = PUNTI_MAX * (1 - punteggio / 100)
    indice = min(int(math.floor(media + 0.5)), len(LIVELLI) - 1)
    return LIVELLI[indice]


def punteggio_alimento(alimento):
    return calcola_punteggio(*(alimento.get(campo) for campo in CAMPI_RISCHIO))


# ---------------------------------------------------------------
# MEDAGLIE "TOP ALIMENTI"
# ---------------------------------------------------------------

def _rapporto_ff(a):
    """
    Rapporto fruttosio/fibre ricalcolato dai valori grezzi.
    """
    fibre = a.get("fibre") or 0
    return (a.get("fruttosio") or 0) / fibre if fibre > 0 else None


MEDAGLIE = (
    {
        "chiave": "protettivi",
        "icona": "🛡️",
        "titolo": "Più protettivi",
        "descrizione": "Punteggio più alto; a parità, più fibre.",
        "unita": "/100",
        "filtro": lambda a: a.get("punteggio") is not None,
        "ordine": lambda a: (-a["punteggio"], -(a.get("fibre") or 0)),
        "valore": lambda a: a["punteggio"],
        "formato": "{:.0f}",
    },
    {
        "chiave": "fruttosio",
        "icona": "🍃",
        "titolo": "Miglior rapporto fruttosio/fibre",
        "descrizione": "Rapporto più basso tra gli alimenti con almeno 1 g di fruttosio.",
        "unita": "",
        "filtro": lambda a: (a.get("fruttosio") or 0) >= 1 and (a.get("fibre") or 0) > 0,
        "ordine": lambda a: (_rapporto_ff(a),),
        "valore": _rapporto_ff,
        "formato": "{:.2f}",
    },
    {
        "chiave": "leggeri",
        "icona": "🪶",
        "titolo": "Meno calorici",
        "descrizione": "Meno Kcal per 100 g (esclusi i valori a 0, che indicano dati mancanti).",
        "unita": " kcal",
        "filtro": lambda a: (a.get("kcal") or 0) > 0,
        "ordine": lambda a: (a["kcal"],),
        "valore": lambda a: a["kcal"],
        "formato": "{:g}",
    },
)

MEDAGLIE_PER_CHIAVE = {m["chiave"]: m for m in MEDAGLIE}

# Quanti alimenti per classifica ricevono la medaglia (sull'intero database)
POSTI_MEDAGLIA = 10


def classifica(alimenti, medaglia, n):
    """
    Primi n alimenti per il criterio della medaglia: lista di (alimento, valore formattato).
    """
    candidati = [a for a in alimenti if medaglia["filtro"](a)]
    candidati.sort(key=lambda a: (*medaglia["ordine"](a), str(a.get("alimento") or "").lower(), a.get("id") or 0))

    return [
        (a, medaglia["formato"].format(medaglia["valore"](a)).replace(".", ",") + medaglia["unita"])
        for a in candidati[:n]
    ]


def medaglie_per_alimento(alimenti, posti=POSTI_MEDAGLIA):
    """
    {id alimento: [medaglia, ...]} per i primi `posti` di ogni classifica.
    """
    assegnate = {}

    for medaglia in MEDAGLIE:
        for alimento, _ in classifica(alimenti, medaglia, posti):
            assegnate.setdefault(alimento["id"], []).append(medaglia)

    return assegnate


# ---------------------------------------------------------------
# DATI PER I GRAFICI
# ---------------------------------------------------------------

def _quota(n, totale):
    return n / totale * 100 if totale else 0.0


def distribuzione_categorie(alimenti):
    """
    Barre ordinate (dalla più grande): [{categoria, n, quota, larghezza}].
    """
    conteggi = {}

    for a in alimenti:
        categoria = (a.get("categoria") or "").strip() or "Senza categoria"
        conteggi[categoria] = conteggi.get(categoria, 0) + 1

    totale = len(alimenti)
    massimo = max(conteggi.values(), default=0)

    return [
        {
            "categoria": categoria,
            "n": n,
            "quota": _quota(n, totale),
            # larghezza relativa alla barra più lunga (asse 0 -> massimo)
            "larghezza": _quota(n, massimo),
        }
        for categoria, n in sorted(conteggi.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    ]


def distribuzione_rischi(alimenti):
    """
    Una barra impilata al 100% per ogni rischio, segmenti nell'ordine dei livelli.
    """
    righe = []

    for campo, etichetta in RISCHI:
        conteggi = {liv["chiave"]: 0 for liv in LIVELLI}
        non_classificati = 0

        for a in alimenti:
            liv = livello(a.get(campo))

            if liv:
                conteggi[liv["chiave"]] += 1
            else:
                non_classificati += 1

        totale = len(alimenti)
        segmenti = [
            {**liv, "n": conteggi[liv["chiave"]], "quota": _quota(conteggi[liv["chiave"]], totale)}
            for liv in LIVELLI
        ]

        if non_classificati:
            segmenti.append({**NON_CLASSIFICATO, "n": non_classificati, "quota": _quota(non_classificati, totale)})

        righe.append({
            "campo": campo,
            "etichetta": etichetta,
            "totale": totale,
            "segmenti": [s for s in segmenti if s["n"]],
        })

    return righe


def legenda_rischi(distribuzione):
    """
    Livelli presenti in almeno una barra, nell'ordine della scala.
    """
    presenti = {s["chiave"] for riga in distribuzione for s in riga["segmenti"]}
    return [liv for liv in (*LIVELLI, NON_CLASSIFICATO) if liv["chiave"] in presenti]


def punteggio_medio(alimenti):
    valori = [a["punteggio"] for a in alimenti if a.get("punteggio") is not None]
    return round(sum(valori) / len(valori)) if valori else None


def radar(alimento, raggio=110, centro=(180, 150)):
    """
    Geometria SVG del radar dei 5 rischi.
    Il raggio indica il livello: anello 1 = Trascurabile ... anello 4 = Alto
    (il centro resta per i valori mancanti, così il profilo non sparisce mai).
    """
    cx, cy = centro
    anelli = len(LIVELLI)
    n = len(RISCHI)

    def punto(indice, r):
        angolo = math.radians(-90 + indice * 360 / n)
        return (round(cx + r * math.cos(angolo), 1), round(cy + r * math.sin(angolo), 1))

    assi = []
    vertici = []

    for i, (campo, etichetta) in enumerate(RISCHI):
        valore = alimento.get(campo)
        liv = livello(valore)
        gradino = liv["punti"] + 1 if liv else 0
        x, y = punto(i, raggio * gradino / anelli)

        lx, ly = punto(i, raggio + 18)
        coseno = math.cos(math.radians(-90 + i * 360 / n))
        ancora = "middle" if abs(coseno) < 0.3 else ("start" if coseno > 0 else "end")

        assi.append({
            "fine": punto(i, raggio),
            "etichetta": etichetta,
            "etichetta_xy": (lx, ly + (-6 if i == 0 else 4)),
            "ancora": ancora,
        })

        vertici.append({
            "x": x,
            "y": y,
            "etichetta": etichetta,
            "valore": (valore or "").strip() or NON_CLASSIFICATO["etichetta"],
            "stato": liv["stato"] if liv else NON_CLASSIFICATO["stato"],
        })

    # Etichette degli anelli lungo la bisettrice tra il primo e il secondo asse,
    # sul lato del pentagono, per non coprire i vertici
    bisettrice = math.radians(-90 + 180 / n)
    lato = math.cos(math.pi / n)

    def etichetta_anello(k):
        r = raggio * k / anelli * lato
        return (round(cx + r * math.cos(bisettrice) + 3, 1), round(cy + r * math.sin(bisettrice) + 3, 1))

    return {
        "centro": centro,
        "assi": assi,
        "anelli": [
            {
                "punti": " ".join(f"{x},{y}" for x, y in (punto(i, raggio * k / anelli) for i in range(n))),
                "etichetta": LIVELLI[k - 1]["etichetta"],
                "etichetta_xy": etichetta_anello(k),
            }
            for k in range(1, anelli + 1)
        ],
        "poligono": " ".join(f"{v['x']},{v['y']}" for v in vertici),
        "vertici": vertici,
    }
