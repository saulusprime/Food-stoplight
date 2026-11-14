"""
Food-stoplight: applicazione Flask (punto d'ingresso, «app:app» per gunicorn).

Qui stanno configurazione, lingue, filtri e variabili dei template, CSRF,
gestione degli errori, intestazioni di sicurezza, controllo di salute e
migrazioni all'avvio. Le pagine sono nei blueprint del pacchetto web/:
    web/pagine.py         tabella, scheda, confronto, guida
    web/alimenti.py       nuovo, modifica, elimina (amministratori)
    web/import_export.py  export, import con anteprima, sincronizzazione USDA
    web/backup.py         backup e ripristino (amministratori)
    web/pasto_diario.py   pasto e diario alimentare
    web/pasti_pronti.py   pasti pronti e aggiunta dei loro ingredienti al pasto
    web/piano.py          piano settimanale dei pasti bilanciato sui rischi
    web/spesa.py          lista della spesa a semaforo verde
    web/profilo.py        profilo personale (semaforo per te)
    web/accesso.py        login, logout, lingua, ruoli e controllo dell'accesso
    web/comandi.py        comandi da riga di comando (flask --app app ...)
    web/comune.py         funzioni condivise
L'API JSON è in api.py, l'app installabile (PWA) in pwa.py.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import Babel, format_date, format_datetime
from flask_babel import gettext as _
from flask_wtf.csrf import CSRFError, CSRFProtect
from jinja2 import pass_context
from jinja2.runtime import Context
from markupsafe import Markup
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import analisi
import api
import database
import lingue
import nutrienti
import profilo
import pwa
import rischi
from config import carica_config
from web import accesso, comandi, import_export, pagine, pasto_diario
from web import alimenti as alimenti_web
from web import backup as backup_web
from web import pasti_pronti as pasti_pronti_web
from web import piano as piano_web
from web import profilo as profilo_web
from web import spesa as spesa_web
from web.accesso import pagina_precedente
from web.comune import condizioni_utente, filtro_numero, get_db, get_db_utenti, init_db
from web.pagine import CONFRONTO_MAX

app = Flask(__name__)
app.config.update(carica_config())

# Lingue dell'interfaccia: italiano e inglese (vedi lingue.py)
babel = Babel(app, locale_selector=lingue.scegli_lingua)
app.jinja_env.policies["ext.i18n.trimmed"] = True

# Funzioni di analisi disponibili nei template
app.jinja_env.globals.update(
    nutrienti=nutrienti,
    stato_rischio=analisi.stato,
    livello_punteggio=analisi.livello_punteggio,
    LIVELLI_RISCHIO=analisi.LIVELLI,
    LINGUE=lingue.LINGUE,
    rischi_elenco=analisi.RISCHI,
    valuta_rischi=rischi.valuta,
    riferimenti_rischi=rischi.RIFERIMENTI,
)

# Etichette, livelli e categorie scritti in italiano nei dati
app.add_template_filter(lingue.traduci, "traduci")


@app.template_filter("percentuale")
def filtro_percentuale(valore: float, decimali: int = 1) -> str:
    """
    59.43 -> "59,4%" (in inglese "59.4%").
    """
    return lingue.decimale(f"{valore:.{decimali}f}") + "%"


@app.template_filter("css_testo")
def filtro_css_testo(testo: object) -> Markup:
    """
    Testo come stringa CSS per content:, sicuro anche dentro <style>.
    """
    sicuro = (
        str(testo).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ")
        .replace("<", "\\3c ").replace(">", "\\3e ")
    )
    return Markup(f'"{sicuro}"')


@app.template_filter("data_estesa")
def filtro_data_estesa(giorno: date) -> str:
    """
    date(2026, 11, 7) -> "sabato 7 novembre 2026" ("Saturday, November 7, 2026").
    """
    return format_date(giorno, _("EEEE d MMMM y"))


@app.template_filter("data_breve")
def filtro_data_breve(giorno: date) -> str:
    """
    date(2026, 11, 7) -> "sab 7/11" ("Sat 11/7").
    """
    return format_date(giorno, _("EEE d/M"))


@app.template_filter("numero")
@pass_context
def filtro_numero_template(contesto: Context, valore: float | None, decimali: int | None = None) -> str:
    """
    |numero nei template: la lingua arriva dal contesto della pagina
    (la tabella della home ne formatta migliaia).
    """
    return filtro_numero(valore, decimali, contesto.get("lingua"))


@app.template_filter("migliaia")
def filtro_migliaia(valore: int) -> str:
    """
    20000 -> "20.000" ("20,000" in inglese).
    """
    testo = f"{valore:,}"
    return testo.replace(",", ".") if lingue.corrente() == "it" else testo


@app.template_filter("data_ora")
def filtro_data_ora(momento: datetime) -> str:
    """
    datetime(2026, 11, 7, 18, 5) -> "07/11/2026 18:05:00" ("7 Nov 2026, 18:05:00").
    """
    return format_datetime(momento, _("dd/MM/y HH:mm:ss"))


def testi_js() -> dict[str, Any]:
    """
    Testi usati da static/js/app.js, nella lingua della pagina.
    """
    return {
        "lingua": lingue.corrente(),
        "temaChiaro": _("Passa alla modalità chiara"),
        "temaScuro": _("Passa alla modalità scura"),
        "conferma": _("Conferma"),
        "chiudiNotifica": _("Chiudi la notifica"),
        "offline": _("Sei offline: le pagine già aperte restano consultabili."),
        "online": _("Di nuovo online."),
        "livelli": {livello: _(livello) for livello in ("Basso", "Medio", "Alto")},
        "tutteLeColonne": _("Mostra tutte le colonne"),
        "colonnePrincipali": _("Solo le colonne principali"),
        "confrontoPochi": _("Seleziona almeno un altro alimento."),
        "confrontoPronti": _("Pronti per il confronto."),
        "confrontoTogli": _("Togli dal confronto:"),
        "confrontoMassimo": _("Puoi confrontare al massimo %(n)d alimenti.", n=CONFRONTO_MAX),
        "tabellaUno": _("{n} alimento nella copia salvata"),
        "tabellaMolti": _("{n} alimenti nella copia salvata"),
    }


@app.context_processor
def contesto_comune() -> dict[str, Any]:
    return {
        "lingua": lingue.corrente(),
        "testi_js": testi_js(),
        # Pagine salvate in anticipo dal service worker: non consumano i messaggi flash
        "precarica": request.headers.get(pwa.INTESTAZIONE_PRECARICA) == "1",
        # Condizioni del profilo personale (semaforo per te), vuoto se non impostato,
        # e campi dei rischi che contano per il profilo
        "condizioni_profilo": condizioni_utente(),
        "campi_profilo": profilo.campi(condizioni_utente()),
    }


# Dietro un proxy (Render, nginx...): host e schema dalle intestazioni X-Forwarded-*
if app.config["PROXY_ATTENDIBILI"]:
    n_proxy = app.config["PROXY_ATTENDIBILI"]
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n_proxy, x_proto=n_proxy, x_host=n_proxy)  # type: ignore[method-assign]

# Protezione CSRF su tutti i form POST (i template usano csrf_token())
csrf = CSRFProtect(app)

accesso.login_manager.init_app(app)

# JSON dell'API leggibile: accenti così come sono, campi nell'ordine di definizione
app.json.ensure_ascii = False  # type: ignore[attr-defined]
app.json.sort_keys = False  # type: ignore[attr-defined]


# ---------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------

def richiesta_api() -> bool:
    return request.path == "/api" or request.path.startswith("/api/")


@app.errorhandler(403)
def forbidden(error: HTTPException) -> ResponseReturnValue:
    if richiesta_api():
        return api.errore_json(error)

    return render_template(
        "errore.html",
        codice=403,
        titolo=_("Accesso negato"),
        messaggio=_("Operazione riservata agli amministratori."),
    ), 403


@app.errorhandler(404)
def not_found(error: HTTPException) -> ResponseReturnValue:
    if richiesta_api():
        return api.errore_json(error)

    return render_template(
        "errore.html",
        codice=404,
        titolo=_("Pagina non trovata"),
        messaggio=_("Risorsa non trovata."),
    ), 404


@app.errorhandler(HTTPException)
def errore_http(error: HTTPException) -> ResponseReturnValue:
    """
    Gli altri errori HTTP (400, 405...) restano quelli di Flask, in JSON per l'API.
    """
    if richiesta_api():
        return api.errore_json(error)

    return error


@app.errorhandler(413)
def file_troppo_grande(error: HTTPException) -> ResponseReturnValue:
    flash(
        _("File troppo grande: il limite è %(mb)d MB.", mb=app.config["MAX_UPLOAD_MB"]),
        "danger"
    )
    pagina = "backup.pagina" if request.path.startswith("/backup") else "import_export.importa"
    return redirect(url_for(pagina))


@app.errorhandler(CSRFError)
def csrf_non_valido(error: CSRFError) -> ResponseReturnValue:
    flash(_("Sessione scaduta o richiesta non valida: riprova."), "danger")
    return redirect(pagina_precedente() or url_for("pagine.index"))


# ---------------------------------------------------------------
# INTESTAZIONI DI SICUREZZA
# ---------------------------------------------------------------

@app.after_request
def intestazioni_sicurezza(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# ---------------------------------------------------------------
# BLUEPRINT, CONTROLLO DI SALUTE E AVVIO
# ---------------------------------------------------------------

for blueprint in (api.bp, pwa.bp, accesso.bp, pagine.bp, alimenti_web.bp, import_export.bp, backup_web.bp,
                  pasto_diario.bp, pasti_pronti_web.bp, piano_web.bp, spesa_web.bp, profilo_web.bp,
                  comandi.bp):
    app.register_blueprint(blueprint)


@app.route("/salute")
def salute() -> ResponseReturnValue:
    """
    Controllo per Docker e Render: risponde 200 se il database è leggibile.
    """
    try:
        versione, ultima = database.stato(app.config["DATABASE_PATH"], "alimenti")
        conn = get_db()
        conn.execute("SELECT 1 FROM alimenti LIMIT 1").fetchall()
        conn.close()
    except sqlite3.Error:
        return jsonify({"stato": "errore"}), 503

    return jsonify({"stato": "ok", "schema_alimenti": versione, "schema_aggiornato": versione == ultima})


# Crea/aggiorna le tabelle (migrazioni) anche quando l'app è avviata con
# "flask run" o da un server WSGI, non solo con "python app.py".
with app.app_context():
    init_db()


if __name__ == "__main__":
    with app.app_context():
        conn = get_db_utenti()
        numero_admin = conn.execute(
            "SELECT COUNT(*) FROM utenti WHERE ruolo = 'admin'"
        ).fetchone()[0]
        conn.close()

    if not numero_admin:
        print(
            " * Nessun amministratore: creane uno con "
            "'flask --app app crea-utente <username>'"
        )

    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"]
    )
