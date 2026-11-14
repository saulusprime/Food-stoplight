"""
Pasto (nella sessione del browser) e diario alimentare (per utente).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from flask_babel import ngettext
from flask_login import (
    current_user,
    login_required,
)

import analisi
import archivio
import nutrienti
import profilo as profilo_personale
from archivio import Alimento
from web.accesso import url_sicuro
from web.comune import (
    condizioni_utente,
    filtro_numero,
    get_db_diario,
    trova_alimento_da_modulo,
)

bp = Blueprint("pasto_diario", __name__)


# ---------------------------------------------------------------
# PASTO (nella sessione) E DIARIO ALIMENTARE (per utente)
# ---------------------------------------------------------------

PASTO_MAX_VOCI = 30
GIORNI_RIEPILOGO = 7
CHIAVI_PASTI = {chiave for chiave, _etichetta in nutrienti.PASTI}

# Valori per 100 g copiati nel diario al momento dell'inserimento
CAMPI_DIARIO = (
    "categoria", "tef_percent", "indice_glicemico",
    *nutrienti.CAMPI_PER_PORZIONE,
    *analisi.CAMPI_RISCHIO,
)


elenco_per_ricerca = archivio.elenco_per_ricerca


def grammi_non_validi() -> None:
    flash(
        _("Grammi non validi: servono da %(minimo)d a %(massimo)d g.",
          minimo=nutrienti.GRAMMI_MIN, massimo=nutrienti.GRAMMI_MAX),
        "danger"
    )


def leggi_pasto() -> list[dict[str, Any]]:
    voci = []

    for voce in session.get("pasto", []):
        try:
            voci.append({"id": int(voce["id"]), "grammi": float(voce["grammi"])})
        except (KeyError, TypeError, ValueError):
            continue

    return voci[:PASTO_MAX_VOCI]


def carica_voci(voci: list[dict[str, Any]]) -> list[tuple[Alimento, float, int]]:
    """
    [(alimento, grammi, indice)] per le voci del pasto il cui alimento esiste ancora.
    """
    if not voci:
        return []

    per_id = archivio.get_alimenti_per_id(sorted({voce["id"] for voce in voci}))
    return [
        (per_id[voce["id"]], voce["grammi"], indice)
        for indice, voce in enumerate(voci)
        if voce["id"] in per_id
    ]


def riepilogo_nutrizionale(voci: list[tuple[Alimento, float]]) -> dict[str, Any] | None:
    """
    Totali, dati mancanti, profilo di rischio (con radar) e semaforo per te
    di una lista di (alimento, grammi).
    """
    if not voci:
        return None

    somme, mancanti = nutrienti.totali(voci)
    profilo = nutrienti.profilo_rischio(voci)

    return {
        "totali": somme,
        "mancanti": mancanti,
        "profilo": profilo,
        "radar": analisi.radar({}, punti={r["campo"]: r["punti"] for r in profilo["rischi"]}),
        "per_te": profilo_personale.per_te_profilo(profilo["rischi"], condizioni_utente()),
        "voci": len(voci),
    }


def pasto_dell_ora() -> str:
    ora = datetime.now().hour

    if ora < 11:
        return "colazione"

    if ora < 15:
        return "pranzo"

    if ora < 18:
        return "spuntino"

    return "cena"


@bp.route("/pasto")
def pasto() -> ResponseReturnValue:
    voci = carica_voci(leggi_pasto())

    return render_template(
        "pasto.html",
        voci=voci,
        riepilogo=riepilogo_nutrizionale([(item, grammi) for item, grammi, _indice in voci]),
        elenco=elenco_per_ricerca(),
        oggi=date.today().isoformat(),
        pasto_suggerito=pasto_dell_ora(),
        max_voci=PASTO_MAX_VOCI,
    )


@bp.route("/pasto/aggiungi", methods=["POST"])
def pasto_aggiungi() -> ResponseReturnValue:
    destinazione = url_sicuro(request.form.get("next")) or url_for("pasto_diario.pasto")
    item, errore = trova_alimento_da_modulo(request.form)
    grammi = nutrienti.leggi_grammi(request.form.get("grammi"))

    if errore or item is None:
        flash(errore or _("Alimento non trovato."), "danger")
        return redirect(destinazione)

    if grammi is None:
        grammi_non_validi()
        return redirect(destinazione)

    voci = leggi_pasto()
    esistente = next((voce for voce in voci if voce["id"] == item["id"]), None)

    if esistente:
        esistente["grammi"] = min(round(esistente["grammi"] + grammi, 1), nutrienti.GRAMMI_MAX)
    elif len(voci) >= PASTO_MAX_VOCI:
        flash(_("Il pasto può contenere al massimo %(n)d alimenti.", n=PASTO_MAX_VOCI), "warning")
        return redirect(destinazione)
    else:
        voci.append({"id": item["id"], "grammi": grammi})

    session["pasto"] = voci
    flash(
        _("Aggiunto al pasto: %(nome)s, %(grammi)s g.", nome=item["alimento"], grammi=filtro_numero(grammi)),
        "success"
    )
    return redirect(destinazione)


@bp.route("/pasto/aggiorna", methods=["POST"])
def pasto_aggiorna() -> ResponseReturnValue:
    voci = leggi_pasto()
    rimuovi = (request.form.get("rimuovi") or "").strip()

    if rimuovi.isdigit():
        if int(rimuovi) < len(voci):
            del voci[int(rimuovi)]
    else:
        for indice, voce in enumerate(voci):
            testo = request.form.get(f"grammi_{indice}")

            if testo is None:
                continue

            grammi = nutrienti.leggi_grammi(testo)

            if grammi is None:
                grammi_non_validi()
                return redirect(url_for("pasto_diario.pasto"))

            voce["grammi"] = grammi

    session["pasto"] = voci
    return redirect(url_for("pasto_diario.pasto"))


@bp.route("/pasto/svuota", methods=["POST"])
def pasto_svuota() -> ResponseReturnValue:
    session.pop("pasto", None)
    flash(_("Pasto svuotato."), "info")
    return redirect(url_for("pasto_diario.pasto"))


def leggi_giorno(testo: str | None) -> date | None:
    try:
        return date.fromisoformat((testo or "").strip())
    except ValueError:
        return None


def istantanea_diario(item: Alimento) -> str:
    return json.dumps({campo: item.get(campo) for campo in CAMPI_DIARIO}, ensure_ascii=False)


def inserisci_diario(
    conn: sqlite3.Connection, giorno: date, pasto_chiave: str, item: Alimento, grammi: float
) -> None:
    conn.execute(
        """
        INSERT INTO diario (utente_id, data, pasto, alimento_id, alimento, grammi, valori, creato_il)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_user.id, giorno.isoformat(), pasto_chiave, item["id"], item["alimento"],
            grammi, istantanea_diario(item), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def voci_diario(utente_id: int, dal: date, al: date | None = None) -> list[dict[str, Any]]:
    """
    Voci del diario tra due date (comprese), con i valori per 100 g salvati.
    """
    conn = get_db_diario()
    righe = conn.execute(
        """
        SELECT id, data, pasto, alimento_id, alimento, grammi, valori
        FROM diario
        WHERE utente_id = ? AND data BETWEEN ? AND ?
        ORDER BY data, id
        """,
        (utente_id, dal.isoformat(), (al or dal).isoformat()),
    ).fetchall()
    conn.close()

    voci = []

    for riga in righe:
        try:
            valori = json.loads(riga["valori"])
        except (TypeError, ValueError):
            valori = {}

        voci.append({**dict(riga), "item": {**valori, "alimento": riga["alimento"]}})

    return voci


def collegamenti_schede(voci: list[dict[str, Any]]) -> set[int]:
    """
    ID degli alimenti ancora presenti con lo stesso nome (per il link alla scheda).
    """
    ids = sorted({v["alimento_id"] for v in voci if v["alimento_id"]})

    if not ids:
        return set()

    presenti = archivio.get_alimenti_per_id(ids)
    nomi = {v["alimento_id"]: v["alimento"] for v in voci}
    return {i for i, a in presenti.items() if a["alimento"] == nomi.get(i)}


def torna_al_diario(giorno: date) -> ResponseReturnValue:
    return redirect(url_for("pasto_diario.diario", data=giorno.isoformat()))


@bp.route("/diario")
@login_required
def diario() -> ResponseReturnValue:
    giorno = leggi_giorno(request.args.get("data")) or date.today()
    voci = voci_diario(current_user.id, giorno)

    per_pasto = []

    for chiave, etichetta in nutrienti.PASTI:
        del_pasto = [v for v in voci if v["pasto"] == chiave]
        kcal = sum((v["item"].get("kcal") or 0) * v["grammi"] / 100 for v in del_pasto)
        per_pasto.append((chiave, etichetta, del_pasto, kcal))

    # Ultimi giorni fino a quello mostrato: Kcal nette e TEF per giorno
    inizio = giorno - timedelta(days=GIORNI_RIEPILOGO - 1)
    settimana: list[dict[str, Any]] = []

    for i in range(GIORNI_RIEPILOGO):
        g = inizio + timedelta(days=i)
        del_giorno = [(v["item"], v["grammi"]) for v in voci_diario(current_user.id, g)]
        somme, _mancanti = nutrienti.totali(del_giorno) if del_giorno else ({}, {})
        settimana.append({
            "giorno": g,
            "voci": len(del_giorno),
            "kcal_nette": somme.get("kcal_nette", 0),
            "tef_kcal": somme.get("tef_kcal", 0),
        })

    massimo = max((s["kcal_nette"] + s["tef_kcal"] for s in settimana), default=0)

    return render_template(
        "diario.html",
        giorno=giorno,
        oggi=date.today(),
        precedente=giorno - timedelta(days=1),
        successivo=giorno + timedelta(days=1),
        per_pasto=per_pasto,
        riepilogo=riepilogo_nutrizionale([(v["item"], v["grammi"]) for v in voci]),
        collegati=collegamenti_schede(voci),
        settimana=settimana,
        massimo_settimana=massimo,
        elenco=elenco_per_ricerca(),
        pasto_suggerito=pasto_dell_ora() if giorno == date.today() else "pranzo",
    )


@bp.route("/diario/aggiungi", methods=["POST"])
@login_required
def diario_aggiungi() -> ResponseReturnValue:
    giorno = leggi_giorno(request.form.get("data")) or date.today()
    pasto_chiave = request.form.get("pasto", "")
    item, errore = trova_alimento_da_modulo(request.form)
    grammi = nutrienti.leggi_grammi(request.form.get("grammi"))

    if pasto_chiave not in CHIAVI_PASTI:
        flash(_("Scegli il pasto: colazione, pranzo, cena o spuntino."), "danger")
    elif errore or item is None:
        flash(errore or _("Alimento non trovato."), "danger")
    elif grammi is None:
        grammi_non_validi()
    else:
        conn = get_db_diario()
        inserisci_diario(conn, giorno, pasto_chiave, item, grammi)
        conn.commit()
        conn.close()
        flash(
            _("Aggiunto al diario: %(nome)s, %(grammi)s g.", nome=item["alimento"], grammi=filtro_numero(grammi)),
            "success"
        )

    return torna_al_diario(giorno)


@bp.route("/diario/aggiungi-pasto", methods=["POST"])
@login_required
def diario_aggiungi_pasto() -> ResponseReturnValue:
    giorno = leggi_giorno(request.form.get("data")) or date.today()
    pasto_chiave = request.form.get("pasto", "")
    voci = carica_voci(leggi_pasto())

    if pasto_chiave not in CHIAVI_PASTI:
        flash(_("Scegli il pasto: colazione, pranzo, cena o spuntino."), "danger")
        return redirect(url_for("pasto_diario.pasto"))

    if not voci:
        flash(_("Il pasto è vuoto."), "warning")
        return redirect(url_for("pasto_diario.pasto"))

    conn = get_db_diario()

    for item, grammi, _indice in voci:
        inserisci_diario(conn, giorno, pasto_chiave, item, grammi)

    conn.commit()
    conn.close()

    if request.form.get("svuota") == "1":
        session.pop("pasto", None)

    flash(
        ngettext("Salvato nel diario %(num)d alimento.", "Salvati nel diario %(num)d alimenti.", len(voci)),
        "success"
    )
    return torna_al_diario(giorno)


def voce_diario_propria(voce_id: int) -> sqlite3.Row:
    """
    Voce del diario dell'utente connesso, altrimenti 404 (anche se è di un altro utente).
    """
    conn = get_db_diario()
    riga = conn.execute(
        "SELECT id, data FROM diario WHERE id = ? AND utente_id = ?", (voce_id, current_user.id)
    ).fetchone()
    conn.close()

    if riga is None:
        abort(404)

    return riga


@bp.route("/diario/voce/<int:voce_id>/aggiorna", methods=["POST"])
@login_required
def diario_aggiorna(voce_id: int) -> ResponseReturnValue:
    riga = voce_diario_propria(voce_id)
    grammi = nutrienti.leggi_grammi(request.form.get("grammi"))

    if grammi is None:
        grammi_non_validi()
    else:
        conn = get_db_diario()
        conn.execute("UPDATE diario SET grammi = ? WHERE id = ?", (grammi, voce_id))
        conn.commit()
        conn.close()

    return torna_al_diario(date.fromisoformat(riga["data"]))


@bp.route("/diario/voce/<int:voce_id>/elimina", methods=["POST"])
@login_required
def diario_elimina(voce_id: int) -> ResponseReturnValue:
    riga = voce_diario_propria(voce_id)

    conn = get_db_diario()
    conn.execute("DELETE FROM diario WHERE id = ?", (voce_id,))
    conn.commit()
    conn.close()

    flash(_("Voce eliminata dal diario."), "info")
    return torna_al_diario(date.fromisoformat(riga["data"]))
