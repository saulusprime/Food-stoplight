"""
Accesso: utenti e ruoli (Flask-Login), decoratore solo_admin, controllo
dell'accesso con ACCESSO_PUBBLICO=false, login, logout e scelta della lingua.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from flask_login import (
    AnonymousUserMixin,
    LoginManager,
    UserMixin,
    current_user,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

import lingue
from lingue import N_
from web.comune import (
    get_db_utenti,
)

bp = Blueprint("accesso", __name__)


# Funzione di vista di Flask (per il decoratore solo_admin)
Vista = TypeVar("Vista", bound=Callable[..., Any])

login_manager = LoginManager()
login_manager.login_view = "accesso.login"
login_manager.login_message = N_("Accedi per continuare.")
login_manager.login_message_category = "warning"
login_manager.localize_callback = _


# ---------------------------------------------------------------
# AUTENTICAZIONE E RUOLI
# ---------------------------------------------------------------

RUOLI = (N_("admin"), N_("visitatore"))
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


# Raggiungibili anche senza login con ACCESSO_PUBBLICO=false: il manifest e il
# service worker si scaricano senza credenziali, la lingua si sceglie anche al login
ENDPOINT_SEMPRE_ACCESSIBILI = (
    "accesso.login", "static", "salute", "accesso.cambia_lingua", "pwa.manifest", "pwa.service_worker", "pwa.offline",
)


@bp.before_app_request
def controlla_accesso() -> ResponseReturnValue | None:
    """
    Con ACCESSO_PUBBLICO=false serve il login anche per consultare.
    """
    if current_app.config["ACCESSO_PUBBLICO"] or current_user.is_authenticated:
        return None

    if request.endpoint in ENDPOINT_SEMPRE_ACCESSIBILI:
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


@bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if current_user.is_authenticated:
        return redirect(url_for("pagine.index"))

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
            flash(_("Accesso effettuato come %(nome)s.", nome=row["username"]), "success")
            return redirect(url_sicuro(request.args.get("next")) or url_for("pagine.index"))

        flash(_("Nome utente o password non validi."), "danger")
        return render_template("login.html", username=username), 401

    return render_template("login.html", username="")


@bp.route("/logout", methods=["POST"])
def logout() -> ResponseReturnValue:
    logout_user()
    # La pagina successiva chiede al service worker di cancellare le pagine salvate
    session["svuota_cache"] = True
    flash(_("Disconnessione effettuata."), "info")
    return redirect(url_for("pagine.index"))


@bp.route("/lingua/<codice>")
def cambia_lingua(codice: str) -> ResponseReturnValue:
    """
    Lingua dell'interfaccia scelta dal menu: resta in un cookie per un anno.
    """
    if codice not in lingue.LINGUE:
        abort(404)

    risposta = redirect(url_sicuro(request.args.get("next")) or url_for("pagine.index"))
    risposta.set_cookie(
        lingue.COOKIE,
        codice,
        max_age=lingue.DURATA_COOKIE,
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        httponly=True,
        samesite="Lax",
    )
    return risposta
