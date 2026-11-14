"""
Piano settimanale dei pasti (piano.py): pranzi e cene con i pasti pronti,
bilanciati sui rischi. Ogni piatto si può cambiare o scegliere a mano, e gli
altri si ribilanciano. Resta nella sessione del browser, come il pasto e la
lista della spesa, e offline nell'ultima copia aperta.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Any

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_babel import format_date, ngettext
from flask_babel import gettext as _

import analisi
import archivio
import lingue
import nutrienti
import pasti_pronti
import piano
import profilo
import spesa
from lingue import N_
from web.comune import condizioni_utente, invia_file
from web.pasti_pronti import alimenti_per_codice, ricette_db, rischi_in_evidenza
from web.pasto_diario import riepilogo_nutrizionale

bp = Blueprint("piano", __name__)

CHIAVE_PIANO = "piano"
ETICHETTE_PASTI = dict(piano.PASTI)
ETICHETTE_PORTATE = {
    "antipasto": N_("Antipasto"),
    "primo": N_("Primo"),
    "secondo": N_("Secondo"),
    "contorno": N_("Contorno"),
}


# ---------------------------------------------------------------
# PIANO NELLA SESSIONE
# ---------------------------------------------------------------

def _intero(valore: object, predefinito: int, minimo: int, massimo: int) -> int:
    try:
        numero = int(str(valore))
    except ValueError:
        return predefinito

    return max(minimo, min(numero, massimo))


def _data(valore: object) -> date | None:
    try:
        return date.fromisoformat(str(valore or "").strip())
    except ValueError:
        return None


def _portate(scelte: object) -> dict[str, list[str]]:
    scelte = scelte if isinstance(scelte, dict) else piano.PORTATE_PREDEFINITE
    return {
        pasto: [p for p in pasti_pronti.CHIAVI_PORTATE if p in (scelte.get(pasto) or ())]
        for pasto in piano.CHIAVI_PASTI
    }


def leggi_piano() -> dict[str, Any]:
    """
    Piano della sessione con opzioni valide e posti; "piatti" (un ID o None
    per posto) è vuoto se non c'è un piano o non corrisponde più ai posti.
    """
    salvato = session.get(CHIAVE_PIANO)
    salvato = salvato if isinstance(salvato, dict) else {}
    giorni = _intero(salvato.get("giorni"), piano.GIORNI_MAX, 1, piano.GIORNI_MAX)
    portate = _portate(salvato.get("portate"))
    posti = piano.posti(giorni, portate)
    piatti: list[int | None] = []

    for valore in salvato.get("piatti") or []:
        piatti.append(valore if isinstance(valore, int) and not isinstance(valore, bool) else None)

    if len(piatti) != len(posti):
        piatti = []

    return {
        "inizio": _data(salvato.get("inizio")) or date.today(),
        "giorni": giorni,
        "portate": portate,
        "persone": _intero(salvato.get("persone"), 1, 1, piano.PERSONE_MAX),
        "posti": posti,
        "piatti": piatti,
        "fissi": sorted({i for i in salvato.get("fissi") or [] if isinstance(i, int) and 0 <= i < len(piatti)}),
    }


def salva_piano(dati: dict[str, Any]) -> None:
    session[CHIAVE_PIANO] = {
        "inizio": dati["inizio"].isoformat(),
        "giorni": dati["giorni"],
        "portate": dati["portate"],
        "persone": dati["persone"],
        "piatti": dati["piatti"],
        "fissi": sorted(dati["fissi"]),
    }


def piatti_disponibili() -> list[dict[str, Any]]:
    """
    Piatti dei pasti pronti (righe di alimenti) con portata, codice e ricetta.
    """
    ricette = ricette_db()
    per_id = archivio.get_alimenti_per_id([r["alimento_id"] for r in ricette if r["alimento_id"]])
    return [
        {**per_id[r["alimento_id"]], "portata": r["portata"], "codice": r["codice"], "ricetta": r}
        for r in ricette
        if r["alimento_id"] in per_id
    ]


# ---------------------------------------------------------------
# DATI PER LA PAGINA
# ---------------------------------------------------------------

def nome_giorno(giorno: date, formato: str = "EEEE d MMMM") -> str:
    testo = format_date(giorno, formato)
    return testo[:1].upper() + testo[1:]


def descrizione_posto(dati: dict[str, Any], indice: int, nome: str) -> str:
    giorno, pasto, _portata = dati["posti"][indice]
    return _(
        "%(giorno)s, %(pasto)s: %(piatto)s",
        giorno=format_date(dati["inizio"] + timedelta(days=giorno), "EEEE d"),
        pasto=lingue.traduci(ETICHETTE_PASTI[pasto]).lower(),
        piatto=nome,
    )


def voce_posto(
    dati: dict[str, Any], indice: int, piatto: dict[str, Any] | None, condizioni: tuple[str, ...],
) -> dict[str, Any]:
    portata = dati["posti"][indice][2]
    return {
        "indice": indice,
        "portata": portata,
        "etichetta_portata": ETICHETTE_PORTATE[portata],
        "piatto": piatto,
        "kcal": piano.kcal_porzione(piatto) if piatto else None,
        "porzione": nutrienti.porzione(piatto) if piatto else None,
        "rischi": rischi_in_evidenza(piatto),
        "per_te": profilo.per_te(piatto, condizioni) if piatto else None,
        "fisso": indice in dati["fissi"],
    }


def settimana(
    dati: dict[str, Any], per_id: dict[int, dict[str, Any]], condizioni: tuple[str, ...],
) -> list[dict[str, Any]]:
    """
    Giorni del piano: data, pasti con le loro voci, Kcal e profilo di rischio del giorno.
    """
    giorni = []

    for g in range(dati["giorni"]):
        pasti = []
        voci_giorno: list[tuple[dict[str, Any], float]] = []

        for pasto, etichetta in piano.PASTI:
            voci = [
                voce_posto(dati, i, per_id.get(dati["piatti"][i] or 0), condizioni)
                for i, (giorno, pasto_posto, _portata) in enumerate(dati["posti"])
                if giorno == g and pasto_posto == pasto
            ]

            if voci:
                pasti.append({"chiave": pasto, "etichetta": etichetta, "voci": voci})
                voci_giorno.extend((v["piatto"], v["porzione"]) for v in voci if v["piatto"])

        rischio = nutrienti.profilo_rischio(voci_giorno) if voci_giorno else None
        data = dati["inizio"] + timedelta(days=g)
        giorni.append({
            "indice": g,
            "data": data,
            "nome": nome_giorno(data),
            "breve": nome_giorno(data, "EEE d"),
            "pasti": pasti,
            "voci": voci_giorno,
            "kcal": math.fsum(piano.kcal_porzione(p) for p, _g in voci_giorno),
            "profilo": rischio,
            "per_te": profilo.per_te_profilo(rischio["rischi"], condizioni) if rischio else None,
        })

    return giorni


def tabella_rischi(giorni: list[dict[str, Any]], riepilogo: dict[str, Any] | None) -> list[dict[str, Any]]:
    """
    Una riga per rischio: livello medio di ogni giorno e della settimana.
    """
    righe = []

    for r, (campo, etichetta) in enumerate(analisi.RISCHI):
        righe.append({
            "campo": campo,
            "etichetta": etichetta,
            "giorni": [g["profilo"]["rischi"][r] if g["profilo"] else None for g in giorni],
            "settimana": riepilogo["profilo"]["rischi"][r] if riepilogo else None,
        })

    return righe


def ingredienti(piatti: list[dict[str, Any]], persone: int) -> list[tuple[str, list[dict[str, Any]]]]:
    """
    Ingredienti abbinati di tutti i piatti con i grammi crudi per le persone,
    sommati e raggruppati per reparto (spesa.raggruppa).
    """
    grammi: dict[str, float] = {}

    for piatto in piatti:
        for voce in pasti_pronti.per_porzione(piatto["ricetta"], persone):
            grammi[voce["codice_crea"]] = grammi.get(voce["codice_crea"], 0.0) + voce["grammi_porzione"]

    alimenti = alimenti_per_codice(sorted(grammi))
    voci = [
        {**alimenti[codice], "grammi": max(1, round(totale))}
        for codice, totale in grammi.items()
        if codice in alimenti
    ]
    voci.sort(key=lambda v: (v["alimento"] or "").casefold())
    return spesa.raggruppa(voci)


def piatti_del_piano(dati: dict[str, Any], per_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [per_id[i] for i in dati["piatti"] if i in per_id]


@bp.route("/piano")
def pagina() -> ResponseReturnValue:
    dati = leggi_piano()
    condizioni = condizioni_utente()
    tutti = piatti_disponibili() if dati["piatti"] else []
    per_id = {p["id"]: p for p in tutti}
    giorni = settimana(dati, per_id, condizioni) if dati["piatti"] else []
    voci = [voce for g in giorni for voce in g["voci"]]
    riepilogo = riepilogo_nutrizionale(voci)
    nel_piano = piatti_del_piano(dati, per_id)
    campi = profilo.campi(condizioni)

    return render_template(
        "piano.html",
        dati=dati,
        giorni=giorni,
        riepilogo=riepilogo,
        tabella_rischi=tabella_rischi(giorni, riepilogo),
        ingredienti=ingredienti(nel_piano, dati["persone"]),
        # Per scegliere un piatto: i nomi di ogni portata
        nomi_portate={
            portata: sorted((p["alimento"] for p in tutti if p["portata"] == portata), key=str.casefold)
            for portata in {posto[2] for posto in dati["posti"]}
        },
        alti_per_te=sum(
            1 for p in nel_piano if campi and profilo.punti_per_te(*(p.get(c) for c in campi)) == analisi.PUNTI_MAX
        ),
        pasti=piano.PASTI,
        portate=pasti_pronti.PORTATE,
        etichette_portate=ETICHETTE_PORTATE,
        giorni_max=piano.GIORNI_MAX,
        persone_max=piano.PERSONE_MAX,
    )


# ---------------------------------------------------------------
# GENERAZIONE E MODIFICHE
# ---------------------------------------------------------------

def torna(indice: int | None = None) -> ResponseReturnValue:
    return redirect(url_for("piano.pagina", _anchor=f"posto-{indice}" if indice is not None else None))


@bp.route("/piano/genera", methods=["POST"])
def genera() -> ResponseReturnValue:
    dati = leggi_piano()
    dati["inizio"] = _data(request.form.get("inizio")) or date.today()
    dati["giorni"] = _intero(request.form.get("giorni"), piano.GIORNI_MAX, 1, piano.GIORNI_MAX)
    dati["portate"] = _portate({pasto: request.form.getlist(f"portate_{pasto}") for pasto in piano.CHIAVI_PASTI})
    dati["posti"] = piano.posti(dati["giorni"], dati["portate"])
    dati["piatti"], dati["fissi"] = [], []

    if not dati["posti"]:
        salva_piano(dati)
        flash(_("Scegli almeno una portata per il pranzo o per la cena."), "warning")
        return torna()

    # Ogni volta un piano diverso: tra i piatti pari nel bilanciamento si sceglie a caso
    seme = random.randrange(1 << 30)
    dati["piatti"] = piano.genera(piatti_disponibili(), dati["posti"], condizioni_utente(), seme=seme)
    salva_piano(dati)

    n = sum(1 for p in dati["piatti"] if p is not None)
    flash(ngettext("Piano pronto: %(num)d piatto, bilanciato sui rischi.",
                   "Piano pronto: %(num)d piatti, bilanciati sui rischi.", n), "success")

    vuote = sorted({posto[2] for posto, p in zip(dati["posti"], dati["piatti"], strict=True) if p is None},
                   key=pasti_pronti.CHIAVI_PORTATE.index)

    if vuote:
        etichette = dict(pasti_pronti.PORTATE)
        flash(_("Nessun piatto tra i pasti pronti per: %(portate)s.",
                portate=", ".join(lingue.traduci(etichette[p]) for p in vuote)), "info")

    return torna()


def ribilancia(dati: dict[str, Any], piatti: list[dict[str, Any]], scelto: int | None = None) -> None:
    """
    Ribilancia il piano attorno ai piatti fissi, lo salva e dice quali altri
    piatti sono cambiati (scelto: il posto appena modificato, che non conta).
    """
    prima = list(dati["piatti"])
    dati["piatti"] = piano.ribilancia(piatti, dati["posti"], prima, dati["fissi"], condizioni_utente())
    salva_piano(dati)

    nomi = {p["id"]: p["alimento"] for p in piatti}
    cambiati = [
        descrizione_posto(dati, i, nomi[nuovo])
        for i, (vecchio, nuovo) in enumerate(zip(prima, dati["piatti"], strict=True))
        if vecchio != nuovo and nuovo is not None and i != scelto
    ]

    if cambiati:
        flash(ngettext("Per bilanciare i rischi è cambiato anche %(piatti)s.",
                       "Per bilanciare i rischi sono cambiati anche: %(piatti)s.",
                       len(cambiati), piatti="; ".join(cambiati)), "info")


@bp.route("/piano/cambia/<int:indice>", methods=["POST"])
def cambia(indice: int) -> ResponseReturnValue:
    """
    Mette nel posto il piatto successivo tra le alternative più bilanciate;
    il posto resta fisso e gli altri si ribilanciano.
    """
    dati = leggi_piano()

    if not 0 <= indice < len(dati["piatti"]):
        return torna()

    piatti = piatti_disponibili()
    nuovo = piano.successivo(piatti, dati["posti"], dati["piatti"], indice, condizioni_utente())

    if nuovo is None:
        flash(_("Nessun altro piatto da proporre per questa portata."), "info")
        return torna(indice)

    dati["piatti"][indice] = nuovo
    dati["fissi"] = sorted({*dati["fissi"], indice})
    ribilancia(dati, piatti, indice)
    return torna(indice)


@bp.route("/piano/scegli/<int:indice>", methods=["POST"])
def scegli(indice: int) -> ResponseReturnValue:
    """
    Mette nel posto il piatto indicato per nome (della stessa portata).
    """
    dati = leggi_piano()

    if not 0 <= indice < len(dati["piatti"]):
        return torna()

    piatti = piatti_disponibili()
    portata = dati["posti"][indice][2]
    nome = (request.form.get("piatto") or "").strip().casefold()
    trovato = next((p for p in piatti if p["portata"] == portata and (p["alimento"] or "").casefold() == nome), None)

    if trovato is None:
        flash(_("Piatto non trovato tra i pasti pronti di questa portata."), "danger")
        return torna(indice)

    dati["piatti"][indice] = trovato["id"]
    dati["fissi"] = sorted({*dati["fissi"], indice})
    ribilancia(dati, piatti, indice)
    return torna(indice)


@bp.route("/piano/libera/<int:indice>", methods=["POST"])
def libera(indice: int) -> ResponseReturnValue:
    """
    Il posto torna libero: il piano può cambiarlo per bilanciare i rischi.
    """
    dati = leggi_piano()

    if indice in dati["fissi"]:
        dati["fissi"] = [i for i in dati["fissi"] if i != indice]
        ribilancia(dati, piatti_disponibili())

    return torna(indice)


@bp.route("/piano/persone", methods=["POST"])
def persone() -> ResponseReturnValue:
    dati = leggi_piano()
    dati["persone"] = _intero(request.form.get("persone"), 1, 1, piano.PERSONE_MAX)
    salva_piano(dati)
    return redirect(url_for("piano.pagina", _anchor="ingredienti"))


@bp.route("/piano/svuota", methods=["POST"])
def svuota() -> ResponseReturnValue:
    dati = leggi_piano()
    dati["piatti"], dati["fissi"] = [], []
    salva_piano(dati)
    flash(_("Piano svuotato."), "info")
    return torna()


@bp.route("/piano/testo")
def scarica_testo() -> ResponseReturnValue:
    """
    Piano e ingredienti in testo semplice.
    """
    dati = leggi_piano()
    per_id = {p["id"]: p for p in piatti_disponibili()} if dati["piatti"] else {}
    righe = [_("Piano dei pasti dal %(data)s", data=format_date(dati["inizio"], "short")), ""]

    for giorno in settimana(dati, per_id, ()):
        righe.append(giorno["nome"])

        for pasto in giorno["pasti"]:
            righe.append(lingue.traduci(pasto["etichetta"]))
            righe.extend(
                f"- {lingue.traduci(v['etichetta_portata'])}: {v['piatto']['alimento'] if v['piatto'] else '–'}"
                for v in pasto["voci"]
            )

        righe.append("")

    gruppi = ingredienti(piatti_del_piano(dati, per_id), dati["persone"])

    if gruppi:
        titolo = ngettext("Ingredienti per %(num)d persona", "Ingredienti per %(num)d persone", dati["persone"])
        righe.extend([titolo, ""])

        for reparto, voci in gruppi:
            righe.append(lingue.traduci(reparto) if reparto else _("Senza categoria"))
            righe.extend(f"- {v['alimento']}, {v['grammi']} g" for v in voci)
            righe.append("")

    contenuto = "\n".join(righe).rstrip() + "\n"
    return invia_file(contenuto.encode("utf-8"), _("piano-dei-pasti") + ".txt", "text/plain; charset=utf-8")
