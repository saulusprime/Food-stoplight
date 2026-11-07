from __future__ import annotations

import io
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from functools import wraps
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

import click
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import (
    AnonymousUserMixin,
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import analisi
import api
import archivio
import backup
import calcoli
import database
import esportazione
import importazione
import nutrienti
import usda
from archivio import Alimento
from config import carica_config

# Funzione di vista di Flask (per il decoratore solo_admin)
Vista = TypeVar("Vista", bound=Callable[..., Any])

app = Flask(__name__)
app.config.update(carica_config())

# Funzioni di analisi disponibili nei template
app.jinja_env.globals.update(
    nutrienti=nutrienti,
    stato_rischio=analisi.stato,
    livello_punteggio=analisi.livello_punteggio,
    LIVELLI_RISCHIO=analisi.LIVELLI,
)


@app.template_filter("percentuale")
def filtro_percentuale(valore: float, decimali: int = 1) -> str:
    """
    59.43 -> "59,4%" (virgola decimale italiana).
    """
    return f"{valore:.{decimali}f}".replace(".", ",") + "%"


GIORNI_SETTIMANA = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre")


@app.template_filter("data_estesa")
def filtro_data_estesa(giorno: date) -> str:
    """
    date(2026, 11, 7) -> "sabato 7 novembre 2026".
    """
    return f"{GIORNI_SETTIMANA[giorno.weekday()]} {giorno.day} {MESI[giorno.month - 1]} {giorno.year}"


@app.template_filter("data_breve")
def filtro_data_breve(giorno: date) -> str:
    """
    date(2026, 11, 7) -> "sab 7/11".
    """
    return f"{GIORNI_SETTIMANA[giorno.weekday()][:3]} {giorno.day}/{giorno.month}"


@app.template_filter("numero")
def filtro_numero(valore: float | None, decimali: int | None = None) -> str:
    """
    Numero con virgola decimale; senza decimali indicati usa la forma compatta (%g).
    """
    if valore is None:
        return "–"

    testo = f"{valore:g}" if decimali is None else f"{valore:.{decimali}f}"
    return testo.replace(".", ",")

DB_PATH = app.config["DATABASE_PATH"]
UTENTI_DB_PATH = app.config["UTENTI_DB_PATH"]
DIARIO_DB_PATH = app.config["DIARIO_DB_PATH"]

# Dietro un proxy (Render, nginx...): host e schema dalle intestazioni X-Forwarded-*
if app.config["PROXY_ATTENDIBILI"]:
    n_proxy = app.config["PROXY_ATTENDIBILI"]
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n_proxy, x_proto=n_proxy, x_host=n_proxy)  # type: ignore[method-assign]

# Protezione CSRF su tutti i form POST (i template usano csrf_token())
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Accedi per continuare."
login_manager.login_message_category = "warning"

# JSON dell'API leggibile: accenti così come sono, campi nell'ordine di definizione
app.json.ensure_ascii = False  # type: ignore[attr-defined]
app.json.sort_keys = False  # type: ignore[attr-defined]


# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    return database.connetti_alimenti(DB_PATH)


def get_db_utenti() -> sqlite3.Connection:
    """
    Gli utenti stanno in un database separato (utenti.db, escluso da git):
    alimenti.db è versionato e non deve contenere credenziali.
    """
    return database.connetti(UTENTI_DB_PATH)


def get_db_diario() -> sqlite3.Connection:
    """
    Il diario alimentare è personale: database separato (diario.db, escluso da git).
    """
    return database.connetti(DIARIO_DB_PATH)


def init_db(backup_prima: bool = True) -> list[str]:
    """
    Applica le migrazioni mancanti ai tre database e restituisce quelle eseguite.
    Prima di migrare un alimenti.db esistente ne salva un backup.
    """
    def copia_di_sicurezza() -> None:
        if backup_prima:
            backup.crea(DB_PATH, app.config["BACKUP_DIR"], "migrazione")

    eseguite = database.migra(UTENTI_DB_PATH, "utenti")
    eseguite += database.migra(DIARIO_DB_PATH, "diario")
    eseguite += database.migra(DB_PATH, "alimenti", prima_di_migrare=copia_di_sicurezza)
    return eseguite


# Query sugli alimenti (in archivio.py, condivise con l'API)
get_alimento = archivio.get_alimento
get_alimenti = archivio.get_alimenti
get_stats = archivio.get_stats
SORT_EXPRESSIONS = archivio.SORT_EXPRESSIONS
ETICHETTE_FILTRI = archivio.ETICHETTE_FILTRI


def leggi_filtri() -> tuple[archivio.Filtri, str, str]:
    return archivio.leggi_filtri(request.args)


# ---------------------------------------------------------------
# FORM / CRUD HELPERS
# ---------------------------------------------------------------

CAMPI_TESTO_FORM = ("alimento", "categoria", *analisi.CAMPI_RISCHIO)

# Campi energia e fruttosio/fibre: vuoti valgono 0 (o vengono calcolati)
CAMPI_ENERGIA_FORM = (
    ("kcal", "Kcal", None),
    ("tef_percent", "TEF (%)", 100.0),
    ("tef_kcal", "TEF (Kcal)", None),
    ("kcal_nette", "Kcal nette", None),
    ("fruttosio", "Fruttosio", None),
    ("fibre", "Fibre", None),
)

NOTE_MAX = 2000


def parse_form() -> tuple[dict[str, Any], list[str]]:
    """
    Legge e sistema i dati inviati dal form CRUD: restituisce (valori, errori).
    I campi derivati lasciati vuoti si calcolano come nell'import (calcoli.completa_energia):
    Kcal e TEF dai macronutrienti, TEF (Kcal) <-> TEF (%), Kcal nette, rapporto F/F.
    I dati nutrizionali lasciati vuoti restano "non disponibili" (NULL).
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
            intervallo = f" tra {minimo:g} e {massimo:g}" if massimo is not None else " maggiore o uguale a 0"
            errori.append(f"{etichetta}: «{testo}» non è valido, serve un numero{intervallo}.")
            return testo

        forniti.add(campo)
        return valore

    for campo, etichetta, massimo in CAMPI_ENERGIA_FORM:
        valore = numero(campo, etichetta, 0, massimo)
        valori[campo] = 0.0 if valore is None else valore

    for campo, etichetta, *_ in nutrienti.NUTRIENTI:
        valori[campo] = numero(campo, etichetta)

    valori["indice_glicemico"] = numero("indice_glicemico", "Indice glicemico", 0, 100)

    nova = (form.get("nova") or "").strip()
    valori["nova"] = nutrienti.leggi_nova(nova) if nova else None

    if nova and valori["nova"] is None:
        errori.append("NOVA: scegli un gruppo da 1 a 4.")

    for campo, etichetta in nutrienti.FODMAP:
        testo = (form.get(campo) or "").strip()
        livello_fodmap = nutrienti.livello_fodmap(testo) if testo else None
        valori[campo] = livello_fodmap["etichetta"] if livello_fodmap else None

        if testo and not livello_fodmap:
            errori.append(f"FODMAP {etichetta.lower()}: livello «{testo}» non riconosciuto.")

    valori["fonte_nutrienti"] = (form.get("fonte_nutrienti") or "").strip() or None

    url = (form.get("url_fonte") or "").strip()
    valori["url_fonte"] = url or None

    if url and not nutrienti.URL_RE.match(url):
        errori.append("URL della fonte: serve un indirizzo che inizia con http:// o https://.")

    fdc = (form.get("fdc_id") or "").strip()
    valori["fdc_id"] = int(fdc) if fdc.isdigit() else (fdc or None)

    if fdc and not fdc.isdigit():
        errori.append("FDC ID: serve un numero intero.")

    note = (form.get("note") or "").strip()
    valori["note"] = note or None

    if len(note) > NOTE_MAX:
        errori.append(f"Note: al massimo {NOTE_MAX} caratteri.")

    if not errori:
        calcoli.completa_energia(valori, forniti, nuovo=True)

    return valori, errori


def salva_alimento(valori: dict[str, Any], alimento_id: int | None = None) -> int:
    return archivio.salva_alimento(valori, alimento_id)


def get_filter_options() -> dict[str, list[archivio.Opzione]]:
    return archivio.get_filter_options()


def get_form_options() -> dict[str, Any]:
    """
    Suggerimenti per i campi testuali del form nuovo/modifica
    (categorie e livelli di rischio) e opzioni dei menu NOVA e FODMAP.
    """
    return {
        **get_filter_options(),
        "nova": [
            (gruppo, f"{gruppo} – {info['etichetta']}")
            for gruppo, info in nutrienti.NOVA.items()
        ],
        "fodmap": [(liv["etichetta"], liv["etichetta"]) for liv in nutrienti.LIVELLI_FODMAP],
    }


# ---------------------------------------------------------------
# AUTENTICAZIONE E RUOLI
# ---------------------------------------------------------------

RUOLI = ("admin", "visitatore")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
PASSWORD_MIN = 8

# Hash fittizio: al login si verifica sempre una password, anche se l'utente
# non esiste, così i tempi di risposta non rivelano gli username registrati.
HASH_FITTIZIO = generate_password_hash(secrets.token_hex(16))


class Utente(UserMixin):
    def __init__(self, row: sqlite3.Row) -> None:
        self.id = row["id"]
        self.username = row["username"]
        self.ruolo = row["ruolo"]

    @property
    def is_admin(self) -> bool:
        return self.ruolo == "admin"


class Anonimo(AnonymousUserMixin):
    username = None
    ruolo = None
    is_admin = False


login_manager.anonymous_user = Anonimo


@login_manager.user_loader
def carica_utente(user_id: str) -> Utente | None:
    conn = get_db_utenti()
    row = conn.execute(
        "SELECT id, username, ruolo FROM utenti WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    return Utente(row) if row else None


def solo_admin(view: Vista) -> Vista:
    """
    Riserva una route agli amministratori:
    anonimo -> pagina di login, visitatore -> 403.
    """
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if not current_user.is_admin:
            abort(403)

        return view(*args, **kwargs)

    return cast(Vista, wrapper)


@app.before_request
def controlla_accesso() -> ResponseReturnValue | None:
    """
    Con ACCESSO_PUBBLICO=false serve il login anche per consultare.
    """
    if app.config["ACCESSO_PUBBLICO"] or current_user.is_authenticated:
        return None

    if request.endpoint in ("login", "static", "salute"):
        return None

    if request.path.startswith("/api"):
        return jsonify({"errore": "Autenticazione richiesta.", "stato": 401}), 401

    return login_manager.unauthorized()


def url_sicuro(target: str | None) -> str | None:
    """
    Accetta solo percorsi interni all'applicazione (evita open redirect).
    """
    target = (target or "").strip()

    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None

    parts = urlsplit(target)

    if parts.scheme or parts.netloc:
        return None

    return target


def pagina_precedente() -> str | None:
    """
    Percorso della pagina di provenienza, solo se è sullo stesso host.
    """
    parts = urlsplit(request.referrer or "")

    if parts.netloc != request.host:
        return None

    return url_sicuro(parts.path + (f"?{parts.query}" if parts.query else ""))


@app.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conn = get_db_utenti()
        row = conn.execute(
            "SELECT * FROM utenti WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        password_ok = check_password_hash(
            row["password_hash"] if row else HASH_FITTIZIO,
            password
        )

        if row and password_ok:
            login_user(Utente(row))
            flash(f"Accesso effettuato come {row['username']}.", "success")
            return redirect(url_sicuro(request.args.get("next")) or url_for("index"))

        flash("Nome utente o password non validi.", "danger")
        return render_template("login.html", username=username), 401

    return render_template("login.html", username="")


@app.route("/logout", methods=["POST"])
def logout() -> ResponseReturnValue:
    logout_user()
    flash("Disconnessione effettuata.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------
# ROUTE PRINCIPALI
# ---------------------------------------------------------------

@app.route("/")
def index() -> ResponseReturnValue:
    filtri, sort, direction = leggi_filtri()

    filter_categoria = filtri["categoria"]
    filter_diabete = filtri["rischio_diabete"]
    filter_colesterolo = filtri["rischio_colesterolo"]
    filter_malassorbimento = filtri["rischio_malassorbimento"]
    filter_metabolico = filtri["rischio_metabolico"]
    filter_tumorale = filtri["rischio_tumorale"]

    alimenti = get_alimenti(filtri, sort, direction)

    total_alimenti, con_dati_tef = get_stats()

    opzioni = get_filter_options()

    filtri_attivi = any(filtri.values())

    # Le medaglie si calcolano sull'intero database, non sugli alimenti filtrati
    tutti = get_alimenti() if filtri_attivi else alimenti
    medaglie = analisi.medaglie_per_alimento(tutti)

    for a in alimenti:
        a["medaglie"] = medaglie.get(a["id"], [])

    # Grafici e classifiche seguono invece i filtri
    distribuzione_rischi = analisi.distribuzione_rischi(alimenti)

    return render_template(
        "index.html",
        alimenti=alimenti,
        filtri_attivi=filtri_attivi,
        grafico_categorie=analisi.distribuzione_categorie(alimenti),
        grafico_rischi=distribuzione_rischi,
        legenda_rischi=analisi.legenda_rischi(distribuzione_rischi),
        punteggio_medio=analisi.punteggio_medio(alimenti),
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
        filter_categoria=filter_categoria,
        filter_diabete=filter_diabete,
        filter_colesterolo=filter_colesterolo,
        filter_malassorbimento=filter_malassorbimento,
        filter_metabolico=filter_metabolico,
        filter_tumorale=filter_tumorale,
        sort=sort,
        dir=direction,
        total_alimenti=total_alimenti,
        con_dati_tef=con_dati_tef,
        visualizzati=len(alimenti),
        category_options=opzioni["categoria"],
        diabete_options=opzioni["rischio_diabete"],
        colesterolo_options=opzioni["rischio_colesterolo"],
        malassorbimento_options=opzioni["rischio_malassorbimento"],
        metabolic_options=opzioni["rischio_metabolico"],
        tumorale_options=opzioni["rischio_tumorale"],
    )


@app.route("/alimento/<int:alimento_id>")
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
    )


@app.route("/nuovo", methods=["GET", "POST"])
@solo_admin
def nuovo() -> ResponseReturnValue:
    pagina = {
        "titolo": "Nuovo alimento",
        "sottotitolo": "Inserisci un nuovo alimento nel database.",
        "action": url_for("nuovo"),
    }

    if request.method == "POST":
        valori, errori = parse_form()

        if not valori["alimento"]:
            errori.insert(0, "Il campo Alimento è obbligatorio.")

        if errori:
            for errore in errori:
                flash(errore, "danger")

            return render_template("form.html", **pagina, item=valori, opzioni=get_form_options())

        nuovo_id = salva_alimento(valori)
        flash("Alimento aggiunto correttamente.", "success")
        return redirect(url_for("scheda", alimento_id=nuovo_id))

    return render_template("form.html", **pagina, item=None, opzioni=get_form_options())


@app.route("/modifica/<int:alimento_id>", methods=["GET", "POST"])
@solo_admin
def modifica(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    pagina = {
        "titolo": "Modifica alimento",
        "sottotitolo": "Aggiorna i dati dell'alimento.",
        "action": url_for("modifica", alimento_id=alimento_id),
    }

    if request.method == "POST":
        valori, errori = parse_form()

        if not valori["alimento"]:
            errori.insert(0, "Il campo Alimento è obbligatorio.")

        if errori:
            for errore in errori:
                flash(errore, "danger")

            return render_template("form.html", **pagina, item={**item, **valori}, opzioni=get_form_options())

        salva_alimento(valori, alimento_id)
        flash("Alimento aggiornato correttamente.", "success")
        return redirect(url_for("scheda", alimento_id=alimento_id))

    return render_template("form.html", **pagina, item=item, opzioni=get_form_options())


@app.route("/elimina/<int:alimento_id>", methods=["POST"])
@solo_admin
def elimina(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    archivio.elimina_alimento(alimento_id)
    flash("Alimento eliminato.", "warning")
    return redirect(url_for("index"))


# ---------------------------------------------------------------
# EXPORT (CSV, Excel, PDF)
# ---------------------------------------------------------------

FORMATI_EXPORT = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

ETICHETTE_ORDINAMENTO = {**importazione.ETICHETTE, "punteggio": "Punteggio"}


def invia_file(dati: bytes, nome: str, mimetype: str) -> Response:
    """
    Risposta di download per un file generato in memoria.
    """
    risposta = send_file(
        io.BytesIO(dati),
        mimetype=mimetype,
        as_attachment=True,
        download_name=nome,
        max_age=0,
    )
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


def nome_file_sicuro(testo: str | None, alternativa: str) -> str:
    """
    "Pane integrale (100%)" -> "pane-integrale-100" per i nomi dei file scaricati.
    """
    ascii_ = unicodedata.normalize("NFKD", testo or "").encode("ascii", "ignore").decode()
    nome = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60]
    return nome or alternativa


def info_export(filtri: archivio.Filtri, sort: str, direction: str, totale: int) -> esportazione.InfoExport:
    return {
        "filtri": [
            (ETICHETTE_FILTRI[campo], valore)
            for campo, valore in filtri.items()
            if valore
        ],
        "ordinamento": (
            f"{ETICHETTE_ORDINAMENTO.get(sort, sort)} "
            f"({'decrescente' if direction == 'desc' else 'crescente'})"
        ),
        "data": datetime.now(),
        "totale": totale,
    }


@app.route("/esporta/<formato>")
def esporta(formato: str) -> ResponseReturnValue:
    """
    Tabella con gli stessi filtri e lo stesso ordinamento della home.
    """
    if formato not in FORMATI_EXPORT:
        abort(404)

    filtri, sort, direction = leggi_filtri()
    alimenti = get_alimenti(filtri, sort, direction)
    info = info_export(filtri, sort, direction, len(alimenti))

    if formato == "csv":
        dati = esportazione.csv_bytes(alimenti)
    elif formato == "xlsx":
        dati = esportazione.xlsx_bytes(alimenti, info)
    else:
        dati = esportazione.pdf_tabella(alimenti, info)

    suffisso = "_filtrati" if any(filtri.values()) else ""
    nome = f"alimenti{suffisso}_{info['data']:%Y-%m-%d}.{formato}"
    return invia_file(dati, nome, FORMATI_EXPORT[formato])


@app.route("/alimento/<int:alimento_id>/pdf")
def scheda_pdf(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    medaglie = analisi.medaglie_per_alimento(get_alimenti()).get(alimento_id, [])
    dati = esportazione.pdf_scheda(item, medaglie, analisi.POSTI_MEDAGLIA, datetime.now())
    nome = f"scheda_{nome_file_sicuro(item['alimento'], str(alimento_id))}.pdf"
    return invia_file(dati, nome, FORMATI_EXPORT["pdf"])


# ---------------------------------------------------------------
# IMPORT CSV / EXCEL con anteprima
#   1. /importa            caricamento del file (letto e salvato in instance/import)
#   2. /importa/anteprima  cosa succederà con ciascuna modalità
#   3. /importa/conferma   backup automatico e scrittura
# ---------------------------------------------------------------

IMPORT_SCADENZA_SECONDI = 3600
ANTEPRIMA_RIGHE = 25
ANTEPRIMA_AVVISI = 50
TOKEN_IMPORT_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


def cartella_import() -> str:
    os.makedirs(app.config["IMPORT_DIR"], exist_ok=True)
    return app.config["IMPORT_DIR"]


def percorso_import(token: str | None) -> str | None:
    if not token or not TOKEN_IMPORT_RE.match(token):
        return None

    return os.path.join(cartella_import(), f"{token}.json")


def pulisci_import_scaduti() -> None:
    limite = time.time() - IMPORT_SCADENZA_SECONDI

    for voce in os.scandir(cartella_import()):
        try:
            if voce.is_file() and voce.stat().st_mtime < limite:
                os.remove(voce.path)
        except OSError:
            pass


def carica_import() -> dict[str, Any] | None:
    """
    File letto e in attesa di conferma per questa sessione, oppure None.
    """
    percorso = percorso_import(session.get("import_token"))

    if not percorso or not os.path.isfile(percorso):
        return None

    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def scarta_import() -> None:
    percorso = percorso_import(session.pop("import_token", None))

    if percorso and os.path.isfile(percorso):
        os.remove(percorso)


@app.route("/importa", methods=["GET", "POST"])
@solo_admin
def importa() -> ResponseReturnValue:
    if request.method == "POST":
        file = request.files.get("file")

        if not file or not file.filename:
            flash("Seleziona un file CSV o Excel da importare.", "danger")
            return redirect(url_for("importa"))

        nome_file = os.path.basename(file.filename.replace("\\", "/"))

        try:
            letto = importazione.leggi_file(nome_file, file.read())
        except importazione.ErroreImport as exc:
            flash(str(exc), "danger")
            return redirect(url_for("importa"))
        except Exception:
            app.logger.exception("Lettura del file di import non riuscita")
            flash("Il file non è leggibile: controlla che sia un CSV o un Excel valido.", "danger")
            return redirect(url_for("importa"))

        scarta_import()
        pulisci_import_scaduti()

        token = secrets.token_urlsafe(24)
        percorso = percorso_import(token)
        assert percorso is not None  # token appena generato, sempre valido

        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(letto, f, ensure_ascii=False)

        session["import_token"] = token
        return redirect(url_for("importa_anteprima"))

    return render_template(
        "import.html",
        in_attesa=carica_import(),
        max_mb=app.config["MAX_UPLOAD_MB"],
        max_righe=importazione.MAX_RIGHE,
    )


def campi_anteprima(letto: dict[str, Any]) -> list[str]:
    """
    Colonne della tabella di anteprima: i campi di base sempre,
    quelli nutrizionali solo se il file li contiene.
    """
    nel_file = {colonna["campo"] for colonna in letto["colonne"]}
    return [
        campo for campo in importazione.CAMPI
        if campo not in importazione.CAMPI_NULLABILI or campo in nel_file
    ]


@app.route("/importa/anteprima")
@solo_admin
def importa_anteprima() -> ResponseReturnValue:
    letto = carica_import()

    if letto is None:
        flash("Nessun file in attesa di conferma: caricane uno.", "warning")
        return redirect(url_for("importa"))

    modalita = request.args.get("modalita", importazione.MODALITA_PREDEFINITA)

    if modalita not in importazione.MODALITA:
        modalita = importazione.MODALITA_PREDEFINITA

    conn = get_db()

    try:
        piani = {
            chiave: importazione.pianifica(conn, letto, chiave)
            for chiave in importazione.MODALITA
        }
        totale_db = conn.execute("SELECT COUNT(*) FROM alimenti").fetchone()[0]
    finally:
        conn.close()

    voci = piani[modalita]

    return render_template(
        "import_anteprima.html",
        letto=letto,
        modalita=modalita,
        modalita_disponibili=importazione.MODALITA,
        riepiloghi={chiave: importazione.riepilogo(piano) for chiave, piano in piani.items()},
        voci=[v for v in voci if v["azione"] != "invariato"][:ANTEPRIMA_RIGHE],
        voci_con_avvisi=[v for v in voci if v["avvisi"]][:ANTEPRIMA_AVVISI],
        totale_db=totale_db,
        campi=campi_anteprima(letto),
        etichette=importazione.ETICHETTE,
        anteprima_righe=ANTEPRIMA_RIGHE,
        anteprima_avvisi=ANTEPRIMA_AVVISI,
    )


@app.route("/importa/conferma", methods=["POST"])
@solo_admin
def importa_conferma() -> ResponseReturnValue:
    letto = carica_import()

    if letto is None:
        flash("Nessun file in attesa di conferma: caricane uno.", "warning")
        return redirect(url_for("importa"))

    modalita = request.form.get("modalita", "")

    if modalita not in importazione.MODALITA:
        abort(400)

    if modalita == "sostituisci" and request.form.get("conferma_sostituisci") != "1":
        flash("Per sostituire l'intera tabella spunta la casella di conferma.", "danger")
        return redirect(url_for("importa_anteprima", modalita=modalita))

    conn = get_db()

    try:
        voci = importazione.pianifica(conn, letto, modalita)
        sommario = importazione.riepilogo(voci)

        if modalita == "sostituisci" and sommario["nuovo"] == 0:
            flash("Il file non contiene righe valide: la tabella non è stata svuotata.", "danger")
            return redirect(url_for("importa_anteprima", modalita=modalita))

        if sommario["scritture"] == 0:
            scarta_import()
            flash("Nessuna modifica da applicare: il database contiene già questi dati.", "info")
            return redirect(url_for("index"))

        nome_backup = backup.crea(DB_PATH, app.config["BACKUP_DIR"], "import")
        adesso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        eliminati = importazione.applica(conn, voci, modalita, adesso)
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Import non riuscito")
        flash("Errore durante l'importazione: nessuna modifica è stata salvata.", "danger")
        return redirect(url_for("importa_anteprima", modalita=modalita))
    finally:
        conn.close()

    scarta_import()

    parti = []

    if eliminati:
        parti.append(f"{eliminati} eliminati")

    parti.append(f"{sommario['nuovo']} aggiunti")

    if sommario["aggiornato"]:
        parti.append(f"{sommario['aggiornato']} aggiornati")

    if sommario["saltato"]:
        parti.append(f"{sommario['saltato']} righe saltate")

    flash(
        f"Import completato: {', '.join(parti)}. "
        f"Il database precedente è nel backup {nome_backup}.",
        "success"
    )
    return redirect(url_for("index"))


@app.route("/importa/annulla", methods=["POST"])
@solo_admin
def importa_annulla() -> ResponseReturnValue:
    scarta_import()
    flash("Import annullato: il database non è stato modificato.", "info")
    return redirect(url_for("importa"))


# ---------------------------------------------------------------
# BACKUP E RIPRISTINO
# ---------------------------------------------------------------

MIMETYPE_SQLITE = "application/vnd.sqlite3"


@app.route("/backup")
@solo_admin
def backup_pagina() -> ResponseReturnValue:
    return render_template(
        "backup.html",
        backups=backup.elenco(app.config["BACKUP_DIR"]),
        totale_alimenti=get_stats()[0],
        conservati=backup.BACKUP_CONSERVATI,
        max_mb=app.config["MAX_UPLOAD_MB"],
    )


@app.route("/backup/scarica")
@solo_admin
def backup_scarica() -> ResponseReturnValue:
    dati = backup.istantanea(DB_PATH)
    return invia_file(dati, f"alimenti_{datetime.now():%Y%m%d-%H%M%S}.db", MIMETYPE_SQLITE)


@app.route("/backup/scarica/<nome>")
@solo_admin
def backup_scarica_salvato(nome: str) -> ResponseReturnValue:
    percorso = backup.percorso(app.config["BACKUP_DIR"], nome)

    if not percorso:
        abort(404)

    with open(percorso, "rb") as f:
        return invia_file(f.read(), nome, MIMETYPE_SQLITE)


@app.route("/backup/crea", methods=["POST"])
@solo_admin
def backup_crea() -> ResponseReturnValue:
    nome = backup.crea(DB_PATH, app.config["BACKUP_DIR"], "manuale")
    flash(f"Backup salvato: {nome}.", "success")
    return redirect(url_for("backup_pagina"))


def esegui_ripristino(file_db: str, etichetta: str) -> None:
    try:
        alimenti = backup.verifica(file_db)
    except backup.ErroreBackup as exc:
        flash(f"Ripristino non eseguito: {exc}", "danger")
        return

    cartella = app.config["BACKUP_DIR"]

    # La potatura dei vecchi backup si fa dopo: il file da ripristinare
    # potrebbe essere proprio il più vecchio della cartella
    nome_backup = backup.crea(DB_PATH, cartella, "ripristino", pota_vecchi=False)
    backup.ripristina(file_db, DB_PATH)
    backup.pota(cartella)

    # Un backup di una versione precedente si porta allo schema attuale
    # (il database da sostituire è già nel backup appena creato)
    init_db(backup_prima=False)

    flash(
        f"Database ripristinato da {etichetta}: {alimenti} alimenti. "
        f"Il database precedente è nel backup {nome_backup}.",
        "success"
    )


@app.route("/backup/ripristina", methods=["POST"])
@solo_admin
def backup_ripristina() -> ResponseReturnValue:
    file = request.files.get("file")

    if not file or not file.filename:
        flash("Seleziona il file del database da ripristinare.", "danger")
        return redirect(url_for("backup_pagina"))

    if request.form.get("conferma") != "1":
        flash("Per ripristinare spunta la casella di conferma.", "danger")
        return redirect(url_for("backup_pagina"))

    temporaneo = os.path.join(cartella_import(), f"ripristino-{secrets.token_hex(8)}.db")
    file.save(temporaneo)

    try:
        esegui_ripristino(temporaneo, os.path.basename(file.filename.replace("\\", "/")))
    finally:
        os.remove(temporaneo)

    return redirect(url_for("backup_pagina"))


@app.route("/backup/ripristina/<nome>", methods=["POST"])
@solo_admin
def backup_ripristina_salvato(nome: str) -> ResponseReturnValue:
    percorso = backup.percorso(app.config["BACKUP_DIR"], nome)

    if not percorso:
        abort(404)

    esegui_ripristino(percorso, nome)
    return redirect(url_for("backup_pagina"))


# ---------------------------------------------------------------
# PASTO (nella sessione) E DIARIO ALIMENTARE (per utente)
# ---------------------------------------------------------------

PASTO_MAX_VOCI = 30
GIORNI_RIEPILOGO = 7
ID_IN_TESTO_RE = re.compile(r"#(\d+)\s*$")
CHIAVI_PASTI = {chiave for chiave, _ in nutrienti.PASTI}

# Valori per 100 g copiati nel diario al momento dell'inserimento
CAMPI_DIARIO = (
    "categoria", "tef_percent", "indice_glicemico",
    *nutrienti.CAMPI_PER_PORZIONE,
    *analisi.CAMPI_RISCHIO,
)


elenco_per_ricerca = archivio.elenco_per_ricerca


def trova_alimento_da_modulo(form: Mapping[str, str]) -> tuple[Alimento | None, str | None]:
    """
    (alimento, errore) dal campo alimento_id, dal testo "Nome · Categoria · #id"
    scelto nella ricerca, oppure da un nome esatto se non è ambiguo.
    """
    testo_id = (form.get("alimento_id") or "").strip()
    testo = (form.get("cerca") or "").strip()

    if not testo_id:
        corrispondenza = ID_IN_TESTO_RE.search(testo)
        testo_id = corrispondenza.group(1) if corrispondenza else ""

    if testo_id.isdigit():
        item = get_alimento(int(testo_id))
        return (item, None) if item else (None, "Alimento non trovato.")

    if not testo:
        return None, "Scegli un alimento dall'elenco."

    righe = archivio.ids_per_nome(testo)

    if len(righe) == 1:
        return get_alimento(righe[0]), None

    if righe:
        return None, f"Ci sono {len(righe)} alimenti «{testo}»: scegline uno dall'elenco."

    return None, f"Nessun alimento «{testo}»: scegline uno dall'elenco."


def grammi_non_validi() -> None:
    flash(
        f"Grammi non validi: servono da {nutrienti.GRAMMI_MIN} a {nutrienti.GRAMMI_MAX} g.",
        "danger"
    )


def leggi_pasto() -> list[dict[str, Any]]:
    voci = []

    for voce in session.get("pasto", []):
        try:
            voci.append({"id": int(voce["id"]), "grammi": float(voce["grammi"])})
        except (KeyError, TypeError, ValueError):
            continue

    return voci[:PASTO_MAX_VOCI]


def carica_voci(voci: list[dict[str, Any]]) -> list[tuple[Alimento, float, int]]:
    """
    [(alimento, grammi, indice)] per le voci del pasto il cui alimento esiste ancora.
    """
    if not voci:
        return []

    per_id = archivio.get_alimenti_per_id(sorted({voce["id"] for voce in voci}))
    return [
        (per_id[voce["id"]], voce["grammi"], indice)
        for indice, voce in enumerate(voci)
        if voce["id"] in per_id
    ]


def riepilogo_nutrizionale(voci: list[tuple[Alimento, float]]) -> dict[str, Any] | None:
    """
    Totali, dati mancanti e profilo di rischio (con radar) di una lista di (alimento, grammi).
    """
    if not voci:
        return None

    somme, mancanti = nutrienti.totali(voci)
    profilo = nutrienti.profilo_rischio(voci)

    return {
        "totali": somme,
        "mancanti": mancanti,
        "profilo": profilo,
        "radar": analisi.radar({}, punti={r["campo"]: r["punti"] for r in profilo["rischi"]}),
        "voci": len(voci),
    }


def pasto_dell_ora() -> str:
    ora = datetime.now().hour

    if ora < 11:
        return "colazione"

    if ora < 15:
        return "pranzo"

    if ora < 18:
        return "spuntino"

    return "cena"


@app.route("/pasto")
def pasto() -> ResponseReturnValue:
    voci = carica_voci(leggi_pasto())

    return render_template(
        "pasto.html",
        voci=voci,
        riepilogo=riepilogo_nutrizionale([(item, grammi) for item, grammi, _ in voci]),
        elenco=elenco_per_ricerca(),
        oggi=date.today().isoformat(),
        pasto_suggerito=pasto_dell_ora(),
        max_voci=PASTO_MAX_VOCI,
    )


@app.route("/pasto/aggiungi", methods=["POST"])
def pasto_aggiungi() -> ResponseReturnValue:
    destinazione = url_sicuro(request.form.get("next")) or url_for("pasto")
    item, errore = trova_alimento_da_modulo(request.form)
    grammi = nutrienti.leggi_grammi(request.form.get("grammi"))

    if errore or item is None:
        flash(errore or "Alimento non trovato.", "danger")
        return redirect(destinazione)

    if grammi is None:
        grammi_non_validi()
        return redirect(destinazione)

    voci = leggi_pasto()
    esistente = next((voce for voce in voci if voce["id"] == item["id"]), None)

    if esistente:
        esistente["grammi"] = min(round(esistente["grammi"] + grammi, 1), nutrienti.GRAMMI_MAX)
    elif len(voci) >= PASTO_MAX_VOCI:
        flash(f"Il pasto può contenere al massimo {PASTO_MAX_VOCI} alimenti.", "warning")
        return redirect(destinazione)
    else:
        voci.append({"id": item["id"], "grammi": grammi})

    session["pasto"] = voci
    flash(f"Aggiunto al pasto: {item['alimento']}, {filtro_numero(grammi)} g.", "success")
    return redirect(destinazione)


@app.route("/pasto/aggiorna", methods=["POST"])
def pasto_aggiorna() -> ResponseReturnValue:
    voci = leggi_pasto()
    rimuovi = (request.form.get("rimuovi") or "").strip()

    if rimuovi.isdigit():
        if int(rimuovi) < len(voci):
            del voci[int(rimuovi)]
    else:
        for indice, voce in enumerate(voci):
            testo = request.form.get(f"grammi_{indice}")

            if testo is None:
                continue

            grammi = nutrienti.leggi_grammi(testo)

            if grammi is None:
                grammi_non_validi()
                return redirect(url_for("pasto"))

            voce["grammi"] = grammi

    session["pasto"] = voci
    return redirect(url_for("pasto"))


@app.route("/pasto/svuota", methods=["POST"])
def pasto_svuota() -> ResponseReturnValue:
    session.pop("pasto", None)
    flash("Pasto svuotato.", "info")
    return redirect(url_for("pasto"))


def leggi_giorno(testo: str | None) -> date | None:
    try:
        return date.fromisoformat((testo or "").strip())
    except ValueError:
        return None


def istantanea_diario(item: Alimento) -> str:
    return json.dumps({campo: item.get(campo) for campo in CAMPI_DIARIO}, ensure_ascii=False)


def inserisci_diario(
    conn: sqlite3.Connection, giorno: date, pasto_chiave: str, item: Alimento, grammi: float
) -> None:
    conn.execute(
        """
        INSERT INTO diario (utente_id, data, pasto, alimento_id, alimento, grammi, valori, creato_il)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_user.id, giorno.isoformat(), pasto_chiave, item["id"], item["alimento"],
            grammi, istantanea_diario(item), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def voci_diario(utente_id: int, dal: date, al: date | None = None) -> list[dict[str, Any]]:
    """
    Voci del diario tra due date (comprese), con i valori per 100 g salvati.
    """
    conn = get_db_diario()
    righe = conn.execute(
        """
        SELECT id, data, pasto, alimento_id, alimento, grammi, valori
        FROM diario
        WHERE utente_id = ? AND data BETWEEN ? AND ?
        ORDER BY data, id
        """,
        (utente_id, dal.isoformat(), (al or dal).isoformat()),
    ).fetchall()
    conn.close()

    voci = []

    for riga in righe:
        try:
            valori = json.loads(riga["valori"])
        except (TypeError, ValueError):
            valori = {}

        voci.append({**dict(riga), "item": {**valori, "alimento": riga["alimento"]}})

    return voci


def collegamenti_schede(voci: list[dict[str, Any]]) -> set[int]:
    """
    ID degli alimenti ancora presenti con lo stesso nome (per il link alla scheda).
    """
    ids = sorted({v["alimento_id"] for v in voci if v["alimento_id"]})

    if not ids:
        return set()

    presenti = archivio.get_alimenti_per_id(ids)
    nomi = {v["alimento_id"]: v["alimento"] for v in voci}
    return {i for i, a in presenti.items() if a["alimento"] == nomi.get(i)}


def torna_al_diario(giorno: date) -> ResponseReturnValue:
    return redirect(url_for("diario", data=giorno.isoformat()))


@app.route("/diario")
@login_required
def diario() -> ResponseReturnValue:
    giorno = leggi_giorno(request.args.get("data")) or date.today()
    voci = voci_diario(current_user.id, giorno)

    per_pasto = []

    for chiave, etichetta in nutrienti.PASTI:
        del_pasto = [v for v in voci if v["pasto"] == chiave]
        kcal = sum((v["item"].get("kcal") or 0) * v["grammi"] / 100 for v in del_pasto)
        per_pasto.append((chiave, etichetta, del_pasto, kcal))

    # Ultimi giorni fino a quello mostrato: Kcal nette e TEF per giorno
    inizio = giorno - timedelta(days=GIORNI_RIEPILOGO - 1)
    settimana: list[dict[str, Any]] = []

    for i in range(GIORNI_RIEPILOGO):
        g = inizio + timedelta(days=i)
        del_giorno = [(v["item"], v["grammi"]) for v in voci_diario(current_user.id, g)]
        somme, _ = nutrienti.totali(del_giorno) if del_giorno else ({}, {})
        settimana.append({
            "giorno": g,
            "voci": len(del_giorno),
            "kcal_nette": somme.get("kcal_nette", 0),
            "tef_kcal": somme.get("tef_kcal", 0),
        })

    massimo = max((s["kcal_nette"] + s["tef_kcal"] for s in settimana), default=0)

    return render_template(
        "diario.html",
        giorno=giorno,
        oggi=date.today(),
        precedente=giorno - timedelta(days=1),
        successivo=giorno + timedelta(days=1),
        per_pasto=per_pasto,
        riepilogo=riepilogo_nutrizionale([(v["item"], v["grammi"]) for v in voci]),
        collegati=collegamenti_schede(voci),
        settimana=settimana,
        massimo_settimana=massimo,
        elenco=elenco_per_ricerca(),
        pasto_suggerito=pasto_dell_ora() if giorno == date.today() else "pranzo",
    )


@app.route("/diario/aggiungi", methods=["POST"])
@login_required
def diario_aggiungi() -> ResponseReturnValue:
    giorno = leggi_giorno(request.form.get("data")) or date.today()
    pasto_chiave = request.form.get("pasto", "")
    item, errore = trova_alimento_da_modulo(request.form)
    grammi = nutrienti.leggi_grammi(request.form.get("grammi"))

    if pasto_chiave not in CHIAVI_PASTI:
        flash("Scegli il pasto: colazione, pranzo, cena o spuntino.", "danger")
    elif errore or item is None:
        flash(errore or "Alimento non trovato.", "danger")
    elif grammi is None:
        grammi_non_validi()
    else:
        conn = get_db_diario()
        inserisci_diario(conn, giorno, pasto_chiave, item, grammi)
        conn.commit()
        conn.close()
        flash(f"Aggiunto al diario: {item['alimento']}, {filtro_numero(grammi)} g.", "success")

    return torna_al_diario(giorno)


@app.route("/diario/aggiungi-pasto", methods=["POST"])
@login_required
def diario_aggiungi_pasto() -> ResponseReturnValue:
    giorno = leggi_giorno(request.form.get("data")) or date.today()
    pasto_chiave = request.form.get("pasto", "")
    voci = carica_voci(leggi_pasto())

    if pasto_chiave not in CHIAVI_PASTI:
        flash("Scegli il pasto: colazione, pranzo, cena o spuntino.", "danger")
        return redirect(url_for("pasto"))

    if not voci:
        flash("Il pasto è vuoto.", "warning")
        return redirect(url_for("pasto"))

    conn = get_db_diario()

    for item, grammi, _ in voci:
        inserisci_diario(conn, giorno, pasto_chiave, item, grammi)

    conn.commit()
    conn.close()

    if request.form.get("svuota") == "1":
        session.pop("pasto", None)

    flash(f"Salvati nel diario {len(voci)} alimenti.", "success")
    return torna_al_diario(giorno)


def voce_diario_propria(voce_id: int) -> sqlite3.Row:
    """
    Voce del diario dell'utente connesso, altrimenti 404 (anche se è di un altro utente).
    """
    conn = get_db_diario()
    riga = conn.execute(
        "SELECT id, data FROM diario WHERE id = ? AND utente_id = ?", (voce_id, current_user.id)
    ).fetchone()
    conn.close()

    if riga is None:
        abort(404)

    return riga


@app.route("/diario/voce/<int:voce_id>/aggiorna", methods=["POST"])
@login_required
def diario_aggiorna(voce_id: int) -> ResponseReturnValue:
    riga = voce_diario_propria(voce_id)
    grammi = nutrienti.leggi_grammi(request.form.get("grammi"))

    if grammi is None:
        grammi_non_validi()
    else:
        conn = get_db_diario()
        conn.execute("UPDATE diario SET grammi = ? WHERE id = ?", (grammi, voce_id))
        conn.commit()
        conn.close()

    return torna_al_diario(date.fromisoformat(riga["data"]))


@app.route("/diario/voce/<int:voce_id>/elimina", methods=["POST"])
@login_required
def diario_elimina(voce_id: int) -> ResponseReturnValue:
    riga = voce_diario_propria(voce_id)

    conn = get_db_diario()
    conn.execute("DELETE FROM diario WHERE id = ?", (voce_id,))
    conn.commit()
    conn.close()

    flash("Voce eliminata dal diario.", "info")
    return torna_al_diario(date.fromisoformat(riga["data"]))


# ---------------------------------------------------------------
# GESTIONE UTENTI (riga di comando)
#   flask --app app crea-utente <username> [--ruolo admin|visitatore]
#   flask --app app imposta-password <username>
#   flask --app app elenco-utenti
#   flask --app app elimina-utente <username>
# ---------------------------------------------------------------

def valida_username(ctx: click.Context, param: click.Parameter, username: str) -> str:
    if not USERNAME_RE.match(username):
        raise click.BadParameter(
            "usa 3-32 caratteri tra lettere, numeri, punto, trattino e underscore."
        )

    return username


def valida_password(ctx: click.Context, param: click.Parameter, password: str) -> str:
    if len(password) < PASSWORD_MIN:
        raise click.BadParameter(f"servono almeno {PASSWORD_MIN} caratteri.")

    return password


@app.cli.command("crea-utente")
@click.argument("username", callback=valida_username)
@click.option(
    "--ruolo",
    type=click.Choice(RUOLI),
    default="admin",
    show_default=True,
    help="admin: gestione completa; visitatore: sola consultazione."
)
@click.password_option(
    "--password",
    prompt="Password",
    confirmation_prompt="Ripeti la password",
    callback=valida_password
)
def crea_utente_cmd(username: str, ruolo: str, password: str) -> None:
    """Crea un nuovo utente."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_utenti()

    try:
        conn.execute(
            """
            INSERT INTO utenti (username, password_hash, ruolo, creato_il)
            VALUES (?, ?, ?, ?)
            """,
            (username, generate_password_hash(password), ruolo, now)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise click.ClickException(f"L'utente '{username}' esiste già.") from None
    finally:
        conn.close()

    click.echo(f"Utente '{username}' creato con ruolo {ruolo}.")


@app.cli.command("crea-admin-iniziale")
def crea_admin_iniziale_cmd() -> None:
    """Crea l'amministratore da ADMIN_USERNAME e ADMIN_PASSWORD se non ne esiste nessuno (primo deploy)."""
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not username or not password:
        click.echo("ADMIN_USERNAME e ADMIN_PASSWORD non impostate: nessun amministratore creato.")
        return

    if not USERNAME_RE.match(username):
        raise click.ClickException(
            "ADMIN_USERNAME: usa 3-32 caratteri tra lettere, numeri, punto, trattino e underscore."
        )

    if len(password) < PASSWORD_MIN:
        raise click.ClickException(f"ADMIN_PASSWORD: servono almeno {PASSWORD_MIN} caratteri.")

    conn = get_db_utenti()

    try:
        if conn.execute("SELECT COUNT(*) FROM utenti WHERE ruolo = 'admin'").fetchone()[0]:
            click.echo("Esiste già un amministratore: nessun utente creato.")
            return

        conn.execute(
            "INSERT INTO utenti (username, password_hash, ruolo, creato_il) VALUES (?, ?, 'admin', ?)",
            (username, generate_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise click.ClickException(f"L'utente '{username}' esiste già (non come amministratore).") from None
    finally:
        conn.close()

    click.echo(f"Amministratore '{username}' creato. Puoi togliere ADMIN_PASSWORD dalla configurazione.")


@app.cli.command("imposta-password")
@click.argument("username")
@click.password_option(
    "--password",
    prompt="Nuova password",
    confirmation_prompt="Ripeti la password",
    callback=valida_password
)
def imposta_password_cmd(username: str, password: str) -> None:
    """Cambia la password di un utente."""
    conn = get_db_utenti()
    cur = conn.execute(
        "UPDATE utenti SET password_hash = ? WHERE username = ?",
        (generate_password_hash(password), username)
    )
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        raise click.ClickException(f"Utente '{username}' non trovato.")

    click.echo(f"Password di '{username}' aggiornata.")


@app.cli.command("elenco-utenti")
def elenco_utenti_cmd() -> None:
    """Elenca gli utenti registrati."""
    conn = get_db_utenti()
    rows = conn.execute(
        "SELECT username, ruolo, creato_il FROM utenti ORDER BY username"
    ).fetchall()
    conn.close()

    if not rows:
        click.echo(
            "Nessun utente registrato. "
            "Creane uno con: flask --app app crea-utente <username>"
        )
        return

    for row in rows:
        click.echo(f"{row['username']:<32} {row['ruolo']:<11} {row['creato_il'] or ''}")


@app.cli.command("elimina-utente")
@click.argument("username")
@click.confirmation_option(prompt="Confermi l'eliminazione dell'utente?")
def elimina_utente_cmd(username: str) -> None:
    """Elimina un utente."""
    conn = get_db_utenti()
    riga = conn.execute("SELECT id FROM utenti WHERE username = ?", (username,)).fetchone()

    if riga is None:
        conn.close()
        raise click.ClickException(f"Utente '{username}' non trovato.")

    conn.execute("DELETE FROM utenti WHERE id = ?", (riga["id"],))
    conn.commit()
    conn.close()

    # Il diario è personale: si elimina insieme all'utente
    conn = get_db_diario()
    voci = conn.execute("DELETE FROM diario WHERE utente_id = ?", (riga["id"],)).rowcount
    conn.commit()
    conn.close()

    click.echo(f"Utente '{username}' eliminato" + (f", con {voci} voci di diario." if voci else "."))


@app.cli.command("usda-nutrienti")
@click.option("--api-key", envvar="USDA_API_KEY", default="DEMO_KEY", show_default=True,
              help="Chiave USDA FoodData Central (variabile USDA_API_KEY).")
@click.option("--pagine", default=1, show_default=True, type=click.IntRange(1, 20),
              help="Pagine da 200 alimenti dell'elenco USDA.")
@click.option("--sovrascrivi", is_flag=True, help="Sostituisce anche i valori già presenti.")
@click.option("--prova", is_flag=True, help="Mostra cosa cambierebbe senza scrivere.")
def usda_nutrienti_cmd(api_key: str, pagine: int, sovrascrivi: bool, prova: bool) -> None:
    """Compila macro e micronutrienti degli alimenti USDA (abbinati per nome)."""
    try:
        alimenti_usda = usda.scarica(api_key, pagine)
    except usda.ErroreUsda as exc:
        raise click.ClickException(str(exc)) from None

    conn = get_db()

    try:
        piano = usda.pianifica(conn, alimenti_usda, sovrascrivi)
        campi = sum(len(voce["valori"]) for voce in piano)
        click.echo(
            f"Scaricati {len(alimenti_usda)} alimenti USDA: {len(piano)} da aggiornare "
            f"nel database ({campi} valori)."
        )

        for voce in piano[:5]:
            click.echo(f"  - {voce['alimento']} (FDC {voce['fdc_id']}): {len(voce['valori'])} valori")

        if prova or not piano:
            click.echo("Nessuna modifica scritta." if prova else "Niente da aggiornare.")
            return

        nome_backup = backup.crea(DB_PATH, app.config["BACKUP_DIR"], "usda")
        usda.applica(conn, piano, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        conn.commit()
    finally:
        conn.close()

    click.echo(f"Aggiornati {len(piano)} alimenti. Backup del database precedente: {nome_backup}.")


# ---------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------

def richiesta_api() -> bool:
    return request.path == "/api" or request.path.startswith("/api/")


@app.errorhandler(403)
def forbidden(error: HTTPException) -> ResponseReturnValue:
    if richiesta_api():
        return api.errore_json(error)

    return "<h1>403</h1><p>Operazione riservata agli amministratori.</p>", 403


@app.errorhandler(404)
def not_found(error: HTTPException) -> ResponseReturnValue:
    if richiesta_api():
        return api.errore_json(error)

    return "<h1>404</h1><p>Risorsa non trovata.</p>", 404


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
        f"File troppo grande: il limite è {app.config['MAX_UPLOAD_MB']} MB.",
        "danger"
    )
    pagina = "backup_pagina" if request.path.startswith("/backup") else "importa"
    return redirect(url_for(pagina))


@app.errorhandler(CSRFError)
def csrf_non_valido(error: CSRFError) -> ResponseReturnValue:
    flash("Sessione scaduta o richiesta non valida: riprova.", "danger")
    return redirect(pagina_precedente() or url_for("index"))


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
# AVVIO
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# API E CONTROLLO DI SALUTE
# ---------------------------------------------------------------

app.register_blueprint(api.bp)


@app.route("/salute")
def salute() -> ResponseReturnValue:
    """
    Controllo per Docker e Render: risponde 200 se il database è leggibile.
    """
    try:
        versione, ultima = database.stato(DB_PATH, "alimenti")
        conn = get_db()
        conn.execute("SELECT 1 FROM alimenti LIMIT 1").fetchall()
        conn.close()
    except sqlite3.Error:
        return jsonify({"stato": "errore"}), 503

    return jsonify({"stato": "ok", "schema_alimenti": versione, "schema_aggiornato": versione == ultima})


@app.cli.command("db-stato")
def db_stato_cmd() -> None:
    """Mostra la versione dello schema dei tre database."""
    for nome, percorso in (("alimenti", DB_PATH), ("utenti", UTENTI_DB_PATH), ("diario", DIARIO_DB_PATH)):
        versione, ultima = database.stato(percorso, nome)
        click.echo(f"{nome:9} versione {versione} di {ultima}  ({percorso})")


# Crea/aggiorna le tabelle (migrazioni) anche quando l'app è avviata con
# "flask run" o da un server WSGI, non solo con "python app.py".
init_db()


if __name__ == "__main__":
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
