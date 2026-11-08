"""
Livelli dei cinque rischi calcolati dai dati dell'alimento, con regole
documentate (riferimenti in RIFERIMENTI, spiegazione nella pagina Guida).

Scala comune a 4 livelli per i nutrienti da limitare, per 100 g (bevande
per 100 ml), come le indicazioni nutrizionali europee e il semaforo FSA:
    Trascurabile  "senza" (Reg. CE 1924/2006)
    Basso         "a basso contenuto" (Reg. CE 1924/2006) = verde FSA
    Medio         ambra FSA
    Alto          rosso FSA

I livelli si salvano nel database (per filtri, ordinamento ed export) e si
ricalcolano a ogni salvataggio, import o sincronizzazione: non si scrivono
a mano. Un rischio senza dati sufficienti resta "Non classificato".
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from flask_babel import gettext as _

import analisi
import classificazioni
import lingue
import nutrienti
from analisi import Alimento

# ---------------------------------------------------------------
# RIFERIMENTI
# ---------------------------------------------------------------

RIFERIMENTI: dict[str, dict[str, str]] = {
    "ue1924": {
        "breve": "Reg. (CE) 1924/2006",
        "citazione": "Regolamento (CE) n. 1924/2006 relativo alle indicazioni nutrizionali e sulla salute "
                     "fornite sui prodotti alimentari, allegato (indicazioni «senza» e «a basso contenuto»).",
        "url": "https://eur-lex.europa.eu/legal-content/IT/ALL/?uri=CELEX:32006R1924",
    },
    "fsa": {
        "breve": "FSA 2016",
        "citazione": "Department of Health, Food Standards Agency. Guide to creating a front of pack (FoP) "
                     "nutrition label for pre-packed products sold through retail outlets. 2016.",
        "url": "https://www.gov.uk/government/publications/front-of-pack-nutrition-labelling-guidance",
    },
    "atkinson2008": {
        "breve": "Atkinson et al. 2008",
        "citazione": "Atkinson FS, Foster-Powell K, Brand-Miller JC. International tables of glycemic index "
                     "and glycemic load values: 2008. Diabetes Care 2008;31(12):2281-2283.",
        "url": "https://doi.org/10.2337/dc08-1239",
    },
    "carico_glicemico": {
        "breve": "GI Foundation, Università di Sydney",
        "citazione": "Glycemic Index Foundation (University of Sydney). Soglie del carico glicemico per porzione: "
                     "fino a 10 basso, 11-19 medio, da 20 alto.",
        "url": "https://glycemicindex.com/2019/08/perspectives-with-dr-alan-barclay-7",
    },
    "oms_zuccheri": {
        "breve": "OMS 2015",
        "citazione": "World Health Organization. Guideline: sugars intake for adults and children. Geneva, 2015.",
        "url": "https://www.who.int/publications/i/item/9789241549028",
    },
    "reynolds2019": {
        "breve": "Reynolds et al. 2019",
        "citazione": "Reynolds A, Mann J, Cummings J, et al. Carbohydrate quality and human health: a series of "
                     "systematic reviews and meta-analyses. Lancet 2019;393(10170):434-445.",
        "url": "https://doi.org/10.1016/S0140-6736(18)31809-9",
    },
    "efsa_grassi": {
        "breve": "EFSA 2010",
        "citazione": "EFSA Panel on Dietetic Products, Nutrition, and Allergies. Scientific Opinion on Dietary "
                     "Reference Values for fats. EFSA Journal 2010;8(3):1461.",
        "url": "https://doi.org/10.2903/j.efsa.2010.1461",
    },
    "larn2014": {
        "breve": "LARN 2014",
        "citazione": "SINU. LARN - Livelli di assunzione di riferimento di nutrienti ed energia per la "
                     "popolazione italiana, IV revisione, 2014 (colesterolo: meno di 300 mg al giorno).",
        "url": "https://sinu.it/tabelle-larn-2014/",
    },
    "varney2017": {
        "breve": "Varney et al. 2017",
        "citazione": "Varney J, Barrett J, Scarlata K, et al. FODMAPs: food composition, defining cutoff values "
                     "and international application. J Gastroenterol Hepatol 2017;32 Suppl 1:53-61.",
        "url": "https://doi.org/10.1111/jgh.13698",
    },
    "sultan2022": {
        "breve": "Sultan et al. 2022",
        "citazione": "Sultan N, Varney JE, Halmos EP, et al. How to implement the 3-phase FODMAP diet into "
                     "gastroenterological practice. J Neurogastroenterol Motil 2022;28(3):343-356.",
        "url": "https://doi.org/10.5056/jnm22035",
    },
    "wcrf2007": {
        "breve": "WCRF/AICR 2007",
        "citazione": "World Cancer Research Fund / American Institute for Cancer Research. Food, Nutrition, "
                     "Physical Activity, and the Prevention of Cancer: a Global Perspective. 2007 "
                     "(densità energetica: obiettivo 125 kcal/100 g, alimenti densi oltre 225-275 kcal/100 g).",
        "url": "https://www.wcrf.org/wp-content/uploads/2021/02/Recommendations.pdf",
    },
    "wcrf2018": {
        "breve": "WCRF/AICR 2018",
        "citazione": "World Cancer Research Fund / American Institute for Cancer Research. Diet, Nutrition, "
                     "Physical Activity and Cancer: a Global Perspective. Continuous Update Project Expert "
                     "Report 2018.",
        "url": "https://www.wcrf.org/diet-activity-and-cancer/",
    },
    "iarc_carni": {
        "breve": "IARC 2015",
        "citazione": "Bouvard V, Loomis D, Guyton KZ, et al. Carcinogenicity of consumption of red and processed "
                     "meat. Lancet Oncol 2015;16(16):1599-1600 (IARC Monographs vol. 114).",
        "url": "https://doi.org/10.1016/S1470-2045(15)00444-1",
    },
    "iarc_alcol": {
        "breve": "IARC, vol. 100E",
        "citazione": "IARC Monographs on the Evaluation of Carcinogenic Risks to Humans, vol. 100E (2012): "
                     "consumption of alcoholic beverages, gruppo 1.",
        "url": "https://publications.iarc.who.int/122",
    },
    "fiolet2018": {
        "breve": "Fiolet et al. 2018",
        "citazione": "Fiolet T, Srour B, Sellem L, et al. Consumption of ultra-processed foods and cancer risk: "
                     "results from NutriNet-Santé prospective cohort. BMJ 2018;360:k322.",
        "url": "https://doi.org/10.1136/bmj.k322",
    },
    "monteiro2019": {
        "breve": "Monteiro et al. 2019",
        "citazione": "Monteiro CA, Cannon G, Levy RB, et al. Ultra-processed foods: what they are and how to "
                     "identify them. Public Health Nutr 2019;22(5):936-941.",
        "url": "https://doi.org/10.1017/S1368980018003762",
    },
}

# ---------------------------------------------------------------
# SOGLIE (per 100 g; bevande per 100 ml)
# (senza, basso, alto): fino a "senza" Trascurabile, fino a "basso" Basso,
# fino ad "alto" Medio, oltre Alto
# ---------------------------------------------------------------

SOGLIE_ZUCCHERI = (0.5, 5.0, 22.5)
SOGLIE_ZUCCHERI_BEVANDE = (0.5, 2.5, 11.25)
SOGLIE_SATURI = (0.1, 1.5, 5.0)
SOGLIE_SATURI_BEVANDE = (0.1, 0.75, 2.5)

# Carico glicemico per porzione: fino a 5 Trascurabile (metà della soglia
# "basso": convenzione dell'app), fino a 10 Basso, 11-19 Medio, da 20 Alto
SOGLIE_CARICO = (5.0, 10.0, 20.0)

FIBRE_FONTE = 3.0        # "fonte di fibre" (Reg. CE 1924/2006)
FIBRE_ALTO = 6.0         # "ad alto contenuto di fibre"
COLESTEROLO_GIORNO = 300  # mg al giorno (LARN 2014)
ALCOL_BEVANDA = 1.0      # g per 100 g: circa 1,2 % vol, soglia delle bevande alcoliche (Reg. UE 1169/2011)
SALE_ALTO = 1.5          # g per 100 g (rosso FSA)
SODIO_PER_SALE = 2.5     # sale = sodio × 2,5

# Densità energetica (WCRF/AICR 2007): fino a 125 kcal/100 g Trascurabile,
# fino a 225 Basso, 225-275 Medio, oltre 275 Alto
SOGLIE_DENSITA = (125.0, 225.0, 275.0)

TRASCURABILE, BASSO, MEDIO, ALTO = range(4)


def fascia(valore: float, soglie: tuple[float, float, float]) -> int:
    senza, basso, alto = soglie

    if valore <= senza:
        return TRASCURABILE

    if valore <= basso:
        return BASSO

    if valore <= alto:
        return MEDIO

    return ALTO


def _fascia_carico(carico: float) -> int:
    senza, basso, alto = SOGLIE_CARICO

    if carico <= senza:
        return TRASCURABILE

    if carico <= basso:
        return BASSO

    return MEDIO if carico < alto else ALTO


def _n(valore: float, decimali: int = 1) -> str:
    testo = f"{valore:.{decimali}f}"

    if decimali and "." in testo:
        testo = testo.rstrip("0").rstrip(".")

    return lingue.decimale(testo)


class Esito:
    """
    Livello (0-3, None = non classificato), motivi e chiavi dei riferimenti.
    """

    def __init__(self) -> None:
        self.livello: int | None = None
        self.motivi: list[str] = []
        self.fonti: list[str] = []

    def alza(self, livello: int, motivo: str, *fonti: str) -> None:
        self.livello = livello if self.livello is None else max(self.livello, livello)
        self.motivi.append(motivo)
        self.fonti.extend(f for f in fonti if f not in self.fonti)

    def abbassa(self, motivo: str, *fonti: str) -> None:
        if self.livello:
            self.livello -= 1
            self.motivi.append(motivo)
            self.fonti.extend(f for f in fonti if f not in self.fonti)


def _numero(alimento: Alimento, campo: str) -> float | None:
    """
    Valore numerico di un campo; None se manca o non è un numero (form con errori).
    """
    valore = alimento.get(campo)

    if valore is None or valore == "" or isinstance(valore, bool):
        return None

    try:
        return float(valore)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------
# REGOLE
# ---------------------------------------------------------------

def _diabete(a: Alimento) -> Esito:
    esito = Esito()
    porzione = nutrienti.porzione(a)
    carboidrati = _numero(a, "carboidrati")
    ig = _numero(a, "indice_glicemico")
    liberi = classificazioni.zuccheri_liberi(a)
    bevanda = classificazioni.e_bevanda(a)

    if carboidrati is not None:
        nella_porzione = carboidrati * porzione / 100

        if ig is not None:
            carico = ig * nella_porzione / 100
            esito.alza(
                _fascia_carico(carico),
                _("Carico glicemico della porzione (%(grammi)s g): %(carico)s, con indice glicemico %(ig)s.",
                  grammi=_n(porzione, 0), carico=_n(carico), ig=_n(ig, 0)),
                "carico_glicemico", "atkinson2008",
            )
        elif nella_porzione <= SOGLIE_CARICO[1]:
            # Con IG al massimo 100 il carico non supera i carboidrati della porzione
            esito.alza(
                _fascia_carico(nella_porzione),
                _("Carboidrati della porzione (%(grammi)s g): %(carboidrati)s g, quindi carico glicemico "
                  "al massimo %(carboidrati)s anche senza conoscere l'indice glicemico.",
                  grammi=_n(porzione, 0), carboidrati=_n(nella_porzione)),
                "carico_glicemico",
            )
        else:
            esito.alza(
                _fascia_carico(nella_porzione),
                _("Indice glicemico non disponibile: stima prudente con il carico massimo possibile "
                  "della porzione (%(grammi)s g), %(carboidrati)s.",
                  grammi=_n(porzione, 0), carboidrati=_n(nella_porzione)),
                "carico_glicemico",
            )

    if liberi is not None and liberi > 0:
        soglie = SOGLIE_ZUCCHERI_BEVANDE if bevanda else SOGLIE_ZUCCHERI
        esito.alza(
            fascia(liberi, soglie),
            _("Zuccheri liberi: %(grammi)s g per 100 %(unita)s.", grammi=_n(liberi), unita="ml" if bevanda else "g"),
            "oms_zuccheri", "ue1924", "fsa",
        )
    elif liberi is not None and esito.livello is None:
        esito.alza(TRASCURABILE, _("Nessuno zucchero libero."), "oms_zuccheri")

    fibre = _numero(a, "fibre")

    if fibre is not None and fibre >= FIBRE_ALTO:
        esito.abbassa(
            _("Ricco di fibre (%(grammi)s g per 100 g): un livello in meno.", grammi=_n(fibre)),
            "ue1924", "reynolds2019",
        )

    return esito


def _colesterolo(a: Alimento) -> Esito:
    esito = Esito()
    bevanda = classificazioni.e_bevanda(a)
    saturi = _numero(a, "grassi_saturi")
    grassi = _numero(a, "grassi")

    if saturi is None and grassi is not None and grassi <= SOGLIE_SATURI[1]:
        # I saturi non superano i grassi totali
        saturi = grassi

    if saturi is not None:
        esito.alza(
            fascia(saturi, SOGLIE_SATURI_BEVANDE if bevanda else SOGLIE_SATURI),
            _("Grassi saturi: %(grammi)s g per 100 %(unita)s.", grammi=_n(saturi), unita="ml" if bevanda else "g"),
            "efsa_grassi", "ue1924", "fsa",
        )

    colesterolo = _numero(a, "colesterolo")

    if colesterolo is not None:
        nella_porzione = colesterolo * nutrienti.porzione(a) / 100

        if nella_porzione >= COLESTEROLO_GIORNO:
            esito.alza(
                MEDIO,
                _("Colesterolo: %(mg)s mg nella porzione, quanto il limite giornaliero di 300 mg.",
                  mg=_n(nella_porzione, 0)),
                "larn2014",
            )

    return esito


def _malassorbimento(a: Alimento) -> Esito:
    esito = Esito()
    porzione = nutrienti.porzione(a)
    fruttosio = _numero(a, "fruttosio")
    glucosio = _numero(a, "glucosio")
    zuccheri = _numero(a, "zuccheri")
    soglia = classificazioni.SOGLIA_FRUTTOSIO_ECCESSO

    if fruttosio is None and zuccheri is not None and zuccheri * porzione / 100 <= soglia:
        # Il fruttosio non supera gli zuccheri totali
        fruttosio = zuccheri

    if fruttosio is None:
        if a.get("fodmap_fruttosio") == "Alto":
            esito.alza(ALTO, _("Alimento ricco di fruttosio in eccesso secondo la letteratura "
                               "(quantità non disponibile)."), "sultan2022")

        return esito

    nella_porzione_f = fruttosio * porzione / 100

    if nella_porzione_f <= soglia:
        esito.alza(
            TRASCURABILE,
            _("Fruttosio nella porzione (%(grammi)s g): %(fruttosio)s g, sotto la soglia di 0,15 g.",
              grammi=_n(porzione, 0), fruttosio=_n(nella_porzione_f, 2)),
            "varney2017",
        )
        return esito

    if glucosio is None:
        if a.get("fodmap_fruttosio") == "Alto":
            esito.alza(ALTO, _("Alimento ricco di fruttosio in eccesso secondo la letteratura."), "sultan2022")

        return esito

    eccesso = (fruttosio - glucosio) * porzione / 100

    if eccesso <= 0:
        esito.alza(
            BASSO,
            _("Fruttosio (%(fruttosio)s g nella porzione) bilanciato dal glucosio: si assorbe insieme.",
              fruttosio=_n(nella_porzione_f, 2)),
            "varney2017",
        )
    elif eccesso <= soglia:
        esito.alza(
            BASSO,
            _("Fruttosio in eccesso sul glucosio: %(eccesso)s g nella porzione (%(grammi)s g), "
              "sotto la soglia di 0,15 g.", eccesso=_n(eccesso, 2), grammi=_n(porzione, 0)),
            "varney2017",
        )
    elif eccesso <= 2 * soglia:
        esito.alza(
            MEDIO,
            _("Fruttosio in eccesso sul glucosio: %(eccesso)s g nella porzione (%(grammi)s g), oltre la "
              "soglia di 0,15 g; con mezza porzione si resta sotto.", eccesso=_n(eccesso, 2), grammi=_n(porzione, 0)),
            "varney2017",
        )
    else:
        esito.alza(
            ALTO,
            _("Fruttosio in eccesso sul glucosio: %(eccesso)s g nella porzione (%(grammi)s g), "
              "oltre il doppio della soglia di 0,15 g.", eccesso=_n(eccesso, 2), grammi=_n(porzione, 0)),
            "varney2017",
        )

    return esito


def _metabolico(a: Alimento) -> Esito:
    esito = Esito()

    if classificazioni.e_bevanda(a):
        # La densità energetica non vale per le bevande (WCRF): contano gli zuccheri
        liberi = classificazioni.zuccheri_liberi(a)

        if liberi is not None:
            esito.alza(
                fascia(liberi, SOGLIE_ZUCCHERI_BEVANDE),
                _("Bevanda con %(grammi)s g di zuccheri liberi per 100 ml.", grammi=_n(liberi)),
                "oms_zuccheri", "wcrf2018", "fsa",
            )

        return esito

    kcal = _numero(a, "kcal")

    if kcal is not None and kcal > 0:
        esito.alza(
            fascia(kcal, SOGLIE_DENSITA),
            _("Densità energetica: %(kcal)s kcal per 100 g.", kcal=_n(kcal, 0)),
            "wcrf2007",
        )

    liberi = classificazioni.zuccheri_liberi(a)

    if liberi is not None and liberi > SOGLIE_ZUCCHERI[2]:
        esito.alza(ALTO, _("Zuccheri liberi: %(grammi)s g per 100 g.", grammi=_n(liberi)), "oms_zuccheri", "fsa")

    return esito


def _tumorale(a: Alimento) -> Esito:
    esito = Esito()
    alcol = _numero(a, "alcol")

    if alcol is not None and alcol >= ALCOL_BEVANDA:
        esito.alza(ALTO, _("Contiene alcol (%(grammi)s g per 100 g): cancerogeno del gruppo 1 IARC.",
                           grammi=_n(alcol)), "iarc_alcol")

    if classificazioni.e_carne_lavorata(a):
        esito.alza(ALTO, _("Carne lavorata: cancerogeno del gruppo 1 IARC."), "iarc_carni")
    elif classificazioni.e_carne_rossa(a):
        esito.alza(MEDIO, _("Carne rossa: probabile cancerogeno (gruppo 2A IARC)."), "iarc_carni")

    sodio = _numero(a, "sodio")

    if sodio is not None and sodio * SODIO_PER_SALE / 1000 > SALE_ALTO:
        esito.alza(MEDIO, _("Sale: %(grammi)s g per 100 g, alto (cibi conservati sotto sale e tumore dello "
                            "stomaco).", grammi=_n(sodio * SODIO_PER_SALE / 1000)), "wcrf2018", "fsa")

    if a.get("nova") == 4:
        esito.alza(MEDIO, _("Alimento ultra-trasformato (NOVA 4)."), "fiolet2018", "monteiro2019")

    if classificazioni.e_bevanda(a):
        liberi = classificazioni.zuccheri_liberi(a)

        if liberi is not None and liberi > SOGLIE_ZUCCHERI_BEVANDE[1]:
            esito.alza(MEDIO, _("Bevanda zuccherata: favorisce l'aumento di peso, fattore di rischio di "
                                "diversi tumori."), "wcrf2018")

    if esito.livello is None:
        fibre = _numero(a, "fibre")

        if fibre is not None and fibre >= FIBRE_FONTE:
            esito.alza(TRASCURABILE, _("Fonte di fibre (%(grammi)s g per 100 g), protettive per il tumore del "
                                       "colon-retto.", grammi=_n(fibre)), "wcrf2018", "ue1924")
        else:
            esito.alza(BASSO, _("Nessun fattore di rischio noto tra quelli valutati."), "wcrf2018")

    return esito


REGOLE = {
    "rischio_diabete": _diabete,
    "rischio_colesterolo": _colesterolo,
    "rischio_malassorbimento": _malassorbimento,
    "rischio_metabolico": _metabolico,
    "rischio_tumorale": _tumorale,
}


# ---------------------------------------------------------------
# USO
# ---------------------------------------------------------------

def valuta(alimento: Alimento) -> dict[str, dict[str, Any]]:
    """
    {campo rischio: {livello (dict di analisi.LIVELLI o NON_CLASSIFICATO), motivi, fonti}}.
    """
    risultato = {}

    for campo, regola in REGOLE.items():
        esito = regola(alimento)
        livello = analisi.LIVELLI[esito.livello] if esito.livello is not None else analisi.NON_CLASSIFICATO
        risultato[campo] = {"livello": livello, "motivi": esito.motivi, "fonti": esito.fonti}

    return risultato


def assegna(valori: MutableMapping[str, Any]) -> None:
    """
    Scrive nei valori dell'alimento le etichette dei cinque livelli
    ("" se il rischio non è classificabile).
    """
    dati = dict(valori)

    for campo, regola in REGOLE.items():
        esito = regola(dati)
        valori[campo] = analisi.LIVELLI[esito.livello]["etichetta"] if esito.livello is not None else ""
