"""
update.py — aggiornamento del database da riga di comando, con le stesse
regole dell'import della web app (importazione.py): file CSV o Excel,
abbinamento per ID oppure per nome e categoria, campi derivati ricalcolati
(Kcal e TEF dai macronutrienti, Kcal nette, rapporto fruttosio/fibre),
backup automatico prima di scrivere.

    python update.py --csv dati.csv                    # aggiorna o aggiunge
    python update.py --csv dati.xlsx --dry-run         # mostra cosa cambierebbe
    python update.py --csv dati.csv --modalita aggiungi
    python update.py --esporta-mancanti da_completare.csv
    python update.py --db altro.db --csv dati.csv
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import datetime

import archivio
import backup
import config
import database
import esportazione
import importazione

SELECT_ALIMENTI = archivio.SELECT_ALIMENTI

# Righe da completare: energia mancante oppure macronutrienti non disponibili
CONDIZIONE_MANCANTI = """
    COALESCE(kcal, 0) = 0
    OR COALESCE(tef_kcal, 0) = 0
    OR COALESCE(tef_percent, 0) = 0
    OR COALESCE(kcal_nette, 0) = 0
    OR proteine IS NULL OR carboidrati IS NULL OR grassi IS NULL
"""


def esporta_mancanti(db: str, percorso: str) -> int:
    """
    Scrive un CSV (stesse colonne dell'export web, quindi reimportabile)
    con gli alimenti da completare; restituisce il numero di righe.
    """
    conn = database.connetti_alimenti(db)

    try:
        righe = [
            dict(r) for r in conn.execute(
                f"{SELECT_ALIMENTI} WHERE {CONDIZIONE_MANCANTI} ORDER BY LOWER(alimento), id"
            ).fetchall()
        ]
    finally:
        conn.close()

    with open(percorso, "wb") as f:
        f.write(esportazione.csv_bytes(righe))

    return len(righe)


def importa(db: str, percorso: str, modalita: str, prova: bool, cartella_backup: str) -> int:
    with open(percorso, "rb") as f:
        letto = importazione.leggi_file(os.path.basename(percorso), f.read())

    conn = database.connetti_alimenti(db)

    try:
        voci = importazione.pianifica(conn, letto, modalita)
        sommario = importazione.riepilogo(voci)

        print(f"File: {letto['nome_file']} ({letto['dettaglio']}), {len(letto['righe'])} righe di dati")
        print(f"Modalità: {importazione.MODALITA[modalita]['titolo']}")
        print(f"Nuovi: {sommario['nuovo']}  Aggiornati: {sommario['aggiornato']}  "
              f"Invariati: {sommario['invariato']}  Uniti: {sommario['unito']}  Saltati: {sommario['saltato']}")

        for voce in [v for v in voci if v["avvisi"]][:10]:
            print(f"  riga {voce['riga']}: {'; '.join(voce['avvisi'])}")

        if prova:
            print("Prova: nessuna modifica scritta.")
            return 0

        if sommario["scritture"] == 0:
            print("Niente da scrivere.")
            return 0

        if modalita == "sostituisci" and sommario["nuovo"] == 0:
            print("Il file non contiene righe valide: la tabella non è stata svuotata.")
            return 1

        nome_backup = backup.crea(db, cartella_backup, "import")
        importazione.applica(conn, voci, modalita, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        conn.commit()
    finally:
        conn.close()

    print(f"Import completato. Backup del database precedente: {nome_backup}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggiorna o completa il database alimenti.")
    parser.add_argument("--db", default=config.env_percorso("DATABASE_PATH", "alimenti.db"),
                        help="Database SQLite (default: DATABASE_PATH oppure alimenti.db)")
    parser.add_argument("--csv", metavar="FILE", help="File .csv o .xlsx da importare")
    parser.add_argument("--modalita", choices=list(importazione.MODALITA), default=importazione.MODALITA_PREDEFINITA,
                        help="aggiorna (default), aggiungi oppure sostituisci")
    parser.add_argument("--dry-run", action="store_true", help="Mostra cosa cambierebbe senza scrivere")
    parser.add_argument("--esporta-mancanti", metavar="FILE", help="CSV con gli alimenti da completare")
    parser.add_argument("--backup-dir", default=config.env_percorso("BACKUP_DIR", os.path.join("instance", "backup")),
                        help="Cartella dei backup (default: BACKUP_DIR oppure instance/backup)")
    args = parser.parse_args(argv)

    if not args.csv and not args.esporta_mancanti:
        parser.error("specifica --csv oppure --esporta-mancanti")

    db = os.path.abspath(args.db)
    eseguite = database.migra(db, "alimenti", prima_di_migrare=lambda: backup.crea(db, args.backup_dir, "migrazione"))

    for descrizione in eseguite:
        print(f"Migrazione applicata: {descrizione}")

    if args.esporta_mancanti:
        n = esporta_mancanti(db, args.esporta_mancanti)
        print(f"Esportate {n} righe da completare in: {args.esporta_mancanti}")

        if not args.csv:
            return 0

    try:
        return importa(db, args.csv, args.modalita, args.dry_run, args.backup_dir)
    except importazione.ErroreImport as exc:
        print(f"Errore: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
