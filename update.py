import argparse
import csv
import io
import os
import re
import sqlite3
from datetime import datetime


# ---------------------------------------------------------------
# CONFIGURAZIONE TEF
# ---------------------------------------------------------------

TEF_PROTEINE = 0.25      # 25%
TEF_CARBIDRATI = 0.075   # 7,5%
TEF_GRASSI = 0.025       # 2,5%


# ---------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------

def normalize_header(value):
    value = str(value or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def to_float(value, default=0.0, inf_value=999999.0):
    """
    Converte un valore in float.
    Gestisce virgola decimale, Inf, NA, ND, ecc.
    """
    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    low = text.lower()

    if low in ("inf", "infinity", "∞"):
        return inf_value

    if low in ("na", "n/a", "nd", "-", "non disponibile"):
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


def csv_raw(row, mapping, key):
    """
    Estrae il valore raw dal CSV usando il mapping delle colonne.
    """
    column = mapping.get(key)

    if column is None:
        return ""

    return (row.get(column) or "").strip()


def read_text(path):
    """
    Legge un file CSV provando diversi encoding.
    """
    encodings = ("utf-8-sig", "cp1252", "latin-1")

    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    with open(path, "r", encoding="latin-1", errors="replace", newline="") as f:
        return f.read()


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

        if norm == "id" or norm.startswith("id "):
            mapping.setdefault("id", original)

        elif "rapporto" in norm:
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

        elif "proteine" in norm or "protein" in norm:
            mapping.setdefault("proteine", original)

        elif "carboidrati" in norm or "carb" in norm:
            mapping.setdefault("carboidrati", original)

        elif "grassi" in norm or "lipidi" in norm or "fat" in norm:
            mapping.setdefault("grassi", original)

        elif "fruttosio" in norm:
            mapping.setdefault("fruttosio", original)

        elif "fibre" in norm or "fibra" in norm:
            mapping.setdefault("fibre", original)

        elif "categoria" in norm:
            mapping.setdefault("categoria", original)

        elif "malassorb" in norm:
            mapping.setdefault("rischio_malassorbimento", original)

        elif "metabolic" in norm or "metabolico" in norm:
            mapping.setdefault("rischio_metabolico", original)

        elif "tumorale" in norm or "tumoral" in norm:
            mapping.setdefault("rischio_tumorale", original)

        elif "fonte" in norm and "kcal" in norm:
            mapping.setdefault("fonte_kcal", original)

        elif "fonte" in norm and "tef" in norm:
            mapping.setdefault("fonte_tef", original)

        elif "fonte" in norm:
            mapping.setdefault("fonte_kcal", original)

        elif "url" in norm or "link" in norm:
            mapping.setdefault("url_fonte", original)

        elif "note" in norm:
            mapping.setdefault("note", original)

        elif "alimento" in norm or "nome" in norm:
            mapping.setdefault("alimento", original)

    return mapping


# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------

def ensure_schema(conn):
    """
    Crea la tabella se non esiste e aggiunge eventuali colonne mancanti.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alimenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alimento TEXT NOT NULL,
            categoria TEXT,

            kcal REAL DEFAULT 0,
            tef_kcal REAL DEFAULT 0,
            tef_percent REAL DEFAULT 0,
            kcal_nette REAL DEFAULT 0,

            proteine REAL DEFAULT 0,
            carboidrati REAL DEFAULT 0,
            grassi REAL DEFAULT 0,

            fruttosio REAL DEFAULT 0,
            fibre REAL DEFAULT 0,
            rapporto REAL DEFAULT 0,

            rischio_malassorbimento TEXT,
            rischio_metabolico TEXT,
            rischio_tumorale TEXT,

            fonte_kcal TEXT,
            fonte_tef TEXT,
            url_fonte TEXT,
            note TEXT,

            aggiornato_il TEXT
        )
    """)

    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(alimenti)").fetchall()
    }

    columns = {
        "kcal": "REAL DEFAULT 0",
        "tef_kcal": "REAL DEFAULT 0",
        "tef_percent": "REAL DEFAULT 0",
        "kcal_nette": "REAL DEFAULT 0",
        "proteine": "REAL DEFAULT 0",
        "carboidrati": "REAL DEFAULT 0",
        "grassi": "REAL DEFAULT 0",
        "fruttosio": "REAL DEFAULT 0",
        "fibre": "REAL DEFAULT 0",
        "rapporto": "REAL DEFAULT 0",
        "rischio_malassorbimento": "TEXT",
        "rischio_metabolico": "TEXT",
        "rischio_tumorale": "TEXT",
        "fonte_kcal": "TEXT",
        "fonte_tef": "TEXT",
        "url_fonte": "TEXT",
        "note": "TEXT",
        "aggiornato_il": "TEXT",
    }

    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(
                f"ALTER TABLE alimenti ADD COLUMN {column_name} {column_type}"
            )


def get_existing(conn, row_id, alimento, categoria):
    """
    Cerca una riga esistente per ID oppure per alimento + categoria.
    """
    if row_id:
        row = conn.execute(
            "SELECT * FROM alimenti WHERE id = ?",
            (row_id,)
        ).fetchone()

        if row:
            return dict(row)

    if alimento:
        row = conn.execute(
            """
            SELECT *
            FROM alimenti
            WHERE LOWER(alimento) = LOWER(?)
              AND LOWER(COALESCE(categoria, '')) = LOWER(?)
            """,
            (alimento, categoria)
        ).fetchone()

        if row:
            return dict(row)

    return None


# ---------------------------------------------------------------
# EXPORT MANCANTI
# ---------------------------------------------------------------

def export_missing(conn, out_path):
    """
    Esporta gli alimenti con Kcal/TEF mancanti o pari a zero.
    """
    rows = conn.execute("""
        SELECT
            id,
            alimento,
            categoria,
            COALESCE(kcal, 0) AS kcal,
            COALESCE(proteine, 0) AS proteine,
            COALESCE(carboidrati, 0) AS carboidrati,
            COALESCE(grassi, 0) AS grassi,
            COALESCE(tef_kcal, 0) AS tef_kcal,
            COALESCE(tef_percent, 0) AS tef_percent,
            COALESCE(kcal_nette, 0) AS kcal_nette,
            COALESCE(fruttosio, 0) AS fruttosio,
            COALESCE(fibre, 0) AS fibre,
            COALESCE(rapporto, 0) AS rapporto,
            COALESCE(rischio_malassorbimento, '') AS rischio_malassorbimento,
            COALESCE(rischio_metabolico, '') AS rischio_metabolico,
            COALESCE(rischio_tumorale, '') AS rischio_tumorale,
            COALESCE(fonte_kcal, '') AS fonte_kcal,
            COALESCE(fonte_tef, '') AS fonte_tef,
            COALESCE(url_fonte, '') AS url_fonte,
            COALESCE(note, '') AS note
        FROM alimenti
        WHERE COALESCE(kcal, 0) = 0
           OR COALESCE(tef_kcal, 0) = 0
           OR COALESCE(tef_percent, 0) = 0
           OR COALESCE(kcal_nette, 0) = 0
        ORDER BY LOWER(alimento)
    """).fetchall()

    headers = {
        "id": "ID",
        "alimento": "Alimento",
        "categoria": "Categoria",
        "kcal": "Kcal",
        "proteine": "Proteine",
        "carboidrati": "Carboidrati",
        "grassi": "Grassi",
        "tef_kcal": "TEF (Kcal)",
        "tef_percent": "TEF (%)",
        "kcal_nette": "Kcal Nette",
        "fruttosio": "Fruttosio (g/100g)",
        "fibre": "Fibre (g/100g)",
        "rapporto": "Rapporto F/Fibre",
        "rischio_malassorbimento": "Rischio Malassorbimento",
        "rischio_metabolico": "Rischio Metabolico",
        "rischio_tumorale": "Rischio Tumorale",
        "fonte_kcal": "Fonte Kcal",
        "fonte_tef": "Fonte TEF",
        "url_fonte": "URL",
        "note": "Note",
    }

    fieldnames = list(headers.values())

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            out_row = {}

            for internal_key, csv_header in headers.items():
                out_row[csv_header] = row[internal_key]

            writer.writerow(out_row)

    print(f"Esportate {len(rows)} righe in: {out_path}")


# ---------------------------------------------------------------
# IMPORT / UPDATE
# ---------------------------------------------------------------

def process_row(conn, row, mapping, dry_run=False):
    """
    Aggiorna o inserisce una riga.
    """
    row_id_raw = csv_raw(row, mapping, "id")

    row_id = None
    if row_id_raw:
        row_id_float = to_float(row_id_raw, default=0.0, inf_value=0.0)
        if row_id_float > 0:
            row_id = int(row_id_float)

    alimento_raw = csv_raw(row, mapping, "alimento")
    categoria_raw = csv_raw(row, mapping, "categoria")

    existing = get_existing(conn, row_id, alimento_raw, categoria_raw)

    defaults = {
        "id": None,
        "alimento": "",
        "categoria": "",
        "kcal": 0.0,
        "tef_kcal": 0.0,
        "tef_percent": 0.0,
        "kcal_nette": 0.0,
        "proteine": 0.0,
        "carboidrati": 0.0,
        "grassi": 0.0,
        "fruttosio": 0.0,
        "fibre": 0.0,
        "rapporto": 0.0,
        "rischio_malassorbimento": "",
        "rischio_metabolico": "",
        "rischio_tumorale": "",
        "fonte_kcal": "",
        "fonte_tef": "",
        "url_fonte": "",
        "note": "",
        "aggiornato_il": "",
    }

    values = dict(existing) if existing else defaults.copy()

    numeric_fields = [
        "kcal",
        "tef_kcal",
        "tef_percent",
        "kcal_nette",
        "proteine",
        "carboidrati",
        "grassi",
        "fruttosio",
        "fibre",
        "rapporto",
    ]

    text_fields = [
        "alimento",
        "categoria",
        "rischio_malassorbimento",
        "rischio_metabolico",
        "rischio_tumorale",
        "fonte_kcal",
        "fonte_tef",
        "url_fonte",
        "note",
    ]

    # Sistema eventuali NULL provenienti dal database
    for field in numeric_fields:
        if values.get(field) is None:
            values[field] = 0.0

    for field in text_fields:
        if values.get(field) is None:
            values[field] = ""

    # Aggiorna solo i campi presenti nel CSV e non vuoti
    for field in text_fields:
        raw = csv_raw(row, mapping, field)
        if raw != "":
            values[field] = raw

    for field in numeric_fields:
        if field == "rapporto":
            raw = csv_raw(row, mapping, field)
            if raw != "":
                values[field] = to_float(raw, default=0.0, inf_value=999999.0)
        else:
            raw = csv_raw(row, mapping, field)
            if raw != "":
                values[field] = to_float(raw, default=0.0, inf_value=0.0)

    # -----------------------------------------------------------
    # CALCOLI AUTOMATICI
    # -----------------------------------------------------------

    kcal = float(values.get("kcal") or 0.0)
    proteine = float(values.get("proteine") or 0.0)
    carboidrati = float(values.get("carboidrati") or 0.0)
    grassi = float(values.get("grassi") or 0.0)

    # Se manca Kcal ma ci sono macronutrienti, stima Kcal
    if kcal == 0 and (proteine > 0 or carboidrati > 0 or grassi > 0):
        kcal = round(proteine * 4 + carboidrati * 4 + grassi * 9, 2)
        values["kcal"] = kcal

    # Se mancano TEF (Kcal) e TEF (%) ma ci sono macronutrienti, stima il TEF
    if (
        kcal > 0
        and float(values.get("tef_kcal") or 0.0) == 0.0
        and float(values.get("tef_percent") or 0.0) == 0.0
        and (proteine > 0 or carboidrati > 0 or grassi > 0)
    ):
        kcal_proteine = proteine * 4
        kcal_carboidrati = carboidrati * 4
        kcal_grassi = grassi * 9

        macro_kcal = kcal_proteine + kcal_carboidrati + kcal_grassi

        if macro_kcal > 0:
            tef_stimato = (
                kcal_proteine * TEF_PROTEINE
                + kcal_carboidrati * TEF_CARBIDRATI
                + kcal_grassi * TEF_GRASSI
            )

            # Il TEF non può superare le Kcal totali
            if tef_stimato > kcal:
                tef_stimato = kcal

            values["tef_kcal"] = round(tef_stimato, 2)
            values["tef_percent"] = round(tef_stimato / kcal * 100, 2)

    # Se manca TEF (Kcal) ma c'è TEF (%), calcola TEF (Kcal)
    if (
        kcal > 0
        and float(values.get("tef_kcal") or 0.0) == 0.0
        and float(values.get("tef_percent") or 0.0) > 0.0
    ):
        values["tef_kcal"] = round(
            kcal * float(values["tef_percent"]) / 100,
            2
        )

    # Se manca TEF (%) ma c'è TEF (Kcal), calcola TEF (%)
    if (
        kcal > 0
        and float(values.get("tef_percent") or 0.0) == 0.0
        and float(values.get("tef_kcal") or 0.0) > 0.0
    ):
        values["tef_percent"] = round(
            float(values["tef_kcal"]) / kcal * 100,
            2
        )

    # Se mancano le Kcal Nette, calcolale
    if kcal > 0 and float(values.get("kcal_nette") or 0.0) == 0.0:
        values["kcal_nette"] = round(
            kcal - float(values.get("tef_kcal") or 0.0),
            2
        )

    # Se manca il rapporto F/Fibre, calcolalo
    if (
        float(values.get("rapporto") or 0.0) == 0.0
        and float(values.get("fibre") or 0.0) > 0.0
    ):
        values["rapporto"] = round(
            float(values.get("fruttosio") or 0.0) / float(values["fibre"]),
            3
        )

    values["aggiornato_il"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    columns = [
        "alimento",
        "categoria",
        "kcal",
        "tef_kcal",
        "tef_percent",
        "kcal_nette",
        "proteine",
        "carboidrati",
        "grassi",
        "fruttosio",
        "fibre",
        "rapporto",
        "rischio_malassorbimento",
        "rischio_metabolico",
        "rischio_tumorale",
        "fonte_kcal",
        "fonte_tef",
        "url_fonte",
        "note",
        "aggiornato_il",
    ]

    if existing and existing.get("id"):
        if not dry_run:
            sql = f"""
                UPDATE alimenti
                SET {", ".join(f"{col} = ?" for col in columns)}
                WHERE id = ?
            """
            params = [values[col] for col in columns] + [existing["id"]]
            conn.execute(sql, params)

        return "updated"

    if not values.get("alimento"):
        return "skipped"

    if not dry_run:
        sql = f"""
            INSERT INTO alimenti ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
        """
        params = [values[col] for col in columns]
        conn.execute(sql, params)

    return "inserted"


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Aggiorna o completa il database alimenti."
    )

    parser.add_argument(
        "--db",
        default="alimenti.db",
        help="Percorso del database SQLite. Default: alimenti.db"
    )

    parser.add_argument(
        "--csv",
        help="File CSV da importare/aggiornare"
    )

    parser.add_argument(
        "--esporta-mancanti",
        help="Genera un CSV con gli alimenti da completare"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula l'import senza scrivere nel database"
    )

    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    ensure_schema(conn)

    if args.esporta_mancanti:
        export_missing(conn, args.esporta_mancanti)
        conn.close()
        return

    if not args.csv:
        parser.error("Devi specificare --csv oppure --esporta-mancanti")

    content = read_text(args.csv)
    sample = content[:4096]
    delimiter = guess_delimiter(sample)

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    if not reader.fieldnames:
        parser.error("Il file CSV sembra vuoto o senza intestazioni.")

    mapping = map_csv_fields(reader.fieldnames)

    if "alimento" not in mapping:
        parser.error("Colonna 'Alimento' non trovata nel CSV.")

    counts = {
        "updated": 0,
        "inserted": 0,
        "skipped": 0,
    }

    for row in reader:
        result = process_row(conn, row, mapping, dry_run=args.dry_run)
        counts[result] += 1

    if not args.dry_run:
        conn.commit()

    conn.close()

    if args.dry_run:
        print("Dry-run completata.")
    else:
        print("Import completato.")

    print(f"Aggiornati: {counts['updated']}")
    print(f"Inseriti:   {counts['inserted']}")
    print(f"Saltati:    {counts['skipped']}")


if __name__ == "__main__":
    main()