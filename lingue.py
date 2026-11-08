"""
Lingue dell'interfaccia web: italiano (lingua del codice) e inglese.

I testi sono scritti in italiano nel codice e nei template; la traduzione
inglese è in translations/en/LC_MESSAGES/messages.po, compilata in
messages.mo. Export (CSV, Excel, PDF), API e riga di comando restano
in italiano.

I testi definiti nei moduli di dati (livelli, rischi, medaglie, etichette
dei campi) si segnano con N_() e si traducono solo dove vengono mostrati,
con il filtro |traduci dei template: così export e API, che usano gli
stessi moduli, restano in italiano.

Dopo aver aggiunto o cambiato dei testi:
    pybabel extract -F babel.cfg -o messages.pot --no-location --sort-output .
    pybabel update -i messages.pot -d translations --no-fuzzy-matching --ignore-obsolete
    (tradurre le voci nuove in translations/en/LC_MESSAGES/messages.po)
    pybabel compile -d translations
Il test tests/test_lingue_pwa.py segnala i testi senza traduzione.
"""

from __future__ import annotations

from flask import g, has_request_context, request
from flask_babel import get_locale, gettext

LINGUE = {"it": "Italiano", "en": "English"}
PREDEFINITA = "it"
COOKIE = "lingua"
DURATA_COOKIE = 365 * 24 * 3600

# Risorse che restano in italiano qualunque sia la lingua scelta
BLUEPRINT_IN_ITALIANO = {"api"}
ENDPOINT_IN_ITALIANO = {"esporta", "scheda_pdf"}


def N_(testo: str) -> str:
    """
    Segna un testo da tradurre senza tradurlo subito (gettext_noop):
    la traduzione si fa dove il testo viene mostrato.
    """
    return testo


def scegli_lingua() -> str:
    """
    Lingua della richiesta: quella scelta dal selettore (cookie), altrimenti
    la preferita del browser tra quelle disponibili, altrimenti l'italiano.
    """
    if not has_request_context():
        return PREDEFINITA

    if request.blueprint in BLUEPRINT_IN_ITALIANO or request.endpoint in ENDPOINT_IN_ITALIANO:
        return PREDEFINITA

    scelta = request.cookies.get(COOKIE)

    if scelta in LINGUE:
        return scelta

    return request.accept_languages.best_match(LINGUE) or PREDEFINITA


def corrente() -> str:
    """
    Codice della lingua in uso ("it" o "en"); "it" fuori da una richiesta.
    """
    if not has_request_context():
        return PREDEFINITA

    # Memorizzata per la richiesta: i filtri dei numeri la chiedono migliaia di volte
    lingua: str | None = g.get("lingua_corrente")

    if lingua is None:
        locale = get_locale()
        lingua = locale.language if locale is not None else PREDEFINITA
        g.lingua_corrente = lingua

    return lingua


def traduci(testo: object) -> str:
    """
    Traduzione di un testo segnato con N_() (etichette, livelli, categorie...).
    Restituisce sempre una stringa normale, che i template proteggono con
    l'escape automatico: si può usare anche su valori letti dal database.
    """
    if testo is None:
        return ""

    testo = str(testo)
    return gettext(testo) if testo else testo


def decimale(testo: str) -> str:
    """
    "12.5" -> "12,5" in italiano, invariato in inglese.
    """
    return testo.replace(".", ",") if corrente() == "it" else testo


# ---------------------------------------------------------------
# Valori dei dati mostrati tradotti (scritti in italiano nel database)
# ---------------------------------------------------------------

CATEGORIE = (
    N_("Frutta"),
    N_("Verdura"),
    N_("Latticini e Uova"),
    N_("Carne"),
    N_("Pesce"),
    N_("Cereali"),
    N_("Legumi/Frutta Secca"),
    N_("Grassi e Oli"),
    N_("Dolci e Snack"),
    N_("Bevande"),
    N_("Piatti e ricette"),
    N_("Altri Alimenti"),
    N_("Senza categoria"),
)
