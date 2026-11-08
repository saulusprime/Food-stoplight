"""
API REST in sola lettura (JSON).

    GET /api                      indice delle risorse
    GET /api/alimenti             elenco con filtri (anche a intervallo), ricerca,
                                  ordinamento multiplo e paginazione
    GET /api/alimenti/<id>        un alimento con i valori derivati
    GET /api/categorie            categorie con il numero di alimenti

Stessi permessi della consultazione web: pubblica, oppure con login se
ACCESSO_PUBBLICO=false (in quel caso senza sessione si riceve 401 JSON).
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, jsonify, request, url_for
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import HTTPException

import analisi
import archivio
import importazione
import nutrienti
import ricette

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
        "url": url_for("scheda", alimento_id=alimento["id"], _external=True),
    }


def _intero(nome: str, predefinito: int, minimo: int, massimo: int | None = None) -> int:
    testo = request.args.get(nome)

    if testo is None or testo == "":
        return predefinito

    try:
        valore = int(testo)
    except ValueError:
        abort(400, description=f"{nome}: serve un numero intero.")

    if valore < minimo or (massimo is not None and valore > massimo):
        intervallo = f"tra {minimo} e {massimo}" if massimo is not None else f"da {minimo} in su"
        abort(400, description=f"{nome}: valore fuori intervallo ({intervallo}).")

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
            "q": "testo cercato nel nome: anche parziale, senza accenti, singolare o plurale, "
                 "con qualche errore di battitura",
            "categoria": "categoria (uguale, maiuscole indifferenti)",
            **dict.fromkeys(analisi.CAMPI_RISCHIO, "livello: Trascurabile, Basso, Medio, Alto"),
            "sicuri": "1: solo alimenti con tutti i rischi classificati e al massimo Basso",
            **{
                f"{campo}_{limite}": f"{'minimo' if limite == 'min' else 'massimo'} per 100 g (compreso)"
                for campo in archivio.CAMPI_INTERVALLO
                for limite, _operatore, _parola in archivio.LIMITI
            },
            "sort": (
                f"fino a {archivio.ORDINAMENTI_MAX} campi separati da virgole tra: "
                + ", ".join(archivio.SORT_EXPRESSIONS)
                + f"; con q anche {archivio.PERTINENZA} (predefinito)"
            ),
            "dir": "asc oppure desc, una per campo separate da virgole",
            "limit": f"risultati per pagina, 1-{LIMITE_MASSIMO} (default {LIMITE_PREDEFINITO})",
            "offset": "risultati da saltare (default 0)",
        },
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
        abort(404, description=f"Alimento {alimento_id} non trovato.")

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
    400: "Richiesta non valida.",
    401: "Autenticazione richiesta.",
    403: "Accesso negato.",
    404: "Risorsa non trovata.",
    405: "Metodo non consentito: l'API è in sola lettura.",
}


def errore_json(errore: HTTPException) -> ResponseReturnValue:
    """
    Errori dell'API in JSON: {"errore": ..., "stato": ...}. I messaggi generici
    di Werkzeug (in inglese) diventano quelli italiani di MESSAGGI.
    """
    codice = errore.code or 500
    messaggio = errore.description

    if messaggio == type(errore).description:
        messaggio = MESSAGGI.get(codice, messaggio)

    return jsonify({"errore": messaggio, "stato": codice}), codice
