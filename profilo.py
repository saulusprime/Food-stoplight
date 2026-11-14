"""
Profilo personale: condizioni dell'utente (diabete, ipercolesterolemia,
malassorbimento del fruttosio) e semaforo «per te».

Il semaforo per te non introduce soglie nuove: per ogni condizione guarda il
rischio già calcolato che la riguarda (rischi.py) e mostra il più alto.
- un rischio Alto basta per dare Alto, anche se un altro non è classificato;
- altrimenti, se un rischio del profilo non è classificato, il semaforo per
  te resta non classificato (l'app non indovina);
- altrimenti vale il livello più alto tra i rischi del profilo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import analisi
from lingue import N_

Condizione = dict[str, str]

CONDIZIONI: tuple[Condizione, ...] = (
    {
        "chiave": "diabete",
        "etichetta": N_("Diabete"),
        "descrizione": N_("Diabete o prediabete: conta il rischio diabete (carico glicemico e zuccheri liberi)."),
        "rischio": "rischio_diabete",
    },
    {
        "chiave": "colesterolo",
        "etichetta": N_("Ipercolesterolemia"),
        "descrizione": N_(
            "Colesterolo alto: conta il rischio colesterolo (grassi saturi e colesterolo della porzione)."
        ),
        "rischio": "rischio_colesterolo",
    },
    {
        "chiave": "fruttosio",
        "etichetta": N_("Malassorbimento del fruttosio"),
        "descrizione": N_("Conta il rischio malassorbimento (fruttosio in eccesso sul glucosio nella porzione)."),
        "rischio": "rischio_malassorbimento",
    },
)

PER_CHIAVE = {c["chiave"]: c for c in CONDIZIONI}

# Livelli «adatti» per il filtro della tabella, come per «Solo alimenti sicuri»
PUNTI_ADATTI = 1


def leggi(valore: object) -> tuple[str, ...]:
    """
    Condizioni valide, nell'ordine di CONDIZIONI e senza ripetizioni, da un
    testo «diabete,fruttosio» o da un elenco di chiavi.
    """
    if isinstance(valore, str):
        scelte = {parte.strip().lower() for parte in valore.split(",")}
    elif isinstance(valore, Iterable):
        scelte = {str(parte).strip().lower() for parte in valore}
    else:
        scelte = set()

    return tuple(c["chiave"] for c in CONDIZIONI if c["chiave"] in scelte)


def testo(condizioni: Iterable[str]) -> str:
    """
    Forma da salvare nel database: «diabete,fruttosio» ("" senza condizioni).
    """
    return ",".join(leggi(list(condizioni)))


def campi(condizioni: Iterable[str]) -> tuple[str, ...]:
    """
    Campi dei rischi del profilo, nell'ordine di CONDIZIONI.
    """
    return tuple(PER_CHIAVE[c]["rischio"] for c in leggi(list(condizioni)))


def punti_per_te(*valori: object) -> int | None:
    """
    Punti (0-3) del semaforo per te dai valori dei rischi del profilo, None se
    non classificato. È anche la funzione SQL per_te(...) di alimenti.db.
    """
    livelli = [analisi.livello(v) for v in valori]

    if not livelli:
        return None

    punti = [liv["punti"] for liv in livelli if liv]

    if analisi.PUNTI_MAX in punti:
        return analisi.PUNTI_MAX

    if len(punti) < len(livelli):
        return None

    return max(punti)


def livello_da_punti(punti: float | None) -> analisi.Livello:
    if punti is None:
        return analisi.NON_CLASSIFICATO

    return analisi.LIVELLI[min(int(punti + 0.5), len(analisi.LIVELLI) - 1)]


def per_te(alimento: Mapping[str, Any], condizioni: Sequence[str]) -> dict[str, Any] | None:
    """
    Semaforo per te di un alimento: livello complessivo e, per ogni
    condizione, il rischio che conta. None senza condizioni.
    """
    scelte = leggi(list(condizioni))

    if not scelte:
        return None

    voci: list[dict[str, Any]] = []

    for chiave in scelte:
        condizione = PER_CHIAVE[chiave]
        valore = alimento.get(condizione["rischio"])
        voci.append({
            **condizione,
            "valore": valore,
            "livello": analisi.livello(valore) or analisi.NON_CLASSIFICATO,
        })

    punti = punti_per_te(*(voce["valore"] for voce in voci))
    livello = livello_da_punti(punti)

    return {
        "punti": punti,
        "livello": livello,
        "voci": voci,
        # Le condizioni che determinano il livello (il rischio più alto)
        "decisive": [v for v in voci if punti is not None and v["livello"]["punti"] == punti],
        "adatto": punti is not None and punti <= PUNTI_ADATTI,
    }


def per_te_profilo(rischi: Sequence[Mapping[str, Any]], condizioni: Sequence[str]) -> dict[str, Any] | None:
    """
    Semaforo per te di un pasto o di una giornata, dai punti medi di ogni
    rischio (nutrienti.profilo_rischio): stesse regole degli alimenti, sui
    livelli dei punti medi.
    """
    scelte = leggi(list(condizioni))

    if not scelte:
        return None

    per_campo = {r["campo"]: r for r in rischi}
    voci: list[dict[str, Any]] = [
        {**PER_CHIAVE[c], "rischio_medio": per_campo.get(PER_CHIAVE[c]["rischio"])} for c in scelte
    ]
    medie = [(v["rischio_medio"] or {}).get("punti") for v in voci]
    livelli = [livello_da_punti(m) if m is not None else None for m in medie]

    if any(liv is not None and liv["punti"] == analisi.PUNTI_MAX for liv in livelli):
        punti: float | None = max(m for m in medie if m is not None)
    elif any(m is None for m in medie):
        punti = None
    else:
        punti = max(m for m in medie if m is not None)

    return {
        "punti": punti,
        "livello": livello_da_punti(punti),
        "voci": voci,
    }
