"""
Fixture comuni: ogni test riparte da una copia pulita di alimenti.db, con gli
utenti di prova e un diario vuoto (l'ambiente è preparato in tests/aiuti.py).
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from tests.aiuti import BACKUP_DIR, DB, DIARIO_DB, IMPORT_DIR, ORIGINALE, accedi, applicazione, prepara_utenti


@pytest.fixture(autouse=True)
def database_pulito() -> Iterator[None]:
    shutil.copy(ORIGINALE, DB)
    prepara_utenti()

    conn = sqlite3.connect(DIARIO_DB)
    conn.execute("DELETE FROM diario")
    conn.commit()
    conn.close()

    for cartella in (BACKUP_DIR, IMPORT_DIR):
        shutil.rmtree(cartella, ignore_errors=True)

    applicazione.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        ACCESSO_PUBBLICO=True,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    yield


@pytest.fixture
def app() -> Any:
    return applicazione.app


@pytest.fixture
def modulo() -> Any:
    return applicazione


@pytest.fixture
def client(app: Any) -> Any:
    return app.test_client()


@pytest.fixture
def admin(app: Any) -> Any:
    return accedi(app, "admin_t")


@pytest.fixture
def visitatore(app: Any) -> Any:
    return accedi(app, "anna_t")


@pytest.fixture
def altro_visitatore(app: Any) -> Any:
    return accedi(app, "bruno_t")


@pytest.fixture
def csrf_attivo(app: Any) -> Iterator[None]:
    app.config["WTF_CSRF_ENABLED"] = True
    yield
    app.config["WTF_CSRF_ENABLED"] = False
