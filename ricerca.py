"""
Ricerca e consultazione della tabella: ricerca per nome tollerante
(parziale, senza accenti, singolare e plurale, errori di battitura) e
paginazione.

Ogni parola cercata deve trovarsi nel nome, in uno di questi modi:
1. uguale, singolare/plurale italiano (mela → mele, pesca → pesche),
   inizio di parola (mozz → mozzarella) o parte di parola (zarell);
2. parola simile, con uno o due errori di battitura (mozarela → mozzarella);
3. inizio simile di una parola più lunga (mozar → mozzarella).
Per ogni parola cercata vale il primo modo che trova qualcosa nel
database: così «pesca» non trova il pesce e «succo mela» non trova
nomi a caso solo perché le parole si somigliano.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

LUNGHEZZA_MASSIMA = 100

# Singolare e plurale: (desinenza, alternative)
DESINENZE = (
    ("cia", ("ce", "cie")),
    ("gia", ("ge", "gie")),
    ("ca", ("che",)),
    ("ga", ("ghe",)),
    ("co", ("chi", "ci")),
    ("go", ("ghi", "gi")),
    ("che", ("ca",)),
    ("ghe", ("ga",)),
    ("chi", ("co",)),
    ("ghi", ("go",)),
    ("a", ("e",)),
    ("o", ("i", "a")),
    ("e", ("i", "a")),
    ("i", ("o", "e")),
)

# Punteggi delle corrispondenze di una parola (conta solo l'ordine)
UGUALE = 1.0
VARIANTE = 0.95
INIZIO = 0.6  # + fino a 0.3 secondo quanta parte della parola copre
DENTRO = 0.5
SIMILE = 0.45
SIMILE_INIZIO = 0.3


def normalizza(testo: object) -> str:
    """
    Minuscolo, senza accenti né punteggiatura, spazi singoli.
    """
    ascii_ = unicodedata.normalize("NFKD", str(testo or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_.lower()).split())


@lru_cache(maxsize=4096)
def _parole_nome(nome: str) -> tuple[str, tuple[str, ...]]:
    normale = normalizza(nome)
    return normale, tuple(normale.split())


def varianti(parola: str) -> set[str]:
    """
    Singolare e plurale italiani della parola (lei esclusa), per parole di
    almeno 4 lettere: mela → mele, pesca → pesche, pomodori → pomodoro.
    """
    if len(parola) < 4:
        return set()

    # solo la desinenza più lunga: pesca → pesche, non pesce
    for desinenza, alternative in DESINENZE:
        if parola.endswith(desinenza):
            radice = parola[: -len(desinenza)]
            return {radice + alternativa for alternativa in alternative} - {parola}

    return set()


def distanza(a: str, b: str, massimo: int) -> int:
    """
    Distanza di Damerau-Levenshtein (inversioni di due lettere comprese),
    oppure massimo + 1 appena si capisce che la supera.
    """
    if abs(len(a) - len(b)) > massimo:
        return massimo + 1

    precedente2: list[int] = []
    precedente = list(range(len(b) + 1))

    for i, ca in enumerate(a, 1):
        corrente = [i] + [0] * len(b)

        for j, cb in enumerate(b, 1):
            costo = 0 if ca == cb else 1
            corrente[j] = min(precedente[j] + 1, corrente[j - 1] + 1, precedente[j - 1] + costo)

            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                corrente[j] = min(corrente[j], precedente2[j - 2] + 1)

        if min(corrente) > massimo:
            return massimo + 1

        precedente2, precedente = precedente, corrente

    return precedente[-1]


def _tolleranza(parola: str) -> int:
    """
    Errori ammessi su una parola intera: nessuno fino a 3 lettere, due da 7.
    """
    return 0 if len(parola) < 4 else 1 if len(parola) < 7 else 2


def _tolleranza_inizio(parola: str) -> int:
    """
    Errori ammessi sull'inizio di una parola più lunga: serve una parola cercata più lunga.
    """
    return 0 if len(parola) < 5 else 1 if len(parola) < 8 else 2


# Modi in cui una parola cercata può trovarsi nel nome
ESATTA, SIMILE_PAROLA, SIMILE_INIZIO_PAROLA = 1, 2, 3


def _corrispondenza(cercata: str, parola: str, varianti_cercata: set[str], modo: int) -> float:
    if parola == cercata:
        return UGUALE

    if parola in varianti_cercata:
        return VARIANTE

    if parola.startswith(cercata):
        return INIZIO + 0.3 * len(cercata) / len(parola)

    if len(cercata) >= 3 and cercata in parola:
        return DENTRO

    if modo >= SIMILE_PAROLA:
        tolleranza = _tolleranza(cercata)

        if tolleranza:
            d = distanza(cercata, parola, tolleranza)

            if d <= tolleranza:
                return SIMILE - 0.05 * (d - 1)

    if modo >= SIMILE_INIZIO_PAROLA:
        tolleranza = _tolleranza_inizio(cercata)

        if tolleranza and len(parola) > len(cercata):
            for lunghezza in range(len(cercata) - 1, len(cercata) + 2):
                if distanza(cercata, parola[:lunghezza], tolleranza) <= tolleranza:
                    return SIMILE_INIZIO

    return 0.0


def _migliore(cercata: str, parole: tuple[str, ...], modo: int, prima: bool) -> float:
    varianti_cercata = varianti(cercata)
    migliore = 0.0

    for j, parola in enumerate(parole):
        valore = _corrispondenza(cercata, parola, varianti_cercata, modo)

        # la prima parola cercata che è anche la prima del nome conta di più
        if valore and prima and j == 0:
            valore += 0.2

        migliore = max(migliore, valore)

    return migliore


def punteggio(nome: str, cercato: str, modi: list[int] | None = None) -> float | None:
    """
    Quanto il nome corrisponde al testo cercato (già normalizzato), o None
    se una delle parole cercate non c'è. modi: per ogni parola cercata, fino
    a quale modo accettarla (predefinito: solo corrispondenze esatte).
    """
    normale, parole = _parole_nome(nome)
    cercate = cercato.split()

    if not cercate:
        return None

    punti = []

    for i, cercata in enumerate(cercate):
        modo = modi[i] if modi else ESATTA
        migliore = _migliore(cercata, parole, modo, i == 0)

        if not migliore:
            return None

        punti.append(migliore)

    risultato = sum(punti) / len(punti)

    # frase intera, solo se finisce a fine parola (mela non vale per melanzane);
    # «contenuta» solo per più parole, altrimenti la pasta all'uovo
    # verrebbe prima delle uova
    if normale == cercato:
        risultato += 2
    elif normale.startswith(cercato + " "):
        risultato += 1
    elif len(cercate) > 1 and f" {cercato} " in f" {normale} ":
        risultato += 0.5

    # a parità, prima i nomi più corti (più vicini a quanto cercato)
    return risultato - 0.001 * len(normale)


def _modo_necessario(cercata: str, nomi: list[tuple[str, ...]]) -> int | None:
    """
    Il primo modo con cui la parola cercata si trova in almeno un nome.
    """
    for modo in (ESATTA, SIMILE_PAROLA, SIMILE_INIZIO_PAROLA):
        if any(_migliore(cercata, parole, modo, False) for parole in nomi):
            return modo

    return None


def cerca(alimenti: Iterable[dict[str, Any]], testo: str) -> list[tuple[dict[str, Any], float]]:
    """
    (alimento, punteggio) degli alimenti il cui nome corrisponde al testo,
    nell'ordine ricevuto.
    """
    cercato = normalizza(testo[:LUNGHEZZA_MASSIMA])
    elenco = list(alimenti)

    if not cercato:
        return [(a, 0.0) for a in elenco]

    nomi = [_parole_nome(a.get("alimento") or "")[1] for a in elenco]
    modi = []

    for cercata in cercato.split():
        modo = _modo_necessario(cercata, nomi)

        if modo is None:
            return []

        modi.append(modo)

    trovati = []

    for alimento in elenco:
        valore = punteggio(alimento.get("alimento") or "", cercato, modi)

        if valore is not None:
            trovati.append((alimento, valore))

    return trovati


# ---------------------------------------------------------------
# PAGINAZIONE
# ---------------------------------------------------------------

PER_PAGINA = (25, 50, 100)
PER_PAGINA_PREDEFINITO = 50
TUTTI = "tutti"


def leggi_per_pagina(testo: object) -> int | None:
    """
    Righe per pagina scelte (25, 50, 100), None per «tutti»; altrimenti il predefinito.
    """
    testo = str(testo or "").strip().lower()

    if testo == TUTTI:
        return None

    return int(testo) if testo.isdigit() and int(testo) in PER_PAGINA else PER_PAGINA_PREDEFINITO


def leggi_pagina(testo: object) -> int:
    testo = str(testo or "").strip()
    return int(testo) if testo.isdigit() and 0 < int(testo) < 100_000 else 1


def pagina(totale: int, numero: int, per_pagina: int | None) -> dict[str, Any]:
    """
    Pagina richiesta (riportata nell'intervallo valido) con gli indici
    delle righe e i numeri di pagina da mostrare: la prima, l'ultima e le
    due vicine alla corrente, con None al posto dei salti.
    """
    if per_pagina is None or totale <= per_pagina:
        return {
            "numero": 1, "pagine": 1, "inizio": 0, "fine": totale,
            "per_pagina": per_pagina, "numeri": [1], "totale": totale,
        }

    pagine = math.ceil(totale / per_pagina)
    numero = min(max(numero, 1), pagine)
    inizio = (numero - 1) * per_pagina

    vicine = {1, pagine, *range(numero - 2, numero + 3)}
    numeri: list[int | None] = []

    for n in sorted(p for p in vicine if 1 <= p <= pagine):
        if numeri and n - (numeri[-1] or 0) == 2:
            numeri.append(n - 1)  # un solo numero saltato: meglio mostrarlo
        elif numeri and n - (numeri[-1] or 0) > 2:
            numeri.append(None)
        numeri.append(n)

    return {
        "numero": numero,
        "pagine": pagine,
        "inizio": inizio,
        "fine": min(inizio + per_pagina, totale),
        "per_pagina": per_pagina,
        "numeri": numeri,
        "totale": totale,
    }
