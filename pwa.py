"""
App installabile (PWA): manifest, service worker e pagina offline.

Il service worker (templates/sw.js) conserva sul dispositivo:
- i file statici (CSS, JavaScript, font, icone), con una versione calcolata
  dal loro contenuto: quando uno cambia, il service worker si aggiorna e
  scarta le copie vecchie;
- le pagine di consultazione (tabella, guida, schede degli alimenti):
  si leggono dalla rete e, senza connessione, dall'ultima copia salvata.
  La tabella (nella versione con tutte le righe: online è divisa in
  pagine) e la guida si salvano all'installazione, le schede quando
  vengono aperte; la tabella si riscarica in background, al massimo una
  volta all'ora, quando la si apre. Pasto, diario, confronto, login e
  amministrazione richiedono la rete.

Le pagine salvate si cancellano all'uscita dall'account (possono contenere
il nome dell'utente e i pulsanti di amministrazione).
"""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path

from flask import Blueprint, Response, current_app, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

import lingue
import ricerca

bp = Blueprint("pwa", __name__)

CACHE_PAGINE = "food-stoplight-pagine"
COLORE_TEMA = "#006644"
COLORE_SFONDO = "#f4f7f4"

# Intestazione delle richieste con cui il service worker salva le pagine
# in anticipo: quelle pagine non consumano i messaggi flash dell'utente
INTESTAZIONE_PRECARICA = "X-Precarica"

FONT = "bootstrap-italia/fonts/Titillium_Web/titillium-web-v10-latin-ext_latin-{}.woff2"

STATICI = (
    "bootstrap-italia/css/bootstrap-italia.min.css",
    "bootstrap-italia/css/fonts.css",
    "bootstrap-italia/js/bootstrap-italia.bundle.min.js",
    *(FONT.format(peso) for peso in ("300", "regular", "600", "700")),
    "css/app.css",
    "js/app.js",
    "icone/icona.svg",
    "icone/icona-192.png",
)

# Template che finiscono nelle pagine salvate all'installazione
TEMPLATE_PRECARICATI = ("sw.js", "base.html", "offline.html")


def _calcola_versione(radice: Path) -> str:
    impronta = hashlib.sha256()
    file = [radice / "static" / percorso for percorso in STATICI]
    file += [radice / "templates" / nome for nome in TEMPLATE_PRECARICATI]
    file += sorted((radice / "translations").rglob("*.mo"))

    for percorso in file:
        impronta.update(percorso.name.encode())
        impronta.update(percorso.read_bytes())

    return impronta.hexdigest()[:12]


_versione_in_cache = cache(_calcola_versione)


def versione() -> str:
    """
    Versione del service worker: cambia quando cambia un file statico salvato,
    un template delle pagine salvate o una traduzione. In sviluppo si ricalcola
    a ogni richiesta, così le modifiche a CSS e JS arrivano subito.
    """
    radice = Path(current_app.root_path)

    if current_app.debug:
        return _calcola_versione(radice)

    return _versione_in_cache(radice)


def senza_cache(risposta: Response) -> Response:
    risposta.headers["Cache-Control"] = "no-cache"
    return risposta


@bp.route("/manifest.webmanifest")
def manifest() -> ResponseReturnValue:
    def icona(nome: str) -> str:
        return url_for("static", filename=f"icone/{nome}")

    dati = {
        "name": _("Food Stoplight – Database Alimenti"),
        "short_name": "Food Stoplight",
        "description": _("Database degli alimenti con semaforo dei rischi per la salute, valori nutrizionali e TEF."),
        "lang": lingue.corrente(),
        "dir": "ltr",
        "id": url_for("index"),
        "start_url": url_for("index"),
        "scope": url_for("index"),
        "display": "standalone",
        "background_color": COLORE_SFONDO,
        "theme_color": COLORE_TEMA,
        "icons": [
            {"src": icona("icona-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": icona("icona-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": icona("icona-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            {"src": icona("icona.svg"), "sizes": "any", "type": "image/svg+xml"},
        ],
        "shortcuts": [
            {"name": _("Pasto"), "url": url_for("pasto")},
            {"name": _("Guida"), "url": url_for("guida")},
        ],
    }

    risposta = current_app.response_class(
        json.dumps(dati, ensure_ascii=False, indent=2),
        mimetype="application/manifest+json",
    )
    return senza_cache(risposta)


def tabella_completa() -> str:
    """
    La tabella con tutte le righe, senza filtri: la copia per l'uso offline.
    """
    return url_for("index", per_pagina=ricerca.TUTTI)


@bp.route("/sw.js")
def service_worker() -> ResponseReturnValue:
    testo = render_template(
        "sw.js",
        versione=versione(),
        cache_pagine=CACHE_PAGINE,
        statici=[url_for("static", filename=percorso) for percorso in STATICI],
        prefisso_statici=url_for("static", filename=""),
        base=url_for("index"),
        pagine=[
            [tabella_completa(), url_for("index")],
            [url_for("guida"), url_for("guida")],
        ],
        tabella_completa=tabella_completa(),
        offline=url_for("pwa.offline"),
        intestazione=INTESTAZIONE_PRECARICA,
    )
    return senza_cache(Response(testo, mimetype="text/javascript"))


@bp.route("/offline")
def offline() -> ResponseReturnValue:
    return render_template("offline.html", cache_pagine=CACHE_PAGINE)
