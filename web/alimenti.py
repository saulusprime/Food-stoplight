"""
Gestione degli alimenti (solo amministratori): form nuovo e modifica, anche
compilato da una fonte (CREA, Open Food Facts, USDA), ed eliminazione.
"""

from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

import archivio
import calcoli
import cofid
import crea
import fonti
import lingue
import nutrienti
import openfoodfacts
import ricette
import rischi
import usda
from archivio import Alimento
from lingue import N_
from web.accesso import solo_admin
from web.comune import (
    aggiorna_ricette,
    get_alimento,
)

bp = Blueprint("alimenti", __name__)


# ---------------------------------------------------------------
# FORM / CRUD HELPERS
# ---------------------------------------------------------------

CAMPI_TESTO_FORM = ("alimento", "categoria")

# Campi energia e fibre: vuoti valgono 0 (o vengono calcolati); il fruttosio vuoto è "non disponibile"
CAMPI_ENERGIA_FORM = (
    ("kcal", N_("Kcal"), None),
    ("tef_percent", N_("TEF (%)"), 100.0),
    ("tef_kcal", N_("TEF (Kcal)"), None),
    ("kcal_nette", N_("Kcal nette"), None),
    ("fruttosio", N_("Fruttosio"), None),
    ("fibre", N_("Fibre"), None),
)

NOTE_MAX = 2000


def parse_form() -> tuple[dict[str, Any], list[str]]:
    """
    Legge e sistema i dati inviati dal form CRUD: restituisce (valori, errori).
    I campi derivati lasciati vuoti si calcolano come nell'import (calcoli.completa_energia):
    Kcal e TEF dai macronutrienti, TEF (Kcal) <-> TEF (%), Kcal nette, rapporto F/F.
    I dati nutrizionali lasciati vuoti restano "non disponibili" (NULL).
    I livelli di rischio non si scrivono: si calcolano dai dati (rischi.py).
    """
    form = request.form
    errori: list[str] = []
    valori: dict[str, Any] = {campo: (form.get(campo) or "").strip() for campo in CAMPI_TESTO_FORM}
    forniti: set[str] = set()

    def numero(campo: str, etichetta: str, minimo: float = 0.0, massimo: float | None = None) -> float | str | None:
        testo = (form.get(campo) or "").strip()

        if not testo:
            return None

        valore, valido = calcoli.leggi_numero(testo)

        if not valido or valore is None or valore < minimo or (massimo is not None and valore > massimo):
            if massimo is not None:
                errori.append(_(
                    "%(campo)s: «%(testo)s» non è valido, serve un numero tra %(minimo)s e %(massimo)s.",
                    campo=lingue.traduci(etichetta), testo=testo, minimo=f"{minimo:g}", massimo=f"{massimo:g}",
                ))
            else:
                errori.append(_(
                    "%(campo)s: «%(testo)s» non è valido, serve un numero maggiore o uguale a 0.",
                    campo=lingue.traduci(etichetta), testo=testo,
                ))
            return testo

        forniti.add(campo)
        return valore

    for campo, etichetta, massimo in CAMPI_ENERGIA_FORM:
        valore = numero(campo, etichetta, 0, massimo)
        valori[campo] = (None if campo == "fruttosio" else 0.0) if valore is None else valore

    for campo, etichetta, *_dettagli in nutrienti.NUTRIENTI:
        valori[campo] = numero(campo, etichetta)

    valori["indice_glicemico"] = numero("indice_glicemico", N_("Indice glicemico"), 0, 100)

    nova = (form.get("nova") or "").strip()
    valori["nova"] = nutrienti.leggi_nova(nova) if nova else None

    if nova and valori["nova"] is None:
        errori.append(_("NOVA: scegli un gruppo da 1 a 4."))

    for campo in nutrienti.CAMPI_FODMAP:
        testo = (form.get(campo) or "").strip()
        livello_fodmap = nutrienti.livello_fodmap(testo) if testo else None
        valori[campo] = livello_fodmap["etichetta"] if livello_fodmap else None

        if testo and not livello_fodmap:
            errori.append(_(
                "%(campo)s: livello «%(testo)s» non riconosciuto.",
                campo=lingue.traduci(nutrienti.ETICHETTE[campo]), testo=testo,
            ))

    valori["fonte_nutrienti"] = (form.get("fonte_nutrienti") or "").strip() or None

    url = (form.get("url_fonte") or "").strip()
    valori["url_fonte"] = url or None

    if url and not nutrienti.URL_RE.match(url):
        errori.append(_("URL della fonte: serve un indirizzo che inizia con http:// o https://."))

    fdc = (form.get("fdc_id") or "").strip()
    valori["fdc_id"] = int(fdc) if fdc.isdigit() else (fdc or None)

    if fdc and not fdc.isdigit():
        errori.append(_("FDC ID: serve un numero intero."))

    note = (form.get("note") or "").strip()
    valori["note"] = note or None

    if len(note) > NOTE_MAX:
        errori.append(_("Note: al massimo %(n)d caratteri.", n=NOTE_MAX))

    porzione = numero("porzione", N_("Porzione tipica (g)"), nutrienti.GRAMMI_MIN, nutrienti.GRAMMI_MAX)
    valori["porzione"] = porzione

    for campo in ("codice_crea", "codice_barre", "codice_cofid"):
        valori[campo] = (form.get(campo) or "").strip() or None

    if valori["codice_crea"] and not crea.CODICE_RE.match(valori["codice_crea"]):
        errori.append(_("Codice CREA: servono 6 caratteri, cifre o lettere maiuscole (es. 007000)."))

    if valori["codice_barre"] and not openfoodfacts.CODICE_RE.match(valori["codice_barre"]):
        errori.append(_("Codice a barre: servono da 8 a 14 cifre."))

    if valori["codice_cofid"]:
        codici = [c.strip() for c in valori["codice_cofid"].split(",")]

        if not all(cofid.CODICE_RE.match(c) for c in codici):
            errori.append(_("Codice CoFID: gruppo e numero, es. 11-1145 (più codici separati da virgola)."))

        valori["codice_cofid"] = ",".join(codici)

    # Provenienza dei valori (campi nascosti del form): restano com'erano
    valori["campi_usda"] = ",".join(usda.leggi_campi(form.get("campi_usda"))) or None
    valori["campi_cofid"] = ",".join(cofid.leggi_campi(form.get("campi_cofid"))) or None
    valori["campi_ricetta"] = ",".join(ricette.leggi_campi(form.get("campi_ricetta"))) or None
    valori["ingredienti"] = ricette.scrivi_ingredienti(ricette.leggi_ingredienti(form.get("ingredienti")))

    if not errori:
        calcoli.completa_energia(valori, forniti, nuovo=True)
        rischi.assegna(valori)

    return valori, errori


def salva_alimento(valori: dict[str, Any], alimento_id: int | None = None) -> int:
    return archivio.salva_alimento(valori, alimento_id)


def get_form_options() -> dict[str, Any]:
    """
    Suggerimenti per i campi testuali del form nuovo/modifica
    (categorie e livelli di rischio) e opzioni dei menu NOVA e FODMAP.
    """
    return {
        **archivio.get_filter_options(),
        "nova": [
            (gruppo, f"{gruppo} – {lingue.traduci(info['etichetta'])}")
            for gruppo, info in nutrienti.NOVA.items()
        ],
        "fodmap": [(liv["etichetta"], lingue.traduci(liv["etichetta"])) for liv in nutrienti.LIVELLI_FODMAP],
    }


@bp.route("/nuovo", methods=["GET", "POST"])
@solo_admin
def nuovo() -> ResponseReturnValue:
    pagina = {
        "titolo": _("Nuovo alimento"),
        "sottotitolo": _("Inserisci un nuovo alimento nel database."),
        "action": url_for("alimenti.nuovo"),
    }

    if request.method == "POST":
        valori, errori = parse_form()

        if not valori["alimento"]:
            errori.insert(0, _("Il campo Alimento è obbligatorio."))

        if errori:
            for errore in errori:
                flash(errore, "danger")

            return render_template("form.html", **pagina, item=valori, opzioni=get_form_options())

        nuovo_id = salva_alimento(valori)
        aggiorna_ricette()
        flash(_("Alimento aggiunto correttamente."), "success")
        return redirect(url_for("pagine.scheda", alimento_id=nuovo_id))

    return render_template("form.html", **pagina, item=da_fonte(None), opzioni=get_form_options())


@bp.route("/modifica/<int:alimento_id>", methods=["GET", "POST"])
@solo_admin
def modifica(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    pagina = {
        "titolo": _("Modifica alimento"),
        "sottotitolo": _("Aggiorna i dati dell'alimento."),
        "action": url_for("alimenti.modifica", alimento_id=alimento_id),
    }

    if request.method == "POST":
        valori, errori = parse_form()

        if not valori["alimento"]:
            errori.insert(0, _("Il campo Alimento è obbligatorio."))

        if errori:
            for errore in errori:
                flash(errore, "danger")

            return render_template("form.html", **pagina, item={**item, **valori}, opzioni=get_form_options())

        salva_alimento(valori, alimento_id)
        aggiorna_ricette()
        flash(_("Alimento aggiornato correttamente."), "success")
        return redirect(url_for("pagine.scheda", alimento_id=alimento_id))

    return render_template("form.html", **pagina, item=da_fonte(item), opzioni=get_form_options())


FONTI_FORM = {
    "crea": N_("CREA (codice alimento)"),
    "off": N_("Open Food Facts (codice a barre)"),
    "usda": N_("USDA (FDC ID)"),
}


def da_fonte(item: Alimento | None) -> Alimento | None:
    """
    Con ?fonte=...&codice=... nel form: valori presi dalla fonte (sopra quelli
    dell'alimento in modifica), da controllare e salvare.
    """
    fonte = request.args.get("fonte")
    codice = (request.args.get("codice") or "").strip()

    if fonte not in FONTI_FORM or not codice:
        return item

    try:
        trovato = fonti.cerca(fonte, codice, current_app.config["USDA_API_KEY"])
    except fonti.ErroreFonte as exc:
        flash(_("Dati non presi dalla fonte: %(errore)s", errore=str(exc)), "danger")
        return item

    flash(_("Valori presi da %(fonte)s: controllali e salva.", fonte=lingue.traduci(FONTI_FORM[fonte])), "info")

    if item is None:
        return trovato

    return {**item, **{c: v for c, v in trovato.items() if v is not None and v != ""}}


@bp.route("/elimina/<int:alimento_id>", methods=["POST"])
@solo_admin
def elimina(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    archivio.elimina_alimento(alimento_id)
    aggiorna_ricette()
    flash(_("Alimento eliminato: %(nome)s.", nome=item["alimento"]), "warning")
    return redirect(url_for("pagine.index"))
