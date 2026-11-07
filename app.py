import io
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from datetime import datetime
from functools import wraps
from urllib.parse import urlsplit

import click
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    send_file,
    session
)
from flask_login import (
    AnonymousUserMixin,
    LoginManager,
    UserMixin,
    current_user,
    login_user,
    logout_user
)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import analisi
import backup
import esportazione
import importazione
from config import carica_config

app = Flask(__name__)
app.config.update(carica_config())

# Funzioni di analisi disponibili nei template
app.jinja_env.globals.update(
    stato_rischio=analisi.stato,
    livello_punteggio=analisi.livello_punteggio,
    LIVELLI_RISCHIO=analisi.LIVELLI,
)


@app.template_filter("percentuale")
def filtro_percentuale(valore, decimali=1):
    """
    59.43 -> "59,4%" (virgola decimale italiana).
    """
    return f"{valore:.{decimali}f}".replace(".", ",") + "%"


@app.template_filter("numero")
def filtro_numero(valore, decimali=None):
    """
    Numero con virgola decimale; senza decimali indicati usa la forma compatta (%g).
    """
    if valore is None:
        return "–"

    testo = f"{valore:g}" if decimali is None else f"{valore:.{decimali}f}"
    return testo.replace(".", ",")

DB_PATH = app.config["DATABASE_PATH"]
UTENTI_DB_PATH = app.config["UTENTI_DB_PATH"]

# Protezione CSRF su tutti i form POST (i template usano csrf_token())
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Accedi per continuare."
login_manager.login_message_category = "warning"


# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # punteggio(r1..r5): punteggio sintetico 0-100, usabile in SELECT e ORDER BY
    conn.create_function(
        "punteggio", len(analisi.CAMPI_RISCHIO), analisi.calcola_punteggio, deterministic=True
    )
    return conn


# Colonne lette da ogni query sugli alimenti, punteggio calcolato compreso
SELECT_ALIMENTI = (
    "SELECT *, punteggio(" + ", ".join(analisi.CAMPI_RISCHIO) + ") AS punteggio FROM alimenti"
)


def get_db_utenti():
    """
    Gli utenti stanno in un database separato (utenti.db, escluso da git):
    alimenti.db è versionato e non deve contenere credenziali.
    """
    conn = sqlite3.connect(UTENTI_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Crea le tabelle se non esistono e aggiunge eventuali colonne mancanti.
    """
    init_db_utenti()

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS alimenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alimento TEXT NOT NULL,
            categoria TEXT,

            kcal REAL DEFAULT 0,
            tef_kcal REAL DEFAULT 0,
            tef_percent REAL DEFAULT 0,
            kcal_nette REAL DEFAULT 0,

            fruttosio REAL DEFAULT 0,
            fibre REAL DEFAULT 0,
            rapporto REAL DEFAULT 0,

            rischio_diabete TEXT,
            rischio_colesterolo TEXT,
            rischio_malassorbimento TEXT,
            rischio_metabolico TEXT,
            rischio_tumorale TEXT,

            aggiornato_il TEXT
        )
    """)

    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(alimenti)").fetchall()
    }

    required_columns = {
        "kcal": "REAL DEFAULT 0",
        "tef_kcal": "REAL DEFAULT 0",
        "tef_percent": "REAL DEFAULT 0",
        "kcal_nette": "REAL DEFAULT 0",
        "fruttosio": "REAL DEFAULT 0",
        "fibre": "REAL DEFAULT 0",
        "rapporto": "REAL DEFAULT 0",
        "rischio_diabete": "TEXT",
        "rischio_colesterolo": "TEXT",
        "rischio_malassorbimento": "TEXT",
        "rischio_metabolico": "TEXT",
        "rischio_tumorale": "TEXT",
        "aggiornato_il": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if column_name not in existing:
            conn.execute(
                f"ALTER TABLE alimenti ADD COLUMN {column_name} {column_type}"
            )

    conn.commit()
    conn.close()


def init_db_utenti():
    conn = get_db_utenti()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            ruolo TEXT NOT NULL DEFAULT 'visitatore'
                CHECK (ruolo IN ('admin', 'visitatore')),
            creato_il TEXT
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------

def to_float(value, default=0.0):
    """
    Converte un valore in float.
    Gestisce anche:
    - virgola decimale: "5,9" -> 5.9
    - Inf
    - NA / ND
    """
    if value is None:
        return default

    text = str(value).strip().replace(" ", "")

    if not text:
        return default

    low = text.lower()

    if low in ("inf", "infinity", "∞"):
        return 999999.0

    if low in ("na", "n/a", "nd", "-"):
        return default

    text = text.replace(",", ".")

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass

    try:
        return float(text)
    except ValueError:
        return default


# ---------------------------------------------------------------
# FORM / CRUD HELPERS
# ---------------------------------------------------------------

def parse_form():
    """
    Legge e sistema i dati inviati dal form CRUD.
    Calcola automaticamente alcuni campi se lasciati vuoti:
    - TEF (Kcal) da Kcal e TEF (%)
    - TEF (%) da TEF (Kcal) e Kcal
    - Kcal Nette = Kcal - TEF (Kcal)
    - Rapporto F/F = Fruttosio / Fibre
    """
    alimento_val = (request.form.get("alimento") or "").strip()
    categoria = (request.form.get("categoria") or "").strip()

    kcal = to_float(request.form.get("kcal"))

    tef_percent_raw = (request.form.get("tef_percent") or "").strip()
    tef_kcal_raw = (request.form.get("tef_kcal") or "").strip()
    kcal_nette_raw = (request.form.get("kcal_nette") or "").strip()

    tef_percent = to_float(tef_percent_raw) if tef_percent_raw else 0.0
    tef_kcal = to_float(tef_kcal_raw) if tef_kcal_raw else 0.0

    if tef_kcal_raw == "" and tef_percent:
        tef_kcal = round(kcal * tef_percent / 100, 2) if kcal else 0.0

    if tef_percent_raw == "" and tef_kcal and kcal:
        tef_percent = round(tef_kcal / kcal * 100, 2)

    kcal_nette = to_float(kcal_nette_raw) if kcal_nette_raw else round(kcal - tef_kcal, 2)

    fruttosio = to_float(request.form.get("fruttosio"))
    fibre = to_float(request.form.get("fibre"))

    rapporto_raw = (request.form.get("rapporto") or "").strip()
    if rapporto_raw == "":
        rapporto = round(fruttosio / fibre, 3) if fibre else 0.0
    else:
        rapporto = to_float(rapporto_raw)

    rischio_diabete = (request.form.get("rischio_diabete") or "").strip()
    rischio_colesterolo = (request.form.get("rischio_colesterolo") or "").strip()
    rischio_malassorbimento = (request.form.get("rischio_malassorbimento") or "").strip()
    rischio_metabolico = (request.form.get("rischio_metabolico") or "").strip()
    rischio_tumorale = (request.form.get("rischio_tumorale") or "").strip()

    return (
        alimento_val,
        categoria,
        kcal,
        tef_kcal,
        tef_percent,
        kcal_nette,
        fruttosio,
        fibre,
        rapporto,
        rischio_diabete,
        rischio_colesterolo,
        rischio_malassorbimento,
        rischio_metabolico,
        rischio_tumorale
    )


def get_alimento(alimento_id):
    """
    Restituisce un singolo alimento oppure None.
    """
    conn = get_db()
    row = conn.execute(
        f"{SELECT_ALIMENTI} WHERE id = ?",
        (alimento_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


# ---------------------------------------------------------------
# QUERY / FILTRI / STATISTICHE
# ---------------------------------------------------------------

SORT_EXPRESSIONS = {
    "alimento": "LOWER(alimento)",
    "categoria": "LOWER(COALESCE(categoria, ''))",
    "kcal": "COALESCE(kcal, 0)",
    "tef_kcal": "COALESCE(tef_kcal, 0)",
    "tef_percent": "COALESCE(tef_percent, 0)",
    "kcal_nette": "COALESCE(kcal_nette, 0)",
    "fruttosio": "COALESCE(fruttosio, 0)",
    "fibre": "COALESCE(fibre, 0)",
    "rapporto": "COALESCE(rapporto, 0)",
    "rischio_diabete": "LOWER(COALESCE(rischio_diabete, ''))",
    "rischio_colesterolo": "LOWER(COALESCE(rischio_colesterolo, ''))",
    "rischio_malassorbimento": "LOWER(COALESCE(rischio_malassorbimento, ''))",
    "rischio_metabolico": "LOWER(COALESCE(rischio_metabolico, ''))",
    "rischio_tumorale": "LOWER(COALESCE(rischio_tumorale, ''))",
    "punteggio": "COALESCE(punteggio(" + ", ".join(analisi.CAMPI_RISCHIO) + "), -1)",
}

# Parametri di filtro della home (e degli export), con le etichette per i file esportati
ETICHETTE_FILTRI = {
    "categoria": "Categoria",
    **{campo: f"Rischio {etichetta.lower()}" for campo, etichetta in analisi.RISCHI},
}


def leggi_filtri():
    """
    (filtri, sort, direction) dalla query string, già validati.
    """
    filtri = {
        campo: request.args.get(campo, "").strip()
        for campo in ETICHETTE_FILTRI
    }

    sort = request.args.get("sort", "alimento").strip()
    if sort not in SORT_EXPRESSIONS:
        sort = "alimento"

    direction = request.args.get("dir", "asc").strip().lower()
    if direction not in ("asc", "desc"):
        direction = "asc"

    return filtri, sort, direction


def get_alimenti(
    categoria="",
    rischio_diabete="",
    rischio_colesterolo="",
    rischio_malassorbimento="",
    rischio_metabolico="",
    rischio_tumorale="",
    sort="alimento",
    direction="asc"
):
    """
    Restituisce gli alimenti filtrati e ordinati.
    """
    sort_expr = SORT_EXPRESSIONS.get(sort, SORT_EXPRESSIONS["alimento"])
    dir_sql = "DESC" if direction.lower() == "desc" else "ASC"

    clauses = []
    params = []

    if categoria:
        clauses.append("LOWER(COALESCE(categoria, '')) = LOWER(?)")
        params.append(categoria)

    if rischio_diabete:
        clauses.append("LOWER(COALESCE(rischio_diabete, '')) = LOWER(?)")
        params.append(rischio_diabete)

    if rischio_colesterolo:
        clauses.append("LOWER(COALESCE(rischio_colesterolo, '')) = LOWER(?)")
        params.append(rischio_colesterolo)

    if rischio_malassorbimento:
        clauses.append("LOWER(COALESCE(rischio_malassorbimento, '')) = LOWER(?)")
        params.append(rischio_malassorbimento)

    if rischio_metabolico:
        clauses.append("LOWER(COALESCE(rischio_metabolico, '')) = LOWER(?)")
        params.append(rischio_metabolico)

    if rischio_tumorale:
        clauses.append("LOWER(COALESCE(rischio_tumorale, '')) = LOWER(?)")
        params.append(rischio_tumorale)

    sql = SELECT_ALIMENTI

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    sql += f" ORDER BY {sort_expr} {dir_sql}, LOWER(alimento) ASC"

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_stats():
    """
    Restituisce:
    - totale alimenti
    - alimenti con dati TEF
    """
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) AS n FROM alimenti").fetchone()["n"]

    con_tef = conn.execute("""
        SELECT COUNT(*) AS n
        FROM alimenti
        WHERE COALESCE(tef_kcal, 0) > 0
           OR COALESCE(tef_percent, 0) > 0
    """).fetchone()["n"]

    conn.close()

    return total, con_tef


def make_options(default_labels, db_values):
    """
    Crea una lista di opzioni per i campi select.
    default_labels è una lista di tuple: (valore, etichetta)
    """
    options = []
    seen = set()

    for value, label in default_labels:
        options.append({
            "value": value,
            "label": label
        })
        seen.add(value.lower())

    for value in db_values:
        if value is None:
            continue

        value = str(value).strip()

        if value and value.lower() not in seen:
            options.append({
                "value": value,
                "label": value
            })
            seen.add(value.lower())

    return options


def get_filter_options():
    """
    Recupera categorie e rischi disponibili dal database.
    Aggiunge comunque i valori standard previsti dal template.
    """
    conn = get_db()

    categories = [
        row["categoria"]
        for row in conn.execute("""
            SELECT DISTINCT categoria
            FROM alimenti
            WHERE categoria IS NOT NULL
              AND TRIM(categoria) != ''
            ORDER BY categoria
        """).fetchall()
    ]

    diabete_values = [
        row["rischio_diabete"]
        for row in conn.execute("""
            SELECT DISTINCT rischio_diabete
            FROM alimenti
            WHERE rischio_diabete IS NOT NULL
              AND TRIM(rischio_diabete) != ''
            ORDER BY rischio_diabete
        """).fetchall()
    ]

    colesterolo_values = [
        row["rischio_colesterolo"]
        for row in conn.execute("""
            SELECT DISTINCT rischio_colesterolo
            FROM alimenti
            WHERE rischio_colesterolo IS NOT NULL
              AND TRIM(rischio_colesterolo) != ''
            ORDER BY rischio_colesterolo
        """).fetchall()
    ]

    malassorbimento_values = [
        row["rischio_malassorbimento"]
        for row in conn.execute("""
            SELECT DISTINCT rischio_malassorbimento
            FROM alimenti
            WHERE rischio_malassorbimento IS NOT NULL
              AND TRIM(rischio_malassorbimento) != ''
            ORDER BY rischio_malassorbimento
        """).fetchall()
    ]

    metabolic_values = [
        row["rischio_metabolico"]
        for row in conn.execute("""
            SELECT DISTINCT rischio_metabolico
            FROM alimenti
            WHERE rischio_metabolico IS NOT NULL
              AND TRIM(rischio_metabolico) != ''
            ORDER BY rischio_metabolico
        """).fetchall()
    ]

    tumorale_values = [
        row["rischio_tumorale"]
        for row in conn.execute("""
            SELECT DISTINCT rischio_tumorale
            FROM alimenti
            WHERE rischio_tumorale IS NOT NULL
              AND TRIM(rischio_tumorale) != ''
            ORDER BY rischio_tumorale
        """).fetchall()
    ]

    conn.close()

    category_options = [
        {"value": c, "label": c}
        for c in categories
    ]

    # Scala a 4 livelli (analisi.LIVELLI), più eventuali altri valori presenti nel DB
    livelli_standard = [
        (liv["etichetta"], f"{liv['emoji']} {liv['etichetta']}")
        for liv in analisi.LIVELLI
    ]

    diabete_options = make_options(livelli_standard, diabete_values)
    colesterolo_options = make_options(livelli_standard, colesterolo_values)
    malassorbimento_options = make_options(livelli_standard, malassorbimento_values)
    metabolic_options = make_options(livelli_standard, metabolic_values)
    tumorale_options = make_options(livelli_standard, tumorale_values)

    return (
        category_options,
        diabete_options,
        colesterolo_options,
        malassorbimento_options,
        metabolic_options,
        tumorale_options
    )


def get_form_options():
    """
    Suggerimenti per i campi testuali del form nuovo/modifica
    (categorie e livelli di rischio), indicizzati per nome del campo.
    """
    (
        category_options,
        diabete_options,
        colesterolo_options,
        malassorbimento_options,
        metabolic_options,
        tumorale_options
    ) = get_filter_options()

    return {
        "categoria": category_options,
        "rischio_diabete": diabete_options,
        "rischio_colesterolo": colesterolo_options,
        "rischio_malassorbimento": malassorbimento_options,
        "rischio_metabolico": metabolic_options,
        "rischio_tumorale": tumorale_options,
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
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.ruolo = row["ruolo"]

    @property
    def is_admin(self):
        return self.ruolo == "admin"


class Anonimo(AnonymousUserMixin):
    username = None
    ruolo = None
    is_admin = False


login_manager.anonymous_user = Anonimo


@login_manager.user_loader
def carica_utente(user_id):
    conn = get_db_utenti()
    row = conn.execute(
        "SELECT id, username, ruolo FROM utenti WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    return Utente(row) if row else None


def solo_admin(view):
    """
    Riserva una route agli amministratori:
    anonimo -> pagina di login, visitatore -> 403.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if not current_user.is_admin:
            abort(403)

        return view(*args, **kwargs)

    return wrapper


@app.before_request
def controlla_accesso():
    """
    Con ACCESSO_PUBBLICO=false serve il login anche per consultare.
    """
    if app.config["ACCESSO_PUBBLICO"] or current_user.is_authenticated:
        return None

    if request.endpoint in ("login", "static"):
        return None

    return login_manager.unauthorized()


def url_sicuro(target):
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


def pagina_precedente():
    """
    Percorso della pagina di provenienza, solo se è sullo stesso host.
    """
    parts = urlsplit(request.referrer or "")

    if parts.netloc != request.host:
        return None

    return url_sicuro(parts.path + (f"?{parts.query}" if parts.query else ""))


@app.route("/login", methods=["GET", "POST"])
def login():
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
def logout():
    logout_user()
    flash("Disconnessione effettuata.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------
# ROUTE PRINCIPALI
# ---------------------------------------------------------------

@app.route("/")
def index():
    filtri, sort, direction = leggi_filtri()

    filter_categoria = filtri["categoria"]
    filter_diabete = filtri["rischio_diabete"]
    filter_colesterolo = filtri["rischio_colesterolo"]
    filter_malassorbimento = filtri["rischio_malassorbimento"]
    filter_metabolico = filtri["rischio_metabolico"]
    filter_tumorale = filtri["rischio_tumorale"]

    alimenti = get_alimenti(**filtri, sort=sort, direction=direction)

    total_alimenti, con_dati_tef = get_stats()

    (
        category_options,
        diabete_options,
        colesterolo_options,
        malassorbimento_options,
        metabolic_options,
        tumorale_options
    ) = get_filter_options()

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
        category_options=category_options,
        diabete_options=diabete_options,
        colesterolo_options=colesterolo_options,
        malassorbimento_options=malassorbimento_options,
        metabolic_options=metabolic_options,
        tumorale_options=tumorale_options
    )


@app.route("/alimento/<int:alimento_id>")
def scheda(alimento_id):
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    medaglie = analisi.medaglie_per_alimento(get_alimenti()).get(alimento_id, [])

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
    )


@app.route("/nuovo", methods=["GET", "POST"])
@solo_admin
def nuovo():
    if request.method == "POST":
        (
            alimento_val,
            categoria,
            kcal,
            tef_kcal,
            tef_percent,
            kcal_nette,
            fruttosio,
            fibre,
            rapporto,
            rischio_diabete,
            rischio_colesterolo,
            rischio_malassorbimento,
            rischio_metabolico,
            rischio_tumorale
        ) = parse_form()

        if not alimento_val:
            flash("Il campo Alimento è obbligatorio.", "danger")

            item = {
                "alimento": alimento_val,
                "categoria": categoria,
                "kcal": kcal,
                "tef_kcal": tef_kcal,
                "tef_percent": tef_percent,
                "kcal_nette": kcal_nette,
                "fruttosio": fruttosio,
                "fibre": fibre,
                "rapporto": rapporto,
                "rischio_diabete": rischio_diabete,
                "rischio_colesterolo": rischio_colesterolo,
                "rischio_malassorbimento": rischio_malassorbimento,
                "rischio_metabolico": rischio_metabolico,
                "rischio_tumorale": rischio_tumorale,
            }

            return render_template(
                "form.html",
                titolo="Nuovo alimento",
                sottotitolo="Inserisci un nuovo alimento nel database.",
                action=url_for("nuovo"),
                item=item,
                opzioni=get_form_options()
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        conn.execute(
            """
            INSERT INTO alimenti (
                alimento,
                categoria,
                kcal,
                tef_kcal,
                tef_percent,
                kcal_nette,
                fruttosio,
                fibre,
                rapporto,
                rischio_diabete,
                rischio_colesterolo,
                rischio_malassorbimento,
                rischio_metabolico,
                rischio_tumorale,
                aggiornato_il
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alimento_val,
                categoria,
                kcal,
                tef_kcal,
                tef_percent,
                kcal_nette,
                fruttosio,
                fibre,
                rapporto,
                rischio_diabete,
                rischio_colesterolo,
                rischio_malassorbimento,
                rischio_metabolico,
                rischio_tumorale,
                now
            )
        )
        conn.commit()
        conn.close()

        flash("Alimento aggiunto correttamente.", "success")
        return redirect(url_for("index"))

    return render_template(
        "form.html",
        titolo="Nuovo alimento",
        sottotitolo="Inserisci un nuovo alimento nel database.",
        action=url_for("nuovo"),
        item=None,
        opzioni=get_form_options()
    )


@app.route("/modifica/<int:alimento_id>", methods=["GET", "POST"])
@solo_admin
def modifica(alimento_id):
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    if request.method == "POST":
        (
            alimento_val,
            categoria,
            kcal,
            tef_kcal,
            tef_percent,
            kcal_nette,
            fruttosio,
            fibre,
            rapporto,
            rischio_diabete,
            rischio_colesterolo,
            rischio_malassorbimento,
            rischio_metabolico,
            rischio_tumorale
        ) = parse_form()

        if not alimento_val:
            flash("Il campo Alimento è obbligatorio.", "danger")

            item.update({
                "alimento": alimento_val,
                "categoria": categoria,
                "kcal": kcal,
                "tef_kcal": tef_kcal,
                "tef_percent": tef_percent,
                "kcal_nette": kcal_nette,
                "fruttosio": fruttosio,
                "fibre": fibre,
                "rapporto": rapporto,
                "rischio_diabete": rischio_diabete,
                "rischio_colesterolo": rischio_colesterolo,
                "rischio_malassorbimento": rischio_malassorbimento,
                "rischio_metabolico": rischio_metabolico,
                "rischio_tumorale": rischio_tumorale,
            })

            return render_template(
                "form.html",
                titolo="Modifica alimento",
                sottotitolo="Aggiorna i dati dell'alimento.",
                action=url_for("modifica", alimento_id=alimento_id),
                item=item,
                opzioni=get_form_options()
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        conn.execute(
            """
            UPDATE alimenti
            SET
                alimento = ?,
                categoria = ?,
                kcal = ?,
                tef_kcal = ?,
                tef_percent = ?,
                kcal_nette = ?,
                fruttosio = ?,
                fibre = ?,
                rapporto = ?,
                rischio_diabete = ?,
                rischio_colesterolo = ?,
                rischio_malassorbimento = ?,
                rischio_metabolico = ?,
                rischio_tumorale = ?,
                aggiornato_il = ?
            WHERE id = ?
            """,
            (
                alimento_val,
                categoria,
                kcal,
                tef_kcal,
                tef_percent,
                kcal_nette,
                fruttosio,
                fibre,
                rapporto,
                rischio_diabete,
                rischio_colesterolo,
                rischio_malassorbimento,
                rischio_metabolico,
                rischio_tumorale,
                now,
                alimento_id
            )
        )
        conn.commit()
        conn.close()

        flash("Alimento aggiornato correttamente.", "success")
        return redirect(url_for("index"))

    return render_template(
        "form.html",
        titolo="Modifica alimento",
        sottotitolo="Aggiorna i dati dell'alimento.",
        action=url_for("modifica", alimento_id=alimento_id),
        item=item,
        opzioni=get_form_options()
    )


@app.route("/elimina/<int:alimento_id>", methods=["POST"])
@solo_admin
def elimina(alimento_id):
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    conn = get_db()
    conn.execute(
        """
        DELETE FROM alimenti
        WHERE id = ?
        """,
        (alimento_id,)
    )
    conn.commit()
    conn.close()

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


def invia_file(dati, nome, mimetype):
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


def nome_file_sicuro(testo, alternativa):
    """
    "Pane integrale (100%)" -> "pane-integrale-100" per i nomi dei file scaricati.
    """
    ascii_ = unicodedata.normalize("NFKD", testo or "").encode("ascii", "ignore").decode()
    nome = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60]
    return nome or alternativa


def info_export(filtri, sort, direction, totale):
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
def esporta(formato):
    """
    Tabella con gli stessi filtri e lo stesso ordinamento della home.
    """
    if formato not in FORMATI_EXPORT:
        abort(404)

    filtri, sort, direction = leggi_filtri()
    alimenti = get_alimenti(**filtri, sort=sort, direction=direction)
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
def scheda_pdf(alimento_id):
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


def cartella_import():
    os.makedirs(app.config["IMPORT_DIR"], exist_ok=True)
    return app.config["IMPORT_DIR"]


def percorso_import(token):
    if not token or not TOKEN_IMPORT_RE.match(token):
        return None

    return os.path.join(cartella_import(), f"{token}.json")


def pulisci_import_scaduti():
    limite = time.time() - IMPORT_SCADENZA_SECONDI

    for voce in os.scandir(cartella_import()):
        try:
            if voce.is_file() and voce.stat().st_mtime < limite:
                os.remove(voce.path)
        except OSError:
            pass


def carica_import():
    """
    File letto e in attesa di conferma per questa sessione, oppure None.
    """
    percorso = percorso_import(session.get("import_token"))

    if not percorso or not os.path.isfile(percorso):
        return None

    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def scarta_import():
    percorso = percorso_import(session.pop("import_token", None))

    if percorso and os.path.isfile(percorso):
        os.remove(percorso)


@app.route("/importa", methods=["GET", "POST"])
@solo_admin
def importa():
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

        with open(percorso_import(token), "w", encoding="utf-8") as f:
            json.dump(letto, f, ensure_ascii=False)

        session["import_token"] = token
        return redirect(url_for("importa_anteprima"))

    return render_template(
        "import.html",
        in_attesa=carica_import(),
        max_mb=app.config["MAX_UPLOAD_MB"],
        max_righe=importazione.MAX_RIGHE,
    )


@app.route("/importa/anteprima")
@solo_admin
def importa_anteprima():
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
        campi=importazione.CAMPI,
        etichette=importazione.ETICHETTE,
        anteprima_righe=ANTEPRIMA_RIGHE,
        anteprima_avvisi=ANTEPRIMA_AVVISI,
    )


@app.route("/importa/conferma", methods=["POST"])
@solo_admin
def importa_conferma():
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
def importa_annulla():
    scarta_import()
    flash("Import annullato: il database non è stato modificato.", "info")
    return redirect(url_for("importa"))


# ---------------------------------------------------------------
# BACKUP E RIPRISTINO
# ---------------------------------------------------------------

MIMETYPE_SQLITE = "application/vnd.sqlite3"


@app.route("/backup")
@solo_admin
def backup_pagina():
    return render_template(
        "backup.html",
        backups=backup.elenco(app.config["BACKUP_DIR"]),
        totale_alimenti=get_stats()[0],
        conservati=backup.BACKUP_CONSERVATI,
        max_mb=app.config["MAX_UPLOAD_MB"],
    )


@app.route("/backup/scarica")
@solo_admin
def backup_scarica():
    dati = backup.istantanea(DB_PATH)
    return invia_file(dati, f"alimenti_{datetime.now():%Y%m%d-%H%M%S}.db", MIMETYPE_SQLITE)


@app.route("/backup/scarica/<nome>")
@solo_admin
def backup_scarica_salvato(nome):
    percorso = backup.percorso(app.config["BACKUP_DIR"], nome)

    if not percorso:
        abort(404)

    with open(percorso, "rb") as f:
        return invia_file(f.read(), nome, MIMETYPE_SQLITE)


@app.route("/backup/crea", methods=["POST"])
@solo_admin
def backup_crea():
    nome = backup.crea(DB_PATH, app.config["BACKUP_DIR"], "manuale")
    flash(f"Backup salvato: {nome}.", "success")
    return redirect(url_for("backup_pagina"))


def esegui_ripristino(file_db, etichetta):
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

    # Un backup di una versione precedente può non avere tutte le colonne
    init_db()

    flash(
        f"Database ripristinato da {etichetta}: {alimenti} alimenti. "
        f"Il database precedente è nel backup {nome_backup}.",
        "success"
    )


@app.route("/backup/ripristina", methods=["POST"])
@solo_admin
def backup_ripristina():
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
def backup_ripristina_salvato(nome):
    percorso = backup.percorso(app.config["BACKUP_DIR"], nome)

    if not percorso:
        abort(404)

    esegui_ripristino(percorso, nome)
    return redirect(url_for("backup_pagina"))


# ---------------------------------------------------------------
# GESTIONE UTENTI (riga di comando)
#   flask --app app crea-utente <username> [--ruolo admin|visitatore]
#   flask --app app imposta-password <username>
#   flask --app app elenco-utenti
#   flask --app app elimina-utente <username>
# ---------------------------------------------------------------

def valida_username(ctx, param, username):
    if not USERNAME_RE.match(username):
        raise click.BadParameter(
            "usa 3-32 caratteri tra lettere, numeri, punto, trattino e underscore."
        )

    return username


def valida_password(ctx, param, password):
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
def crea_utente_cmd(username, ruolo, password):
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


@app.cli.command("imposta-password")
@click.argument("username")
@click.password_option(
    "--password",
    prompt="Nuova password",
    confirmation_prompt="Ripeti la password",
    callback=valida_password
)
def imposta_password_cmd(username, password):
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
def elenco_utenti_cmd():
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
def elimina_utente_cmd(username):
    """Elimina un utente."""
    conn = get_db_utenti()
    cur = conn.execute("DELETE FROM utenti WHERE username = ?", (username,))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        raise click.ClickException(f"Utente '{username}' non trovato.")

    click.echo(f"Utente '{username}' eliminato.")


# ---------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------

@app.errorhandler(403)
def forbidden(error):
    return "<h1>403</h1><p>Operazione riservata agli amministratori.</p>", 403


@app.errorhandler(404)
def not_found(error):
    return "<h1>404</h1><p>Risorsa non trovata.</p>", 404


@app.errorhandler(413)
def file_troppo_grande(error):
    flash(
        f"File troppo grande: il limite è {app.config['MAX_UPLOAD_MB']} MB.",
        "danger"
    )
    pagina = "backup_pagina" if request.path.startswith("/backup") else "importa"
    return redirect(url_for(pagina))


@app.errorhandler(CSRFError)
def csrf_non_valido(error):
    flash("Sessione scaduta o richiesta non valida: riprova.", "danger")
    return redirect(pagina_precedente() or url_for("index"))


# ---------------------------------------------------------------
# INTESTAZIONI DI SICUREZZA
# ---------------------------------------------------------------

@app.after_request
def intestazioni_sicurezza(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# ---------------------------------------------------------------
# AVVIO
# ---------------------------------------------------------------

# Crea/aggiorna le tabelle anche quando l'app è avviata con "flask run"
# o da un server WSGI, non solo con "python app.py".
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
