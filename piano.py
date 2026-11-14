"""
Piano settimanale dei pasti: pranzi e cene di una settimana con i pasti
pronti (pasti_pronti.py), scelti in modo che i rischi restino bilanciati.

Ogni pasto ha le sue portate (di base a pranzo primo e contorno, a cena
secondo e contorno), una porzione a testa. Nessun piatto si ripete nella
settimana, finché nella portata ce ne sono abbastanza.

Bilanciamento: tra due piani si preferisce, nell'ordine, quello con
1. con un profilo (profilo.py), meno piatti Alto per te, poi meno piatti non
   classificati per te;
2. meno volte lo stesso rischio Alto in due piatti dello stesso giorno;
3. la somma più bassa dei quadrati delle medie settimanali dei cinque
   rischi, pesate sulle Kcal della porzione come per il pasto
   (nutrienti.profilo_rischio). Il quadrato fa pesare un rischio che si
   accumula più di tanti rischi bassi; i rischi del profilo contano il doppio.
   Differenze fino a TOLLERANZA contano come pari.

Il piano si riempie un posto alla volta (prima le portate con più Kcal),
scegliendo a caso tra i piatti pari, così ogni piano è diverso; poi si
migliora cambiando un piatto alla volta finché nessun cambio abbassa il costo
più della tolleranza. I piatti scelti a mano restano fermi: dopo ogni scelta
gli altri si ribilanciano partendo dal piano com'è, con meno cambi possibile.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import analisi
import nutrienti
import pasti_pronti
import profilo
from lingue import N_

Piatto = dict[str, Any]
# (giorno da 0, pasto, portata)
Posto = tuple[int, str, str]
Costo = tuple[int, int, int, float]

GIORNI_MAX = 7
PERSONE_MAX = 8

PASTI = (
    ("pranzo", N_("Pranzo")),
    ("cena", N_("Cena")),
)
CHIAVI_PASTI = tuple(chiave for chiave, _etichetta in PASTI)
PORTATE_PREDEFINITE: dict[str, tuple[str, ...]] = {
    "pranzo": ("primo", "contorno"),
    "cena": ("secondo", "contorno"),
}

PESO_PROFILO = 2
# Sulla somma dei quadrati delle medie (0-3) dei rischi
TOLLERANZA = 0.05
PASSATE_MAX = 20


def posti(giorni: int, portate: Mapping[str, Iterable[str]]) -> list[Posto]:
    """
    Posti del piano in ordine: giorno, pasto (pranzo, cena), portata
    nell'ordine di pasti_pronti.PORTATE.
    """
    return [
        (giorno, pasto, portata)
        for giorno in range(max(0, min(giorni, GIORNI_MAX)))
        for pasto in CHIAVI_PASTI
        for portata in pasti_pronti.CHIAVI_PORTATE
        if portata in set(portate.get(pasto, ()))
    ]


def kcal_porzione(piatto: Mapping[str, Any]) -> float:
    return float(piatto.get("kcal") or 0) * nutrienti.porzione(dict(piatto)) / 100


# ---------------------------------------------------------------
# COSTO DI UN PIANO
# ---------------------------------------------------------------

@dataclass(frozen=True)
class _Dati:
    id: int
    portata: str
    nome: str
    peso: float
    punti: tuple[int | None, ...]
    per_te: int | None


def _dati(piatto: Mapping[str, Any], campi_profilo: Sequence[str]) -> _Dati:
    livelli = [analisi.livello(piatto.get(campo)) for campo in analisi.CAMPI_RISCHIO]
    return _Dati(
        id=int(piatto["id"]),
        portata=str(piatto.get("portata") or ""),
        nome=str(piatto.get("alimento") or "").casefold(),
        peso=kcal_porzione(piatto),
        punti=tuple(liv["punti"] if liv else None for liv in livelli),
        per_te=profilo.punti_per_te(*(piatto.get(c) for c in campi_profilo)) if campi_profilo else 0,
    )


class _Bilancio:
    """
    Somme dei rischi dei piatti nel piano, aggiornate a ogni piatto messo o tolto.
    """

    def __init__(self, campi_profilo: Sequence[str]) -> None:
        n = len(analisi.CAMPI_RISCHIO)
        self.somme = [0.0] * n
        self.pesi = [0.0] * n
        self.contati = [0] * n
        self.alti: dict[tuple[int, int], int] = {}
        self.alti_per_te = 0
        self.nc_per_te = 0
        self.con_profilo = bool(campi_profilo)
        self.pesi_rischi = [
            PESO_PROFILO if campo in campi_profilo else 1 for campo in analisi.CAMPI_RISCHIO
        ]

    def applica(self, dati: _Dati, giorno: int, segno: int) -> None:
        for r, punti in enumerate(dati.punti):
            if punti is None:
                continue

            if dati.peso > 0:
                self.somme[r] += segno * punti * dati.peso
                self.pesi[r] += segno * dati.peso
                self.contati[r] += segno

            if punti == analisi.PUNTI_MAX:
                self.alti[(giorno, r)] = self.alti.get((giorno, r), 0) + segno

        if self.con_profilo:
            if dati.per_te == analisi.PUNTI_MAX:
                self.alti_per_te += segno
            elif dati.per_te is None:
                self.nc_per_te += segno

    def costo(self) -> Costo:
        collisioni = sum(n - 1 for n in self.alti.values() if n > 1)
        quadrati = sum(
            peso * (somma / totale) ** 2
            for peso, somma, totale, contati in zip(self.pesi_rischi, self.somme, self.pesi, self.contati, strict=True)
            if contati > 0 and totale > 0
        )
        return (self.alti_per_te, self.nc_per_te, collisioni, round(quadrati, 6))

    def costo_con(self, giorno: int, togli: _Dati | None, metti: _Dati | None) -> Costo:
        if togli:
            self.applica(togli, giorno, -1)
        if metti:
            self.applica(metti, giorno, 1)

        costo = self.costo()

        if metti:
            self.applica(metti, giorno, -1)
        if togli:
            self.applica(togli, giorno, 1)

        return costo


def migliore(nuovo: Costo, attuale: Costo) -> bool:
    """
    nuovo è meglio di attuale oltre la tolleranza.
    """
    if nuovo[:3] != attuale[:3]:
        return nuovo[:3] < attuale[:3]

    return nuovo[3] < attuale[3] - TOLLERANZA


class _Piano:
    def __init__(
        self,
        piatti: Iterable[Mapping[str, Any]],
        posti_piano: Sequence[Posto],
        scelti: Sequence[int | None],
        condizioni: Sequence[str],
    ) -> None:
        campi = profilo.campi(condizioni)
        self.dati = {int(p["id"]): _dati(p, campi) for p in piatti}
        self.posti = list(posti_piano)
        self.per_portata: dict[str, list[_Dati]] = {}

        for dati in sorted(self.dati.values(), key=lambda d: (d.nome, d.id)):
            self.per_portata.setdefault(dati.portata, []).append(dati)

        self.bilancio = _Bilancio(campi)
        self.scelti: list[int | None] = [None] * len(self.posti)

        for indice, piatto_id in enumerate(list(scelti)[:len(self.posti)]):
            if piatto_id in self.dati and self.dati[piatto_id].portata == self.posti[indice][2]:
                self.metti(indice, piatto_id)

    def metti(self, indice: int, piatto_id: int | None) -> None:
        giorno = self.posti[indice][0]
        attuale = self.scelti[indice]

        if attuale is not None:
            self.bilancio.applica(self.dati[attuale], giorno, -1)
        if piatto_id is not None:
            self.bilancio.applica(self.dati[piatto_id], giorno, 1)

        self.scelti[indice] = piatto_id

    def candidati(self, indice: int) -> list[_Dati]:
        """
        Piatti della portata del posto non già altrove nel piano; se sono
        tutti nel piano, tutti quelli della portata.
        """
        portata = self.posti[indice][2]
        altrove = {p for i, p in enumerate(self.scelti) if i != indice and p is not None}
        tutti = self.per_portata.get(portata, [])
        return [d for d in tutti if d.id not in altrove] or tutti

    def costi(self, indice: int) -> list[tuple[Costo, _Dati]]:
        giorno = self.posti[indice][0]
        attuale = self.scelti[indice]
        togli = self.dati[attuale] if attuale is not None else None
        return [(self.bilancio.costo_con(giorno, togli, d), d) for d in self.candidati(indice)]

    def riempi(self, indici: Iterable[int], rng: random.Random | None) -> None:
        """
        Riempie i posti indicati uno alla volta: prima le portate con più
        Kcal, scegliendo tra i piatti pari a caso (senza rng il primo).
        """
        def kcal_medie(indice: int) -> float:
            piatti = self.per_portata.get(self.posti[indice][2], [])
            return -sum(d.peso for d in piatti) / len(piatti) if piatti else 0.0

        ordine = list(indici)

        if rng:
            rng.shuffle(ordine)

        for indice in sorted(ordine, key=kcal_medie):
            costi = self.costi(indice)

            if not costi:
                continue

            minimo = min(costo for costo, _d in costi)
            pari = [d for costo, d in costi if costo[:3] == minimo[:3] and costo[3] <= minimo[3] + TOLLERANZA]
            scelto = rng.choice(pari) if rng else min(pari, key=lambda d: (d.nome, d.id))
            self.metti(indice, scelto.id)

    def migliora(self, indici: Sequence[int]) -> None:
        """
        Cambia un piatto alla volta, finché nessun cambio abbassa il costo
        più della tolleranza.
        """
        for _passata in range(PASSATE_MAX):
            cambiato = False

            for indice in indici:
                attuale = self.bilancio.costo()
                costo, dati = min(self.costi(indice), key=lambda c: (c[0], c[1].nome, c[1].id), default=(None, None))

                if costo is not None and dati is not None and migliore(costo, attuale):
                    self.metti(indice, dati.id)
                    cambiato = True

            if not cambiato:
                return


# ---------------------------------------------------------------
# GENERAZIONE E MODIFICHE
# ---------------------------------------------------------------

def _fissi_validi(scelti: Sequence[int | None], fissi: Iterable[int]) -> set[int]:
    return {i for i in fissi if 0 <= i < len(scelti) and scelti[i] is not None}


def genera(
    piatti: Sequence[Mapping[str, Any]],
    posti_piano: Sequence[Posto],
    condizioni: Sequence[str] = (),
    seme: int | None = None,
) -> list[int | None]:
    """
    ID dei piatti del piano, uno per posto (None se la portata non ha
    piatti). Con un seme la scelta tra i piatti pari è a caso ma ripetibile.
    """
    piano = _Piano(piatti, posti_piano, [], condizioni)
    rng = random.Random(seme) if seme is not None else None
    tutti = list(range(len(piano.posti)))
    piano.riempi(tutti, rng)
    piano.migliora(tutti)
    return piano.scelti


def ribilancia(
    piatti: Sequence[Mapping[str, Any]],
    posti_piano: Sequence[Posto],
    scelti: Sequence[int | None],
    fissi: Iterable[int] = (),
    condizioni: Sequence[str] = (),
) -> list[int | None]:
    """
    Piano ribilanciato attorno ai posti fissi (indici), partendo da quello
    attuale: si riempiono i posti vuoti e si cambia solo ciò che migliora il
    bilanciamento oltre la tolleranza.
    """
    piano = _Piano(piatti, posti_piano, scelti, condizioni)
    bloccati = _fissi_validi(piano.scelti, fissi)
    liberi = [i for i in range(len(piano.posti)) if i not in bloccati]

    # Un piatto scelto a mano che era già altrove: l'altro posto (libero) si rifà
    visti = {piano.scelti[i] for i in bloccati}

    for indice in liberi:
        if piano.scelti[indice] in visti:
            piano.metti(indice, None)
        else:
            visti.add(piano.scelti[indice])

    piano.riempi([i for i in liberi if piano.scelti[i] is None], None)
    piano.migliora(liberi)
    return piano.scelti


def alternative(
    piatti: Sequence[Mapping[str, Any]],
    posti_piano: Sequence[Posto],
    scelti: Sequence[int | None],
    indice: int,
    condizioni: Sequence[str] = (),
) -> list[int]:
    """
    ID dei piatti che possono andare nel posto, dal più bilanciato con il
    resto del piano; esclusi quelli già in un altro posto.
    """
    piano = _Piano(piatti, posti_piano, scelti, condizioni)

    if not 0 <= indice < len(piano.posti):
        return []

    return [d.id for _costo, d in sorted(piano.costi(indice), key=lambda c: (c[0], c[1].nome, c[1].id))]


def successivo(
    piatti: Sequence[Mapping[str, Any]],
    posti_piano: Sequence[Posto],
    scelti: Sequence[int | None],
    indice: int,
    condizioni: Sequence[str] = (),
) -> int | None:
    """
    Piatto che segue quello del posto tra le alternative (dopo l'ultima si
    ricomincia): premendo «cambia» più volte si vedono tutte, dalla più
    bilanciata. None se non ce ne sono altre.
    """
    ordine = alternative(piatti, posti_piano, scelti, indice, condizioni)
    attuale = scelti[indice] if 0 <= indice < len(scelti) else None
    altri = [i for i in ordine if i != attuale]

    if not altri:
        return None

    if attuale not in ordine:
        return altri[0]

    posizione = ordine.index(attuale)
    return (ordine[posizione + 1:] + ordine[:posizione])[0]
