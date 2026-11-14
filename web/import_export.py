"""
Import ed export: tabella in CSV, Excel e PDF, scheda in PDF, import di
file CSV ed Excel con anteprima, sincronizzazione con USDA FoodData Central
(manuale e automatica).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from datetime import datetime
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
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

import analisi
import archivio
import backup
import esportazione
import fonti
import importazione
import lingue
import sincronizzazione
import usda
from web.accesso import solo_admin
from web.comune import (
    condizioni_utente,
    get_alimenti,
    get_alimento,
    get_db,
    invia_file,
    leggi_filtri,
    nome_file_sicuro,
)

bp = Blueprint("import_export", __name__)


# ---------------------------------------------------------------
# EXPORT (CSV, Excel, PDF)
# ---------------------------------------------------------------

FORMATI_EXPORT = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

ETICHETTE_ORDINAMENTO = {
    **importazione.ETICHETTE,
    "punteggio": "Punteggio",
    archivio.PER_TE: "Per te",
    archivio.PERTINENZA: "Pertinenza alla ricerca",
}


def filtro_esportato(campo: str, valore: str) -> tuple[str, str]:
    """
    (nome, valore) di un filtro per l'intestazione dei file esportati, nella
    lingua della richiesta: «Categoria Frutta», «Kcal ≤ 100», «Ricerca mele».
    """
    if campo == "q":
        return _("Ricerca"), valore

    if campo == "sicuri":
        return _("Solo alimenti sicuri"), _("sì")

    if campo == archivio.PER_TE:
        return _("Solo sicuri per il mio profilo"), _("sì")

    if campo in archivio.FILTRI_UGUALI:
        nome = _("Categoria") if campo == "categoria" else lingue.traduci(importazione.ETICHETTE[campo])
        return nome, lingue.traduci(valore)

    base, limite = campo.rsplit("_", 1)
    simbolo = "≥" if limite == "min" else "≤"
    return lingue.traduci(archivio.CAMPI_INTERVALLO[base]), f"{simbolo} {lingue.decimale(valore)}"


def info_export(filtri: archivio.Filtri, sort: str, direction: str, totale: int) -> esportazione.InfoExport:
    criteri = archivio.ordinamenti(sort.split(","), direction.split(","), bool(filtri.get("q")), condizioni_utente())

    def descrizione(campo: str, direzione: str) -> str:
        etichetta = lingue.traduci(ETICHETTE_ORDINAMENTO.get(campo, campo))

        if campo == archivio.PERTINENZA:
            return etichetta

        verso = lingue.traduci("Decrescente" if direzione == "desc" else "Crescente").lower()
        return f"{etichetta} ({verso})"

    return {
        "filtri": [filtro_esportato(campo, valore) for campo, valore in filtri.items() if valore],
        "ordinamento": f", {_('poi per')} ".join(descrizione(campo, direzione) for campo, direzione in criteri),
        "data": datetime.now(),
        "totale": totale,
    }


# Nomi dei file esportati: (tabella, tabella con filtri, scheda) per lingua
NOMI_FILE = {
    "it": ("alimenti", "alimenti_filtrati", "scheda"),
    "en": ("foods", "foods_filtered", "food"),
}


@bp.route("/esporta/<formato>")
def esporta(formato: str) -> ResponseReturnValue:
    """
    Tabella con gli stessi filtri e lo stesso ordinamento della home.
    """
    if formato not in FORMATI_EXPORT:
        abort(404)

    filtri, sort, direction = leggi_filtri()
    alimenti = get_alimenti(filtri, sort, direction)
    info = info_export(filtri, sort, direction, len(alimenti))

    if formato == "csv":
        dati = esportazione.csv_bytes(alimenti)
    elif formato == "xlsx":
        dati = esportazione.xlsx_bytes(alimenti, info)
    else:
        dati = esportazione.pdf_tabella(alimenti, info)

    tutti, filtrati, _scheda = NOMI_FILE.get(lingue.corrente(), NOMI_FILE["it"])
    nome = f"{filtrati if any(filtri.values()) else tutti}_{info['data']:%Y-%m-%d}.{formato}"
    return invia_file(dati, nome, FORMATI_EXPORT[formato])


@bp.route("/alimento/<int:alimento_id>/pdf")
def scheda_pdf(alimento_id: int) -> ResponseReturnValue:
    item = get_alimento(alimento_id)

    if not item:
        abort(404)

    medaglie = analisi.medaglie_per_alimento(get_alimenti()).get(alimento_id, [])
    dati = esportazione.pdf_scheda(item, medaglie, analisi.POSTI_MEDAGLIA, datetime.now())
    prefisso = NOMI_FILE.get(lingue.corrente(), NOMI_FILE["it"])[2]
    nome = f"{prefisso}_{nome_file_sicuro(item['alimento'], str(alimento_id))}.pdf"
    return invia_file(dati, nome, FORMATI_EXPORT["pdf"])


# ---------------------------------------------------------------
# IMPORT CSV / EXCEL con anteprima
#   1. /importa            caricamento del file (letto e salvato in instance/import)
#   2. /importa/anteprima  cosa succederà con ciascuna modalità
#   3. /importa/conferma   backup automatico e scrittura
# ---------------------------------------------------------------

IMPORT_SCADENZA_SECONDI = 3600
ANTEPRIMA_RIGHE = 25
ANTEPRIMA_AVVISI = 50
TOKEN_IMPORT_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


def cartella_import() -> str:
    os.makedirs(current_app.config["IMPORT_DIR"], exist_ok=True)
    return current_app.config["IMPORT_DIR"]


def percorso_import(token: str | None) -> str | None:
    if not token or not TOKEN_IMPORT_RE.match(token):
        return None

    return os.path.join(cartella_import(), f"{token}.json")


def pulisci_import_scaduti() -> None:
    limite = time.time() - IMPORT_SCADENZA_SECONDI

    for voce in os.scandir(cartella_import()):
        try:
            if voce.is_file() and voce.stat().st_mtime < limite:
                os.remove(voce.path)
        except OSError:
            pass


def carica_import() -> dict[str, Any] | None:
    """
    File letto e in attesa di conferma per questa sessione, oppure None.
    """
    percorso = percorso_import(session.get("import_token"))

    if not percorso or not os.path.isfile(percorso):
        return None

    with open(percorso, encoding="utf-8") as f:
        return json.load(f)


def scarta_import() -> None:
    percorso = percorso_import(session.pop("import_token", None))

    if percorso and os.path.isfile(percorso):
        os.remove(percorso)


@bp.route("/importa", methods=["GET", "POST"])
@solo_admin
def importa() -> ResponseReturnValue:
    if request.method == "POST":
        file = request.files.get("file")

        if not file or not file.filename:
            flash(_("Seleziona un file CSV o Excel da importare."), "danger")
            return redirect(url_for("import_export.importa"))

        nome_file = os.path.basename(file.filename.replace("\\", "/"))

        try:
            letto = importazione.leggi_file(nome_file, file.read())
        except importazione.ErroreImport as exc:
            flash(str(exc), "danger")
            return redirect(url_for("import_export.importa"))
        except Exception:
            current_app.logger.exception("Lettura del file di import non riuscita")
            flash(_("Il file non è leggibile: controlla che sia un CSV o un Excel valido."), "danger")
            return redirect(url_for("import_export.importa"))

        scarta_import()
        pulisci_import_scaduti()

        token = secrets.token_urlsafe(24)
        percorso = percorso_import(token)
        assert percorso is not None  # token appena generato, sempre valido

        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(letto, f, ensure_ascii=False)

        session["import_token"] = token
        return redirect(url_for("import_export.importa_anteprima"))

    return render_template(
        "import.html",
        in_attesa=carica_import(),
        max_mb=current_app.config["MAX_UPLOAD_MB"],
        max_righe=importazione.MAX_RIGHE,
        sincro=sincronizzazione.stato(
            current_app.config["DATABASE_PATH"], current_app.config["USDA_API_KEY"],
            current_app.config["USDA_SINCRONIZZA_GIORNI"],
        ),
        da_sincronizzare=conta_da_sincronizzare(),
    )


def conta_da_sincronizzare() -> int:
    conn = get_db()

    try:
        return len(usda.righe_da_sincronizzare(conn))
    finally:
        conn.close()


@bp.route("/sincronizza", methods=["POST"])
@solo_admin
def sincronizza() -> ResponseReturnValue:
    chiave = current_app.config["USDA_API_KEY"]

    if not usda.chiave_valida(chiave):
        flash(_("Per sincronizzare serve una chiave USDA personale (USDA_API_KEY)."), "danger")
    elif sincronizzazione.avvia_in_background(
        current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], chiave
    ):
        flash(_("Sincronizzazione con USDA avviata: ricarica la pagina tra qualche minuto per l'esito."), "info")
    else:
        flash(_("C'è già una sincronizzazione in corso."), "warning")

    return redirect(url_for("import_export.importa") + "#sincronizzazione")


def campi_anteprima(letto: dict[str, Any]) -> list[str]:
    """
    Colonne della tabella di anteprima: i campi di base sempre,
    quelli nutrizionali solo se il file li contiene.
    """
    nel_file = {colonna["campo"] for colonna in letto["colonne"]}
    return [
        campo for campo in importazione.CAMPI
        if campo not in importazione.CAMPI_NULLABILI or campo in nel_file
    ]


@bp.route("/importa/anteprima")
@solo_admin
def importa_anteprima() -> ResponseReturnValue:
    letto = carica_import()

    if letto is None:
        flash(_("Nessun file in attesa di conferma: caricane uno."), "warning")
        return redirect(url_for("import_export.importa"))

    modalita = request.args.get("modalita", importazione.MODALITA_PREDEFINITA)

    if modalita not in importazione.MODALITA:
        modalita = importazione.MODALITA_PREDEFINITA

    conn = get_db()

    try:
        piani = {
            chiave: importazione.pianifica(conn, letto, chiave)
            for chiave in importazione.MODALITA
        }
        totale_db = conn.execute("SELECT COUNT(*) FROM alimenti").fetchone()[0]
    finally:
        conn.close()

    voci = piani[modalita]

    return render_template(
        "import_anteprima.html",
        letto=letto,
        modalita=modalita,
        modalita_disponibili=importazione.MODALITA,
        riepiloghi={chiave: importazione.riepilogo(piano) for chiave, piano in piani.items()},
        voci=[v for v in voci if v["azione"] != "invariato"][:ANTEPRIMA_RIGHE],
        voci_con_avvisi=[v for v in voci if v["avvisi"]][:ANTEPRIMA_AVVISI],
        totale_db=totale_db,
        campi=campi_anteprima(letto),
        etichette=importazione.ETICHETTE,
        anteprima_righe=ANTEPRIMA_RIGHE,
        anteprima_avvisi=ANTEPRIMA_AVVISI,
    )


@bp.route("/importa/conferma", methods=["POST"])
@solo_admin
def importa_conferma() -> ResponseReturnValue:
    letto = carica_import()

    if letto is None:
        flash(_("Nessun file in attesa di conferma: caricane uno."), "warning")
        return redirect(url_for("import_export.importa"))

    modalita = request.form.get("modalita", "")

    if modalita not in importazione.MODALITA:
        abort(400)

    if modalita == "sostituisci" and request.form.get("conferma_sostituisci") != "1":
        flash(_("Per sostituire l'intera tabella spunta la casella di conferma."), "danger")
        return redirect(url_for("import_export.importa_anteprima", modalita=modalita))

    conn = get_db()

    try:
        voci = importazione.pianifica(conn, letto, modalita)
        sommario = importazione.riepilogo(voci)

        if modalita == "sostituisci" and sommario["nuovo"] == 0:
            flash(_("Il file non contiene righe valide: la tabella non è stata svuotata."), "danger")
            return redirect(url_for("import_export.importa_anteprima", modalita=modalita))

        if sommario["scritture"] == 0:
            scarta_import()
            flash(_("Nessuna modifica da applicare: il database contiene già questi dati."), "info")
            return redirect(url_for("pagine.index"))

        nome_backup = backup.crea(current_app.config["DATABASE_PATH"], current_app.config["BACKUP_DIR"], "import")
        adesso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        eliminati = importazione.applica(conn, voci, modalita, adesso)
        fonti.ricalcola_ricette(conn, adesso)
        conn.commit()
    except Exception:
        conn.rollback()
        current_app.logger.exception("Import non riuscito")
        flash(_("Errore durante l'importazione: nessuna modifica è stata salvata."), "danger")
        return redirect(url_for("import_export.importa_anteprima", modalita=modalita))
    finally:
        conn.close()

    scarta_import()

    parti = []

    if eliminati:
        parti.append(ngettext("%(num)d eliminato", "%(num)d eliminati", eliminati))

    parti.append(ngettext("%(num)d aggiunto", "%(num)d aggiunti", sommario["nuovo"]))

    if sommario["aggiornato"]:
        parti.append(ngettext("%(num)d aggiornato", "%(num)d aggiornati", sommario["aggiornato"]))

    if sommario["saltato"]:
        parti.append(ngettext("%(num)d riga saltata", "%(num)d righe saltate", sommario["saltato"]))

    flash(
        _(
            "Import completato: %(parti)s. Il database precedente è nel backup %(backup)s.",
            parti=", ".join(parti), backup=nome_backup,
        ),
        "success"
    )
    return redirect(url_for("pagine.index"))


@bp.route("/importa/annulla", methods=["POST"])
@solo_admin
def importa_annulla() -> ResponseReturnValue:
    scarta_import()
    flash(_("Import annullato: il database non è stato modificato."), "info")
    return redirect(url_for("import_export.importa"))



@bp.before_app_request
def avvia_sincronizzazione_automatica() -> None:
    """
    Avvia una volta per processo il controllo periodico della sincronizzazione
    USDA (solo con una chiave personale e USDA_SINCRONIZZA_GIORNI > 0).
    """
    if not current_app.testing:
        config = current_app.config
        sincronizzazione.avvia_automatica(
            config["DATABASE_PATH"], config["BACKUP_DIR"], config["USDA_API_KEY"], config["USDA_SINCRONIZZA_GIORNI"]
        )
