"""
Lista della spesa «a semaforo verde»: per ogni reparto (categoria degli
alimenti) gli alimenti da comprare con il semaforo migliore.

- Semaforo verde: i cinque rischi tutti classificati, nessuno oltre Basso, e
  punteggio verde (livello Trascurabile, da 84 su 100).
- Nei reparti con meno alimenti verdi di quelli chiesti (con le regole
  attuali cereali, oli e grassi non ne hanno) si aggiungono le scelte migliori
  senza rischi alti: tutti classificati, nessuno Alto. Restano segnate come
  non verdi.
- Solo quello che si compra: niente alimenti cotti («…, cotti, bolliti»),
  niente ricette e piatti pronti, niente erbe aromatiche e condimenti (porzione
  tipica sotto i 30 g: si aggiungono a mano); un alimento per tipo (la prima
  parola del nome: le mele una volta sola, anche se le varietà sono tante).
- Con un profilo (profilo.py) vengono prima gli alimenti con il semaforo per
  te più basso, poi quelli con il punteggio più alto.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Any

import analisi
import profilo

Alimento = dict[str, Any]

# Reparti nell'ordine del supermercato; i primi sono quelli proposti
REPARTI = (
    "Verdura", "Frutta", "Cereali", "Legumi/Frutta Secca", "Pesce", "Carne", "Latticini e Uova",
    "Grassi e Oli", "Bevande", "Dolci e Snack", "Altri Alimenti",
)
REPARTI_PREDEFINITI = REPARTI[:7]

# Categorie che non sono prodotti da comprare
ESCLUSE = frozenset({"Piatti e ricette"})

PER_REPARTO = 3
PER_REPARTO_MAX = 6
VOCI_MAX = 40

# Preparazioni dopo una virgola, come le scrive il CREA: «Fagioli, Borlotti, freschi, cotti, bolliti».
# «Prosciutto cotto» resta: è il nome del prodotto
COTTO_RE = re.compile(
    r",\s*(cott[oaie]|bollit|arrost|fritt|al forno|alla griglia|grigliat|stufat|in umido|lessat|"
    r"al vapore|brasat|saltat)",
    re.IGNORECASE,
)

# Sotto questa porzione tipica (g) erbe aromatiche e condimenti: non si propongono
PORZIONE_MIN = 30

PUNTI_VERDI = 1                     # al massimo Basso
PUNTI_ACCETTABILI = 2               # al massimo Medio: niente rischi alti


def punti_rischi(alimento: Alimento) -> list[int] | None:
    """
    Punti (0-3) dei cinque rischi, o None se uno non è classificato.
    """
    livelli = [analisi.livello(alimento.get(campo)) for campo in analisi.CAMPI_RISCHIO]

    if any(liv is None for liv in livelli):
        return None

    return [liv["punti"] for liv in livelli if liv]


def verde(alimento: Alimento) -> bool:
    punti = punti_rischi(alimento)
    livello = analisi.livello_punteggio(alimento.get("punteggio"))
    return punti is not None and max(punti) <= PUNTI_VERDI and livello is analisi.LIVELLI[0]


def accettabile(alimento: Alimento) -> bool:
    """
    Si può proporre: rischi tutti classificati, nessuno Alto.
    """
    punti = punti_rischi(alimento)
    return punti is not None and max(punti) <= PUNTI_ACCETTABILI


def acquistabile(alimento: Alimento) -> bool:
    return (alimento.get("categoria") or "") not in ESCLUSE and not COTTO_RE.search(alimento.get("alimento") or "")


def proponibile(alimento: Alimento) -> bool:
    """
    Si propone in automatico: si compra, non è un condimento, nessun rischio alto.
    """
    porzione = alimento.get("porzione")
    return (
        acquistabile(alimento)
        and accettabile(alimento)
        and not (porzione is not None and 0 < porzione < PORZIONE_MIN)
    )


def tipo(alimento: Alimento) -> str:
    """
    Tipo di alimento per la varietà della lista: la prima parola del nome,
    senza accenti e maiuscole («Mele, golden» -> «mele»).
    """
    parole = (alimento.get("alimento") or "").replace(",", " ").split()
    prima = parole[0] if parole else ""
    return unicodedata.normalize("NFKD", prima).encode("ascii", "ignore").decode().casefold()


def _ordine(alimento: Alimento, campi_profilo: Sequence[str]) -> tuple[Any, ...]:
    per_te = profilo.punti_per_te(*(alimento.get(c) for c in campi_profilo)) if campi_profilo else 0
    return (
        per_te if per_te is not None else analisi.PUNTI_MAX + 1,
        -(alimento.get("punteggio") or 0),
        (alimento.get("alimento") or "").casefold(),
        alimento.get("id") or 0,
    )


def candidati(alimenti: Iterable[Alimento], reparto: str, condizioni: Sequence[str] = ()) -> list[Alimento]:
    """
    Alimenti proponibili per il reparto, in ordine: prima i verdi, poi gli
    altri senza rischi alti; un solo alimento per tipo.
    """
    campi = profilo.campi(condizioni)
    adatti = [a for a in alimenti if a.get("categoria") == reparto and proponibile(a)]
    adatti.sort(key=lambda a: (not verde(a), *_ordine(a, campi)))

    scelti = []
    visti: set[str] = set()

    for alimento in adatti:
        chiave = tipo(alimento)

        if chiave not in visti:
            visti.add(chiave)
            scelti.append(alimento)

    return scelti


def genera(
    alimenti: Sequence[Alimento],
    reparti: Iterable[str],
    per_reparto: int = PER_REPARTO,
    condizioni: Sequence[str] = (),
    seme: int | None = None,
) -> list[int]:
    """
    ID degli alimenti della lista, reparto per reparto nell'ordine di REPARTI.
    Con un seme gli alimenti verdi si scelgono a caso tra tutti quelli del
    reparto (per proporre una lista diversa), altrimenti i primi.
    """
    scelti_reparti = ordina_reparti(reparti)
    per_reparto = max(1, min(per_reparto, PER_REPARTO_MAX))
    lista: list[int] = []

    for reparto in scelti_reparti:
        proposti = candidati(alimenti, reparto, condizioni)
        verdi = [a for a in proposti if verde(a)]
        altri = [a for a in proposti if not verde(a)]

        if seme is not None and len(verdi) > per_reparto:
            estratti = random.Random(f"{seme}-{reparto}").sample(range(len(verdi)), per_reparto)
            verdi = [verdi[i] for i in sorted(estratti)]

        reparto_lista = (verdi + altri)[:per_reparto]
        lista.extend(a["id"] for a in reparto_lista)

    return lista[:VOCI_MAX]


def ordina_reparti(reparti: Iterable[str]) -> list[str]:
    """
    Reparti senza ripetizioni, nell'ordine di REPARTI (gli altri dopo, in ordine alfabetico).
    """
    unici = list(dict.fromkeys(r for r in reparti if r and r not in ESCLUSE))
    noti = [r for r in REPARTI if r in unici]
    return noti + sorted((r for r in unici if r not in REPARTI), key=str.casefold)


def sostituto(
    alimenti: Sequence[Alimento],
    voce: Alimento,
    presenti: Iterable[int],
    condizioni: Sequence[str] = (),
) -> Alimento | None:
    """
    Alimento con cui cambiare una voce della lista, dello stesso reparto e di
    un tipo che non è già nella lista: il verde successivo (dopo l'ultimo si
    ricomincia), quindi il primo verde per una voce non verde; senza verdi
    liberi, il candidato successivo non verde.
    """
    proposti = candidati(alimenti, voce.get("categoria") or "", condizioni)
    nella_lista = set(presenti) - {voce.get("id")}
    tipi_presenti = {tipo(a) for a in alimenti if a.get("id") in nella_lista}
    liberi = [a for a in proposti if a["id"] != voce.get("id") and tipo(a) not in tipi_presenti]

    if not liberi:
        return None

    posizione = next((i for i, a in enumerate(proposti) if a["id"] == voce.get("id")), -1)
    id_liberi = {a["id"] for a in liberi}
    successivi = [a for a in proposti[posizione + 1:] + proposti[:posizione + 1] if a["id"] in id_liberi]
    return next((a for a in successivi if verde(a)), successivi[0])


def raggruppa(voci: Iterable[Alimento]) -> list[tuple[str, list[Alimento]]]:
    """
    [(reparto, voci)] nell'ordine di REPARTI; nel reparto, l'ordine della lista.
    """
    gruppi: dict[str, list[Alimento]] = {}

    for voce in voci:
        gruppi.setdefault(voce.get("categoria") or "", []).append(voce)

    return [(reparto, gruppi[reparto]) for reparto in ordina_reparti(gruppi) if reparto in gruppi] + [
        (reparto, gruppi[reparto]) for reparto in gruppi if reparto in ESCLUSE
    ]


def testo(gruppi: Sequence[tuple[str, Sequence[Alimento]]], titolo: str, nome_reparto: Any = str) -> str:
    """
    Lista in testo semplice, un reparto per paragrafo («- Carciofi, crudi»).
    nome_reparto traduce il nome del reparto.
    """
    righe = [titolo, ""]

    for reparto, voci in gruppi:
        righe.append(nome_reparto(reparto))
        righe.extend(f"- {voce['alimento']}" for voce in voci)
        righe.append("")

    return "\n".join(righe).rstrip() + "\n"
