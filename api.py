"""
API REST in sola lettura (JSON).

    GET /api                      indice delle risorse
    GET /api/alimenti             elenco con filtri (anche a intervallo), ricerca,
                                  ordinamento multiplo e paginazione
    GET /api/alimenti/<id>        un alimento con i valori derivati
    GET /api/categorie            categorie con il numero di alimenti

Stessi permessi della consultazione web: pubblica, oppure con login se
ACCESSO_PUBBLICO=false (in quel caso senza sessione si riceve 401 JSON).

I messaggi (errori, descrizione dei parametri) seguono la lingua della
richiesta: intestazione Accept-Language o cookie della lingua scelta nel
sito. Chiavi e valori dei dati (categorie, livelli) restano in italiano.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, jsonify, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from werkzeug.exceptions import HTTPException

import analisi
import archivio
import importazione
import lingue
import nutrienti
import ricette
from lingue import N_

bp = Blueprint("api", __name__, url_prefix="/api")

VERSIONE_API = 1
LIMITE_PREDEFINITO = 100
LIMITE_MASSIMO = 500

# Campi restituiti per ogni alimento, nell'ordine delle colonne esportate
CAMPI = ("id", *importazione.CAMPI, "aggiornato_il")


def serializza(alimento: archivio.Alimento) -> dict[str, Any]:
    """
    Alimento in JSON: i campi del database più punteggio e valori derivati.
    """
    livello = analisi.livello_punteggio(alimento.get("punteggio"))
    fodmap = nutrienti.fodmap_complessivo(alimento)
    nova = nutrienti.gruppo_nova(alimento)

    return {
        **{campo: alimento.get(campo) for campo in CAMPI},
        "ingredienti": ricette.leggi_ingredienti(alimento.get("ingredienti")),
        "punteggio": alimento.get("punteggio"),
        "livello_medio": livello["etichetta"] if alimento.get("punteggio") is not None else None,
        "carico_glicemico": nutrienti.carico_glicemico(alimento),
        "fodmap_complessivo": fodmap["etichetta"] if fodmap else None,
        "nova_descrizione": nova["etichetta"] if nova else None,
        "url": url_for("pagine.scheda", alimento_id=alimento["id"], _external=True),
    }


def _intero(nome: str, predefinito: int, minimo: int, massimo: int | None = None) -> int:
    testo = request.args.get(nome)

    if testo is None or testo == "":
        return predefinito

    try:
        valore = int(testo)
    except ValueError:
        abort(400, description=_("%(nome)s: serve un numero intero.", nome=nome))

    if valore < minimo or (massimo is not None and valore > massimo):
        if massimo is not None:
            intervallo = _("tra %(minimo)d e %(massimo)d", minimo=minimo, massimo=massimo)
        else:
            intervallo = _("da %(minimo)d in su", minimo=minimo)
        abort(400, description=_("%(nome)s: valore fuori intervallo (%(intervallo)s).",
                                 nome=nome, intervallo=intervallo))

    return valore


@bp.get("")
def indice() -> ResponseReturnValue:
    return jsonify({
        "versione": VERSIONE_API,
        "risorse": {
            "alimenti": url_for("api.elenco_alimenti", _external=True),
            "alimento": url_for("api.alimento", alimento_id=1, _external=True).replace("/1", "/<id>"),
            "categorie": url_for("api.elenco_categorie", _external=True),
        },
        "parametri_alimenti": {
            "q": _("testo cercato nel nome: anche parziale, senza accenti, singolare o plurale, "
                   "con qualche errore di battitura"),
            "categoria": _("categoria in italiano (uguale, maiuscole indifferenti)"),
            **dict.fromkeys(analisi.CAMPI_RISCHIO, _("livello: Trascurabile, Basso, Medio, Alto")),
            "sicuri": _("1: solo alimenti con tutti i rischi classificati e al massimo Basso"),
            **{
                f"{campo}_{limite}": _("minimo per 100 g (compreso)") if limite == "min"
                else _("massimo per 100 g (compreso)")
                for campo in archivio.CAMPI_INTERVALLO
                for limite, _operatore, _parola in archivio.LIMITI
            },
            "sort": _(
                "fino a %(n)d campi separati da virgole tra: %(campi)s; con q anche %(pertinenza)s (predefinito)",
                n=archivio.ORDINAMENTI_MAX, campi=", ".join(archivio.SORT_EXPRESSIONS), pertinenza=archivio.PERTINENZA,
            ),
            "dir": _("asc oppure desc, una per campo separate da virgole"),
            "limit": _("risultati per pagina, 1-%(massimo)d (predefinito %(predefinito)d)",
                       massimo=LIMITE_MASSIMO, predefinito=LIMITE_PREDEFINITO),
            "offset": _("risultati da saltare (predefinito 0)"),
        },
        "lingua": _("Messaggi nella lingua di Accept-Language (it, en); chiavi e valori dei dati in italiano."),
    })


@bp.get("/alimenti")
def elenco_alimenti() -> ResponseReturnValue:
    filtri, sort, direction = archivio.leggi_filtri(request.args)
    limite = _intero("limit", LIMITE_PREDEFINITO, 1, LIMITE_MASSIMO)
    scarto = _intero("offset", 0, 0)

    alimenti = archivio.get_alimenti(filtri, sort, direction)
    pagina = alimenti[scarto:scarto + limite]

    def collegamento(nuovo_scarto: int) -> str:
        parametri = {**request.args.to_dict(), "limit": str(limite), "offset": str(nuovo_scarto)}
        return url_for("api.elenco_alimenti", _external=True, **parametri)

    return jsonify({
        "totale": len(alimenti),
        "limit": limite,
        "offset": scarto,
        "successiva": collegamento(scarto + limite) if scarto + limite < len(alimenti) else None,
        "precedente": collegamento(max(scarto - limite, 0)) if scarto > 0 else None,
        "risultati": [serializza(a) for a in pagina],
    })


@bp.get("/alimenti/<int:alimento_id>")
def alimento(alimento_id: int) -> ResponseReturnValue:
    trovato = archivio.get_alimento(alimento_id)

    if trovato is None:
        abort(404, description=_("Alimento %(id)d non trovato.", id=alimento_id))

    return jsonify(serializza(trovato))


@bp.get("/categorie")
def elenco_categorie() -> ResponseReturnValue:
    return jsonify([
        {
            "categoria": categoria,
            "alimenti": numero,
            "url": url_for("api.elenco_alimenti", categoria=categoria, _external=True),
        }
        for categoria, numero in archivio.categorie()
    ])


MESSAGGI = {
    400: N_("Richiesta non valida."),
    401: N_("Autenticazione richiesta."),
    403: N_("Accesso negato."),
    404: N_("Risorsa non trovata."),
    405: N_("Metodo non consentito: l'API è in sola lettura."),
}


def errore_json(errore: HTTPException) -> ResponseReturnValue:
    """
    Errori dell'API in JSON: {"errore": ..., "stato": ...}. I messaggi generici
    di Werkzeug diventano quelli di MESSAGGI, nella lingua della richiesta.
    """
    codice = errore.code or 500
    messaggio = errore.description

    if messaggio == type(errore).description and codice in MESSAGGI:
        messaggio = lingue.traduci(MESSAGGI[codice])

    return jsonify({"errore": messaggio, "stato": codice}), codice
