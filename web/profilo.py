"""
Profilo personale: scelta delle condizioni (diabete, ipercolesterolemia,
malassorbimento del fruttosio) per il semaforo per te (profilo.py).
Con l'accesso si salva nell'account, senza nella sessione del browser.
"""

from __future__ import annotations

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
from flask_babel import gettext as _
from flask_login import current_user

import profilo
from web.comune import CHIAVE_SESSIONE_PROFILO, condizioni_utente, get_db_utenti

bp = Blueprint("profilo", __name__)


def salva_condizioni(condizioni: tuple[str, ...]) -> None:
    testo = profilo.testo(condizioni)

    if current_user.is_authenticated:
        conn = get_db_utenti()

        try:
            conn.execute("UPDATE utenti SET condizioni = ? WHERE id = ?", (testo, current_user.id))
            conn.commit()
        finally:
            conn.close()

        current_user.condizioni = testo
    elif testo:
        session[CHIAVE_SESSIONE_PROFILO] = testo
    else:
        session.pop(CHIAVE_SESSIONE_PROFILO, None)


@bp.route("/profilo", methods=["GET", "POST"])
def pagina() -> ResponseReturnValue:
    if request.method == "POST":
        condizioni = profilo.leggi(request.form.getlist("condizioni"))
        salva_condizioni(condizioni)

        # Le pagine salvate per l'uso offline mostrano il semaforo per te:
        # la pagina successiva chiede al service worker di riscaricarle
        session["svuota_cache"] = True

        if condizioni:
            flash(_("Profilo salvato: tabella e schede mostrano il semaforo per te."), "success")
        else:
            flash(_("Profilo vuoto: il semaforo per te non viene mostrato."), "info")

        return redirect(url_for("profilo.pagina"))

    return render_template(
        "profilo.html",
        condizioni=profilo.CONDIZIONI,
        scelte=condizioni_utente(),
    )
