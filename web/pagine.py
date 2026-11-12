"""
Consultazione: tabella degli alimenti (filtri, ricerca, ordinamento,
paginazione), scheda, confronto tra alimenti e guida.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

import analisi
import archivio
import calcoli
import classificazioni
import cofid
import crea
import importazione
import lingue
import nutrienti
import openfoodfacts
import pasti_pronti
import ricerca
import ricette
import rischi
import usda
from archivio import Alimento
from lingue import N_
from web import pasti_pronti as pasti_pronti_web
from web.comune import (
    get_alimenti,
    get_alimento,
    get_stats,
    leggi_filtri,
    trova_alimento_da_modulo,
)

bp = Blueprint("pagine", __name__)


# ---------------------------------------------------------------
# ROUTE PRINCIPALI
# ---------------------------------------------------------------

# Criteri di ordinamento della tabella, con le etichette dei menu
ETICHETTE_ORDINE = {
    archivio.PERTINENZA: N_("Pertinenza alla ricerca"),
    "alimento": N_("Alimento"),
    "categoria": N_("Categoria"),
    "punteggio": N_("Punteggio"),
    "kcal": N_("Kcal"),
    "kcal_nette": N_("Kcal nette"),
    "tef_percent": N_("TEF (%)"),
    "tef_kcal": N_("TEF (Kcal)"),
    "zuccheri": N_("Zuccheri"),
    "fruttosio": N_("Fruttosio"),
    "fibre": N_("Fibre"),
    "rapporto": N_("Rapporto F/F"),
    "grassi_saturi": N_("Grassi saturi"),
    "sodio": N_("Sodio"),
    **dict(analisi.RISCHI),
}


def parametri_vista(filtri: archivio.Filtri, sort: str, direction: str, per_pagina: int | None) -> dict[str, str]:
    """
    Parametri della query string che descrivono la tabella mostrata (pagina
    esclusa): filtri non vuoti, ordinamento e righe per pagina se diversi dal predefinito.
    """
    parametri = {campo: valore for campo, valore in filtri.items() if valore}
    predefinito = archivio.ordinamenti([], [], bool(filtri.get("q")))

    if sort.split(",") != [campo for campo, _ in predefinito] or direction.split(",") != [d for _, d in predefinito]:
        parametri["sort"] = sort
        parametri["dir"] = direction

    if per_pagina != ricerca.PER_PAGINA_PREDEFINITO:
        parametri["per_pagina"] = str(per_pagina) if per_pagina else ricerca.TUTTI

    return parametri


@bp.app_template_global()
def url_tabella(**cambi: Any) -> str:
    """
    Indirizzo della tabella con i parametri correnti più le modifiche
    (valore vuoto o None = togli il parametro). Si torna alla prima pagina
    salvo pagina esplicita.
    """
    parametri = {**g.get("parametri_tabella", {}), **cambi}
    return url_for("pagine.index", **{k: v for k, v in parametri.items() if v not in (None, "")})


def ordine_colonne(criteri: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    """
    Per ogni colonna ordinabile: posizione tra i criteri (1, 2, 3 o None),
    direzione, indirizzo del clic (ordina solo per questa colonna, o ne
    inverte la direzione se è già la prima) e del Maiusc+clic (aggiunge la
    colonna come criterio successivo, o ne inverte la direzione).
    """
    colonne = {}

    for campo in archivio.SORT_EXPRESSIONS:
        posizione = next((i for i, (c, _) in enumerate(criteri) if c == campo), None)
        direzione = criteri[posizione][1] if posizione is not None else None
        nuova = "desc" if posizione == 0 and direzione == "asc" else "asc"

        altri = [(c, d) for c, d in criteri if c != archivio.PERTINENZA]

        if posizione is None:
            altri = [*altri[: archivio.ORDINAMENTI_MAX - 1], (campo, "asc")]
        else:
            altri = [(c, ("desc" if d == "asc" else "asc") if c == campo else d) for c, d in altri]

        colonne[campo] = {
            "posizione": posizione + 1 if posizione is not None else None,
            "direzione": direzione,
            "url": url_tabella(sort=campo, dir=nuova),
            "url_aggiungi": url_tabella(sort=",".join(c for c, _ in altri), dir=",".join(d for _, d in altri)),
        }

    return colonne


@bp.route("/")
def index() -> ResponseReturnValue:
    filtri, sort, direction = leggi_filtri()
    criteri = archivio.ordinamenti(sort.split(","), direction.split(","), bool(filtri["q"]))
    per_pagina = ricerca.leggi_per_pagina(request.args.get("per_pagina"))
    g.parametri_tabella = parametri_vista(filtri, sort, direction, per_pagina)

    # I menu di ordinamento inviano sort e dir ripetuti: indirizzo compatto (sort=categoria,kcal)
    if len(request.args.getlist("sort")) > 1 or len(request.args.getlist("dir")) > 1:
        return redirect(url_tabella(pagina=request.args.get("pagina")))

    alimenti = get_alimenti(filtri, sort, direction)
    filtri_attivi = any(filtri.values())

    # Le medaglie si calcolano sull'intero database, non sugli alimenti filtrati
    tutti = get_alimenti() if filtri_attivi else alimenti
    medaglie = analisi.medaglie_per_alimento(tutti)

    # Grafici e classifiche seguono i filtri, la tabella mostra una pagina
    paginazione = ricerca.pagina(len(alimenti), ricerca.leggi_pagina(request.args.get("pagina")), per_pagina)
    righe = alimenti[paginazione["inizio"]:paginazione["fine"]]

    for a in righe:
        a["medaglie"] = medaglie.get(a["id"], [])
        # Valori per filtri e ordinamento sul dispositivo (static/js/tabella.js)
        a["_rischi"] = "|".join(a.get(campo) or "" for campo in analisi.CAMPI_RISCHIO)
        a["_valori"] = "|".join(
            "" if a.get(campo) is None else repr(float(a[campo])) for campo in archivio.CAMPI_NUMERICI_ORDINABILI
        )

    distribuzione_rischi = analisi.distribuzione_rischi(alimenti)
    opzioni = archivio.get_filter_options()
    intervalli = {
        campo: (filtri[f"{campo}_min"], filtri[f"{campo}_max"])
        for campo in archivio.CAMPI_INTERVALLO
    }

    return render_template(
        "index.html",
        alimenti=righe,
        visualizzati=len(alimenti),
        paginazione=paginazione,
        filtri=filtri,
        filtri_attivi=filtri_attivi,
        intervalli=intervalli,
        intervalli_attivi=sum(1 for coppia in intervalli.values() for valore in coppia if valore),
        campi_intervallo=archivio.CAMPI_INTERVALLO,
        grafico_categorie=analisi.distribuzione_categorie(alimenti),
        grafico_rischi=distribuzione_rischi,
        legenda_rischi=analisi.legenda_rischi(distribuzione_rischi),
        classifiche=[
            (medaglia, analisi.classifica(alimenti, medaglia, 5))
            for medaglia in analisi.MEDAGLIE
        ],
        posti_medaglia=analisi.POSTI_MEDAGLIA,
        parametri_export={
            **{campo: valore for campo, valore in filtri.items() if valore},
            "sort": sort,
            "dir": direction,
        },
        parametri_tabella=g.parametri_tabella,
        vista_dispositivo={
            "parametri": urlencode({k: v for k, v in g.parametri_tabella.items() if k != "per_pagina"}),
            "rischi": analisi.CAMPI_RISCHIO,
            "valori": archivio.CAMPI_NUMERICI_ORDINABILI,
            "intervalli": list(archivio.CAMPI_INTERVALLO),
            "ordinabili": list(archivio.SORT_EXPRESSIONS),
            "ordinamenti_max": archivio.ORDINAMENTI_MAX,
        },
        criteri=criteri,
        colonne=ordine_colonne(criteri),
        opzioni_ordine=[
            (campo, etichetta)
            for campo, etichetta in ETICHETTE_ORDINE.items()
            if campo != archivio.PERTINENZA or filtri["q"]
        ],
        ordinamenti_max=archivio.ORDINAMENTI_MAX,
        per_pagina_opzioni=ricerca.PER_PAGINA,
        tutti_valore=ricerca.TUTTI,
        confronto_max=CONFRONTO_MAX,
        category_options=opzioni["categoria"],
        diabete_options=opzioni["rischio_diabete"],
        colesterolo_options=opzioni["rischio_colesterolo"],
        malassorbimento_options=opzioni["rischio_malassorbimento"],
        metabolic_options=opzioni["rischio_metabolico"],
        tumorale_options=opzioni["rischio_tumorale"],
    )


@bp.route("/alimento/<int:alimento_id>")
def scheda(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    grammi = nutrienti.leggi_grammi(request.args.get("grammi")) or 100.0
    tutti = get_alimenti()
    medaglie = analisi.medaglie_per_alimento(tutti).get(alimento_id, [])

    return render_template(
        "scheda.html",
        item=item,
        rischi=[
            (etichetta, item.get(campo))
            for campo, etichetta in analisi.RISCHI
        ],
        radar=analisi.radar(item),
        medaglie=medaglie,
        posti_medaglia=analisi.POSTI_MEDAGLIA,
        livello=analisi.livello_punteggio(item.get("punteggio")),
        grammi=grammi,
        porzione=nutrienti.per_porzione(item, grammi),
        carico_100=nutrienti.carico_glicemico(item),
        carico_porzione=nutrienti.carico_glicemico(item, grammi),
        disponibili=nutrienti.carboidrati_disponibili(item),
        fodmap=nutrienti.fodmap_complessivo(item),
        nova=nutrienti.gruppo_nova(item),
        alternative=nutrienti.alternative(item, tutti),
        valutazione=rischi.valuta(item),
        riferimenti=rischi.RIFERIMENTI,
        fonti_dati=fonti_alimento(item),
        pasto_pronto=dati_pasto_pronto(alimento_id),
    )


def dati_pasto_pronto(alimento_id: int) -> dict[str, Any] | None:
    """
    Per il piatto di un pasto pronto: ricetta, ingredienti per una porzione
    e fonte; None per gli altri alimenti.
    """
    ricetta = pasti_pronti_web.ricetta_per("alimento_id", alimento_id)

    if ricetta is None:
        return None

    return {
        **ricetta,
        "ingredienti": pasti_pronti_web.ingredienti_porzione(ricetta),
        "fonte_ricetta": pasti_pronti.FONTI.get(ricetta["fonte"], {}),
        "porzioni_max": pasti_pronti.PORZIONI_MAX,
    }


def fonti_alimento(item: Alimento) -> dict[str, Any]:
    """
    Da dove vengono i dati di un alimento, per la scheda: CREA, USDA (e quali
    campi), Open Food Facts, indice glicemico dalla tabella di Atkinson 2008.
    """
    campi_usda = usda.leggi_campi(item.get("campi_usda"))
    campi_cofid = cofid.leggi_campi(item.get("campi_cofid"))
    campi_ricetta = ricette.leggi_campi(item.get("campi_ricetta"))
    indice = classificazioni.indice_glicemico(item)

    def etichette(campi: list[str]) -> list[str]:
        return [lingue.traduci(ETICHETTE_CAMPI.get(c, c)) for c in campi]

    return {
        "crea": crea.URL_SCHEDA.format(codice=item["codice_crea"]) if item.get("codice_crea") else None,
        "usda": usda.url_scheda(item["fdc_id"]) if item.get("fdc_id") else None,
        "campi_usda": etichette(campi_usda),
        "usda_tutti": bool(item.get("fdc_id")) and not campi_usda and not item.get("codice_crea"),
        "cofid": [
            (codice, (cofid.alimenti().get(codice) or {}).get("nome") or "")
            for codice in cofid.leggi_codici(item.get("codice_cofid"))
        ] if campi_cofid else [],
        "cofid_url": cofid.URL,
        "campi_cofid": etichette(campi_cofid),
        "campi_ricetta": etichette(campi_ricetta),
        "ingredienti": ricette.leggi_ingredienti(item.get("ingredienti")),
        "off": openfoodfacts.URL_SCHEDA.format(codice=item["codice_barre"]) if item.get("codice_barre") else None,
        "indice_glicemico": indice if indice and indice.valore == item.get("indice_glicemico") else None,
    }


ETICHETTE_CAMPI = {
    **importazione.ETICHETTE,
    "fruttosio": N_("Fruttosio"),
    "fibre": N_("Fibre"),
    "kcal": N_("Kcal"),
}


# ---------------------------------------------------------------
# CONFRONTO TRA ALIMENTI
# ---------------------------------------------------------------

CONFRONTO_MAX = 4

# Righe numeriche del confronto, per 100 g: (campo, etichetta, unità, decimali)
CONFRONTO_ENERGIA = (
    ("kcal", N_("Kcal"), "", 0),
    ("kcal_nette", N_("Kcal nette"), "", 0),
    ("tef_percent", N_("TEF (%)"), "", 1),
)
CONFRONTO_MACRO = (
    *((campo, etichetta, unita, decimali) for campo, etichetta, unita, decimali, _codice in nutrienti.MACRO[:3]),
    ("fruttosio", N_("di cui fruttosio"), "g", 2),
    *((campo, etichetta, unita, decimali) for campo, etichetta, unita, decimali, _codice in nutrienti.MACRO[3:]),
    ("fibre", N_("Fibre"), "g", 1),
    ("rapporto", N_("Rapporto fruttosio/fibre"), "", 2),
)
CONFRONTO_MICRO = tuple((c, e, u, d) for c, e, u, d, _codice in nutrienti.MICRO)


def ids_confronto(valori: list[str]) -> list[int]:
    """
    ID degli alimenti da confrontare, nell'ordine e senza ripetizioni (anche «1,2,3»).
    """
    ids: list[int] = []

    for valore in valori:
        for parte in valore.split(","):
            parte = parte.strip()

            if parte.isdigit() and int(parte) not in ids:
                ids.append(int(parte))

    return ids


def righe_numeriche(alimenti: list[Alimento], campi: Sequence[tuple[str, str, str, int]]) -> list[dict[str, Any]]:
    """
    Righe di valori del confronto, con la quota di ciascuno sul massimo della
    riga (per le barre); senza le righe in cui manca il dato per tutti.
    """
    righe = []

    for campo, etichetta, unita, decimali in campi:
        valori = [a.get(campo) for a in alimenti]
        numeri = [v for v in valori if v is not None]

        if not numeri:
            continue

        massimo = max(numeri)
        righe.append({
            "etichetta": etichetta,
            "unita": unita,
            "decimali": decimali,
            "valori": [
                (v, v / massimo if v is not None and massimo > 0 else 0.0)
                for v in valori
            ],
        })

    return righe


@bp.route("/confronta")
def confronta() -> ResponseReturnValue:
    """
    Due o più alimenti affiancati (?id=1&id=2...). Dal campo di ricerca
    (cerca) si aggiunge un alimento e si torna all'indirizzo con gli ID.
    """
    ids = ids_confronto(request.args.getlist("id"))

    if "cerca" in request.args:
        item, errore = trova_alimento_da_modulo(request.args)

        if errore or item is None:
            flash(errore or _("Alimento non trovato."), "warning")
        elif item["id"] in ids:
            flash(_("«%(nome)s» è già nel confronto.", nome=item["alimento"]), "info")
        elif len(ids) >= CONFRONTO_MAX:
            flash(
                _("Si possono confrontare al massimo %(n)d alimenti: togline uno prima di aggiungerne un altro.",
                  n=CONFRONTO_MAX),
                "warning",
            )
        else:
            ids.append(item["id"])

        return redirect(url_for("pagine.confronta", id=ids))

    if len(ids) > CONFRONTO_MAX:
        flash(_("Si possono confrontare al massimo %(n)d alimenti: ecco i primi %(n)d.", n=CONFRONTO_MAX), "warning")
        return redirect(url_for("pagine.confronta", id=ids[:CONFRONTO_MAX]))

    trovati = archivio.get_alimenti_per_id(ids)

    if len(trovati) < len(ids):
        flash(_("Alcuni alimenti non sono più nel database e sono stati tolti dal confronto."), "warning")
        return redirect(url_for("pagine.confronta", id=[i for i in ids if i in trovati]))

    alimenti = [trovati[i] for i in ids]

    return render_template(
        "confronto.html",
        alimenti=alimenti,
        ids=ids,
        confronto_max=CONFRONTO_MAX,
        energia=righe_numeriche(alimenti, CONFRONTO_ENERGIA),
        macro=righe_numeriche(alimenti, CONFRONTO_MACRO),
        micro=righe_numeriche(alimenti, CONFRONTO_MICRO),
        indici=[
            {
                "ig": nutrienti.livello_indice_glicemico(a.get("indice_glicemico")),
                "carico": nutrienti.carico_glicemico(a, nutrienti.porzione(a)),
                "porzione": nutrienti.porzione(a),
                "nova": nutrienti.gruppo_nova(a),
                "fodmap": nutrienti.fodmap_complessivo(a),
            }
            for a in alimenti
        ],
        etichette_rischi={campo: importazione.ETICHETTE[campo] for campo in analisi.CAMPI_RISCHIO},
        elenco=archivio.elenco_per_ricerca() if len(alimenti) < CONFRONTO_MAX else [],
    )



@bp.route("/guida")
def guida() -> ResponseReturnValue:
    """
    Legenda dei livelli di rischio e metodologia (punteggio, TEF, indicatori).
    """
    return render_template(
        "guida.html",
        livelli=analisi.LIVELLI,
        non_classificato=analisi.NON_CLASSIFICATO,
        rischi=analisi.RISCHI,
        medaglie=analisi.MEDAGLIE,
        posti_medaglia=analisi.POSTI_MEDAGLIA,
        tef=calcoli.TEF_MACRONUTRIENTI,
        kcal_per_grammo=calcoli.KCAL_PER_GRAMMO,
        cofid_url=cofid.URL,
        cofid_licenza=cofid.URL_LICENZA,
        nova=nutrienti.NOVA.values(),
        livelli_fodmap=nutrienti.LIVELLI_FODMAP,
        fodmap=nutrienti.FODMAP,
        totale_alimenti=get_stats()[0],
    )
