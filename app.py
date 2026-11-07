import os
import re
import csv
import io
import sqlite3
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "alimenti.db")

app = Flask(__name__)
app.secret_key = "cambia-questa-chiave-segreta"


# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Crea la tabella se non esiste e aggiunge eventuali colonne mancanti.
    """
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


def normalize_header(value):
    """
    Normalizza l'intestazione di una colonna CSV.
    Esempio:
    "Fruttosio (g/100g)" -> "fruttosio g 100g"
    """
    value = str(value or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def csv_value(row, mapping, key):
    """
    Estrae in modo sicuro un valore dal CSV usando il mapping delle colonne.
    """
    original_column = mapping.get(key)

    if original_column is None:
        return ""

    return row.get(original_column) or ""


def decode_csv_bytes(raw):
    """
    Prova a decodificare il file CSV con diversi encoding.
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("latin-1", errors="replace")


def guess_delimiter(sample):
    """
    Prova a riconoscere il separatore del CSV.
    """
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def map_csv_fields(fieldnames):
    """
    Collega le intestazioni del CSV ai campi interni del database.
    """
    mapping = {}

    for original in fieldnames or []:
        norm = normalize_header(original)
        orig_lower = str(original or "").lower()

        if not norm:
            continue

        if "rapporto" in norm:
            mapping.setdefault("rapporto", original)

        elif "tef" in norm and ("%" in orig_lower or "percent" in norm):
            mapping.setdefault("tef_percent", original)

        elif "tef" in norm and "kcal" in norm:
            mapping.setdefault("tef_kcal", original)

        elif "tef" in norm:
            mapping.setdefault("tef_percent", original)

        elif ("kcal" in norm and "nette" in norm) or ("nette" in norm and "kcal" not in norm):
            mapping.setdefault("kcal_nette", original)

        elif norm == "kcal" or ("kcal" in norm and "tef" not in norm and "nette" not in norm):
            mapping.setdefault("kcal", original)

        elif "fruttosio" in norm:
            mapping.setdefault("fruttosio", original)

        elif "fibre" in norm or "fibra" in norm:
            mapping.setdefault("fibre", original)

        elif "categoria" in norm:
            mapping.setdefault("categoria", original)

        elif "diabete" in norm:
            mapping.setdefault("rischio_diabete", original)

        elif "colesterolo" in norm:
            mapping.setdefault("rischio_colesterolo", original)

        elif "malassorb" in norm:
            mapping.setdefault("rischio_malassorbimento", original)

        elif "metabolic" in norm or "metabolico" in norm:
            mapping.setdefault("rischio_metabolico", original)

        elif "tumorale" in norm or "tumoral" in norm:
            mapping.setdefault("rischio_tumorale", original)

        elif "alimento" in norm or "nome" in norm:
            mapping.setdefault("alimento", original)

    return mapping


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
        """
        SELECT *
        FROM alimenti
        WHERE id = ?
        """,
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
}


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

    sql = "SELECT * FROM alimenti"

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

    diabete_options = make_options(
        [
            ("Basso", "🟢 Basso"),
            ("Medio", "🟡 Medio"),
            ("Alto", "🔴 Alto"),
        ],
        diabete_values
    )

    colesterolo_options = make_options(
        [
            ("Basso", "🟢 Basso"),
            ("Medio", "🟡 Medio"),
            ("Alto", "🔴 Alto"),
        ],
        colesterolo_values
    )

    malassorbimento_options = make_options(
        [
            ("Basso", "🟢 Basso"),
            ("Medio", "🟡 Medio"),
            ("Alto", "🔴 Alto"),
        ],
        malassorbimento_values
    )

    metabolic_options = make_options(
        [
            ("Basso", "🟢 Basso"),
            ("Medio", "🟡 Medio"),
            ("Alto", "🔴 Alto"),
        ],
        metabolic_values
    )

    tumorale_options = make_options(
        [
            ("Protettivo", "🛡️ Protettivo"),
            ("Neutro", "⚪ Neutro"),
            ("Aumentato", "⚠️ Aumentato"),
        ],
        tumorale_values
    )

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
# ROUTE PRINCIPALI
# ---------------------------------------------------------------

@app.route("/")
def index():
    filter_categoria = request.args.get("categoria", "").strip()
    filter_diabete = request.args.get("rischio_diabete", "").strip()
    filter_colesterolo = request.args.get("rischio_colesterolo", "").strip()
    filter_malassorbimento = request.args.get("rischio_malassorbimento", "").strip()
    filter_metabolico = request.args.get("rischio_metabolico", "").strip()
    filter_tumorale = request.args.get("rischio_tumorale", "").strip()

    sort = request.args.get("sort", "alimento").strip()
    if sort not in SORT_EXPRESSIONS:
        sort = "alimento"

    direction = request.args.get("dir", "asc").strip().lower()
    if direction not in ("asc", "desc"):
        direction = "asc"

    alimenti = get_alimenti(
        categoria=filter_categoria,
        rischio_diabete=filter_diabete,
        rischio_colesterolo=filter_colesterolo,
        rischio_malassorbimento=filter_malassorbimento,
        rischio_metabolico=filter_metabolico,
        rischio_tumorale=filter_tumorale,
        sort=sort,
        direction=direction
    )

    total_alimenti, con_dati_tef = get_stats()

    (
        category_options,
        diabete_options,
        colesterolo_options,
        malassorbimento_options,
        metabolic_options,
        tumorale_options
    ) = get_filter_options()

    return render_template(
        "index.html",
        alimenti=alimenti,
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


@app.route("/nuovo", methods=["GET", "POST"])
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
# IMPORT CSV
# ---------------------------------------------------------------

@app.route("/importa", methods=["GET", "POST"])
def importa():
    if request.method == "POST":
        file = request.files.get("file")

        if not file or not file.filename:
            flash("Seleziona un file CSV da importare.", "danger")
            return redirect(url_for("importa"))

        if not file.filename.lower().endswith(".csv"):
            flash("Il file deve avere estensione .csv.", "danger")
            return redirect(url_for("importa"))

        svuota_tabella = request.form.get("svuota") == "1"

        try:
            raw = file.read()
            content = decode_csv_bytes(raw)

            sample = content[:4096]
            delimiter = guess_delimiter(sample)

            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

            if not reader.fieldnames:
                flash("Il file CSV sembra vuoto o senza intestazioni.", "danger")
                return redirect(url_for("importa"))

            mapping = map_csv_fields(reader.fieldnames)

            if "alimento" not in mapping:
                flash(
                    "Colonna 'Alimento' non trovata. "
                    "Controlla le intestazioni del CSV.",
                    "danger"
                )
                return redirect(url_for("importa"))

            imported = 0
            skipped = 0
            errors = []

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn = get_db()

            try:
                if svuota_tabella:
                    conn.execute("DELETE FROM alimenti")

                for row_number, row in enumerate(reader, start=2):
                    try:
                        alimento_val = csv_value(row, mapping, "alimento").strip()

                        if not alimento_val:
                            skipped += 1
                            errors.append(f"riga {row_number}: Alimento vuoto")
                            continue

                        categoria = csv_value(row, mapping, "categoria").strip()

                        kcal = to_float(csv_value(row, mapping, "kcal"))

                        tef_percent_raw = csv_value(row, mapping, "tef_percent").strip()
                        tef_kcal_raw = csv_value(row, mapping, "tef_kcal").strip()
                        kcal_nette_raw = csv_value(row, mapping, "kcal_nette").strip()

                        tef_percent = to_float(tef_percent_raw) if tef_percent_raw else 0.0
                        tef_kcal = to_float(tef_kcal_raw) if tef_kcal_raw else 0.0

                        if tef_kcal_raw == "" and tef_percent:
                            tef_kcal = round(kcal * tef_percent / 100, 2) if kcal else 0.0

                        if tef_percent_raw == "" and tef_kcal and kcal:
                            tef_percent = round(tef_kcal / kcal * 100, 2)

                        kcal_nette = to_float(kcal_nette_raw) if kcal_nette_raw else round(kcal - tef_kcal, 2)

                        fruttosio = to_float(csv_value(row, mapping, "fruttosio"))
                        fibre = to_float(csv_value(row, mapping, "fibre"))

                        rapporto_raw = csv_value(row, mapping, "rapporto").strip()
                        if rapporto_raw == "":
                            rapporto = round(fruttosio / fibre, 3) if fibre else 0.0
                        else:
                            rapporto = to_float(rapporto_raw)

                        rischio_diabete = csv_value(row, mapping, "rischio_diabete").strip()
                        rischio_colesterolo = csv_value(row, mapping, "rischio_colesterolo").strip()
                        rischio_malassorbimento = csv_value(row, mapping, "rischio_malassorbimento").strip()
                        rischio_metabolico = csv_value(row, mapping, "rischio_metabolico").strip()
                        rischio_tumorale = csv_value(row, mapping, "rischio_tumorale").strip()

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

                        imported += 1

                    except Exception as exc:
                        skipped += 1
                        errors.append(f"riga {row_number}: {exc}")

                conn.commit()

                if imported > 0:
                    flash(
                        f"Import completato: {imported} alimenti importati.",
                        "success"
                    )
                else:
                    flash("Nessun alimento importato.", "warning")

                if skipped > 0:
                    preview_errors = "; ".join(errors[:5])
                    flash(
                        f"{skipped} righe saltate. Eventuali problemi: {preview_errors}",
                        "warning"
                    )

            except Exception as exc:
                conn.rollback()
                flash(f"Errore durante l'importazione: {exc}", "danger")

            finally:
                conn.close()

        except Exception as exc:
            flash(f"Errore nella lettura del file: {exc}", "danger")

        return redirect(url_for("index"))

    return render_template("import.html")


# ---------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return "<h1>404</h1><p>Risorsa non trovata.</p>", 404


# ---------------------------------------------------------------
# AVVIO
# ---------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)