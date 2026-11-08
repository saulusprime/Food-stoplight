"""
Classificazioni degli alimenti ricavate da nome, categoria e composizione,
con le fonti che le documentano: tipo di alimento (bevanda, carne rossa o
lavorata), zuccheri liberi, grado di trasformazione NOVA, livelli FODMAP
e indice glicemico dalle tabelle internazionali.

Sono regole per alimenti generici (come quelli delle tabelle CREA), non per
prodotti confezionati: per quelli valgono i dati di Open Food Facts.
"""

from __future__ import annotations

import csv
import re
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

from analisi import Alimento

CARTELLA_DATI = Path(__file__).resolve().parent / "dati"


def _parole(*voci: str) -> re.Pattern[str]:
    """
    Espressione che trova una delle voci a inizio parola (senza distinguere maiuscole).
    """
    return re.compile(r"\b(?:" + "|".join(voci) + ")", re.IGNORECASE)


def _nome(alimento: Alimento) -> str:
    return str(alimento.get("alimento") or "")


# ---------------------------------------------------------------
# TIPO DI ALIMENTO
# ---------------------------------------------------------------

BEVANDA_RE = re.compile(
    r"^(?:latte(?! (?:in polvere|condensato|di cocco))\b|succo|spremuta|nettare|bevanda|t[eè]\b|caff[eè]|"
    r"tisana|frullato|aranciata|chinotto|gassosa|cola\b|acqua tonica|birra|vino|spumante|liquore|"
    r"amaro|grappa|vermouth|marsala|brandy|cognac|whisky|gin\b|vodka|rum\b|sidro|champagne|prosecco)",
    re.IGNORECASE,
)

# IARC (Bouvard et al., Lancet Oncol 2015): carne rossa = muscolo di mammifero
# non lavorato; carne lavorata = salata, stagionata, fermentata, affumicata...
CARNE_ROSSA_RE = _parole(
    "bovin", "manzo", "vitell", "vacca", "bue", "scottona", "suin", "maiale", "lonza", "lonzino",
    "agnell", "ovin", "montone", "pecora", "capra", "capretto", "cavall", "equin", "asin", "puledro",
    "coniglio", "lepre", "cinghiale", "cervo", "capriolo", "daino", "hamburger",
)
CARNE_LAVORATA_RE = _parole(
    "prosciutt", "salam", "salsicc", "mortadell", "w[uü]rstel", "speck", "pancetta", "bresaola", "coppa",
    "culatell", "cotechino", "zampone", "lardo", "guanciale", "'nduja", "nduja", "salum", "carne in scatola",
    "hot dog", "porchetta", "soppressat", "finocchiona", "ciauscolo", "kebab", "corned beef", "capocoll",
    "cicciol", "pat[eè]\\b", "in scatola", "in gelatina",
)
CATEGORIE_CARNE = {"Carne"}

# Organi che non sono tessuto muscolare: per la IARC non sono carne rossa
FRATTAGLIE_RE = _parole("fegato", "rene", "reni", "rognon", "cervell", "animell", "polmon", "milza", "trippa",
                        "coratella", "pancreas")


def e_bevanda(alimento: Alimento) -> bool:
    return alimento.get("categoria") == "Bevande" or bool(BEVANDA_RE.search(_nome(alimento)))


def e_carne_lavorata(alimento: Alimento) -> bool:
    if alimento.get("categoria") not in CATEGORIE_CARNE:
        return False

    return bool(CARNE_LAVORATA_RE.search(_nome(alimento)))


def e_carne_rossa(alimento: Alimento) -> bool:
    if alimento.get("categoria") not in CATEGORIE_CARNE or e_carne_lavorata(alimento):
        return False

    if FRATTAGLIE_RE.search(_nome(alimento)):
        return False

    return bool(CARNE_ROSSA_RE.search(_nome(alimento)))


# ---------------------------------------------------------------
# ZUCCHERI LIBERI (OMS 2015)
# Zuccheri aggiunti più quelli di miele, sciroppi e succhi di frutta;
# non quelli della frutta e della verdura intere né del latte.
# ---------------------------------------------------------------

SUCCO_RE = _parole("succo", "spremuta", "nettare", "sciropp", "miele", "zucchero", "marmellat", "confettur",
                   "candit", "caramell", "glassat", "zuccherat")
CATEGORIE_ZUCCHERI_INTRINSECI = {"Frutta", "Verdura", "Legumi/Frutta Secca", "Carne", "Pesce"}
LATTICINI_DOLCI_RE = _parole("alla frutta", "con frutta", "(?<!non )zuccherat", "gelat", "budino",
                             "panna cotta", "dessert", "condensato", "aromatizzat", "dolcificat", "al cacao",
                             "cioccolat")


def zuccheri_liberi(alimento: Alimento) -> float | None:
    """
    Grammi di zuccheri liberi per 100 g (stima prudente): tutti gli zuccheri
    per succhi, miele, sciroppi e alimenti trasformati; nessuno per frutta,
    verdura, legumi, carne e pesce non zuccherati (NOVA 1); per latte e
    latticini non dolcificati si escludono gli zuccheri del latte.
    """
    zuccheri = alimento.get("zuccheri")

    if zuccheri is None:
        return None

    nome = _nome(alimento)

    if SUCCO_RE.search(nome):
        return float(zuccheri)

    nova = alimento.get("nova")
    categoria = alimento.get("categoria")

    if categoria == "Latticini e Uova":
        if LATTICINI_DOLCI_RE.search(nome):
            lattosio = alimento.get("lattosio") or 0
            return max(float(zuccheri) - lattosio, 0.0)

        return 0.0

    if nova == 1 or (nova is None and categoria in CATEGORIE_ZUCCHERI_INTRINSECI):
        return 0.0

    return float(zuccheri)


# ---------------------------------------------------------------
# NOVA (Monteiro et al., Public Health Nutr 2019)
# Regole per nome e categoria; le ricette (piatti preparati in casa con
# ingredienti dei gruppi 1-3) non hanno un gruppo.
# ---------------------------------------------------------------

NOVA_4_RE = _parole(
    "merendin", "snack", "patatine", "chips", "crackers?", "grissin", "fette biscottate", "biscott",
    "cornflakes", "corn flakes", "fiocchi di (?:mais|riso|frumento)", "cereali per la colazione", "muesli",
    "cornett", "brioche", "croissant", "pandoro", "panettone", "colomba", "wafer", "barrett", "crema spalmabile",
    "nutella", "cioccolat", "caramell", "gomma da masticare", "confett[io]", "torron", "gelat", "budino",
    "bibit", "cola\\b", "aranciata", "chinotto", "gassosa", "acqua tonica", "energy drink",
    "w[uü]rstel", "hot dog", "mortadell", "hamburger", "nuggets?", "bastoncini", "cotoletta", "surimi",
    "sofficini", "dado", "brodo granulare", "preparato", "margarin", "maionese", "ketchup", "pan carr[eè]",
    "pancarr[eè]", "pan bauletto", "piadina", "tramezzin", "pizza surgelat", "burger", "zucchero a velo",
    "sciroppo di glucosio",
    "yogurt alla", "yogurt aromatizzat", "formaggino", "formaggio fuso", "sottiletta", "latte condensato",
    "latte in polvere", "panna spray", "kebab",
)
NOVA_3_RE = _parole(
    "formagg", "parmigian", "grana", "pecorino", "mozzarell", "ricotta", "provolon", "gorgonzola", "fontina",
    "asiago", "emment", "caciocavall", "scamorza", "stracchino", "crescenza", "mascarpone", "taleggio",
    "brie", "camembert", "cheddar", "edam", "feta", "caciott", "cacioricott", "fior di latte", "burrin",
    "butirro", "dolce verde", "italico", "latteria", "robiola", "groviera", "gruy[eè]re", "montasio",
    "capocoll", "cicciol", "pat[eè]\\b", "marinat", "bottarga", "caviale", "panin", "burro d'arachid",
    "crusca di frumento, bastoncini",
    "prosciutt", "salam", "salsicc", "speck", "pancetta", "bresaola", "coppa", "culatell", "cotechino",
    "zampone", "lardo", "guanciale", "nduja", "porchetta", "soppressat", "finocchiona", "salum",
    "pane", "focaccia", "pizza", "in scatola", "sott'olio", "sottolio", "sott'aceto", "sottaceto",
    "sotto sale", "sotto aceto", "sciroppat", "candit", "marmellat", "confettur", "conserv", "affumicat",
    "baccal", "stoccafisso", "acciughe salate", "salat[oiae]\\b", "birra", "vino", "spumante", "sidro",
    "prosecco", "champagne", "marsala", "vermouth", "tofu", "olive", "capperi", "tonno sott", "frutta secca salata",
)
NOVA_2_RE = _parole(
    "olio", "burro", "strutto", "lardo fuso", "zucchero", "miele", "sale\\b", "aceto", "sciroppo d'acero",
    "fecola", "amido",
)
CATEGORIE_NOVA_1 = {"Frutta", "Verdura", "Legumi/Frutta Secca", "Carne", "Pesce", "Cereali", "Latticini e Uova",
                    "Bevande"}


def gruppo_nova(alimento: Alimento) -> int | None:
    """
    Gruppo NOVA 1-4 per un alimento generico, None per ricette e casi incerti.
    Per gli alimenti confezionati il gruppo viene da Open Food Facts.
    """
    nome = _nome(alimento)
    categoria = alimento.get("categoria")

    if categoria == "Piatti e ricette":
        return None

    if NOVA_4_RE.search(nome):
        return 4

    if (alimento.get("alcol") or 0) >= 1 and not NOVA_3_RE.search(nome):
        # Bevande alcoliche distillate (gruppo 4), fermentate (gruppo 3)
        return 4

    if NOVA_3_RE.search(nome):
        return 3

    if NOVA_2_RE.search(nome) or categoria == "Grassi e Oli":
        return 2

    if categoria in CATEGORIE_NOVA_1:
        return 1

    return None


# ---------------------------------------------------------------
# FODMAP
# Quantitativi: soglie per porzione di Varney et al. (J Gastroenterol
# Hepatol 2017): oligosaccaridi 0,3 g, lattosio 1 g, fruttosio in eccesso
# sul glucosio 0,15 g. Qualitativi: alimenti di base ricchi di ciascun FODMAP
# nelle diete occidentale e mediterranea (Sultan et al., J Neurogastroenterol
# Motil 2022, tabella 3).
# ---------------------------------------------------------------

SOGLIA_OLIGOSACCARIDI = 0.3
SOGLIA_LATTOSIO = 1.0
SOGLIA_FRUTTOSIO_ECCESSO = 0.15

FODMAP_ALTI = {
    "fodmap_gos": _parole("lenticchi", "ceci", "fave\\b", "fagioli\\b", "fagioli (?!verdi)", "pistacchi",
                          "mandorl", "soia\\b", "lupini"),
    "fodmap_fruttani": _parole("cipoll", "aglio", "scalogn", "porr", "melagran", "anguria", "cocomero",
                               "zucchin", "pistacchi", "frumento", "grano(?! saraceno)", "semola", "farina di grano",
                               "farina 0", "farina tipo", "pane(?! di (?:riso|mais))", "pasta(?! di (?:riso|mais))",
                               "pizza", "crackers?", "grissin", "fette biscottate", "cous ?cous", "bulgur", "segale",
                               "orzo\\b", "carciof", "asparag", "topinambur"),
    "fodmap_fruttosio": _parole("mango", "anguria", "cocomero", "fichi", "miele", "marmellat", "confettur"),
    "fodmap_lattosio": _parole("latte(?! di (?:cocco|mandorl|soia|riso|avena))"),
    "fodmap_polioli": _parole("patate? (?:dolc|american)", "batat", "avocado", "funghi", "fungo", "champignon",
                              "porcini", "anguria", "cocomero", "melanzan", "mel[ae]\\b", "peperon[ei] verd",
                              "cavolfior"),
}

# Alimenti di base a basso contenuto di FODMAP (stessa tabella)
FODMAP_BASSI_RE = _parole(
    "riso(?! soffiato)", "arachid", "pomodor", "cetriol", "spinac", "peperon[ei] ross", "olive", "olio d'oliva",
    "olio extra", "patat(?:a|e)(?! (?:dolc|american))", "vino",
)

# Alimenti di origine animale senza carboidrati: nessun FODMAP
CATEGORIE_SENZA_FODMAP = {"Carne", "Pesce"}


def _per_porzione(alimento: Alimento, campo: str) -> float | None:
    valore = alimento.get(campo)

    if valore is None:
        return None

    porzione = alimento.get("porzione") or 100
    return float(valore) * float(porzione) / 100


def fodmap(alimento: Alimento, altri: dict[str, float | None] | None = None) -> dict[str, str | None]:
    """
    Livelli FODMAP ("Basso"/"Alto", None se non documentato) per categoria.
    altri: valori della fonte non salvati nel database (fos, raffinosio per 100 g).
    """
    nome = _nome(alimento)
    altri = altri or {}
    livelli: dict[str, str | None] = dict.fromkeys(FODMAP_ALTI)

    carboidrati = alimento.get("carboidrati")
    fibre = alimento.get("fibre")
    senza_carboidrati = (carboidrati is not None and carboidrati <= 0 and not fibre)

    if senza_carboidrati or FODMAP_BASSI_RE.search(nome) or (
        alimento.get("categoria") in CATEGORIE_SENZA_FODMAP and not carboidrati
    ):
        livelli = dict.fromkeys(FODMAP_ALTI, "Basso")

    for campo, espressione in FODMAP_ALTI.items():
        if espressione.search(nome):
            livelli[campo] = "Alto"

    # Valori misurati: prevalgono sulle liste
    lattosio = _per_porzione(alimento, "lattosio")

    if lattosio is not None:
        livelli["fodmap_lattosio"] = "Alto" if lattosio > SOGLIA_LATTOSIO else "Basso"

    fruttosio = _per_porzione(alimento, "fruttosio")
    glucosio = _per_porzione(alimento, "glucosio")

    if fruttosio is not None and glucosio is not None:
        livelli["fodmap_fruttosio"] = "Alto" if fruttosio - glucosio > SOGLIA_FRUTTOSIO_ECCESSO else "Basso"

    porzione = float(alimento.get("porzione") or 100)

    for chiave, campo in (("fos", "fodmap_fruttani"), ("raffinosio", "fodmap_gos")):
        valore = altri.get(chiave)

        if valore is not None and valore * porzione / 100 > SOGLIA_OLIGOSACCARIDI:
            livelli[campo] = "Alto"

    return livelli


# ---------------------------------------------------------------
# INDICE GLICEMICO
# Valori della tabella 1 di Atkinson, Foster-Powell e Brand-Miller,
# Diabetes Care 2008, assegnati agli alimenti CREA corrispondenti
# (file dati/indice_glicemico.csv: codice CREA, IG, voce della tabella).
# ---------------------------------------------------------------

class IndiceGlicemico(NamedTuple):
    valore: float
    voce: str                 # descrizione della voce (o delle voci) di Atkinson 2008
    voci_appendice: str = ""  # numeri delle voci della tabella A1 dell'appendice; vuoto = tabella 1


@cache
def indici_glicemici() -> dict[str, IndiceGlicemico]:
    """
    {codice CREA: indice glicemico} da dati/indice_glicemico.csv: tabella 1 di
    Atkinson 2008 (alimenti comuni, medie di più studi) o, dove manca,
    tabella A1 dell'appendice (singoli studi, media delle voci scelte).
    """
    percorso = CARTELLA_DATI / "indice_glicemico.csv"

    if not percorso.is_file():
        return {}

    with percorso.open(encoding="utf-8", newline="") as f:
        return {
            riga["codice_crea"]: IndiceGlicemico(
                float(riga["indice_glicemico"]), riga["voce_tabella"], (riga.get("voci_appendice") or "").strip(),
            )
            for riga in csv.DictReader(f)
            if riga.get("codice_crea") and riga.get("indice_glicemico")
        }


def indice_glicemico(alimento: Alimento) -> IndiceGlicemico | None:
    codice = alimento.get("codice_crea")
    return indici_glicemici().get(str(codice)) if codice else None


def classifica(alimento: dict[str, Any], altri: dict[str, float | None] | None = None) -> dict[str, Any]:
    """
    Campi classificati da aggiungere a un alimento importato da una fonte:
    NOVA (se manca), FODMAP (dove documentati) e indice glicemico (CREA).
    """
    risultato: dict[str, Any] = {}

    if alimento.get("nova") is None:
        risultato["nova"] = gruppo_nova(alimento)

    for campo, livello in fodmap({**alimento, **risultato}, altri).items():
        if livello is not None:
            risultato[campo] = livello

    ig = indice_glicemico(alimento)

    if ig is not None:
        risultato["indice_glicemico"] = ig.valore

    return risultato
