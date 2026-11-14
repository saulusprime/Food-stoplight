"""
Lista della spesa «a semaforo verde» (spesa.py): generata per reparti,
modificabile (cambia, togli, aggiungi), da stampare o scaricare. Resta nella
sessione del browser, come il pasto, e offline nell'ultima copia aperta.
"""

from __future__ import annotations

import random
import secrets
from datetime import date
from typing import Any

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import format_date
from flask_babel import gettext as _

import archivio
import lingue
import profilo
import spesa
from archivio import Alimento
from web.comune import condizioni_utente, get_alimenti, invia_file, trova_alimento_da_modulo

bp = Blueprint("spesa", __name__)

CHIAVE_LISTA = "spesa"
CHIAVE_OPZIONI = "spesa_opzioni"
# Cambia a ogni lista generata o svuotata: le spunte salvate sul dispositivo ripartono da zero
CHIAVE_VERSIONE = "spesa_versione"


def leggi_lista() -> list[int]:
    ids = []

    for valore in session.get(CHIAVE_LISTA, []):
        try:
            ids.append(int(valore))
        except (TypeError, ValueError):
            continue

    return list(dict.fromkeys(ids))[:spesa.VOCI_MAX]


def salva_lista(ids: list[int]) -> None:
    session[CHIAVE_LISTA] = ids[:spesa.VOCI_MAX]


def leggi_opzioni() -> dict[str, Any]:
    opzioni = session.get(CHIAVE_OPZIONI) or {}
    reparti = [r for r in opzioni.get("reparti", []) if isinstance(r, str)] or list(spesa.REPARTI_PREDEFINITI)

    try:
        per_reparto = int(opzioni.get("per_reparto", spesa.PER_REPARTO))
    except (TypeError, ValueError):
        per_reparto = spesa.PER_REPARTO

    return {"reparti": reparti, "per_reparto": max(1, min(per_reparto, spesa.PER_REPARTO_MAX))}


def reparti_disponibili(alimenti: list[Alimento]) -> list[str]:
    return spesa.ordina_reparti(a.get("categoria") or "" for a in alimenti)


@bp.route("/spesa")
def lista() -> ResponseReturnValue:
    condizioni = condizioni_utente()
    tutti = get_alimenti()
    per_id = {a["id"]: a for a in tutti}
    ids = [i for i in leggi_lista() if i in per_id]
    voci = []

    for alimento_id in ids:
        alimento = per_id[alimento_id]
        voce = {
            **alimento,
            "verde": spesa.verde(alimento),
            "per_te": profilo.per_te(alimento, condizioni),
            "alternativa": None,
        }

        if not voce["verde"]:
            alternativa = spesa.sostituto(tutti, alimento, ids, condizioni)
            voce["alternativa"] = alternativa if alternativa and spesa.verde(alternativa) else None

        voci.append(voce)

    return render_template(
        "spesa.html",
        gruppi=spesa.raggruppa(voci),
        voci=len(voci),
        opzioni=leggi_opzioni(),
        reparti=reparti_disponibili(tutti),
        per_reparto_max=spesa.PER_REPARTO_MAX,
        voci_max=spesa.VOCI_MAX,
        versione=session.get(CHIAVE_VERSIONE, ""),
        elenco=archivio.elenco_per_ricerca(),
    )


@bp.route("/spesa/genera", methods=["POST"])
def genera() -> ResponseReturnValue:
    tutti = get_alimenti()
    disponibili = set(reparti_disponibili(tutti))
    reparti = [r for r in request.form.getlist("reparti") if r in disponibili]

    try:
        per_reparto = int(request.form.get("per_reparto") or spesa.PER_REPARTO)
    except ValueError:
        per_reparto = spesa.PER_REPARTO

    per_reparto = max(1, min(per_reparto, spesa.PER_REPARTO_MAX))
    session[CHIAVE_OPZIONI] = {"reparti": reparti, "per_reparto": per_reparto}

    if not reparti:
        flash(_("Scegli almeno un reparto."), "warning")
        return redirect(url_for("spesa.lista"))

    # Ogni volta una lista diversa: i verdi si scelgono a caso nel reparto
    ids = spesa.genera(tutti, reparti, per_reparto, condizioni_utente(), seme=random.randrange(1 << 30))
    salva_lista(ids)
    session[CHIAVE_VERSIONE] = secrets.token_hex(4)

    per_id = {a["id"]: a for a in tutti}
    coperti = {per_id[i].get("categoria") for i in ids}
    vuoti = [lingue.traduci(r) for r in spesa.ordina_reparti(reparti) if r not in coperti]

    flash(_("Lista della spesa pronta: %(n)d alimenti.", n=len(ids)), "success")

    if vuoti:
        flash(_("Niente da proporre senza rischi alti per: %(reparti)s.", reparti=", ".join(vuoti)), "info")

    return redirect(url_for("spesa.lista"))


@bp.route("/spesa/aggiungi", methods=["POST"])
def aggiungi() -> ResponseReturnValue:
    item, errore = trova_alimento_da_modulo(request.form)

    if errore or item is None:
        flash(errore or _("Alimento non trovato."), "danger")
        return redirect(url_for("spesa.lista"))

    ids = leggi_lista()

    if item["id"] in ids:
        flash(_("«%(nome)s» è già nella lista.", nome=item["alimento"]), "info")
    elif len(ids) >= spesa.VOCI_MAX:
        flash(_("La lista può contenere al massimo %(n)d alimenti.", n=spesa.VOCI_MAX), "warning")
    else:
        salva_lista([*ids, item["id"]])
        flash(_("Aggiunto alla lista: %(nome)s.", nome=item["alimento"]), "success")

    return redirect(url_for("spesa.lista"))


@bp.route("/spesa/cambia/<int:alimento_id>", methods=["POST"])
def cambia(alimento_id: int) -> ResponseReturnValue:
    """
    Cambia una voce con l'alimento indicato (con=ID, dall'alternativa
    proposta) o con il successivo dello stesso reparto.
    """
    ids = leggi_lista()

    if alimento_id not in ids:
        return redirect(url_for("spesa.lista"))

    tutti = get_alimenti()
    per_id = {a["id"]: a for a in tutti}
    voce = per_id.get(alimento_id)
    scelto = (request.form.get("con") or "").strip()
    nuovo: Alimento | None = None

    if scelto.isdigit() and int(scelto) in per_id and int(scelto) not in ids:
        nuovo = per_id[int(scelto)]
    elif voce:
        nuovo = spesa.sostituto(tutti, voce, ids, condizioni_utente())

    if nuovo is None:
        flash(_("Nessun altro alimento da proporre in questo reparto."), "info")
        return redirect(url_for("spesa.lista"))

    salva_lista([nuovo["id"] if i == alimento_id else i for i in ids])
    return redirect(url_for("spesa.lista", _anchor=f"voce-{nuovo['id']}"))


@bp.route("/spesa/togli/<int:alimento_id>", methods=["POST"])
def togli(alimento_id: int) -> ResponseReturnValue:
    salva_lista([i for i in leggi_lista() if i != alimento_id])
    return redirect(url_for("spesa.lista"))


@bp.route("/spesa/svuota", methods=["POST"])
def svuota() -> ResponseReturnValue:
    session.pop(CHIAVE_LISTA, None)
    session[CHIAVE_VERSIONE] = secrets.token_hex(4)
    flash(_("Lista della spesa svuotata."), "info")
    return redirect(url_for("spesa.lista"))


@bp.route("/spesa/testo")
def scarica_testo() -> ResponseReturnValue:
    per_id = archivio.get_alimenti_per_id(leggi_lista())
    voci = [per_id[i] for i in leggi_lista() if i in per_id]
    titolo = _("Lista della spesa del %(data)s", data=format_date(date.today(), "short"))
    contenuto = spesa.testo(spesa.raggruppa(voci), titolo, lingue.traduci)
    nome = _("lista-della-spesa") + ".txt"
    return invia_file(contenuto.encode("utf-8"), nome, "text/plain; charset=utf-8")
