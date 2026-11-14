"""
Pasti pronti: ricette per portata e aggiunta dei loro ingredienti al pasto
(nella sessione), con le quantità per le porzioni scelte.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from flask_babel import ngettext

import analisi
import archivio
import fonti
import nutrienti
import pasti_pronti
import profilo
from lingue import N_
from web.accesso import url_sicuro
from web.comune import condizioni_utente, get_db
from web.pasto_diario import PASTO_MAX_VOCI, leggi_pasto

bp = Blueprint("pasti_pronti", __name__)

ORDINAMENTI = {
    "nome": N_("Nome"),
    "punteggio": N_("Punteggio migliore"),
    "kcal": N_("Meno Kcal per porzione"),
}

# Rischi mostrati nell'elenco: solo quelli da tenere d'occhio
LIVELLI_IN_EVIDENZA = {"medio", "alto"}


def ricette_db() -> list[pasti_pronti.Ricetta]:
    conn = get_db()

    try:
        return fonti.leggi_pasti_pronti(conn)
    finally:
        conn.close()


def ricetta_per(campo: str, valore: object) -> pasti_pronti.Ricetta | None:
    """
    Pasto pronto per codice o per id del piatto (campo "codice" o "alimento_id").
    """
    if campo not in ("codice", "alimento_id"):
        raise ValueError(campo)

    return next((r for r in ricette_db() if r[campo] == valore), None)


def alimenti_per_codice(codici: list[str]) -> dict[str, dict[str, Any]]:
    """
    {codice CREA: alimento} per gli ingredienti (id, nome e categoria bastano).
    """
    if not codici:
        return {}

    conn = get_db()

    try:
        righe = conn.execute(
            "SELECT id, alimento, categoria, codice_crea FROM alimenti "
            f"WHERE codice_crea IN ({', '.join('?' for _ in codici)})",
            codici,
        ).fetchall()
    finally:
        conn.close()

    return {riga["codice_crea"]: dict(riga) for riga in righe}


def ingredienti_porzione(ricetta: pasti_pronti.Ricetta, porzioni: float = 1) -> list[dict[str, Any]]:
    """
    Tutti gli ingredienti della ricetta con i grammi per le porzioni e,
    se abbinato, l'alimento dell'app (None se non conteggiato o eliminato).
    """
    alimenti = alimenti_per_codice(sorted({v["codice_crea"] for v in ricetta["ingredienti"] if v["codice_crea"]}))
    fattore = porzioni / ricetta["porzioni"]

    return [
        {
            **voce,
            "grammi_porzione": None if voce["grammi"] is None else round(voce["grammi"] * fattore, 1),
            "alimento": alimenti.get(voce["codice_crea"]) if voce["codice_crea"] else None,
        }
        for voce in ricetta["ingredienti"]
    ]


def rischi_in_evidenza(piatto: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not piatto:
        return []

    risultato = []

    for campo, etichetta in analisi.RISCHI:
        livello = analisi.livello(piatto.get(campo))

        if livello and livello["chiave"] in LIVELLI_IN_EVIDENZA:
            risultato.append({"etichetta": etichetta, "valore": piatto.get(campo)})

    return risultato


@bp.route("/pasti-pronti")
def elenco() -> ResponseReturnValue:
    ricette = ricette_db()
    piatti = archivio.get_alimenti_per_id([r["alimento_id"] for r in ricette if r["alimento_id"]])
    portata = request.args.get("portata", "")
    portata = portata if portata in pasti_pronti.CHIAVI_PORTATE else ""
    condizioni = condizioni_utente()
    # Con un profilo si ordina anche per semaforo per te
    ordinamenti = {**ORDINAMENTI, archivio.PER_TE: N_("Per te")} if condizioni else ORDINAMENTI
    ordina = request.args.get("ordina", "nome")
    ordina = ordina if ordina in ordinamenti else "nome"

    voci = []

    for ricetta in ricette:
        piatto = piatti.get(ricetta["alimento_id"]) if ricetta["alimento_id"] else None
        porzione = (piatto or {}).get("porzione")
        voci.append({
            **ricetta,
            "piatto": piatto,
            "kcal_porzione": (piatto["kcal"] or 0) * porzione / 100 if piatto and porzione else None,
            "rischi": rischi_in_evidenza(piatto),
            "per_te": profilo.per_te(piatto, condizioni) if piatto else None,
        })

    def chiave(voce: dict[str, Any]) -> tuple[Any, ...]:
        # Senza piatto o senza dato in fondo; a parità, per nome
        nome = voce["nome"].casefold()
        punteggio = (voce["piatto"] or {}).get("punteggio")

        if ordina == archivio.PER_TE:
            punti = (voce["per_te"] or {}).get("punti")
            return (
                punti if punti is not None else float("inf"),
                -punteggio if punteggio is not None else 1.0,
                nome,
            )
        if ordina == "punteggio":
            return (-punteggio if punteggio is not None else 1.0, nome)
        if ordina == "kcal":
            return (voce["kcal_porzione"] if voce["kcal_porzione"] is not None else float("inf"), nome)
        return (0.0, nome)

    voci.sort(key=chiave)

    gruppi = [
        (chiave, etichetta, [v for v in voci if v["portata"] == chiave])
        for chiave, etichetta in pasti_pronti.PORTATE
        if not portata or chiave == portata
    ]

    return render_template(
        "pasti_pronti.html",
        gruppi=gruppi,
        portate=pasti_pronti.PORTATE,
        portata=portata,
        ordina=ordina,
        ordinamenti=ordinamenti,
        conteggi=Counter(r["portata"] for r in ricette),
        totale=len(ricette),
        fonti_ricette=pasti_pronti.FONTI,
        porzioni_max=pasti_pronti.PORZIONI_MAX,
    )


def leggi_porzioni(testo: object) -> int | None:
    try:
        porzioni = int(str(testo or "1"))
    except ValueError:
        return None

    return porzioni if 1 <= porzioni <= pasti_pronti.PORZIONI_MAX else None


@bp.route("/pasti-pronti/<codice>/aggiungi", methods=["POST"])
def aggiungi(codice: str) -> ResponseReturnValue:
    """
    Aggiunge al pasto gli ingredienti abbinati della ricetta, con i grammi
    crudi per le porzioni scelte; un alimento già nel pasto somma i grammi.
    """
    destinazione = url_sicuro(request.form.get("next")) or url_for("pasto_diario.pasto")
    ricetta = ricetta_per("codice", codice)

    if ricetta is None:
        abort(404)

    porzioni = leggi_porzioni(request.form.get("porzioni"))

    if porzioni is None:
        flash(_("Porzioni non valide: da 1 a %(n)d.", n=pasti_pronti.PORZIONI_MAX), "danger")
        return redirect(destinazione)

    voci = leggi_pasto()
    aggiunti = 0

    for voce in ingredienti_porzione(ricetta, porzioni):
        if not voce["alimento"] or not voce["grammi_porzione"]:
            continue

        # Le quantità minime (erbe, spezie) salgono al grammo: il pasto non ne accetta di meno
        grammi = min(max(voce["grammi_porzione"], nutrienti.GRAMMI_MIN), nutrienti.GRAMMI_MAX)
        esistente = next((v for v in voci if v["id"] == voce["alimento"]["id"]), None)

        if esistente:
            esistente["grammi"] = min(round(esistente["grammi"] + grammi, 1), nutrienti.GRAMMI_MAX)
        else:
            voci.append({"id": voce["alimento"]["id"], "grammi": grammi})

        aggiunti += 1

    if len(voci) > PASTO_MAX_VOCI:
        flash(_("Il pasto può contenere al massimo %(n)d alimenti: svuotalo o togline qualcuno prima di "
                "aggiungere «%(nome)s».", n=PASTO_MAX_VOCI, nome=ricetta["nome"]), "warning")
        return redirect(destinazione)

    if not aggiunti:
        flash(_("Nessun ingrediente di «%(nome)s» è tra gli alimenti.", nome=ricetta["nome"]), "warning")
        return redirect(destinazione)

    session["pasto"] = voci
    flash(
        ngettext("Aggiunti al pasto gli ingredienti di «%(nome)s» per %(num)d porzione.",
                 "Aggiunti al pasto gli ingredienti di «%(nome)s» per %(num)d porzioni.",
                 porzioni, nome=ricetta["nome"]),
        "success",
    )
    return redirect(destinazione)
