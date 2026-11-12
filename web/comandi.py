"""
Comandi da riga di comando (flask --app app <comando>): utenti, import dal
CREA, sincronizzazione USDA, ricalcoli, dati CoFID, pasti pronti, stato dei
database.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

import click
from flask import (
    Blueprint,
    current_app,
)
from werkzeug.security import generate_password_hash

import backup
import cofid
import crea
import database
import fonti
import pasti_pronti
import sincronizzazione
import usda
from web.accesso import PASSWORD_MIN, RUOLI, USERNAME_RE
from web.comune import (
    adesso_testo,
    get_db,
    get_db_diario,
    get_db_utenti,
)

bp = Blueprint("comandi", __name__, cli_group=None)


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


@bp.cli.command("crea-utente")
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


@bp.cli.command("crea-admin-iniziale")
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


@bp.cli.command("imposta-password")
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


@bp.cli.command("elenco-utenti")
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


@bp.cli.command("elimina-utente")
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


@bp.cli.command("crea-importa")
@click.argument("codici", nargs=-1)
@click.option("--tutti", is_flag=True, help="Tutti gli alimenti dell'indice CREA.")
@click.option("--sostituisci", is_flag=True,
              help="Elimina prima gli alimenti senza codice CREA (sintetici, USDA, inseriti a mano).")
@click.option("--cache", "cartella_cache", type=click.Path(file_okay=False),
              help="Cartella in cui salvare le pagine CREA scaricate (e riusarle).")
@click.option("--api-key", envvar="USDA_API_KEY", default=usda.CHIAVE_DEMO, show_default=True,
              help="Chiave USDA per i valori che il CREA non pubblica (variabile USDA_API_KEY).")
@click.option("--prova", is_flag=True, help="Legge e calcola tutto senza scrivere.")
def crea_importa_cmd(codici: tuple[str, ...], tutti: bool, sostituisci: bool, cartella_cache: str | None,
                     api_key: str, prova: bool) -> None:
    """Importa o aggiorna alimenti dalle tabelle CREA (codici, oppure --tutti)."""
    if not codici and not tutti:
        raise click.UsageError("indica uno o più codici CREA oppure --tutti")

    try:
        elenco = list(crea.scarica_indice()) if tutti else [c.upper() for c in codici]
    except crea.ErroreCrea as exc:
        raise click.ClickException(str(exc)) from None

    click.echo(f"Alimenti CREA da leggere: {len(elenco)} (una pagina al secondo).")
    cache_pagine = Path(cartella_cache) if cartella_cache else None
    conn = get_db()

    try:
        config = current_app.config
        nome_backup = None if prova else backup.crea(config["DATABASE_PATH"], config["BACKUP_DIR"], "crea")
        try:
            esito = fonti.importa_crea(conn, elenco, adesso_testo(), api_key, cache_pagine, sostituisci,
                                       avanzamento=click.echo)
        except usda.ErroreUsda as exc:
            conn.rollback()
            raise click.ClickException(
                f"USDA: {exc} Import annullato prima di leggere il CREA, nessuna modifica scritta: "
                "senza i valori USDA gli alimenti abbinati li perderebbero."
            ) from None

        for errore in esito["errori"][:20]:
            click.echo(f"  ! {errore}")

        click.echo(
            f"Letti {esito['letti']}: nuovi {esito['nuovi']}, aggiornati {esito['aggiornati']}, "
            f"invariati {esito['invariati']}, eliminati {esito['eliminati']}."
        )

        if prova:
            conn.rollback()
            click.echo("Prova: nessuna modifica scritta.")
            return

        conn.commit()
    finally:
        conn.close()

    click.echo(f"Import completato. Backup del database precedente: {nome_backup}.")


@bp.cli.command("usda-sincronizza")
@click.option("--api-key", envvar="USDA_API_KEY", default="", help="Chiave USDA personale (variabile USDA_API_KEY).")
def usda_sincronizza_cmd(api_key: str) -> None:
    """Aggiorna da USDA i valori presi da USDA (serve una chiave personale)."""
    if not usda.chiave_valida(api_key):
        raise click.ClickException(
            "Serve una chiave USDA personale (USDA_API_KEY), non DEMO_KEY: https://fdc.nal.usda.gov/api-key-signup"
        )

    try:
        esito = sincronizzazione.esegui(current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], api_key)
    except sincronizzazione.GiaInCorso:
        raise click.ClickException("Un'altra sincronizzazione è in corso.") from None

    if esito["esito"] != "riuscita":
        raise click.ClickException(f"Sincronizzazione non riuscita: {esito['messaggio']}")

    click.echo(f"Sincronizzazione riuscita: {esito['aggiornati']} alimenti aggiornati. Backup: {esito['backup']}.")


@bp.cli.command("ricalcola-rischi")
def ricalcola_rischi_cmd() -> None:
    """Ricalcola i livelli di rischio di tutti gli alimenti con le regole attuali."""
    conn = get_db()

    try:
        nome_backup = backup.crea(current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], "rischi")
        cambiati = fonti.ricalcola_rischi(conn, adesso_testo())
        conn.commit()
    finally:
        conn.close()

    click.echo(f"Livelli ricalcolati: {cambiati} alimenti cambiati. Backup: {nome_backup}.")


@bp.cli.command("ricalcola-ricette")
def ricalcola_ricette_cmd() -> None:
    """Ricalcola dagli ingredienti fruttosio, glucosio, lattosio e saturi delle ricette CREA."""
    conn = get_db()

    try:
        nome_backup = backup.crea(current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], "ricette")
        cambiate = fonti.ricalcola_ricette(conn, adesso_testo())
        conn.commit()
    finally:
        conn.close()

    click.echo(f"Ricette ricalcolate: {cambiate} cambiate. Backup: {nome_backup}.")


@bp.cli.command("pasti-importa")
@click.option("--prova", is_flag=True, help="Legge e calcola tutto senza scrivere.")
def pasti_importa_cmd(prova: bool) -> None:
    """
    Carica i pasti pronti da dati/pasti_pronti.csv e
    dati/pasti_pronti_ingredienti.csv e ricalcola i loro piatti.
    """
    try:
        ricette = pasti_pronti.leggi_dati()
    except pasti_pronti.ErroreDati as exc:
        for errore in exc.errori[:20]:
            click.echo(f"  ! {errore}", err=True)
        raise click.ClickException(f"File dei pasti pronti non validi: {len(exc.errori)} errori.") from None

    conn = get_db()

    try:
        nome_backup = None if prova else backup.crea(
            current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], "pasti"
        )

        try:
            esito = fonti.carica_pasti_pronti(conn, ricette, adesso_testo())
        except pasti_pronti.IngredientiMancanti as exc:
            conn.rollback()
            raise click.ClickException(f"Codici CREA degli ingredienti non trovati tra gli alimenti: {exc}") from None

        for errore in esito["errori"][:20]:
            click.echo(f"  ! {errore}")

        click.echo(
            f"Ricette: {esito['ricette']}. Piatti nuovi {esito['nuovi']}, aggiornati {esito['aggiornati']}, "
            f"invariati {esito['invariati']}; ricette eliminate {esito['eliminati']}."
        )

        if prova:
            conn.rollback()
            click.echo("Prova: nessuna modifica scritta.")
            return

        conn.commit()
    finally:
        conn.close()

    click.echo(f"Pasti pronti caricati. Backup del database precedente: {nome_backup}.")


@bp.cli.command("cofid-estrai")
@click.argument("file_excel", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def cofid_estrai_cmd(file_excel: Path) -> None:
    """
    Rigenera dati/cofid.csv dal file Excel ufficiale di CoFID 2021, con i soli
    alimenti abbinati in dati/crea_cofid.csv. Poi «flask crea-importa --tutti»
    aggiorna gli alimenti.
    """
    codici = {codice for gruppi in cofid.abbinamenti().values() for codice in gruppi.values()}

    try:
        righe = cofid.estrai_excel(file_excel, codici)
    except (KeyError, ValueError, OSError) as exc:
        raise click.ClickException(f"File CoFID non leggibile: {exc}") from None

    cofid.scrivi_dati(righe)
    trovati = {r["codice"] for r in righe}
    click.echo(f"{len(righe)} alimenti CoFID scritti in {cofid.FILE_DATI.name}.")

    if codici - trovati:
        click.echo(f"Codici non trovati nel file: {', '.join(sorted(codici - trovati))}", err=True)



@bp.cli.command("db-stato")
def db_stato_cmd() -> None:
    """Mostra la versione dello schema dei tre database."""
    config = current_app.config

    for nome, chiave in (("alimenti", "DATABASE_PATH"), ("utenti", "UTENTI_DB_PATH"), ("diario", "DIARIO_DB_PATH")):
        percorso = config[chiave]
        versione, ultima = database.stato(percorso, nome)
        click.echo(f"{nome:9} versione {versione} di {ultima}  ({percorso})")
