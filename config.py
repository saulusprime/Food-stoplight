"""
Configurazione dell'applicazione Food-stoplight.

I valori sono letti dalle variabili d'ambiente; in locale possono stare nel
file .env nella cartella del progetto (vedi .env.example).

APP_ENV seleziona il profilo:
- sviluppo   (default): debug attivo, chiave segreta temporanea se manca
- produzione: debug sempre disattivato, FLASK_SECRET_KEY obbligatoria,
              cookie di sessione inviati solo su HTTPS
"""

from __future__ import annotations

import os
import secrets
import sys
from typing import Any

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Le variabili già presenti nell'ambiente hanno la precedenza sul file .env
load_dotenv(os.path.join(BASE_DIR, ".env"))

AMBIENTI = ("sviluppo", "produzione")
LUNGHEZZA_MINIMA_CHIAVE = 32


def env_str(nome: str, default: str = "") -> str:
    valore = os.environ.get(nome)

    if valore is None or not valore.strip():
        return default

    return valore.strip()


def env_bool(nome: str, default: bool = False) -> bool:
    valore = env_str(nome).lower()

    if not valore:
        return default

    if valore in ("1", "true", "yes", "si", "sì", "on"):
        return True

    if valore in ("0", "false", "no", "off"):
        return False

    raise RuntimeError(f"{nome}: valore booleano non valido ({valore!r}).")


def env_int(nome: str, default: int) -> int:
    valore = env_str(nome)

    if not valore:
        return default

    try:
        return int(valore)
    except ValueError:
        raise RuntimeError(
            f"{nome}: atteso un numero intero, trovato {valore!r}."
        ) from None


def env_percorso(nome: str, default: str) -> str:
    """
    Percorso di un file: se relativo, è riferito alla cartella del progetto.
    """
    return os.path.join(BASE_DIR, env_str(nome, default))


def avviso(messaggio: str) -> None:
    print(f" * ATTENZIONE: {messaggio}", file=sys.stderr)


def leggi_secret_key(produzione: bool) -> str:
    chiave = env_str("FLASK_SECRET_KEY")

    if produzione:
        if not chiave:
            raise RuntimeError(
                "FLASK_SECRET_KEY è obbligatoria in produzione (vedi .env.example)."
            )

        if len(chiave) < LUNGHEZZA_MINIMA_CHIAVE:
            raise RuntimeError(
                "FLASK_SECRET_KEY troppo corta: in produzione servono almeno "
                f"{LUNGHEZZA_MINIMA_CHIAVE} caratteri."
            )

        return chiave

    if not chiave:
        avviso(
            "FLASK_SECRET_KEY non impostata: uso una chiave temporanea, "
            "le sessioni si perdono a ogni riavvio."
        )
        return secrets.token_hex(32)

    return chiave


def carica_config() -> dict[str, Any]:
    """
    Restituisce il dizionario da passare a app.config.update().
    """
    ambiente = env_str("APP_ENV", "sviluppo").lower()

    if ambiente not in AMBIENTI:
        raise RuntimeError(
            f"APP_ENV non valido: {ambiente!r} "
            f"(valori ammessi: {', '.join(AMBIENTI)})."
        )

    produzione = ambiente == "produzione"

    debug = env_bool("APP_DEBUG", not produzione)

    if produzione and debug:
        avviso("APP_DEBUG ignorato: in produzione il debug è sempre disattivato.")
        debug = False

    max_upload_mb = env_int("MAX_UPLOAD_MB", 10)

    return {
        "AMBIENTE": ambiente,
        "DEBUG": debug,
        "SECRET_KEY": leggi_secret_key(produzione),

        # Server di sviluppo (python app.py)
        "HOST": env_str("APP_HOST", "127.0.0.1"),
        "PORT": env_int("APP_PORT", 5000),

        # true: chiunque consulta la tabella; false: login richiesto anche per leggere
        "ACCESSO_PUBBLICO": env_bool("ACCESSO_PUBBLICO", True),

        "DATABASE_PATH": env_percorso("DATABASE_PATH", "alimenti.db"),
        "UTENTI_DB_PATH": env_percorso("UTENTI_DB_PATH", "utenti.db"),
        "DIARIO_DB_PATH": env_percorso("DIARIO_DB_PATH", "diario.db"),

        # USDA FoodData Central: chiave personale (non DEMO_KEY) per la
        # sincronizzazione automatica ogni USDA_SINCRONIZZA_GIORNI giorni (0 = spenta)
        "USDA_API_KEY": env_str("USDA_API_KEY", ""),
        "USDA_SINCRONIZZA_GIORNI": env_int("USDA_SINCRONIZZA_GIORNI", 30),

        # Backup automatici e manuali del database alimenti
        "BACKUP_DIR": env_percorso("BACKUP_DIR", os.path.join("instance", "backup")),

        # File caricati in attesa di conferma dell'import (eliminati dopo un'ora)
        "IMPORT_DIR": env_percorso("IMPORT_DIR", os.path.join("instance", "import")),

        # Numero di proxy davanti all'app (Render, nginx): 0 = nessuno.
        # Serve per leggere schema e host corretti dalle intestazioni X-Forwarded-*.
        "PROXY_ATTENDIBILI": env_int("PROXY_ATTENDIBILI", 0),

        # Limite di dimensione delle richieste (file da importare, backup da ripristinare)
        "MAX_UPLOAD_MB": max_upload_mb,
        "MAX_CONTENT_LENGTH": max_upload_mb * 1024 * 1024,

        # Cookie di sessione
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": env_bool("SESSION_COOKIE_SECURE", produzione),

        # Il token CSRF vale per tutta la sessione (nessuna scadenza a tempo)
        "WTF_CSRF_TIME_LIMIT": None,
    }
