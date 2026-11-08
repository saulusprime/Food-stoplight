"""
Alimenti dalle Tabelle di composizione degli alimenti del CREA
(Centro di ricerca Alimenti e Nutrizione, aggiornamento 2019):
https://www.alimentinutrizione.it/tabelle-nutrizionali

Il sito non ha API né file da scaricare: si leggono le schede HTML, una
per alimento, identificate dal codice CREA (es. 007000 = Albicocche,
fresche). I dati si possono riprodurre citando la fonte originale, come
chiede il CREA: ogni alimento importato porta fonte, codice e link alla scheda.

I valori sono per 100 g di parte edibile. I grassi saturi sono pubblicati
come percentuale degli acidi grassi totali: i grammi si stimano con i
fattori di conversione lipidi -> acidi grassi della FAO/INFOODS.
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import requests

URL_BASE = "https://www.alimentinutrizione.it"
URL_INDICE = URL_BASE + "/tabelle-nutrizionali/ricerca-per-ordine-alfabetico"
URL_SCHEDA = URL_BASE + "/tabelle-nutrizionali/{codice}"
FONTE = "CREA, Tabelle di composizione degli alimenti (2019)"

CODICE_RE = re.compile(r"^[0-9A-Z]{6}$")
INTESTAZIONI_HTTP = {"User-Agent": "Food-stoplight/1.0 (+https://github.com/saulusprime/Food-stoplight)"}

# Pausa tra due richieste al sito, per non sovraccaricarlo
PAUSA_SECONDI = 1.0

# Nutrienti della scheda CREA -> campi dell'app (stesse unità)
NUTRIENTI = {
    "Energia (kcal)": "kcal",
    "Proteine (g)": "proteine",
    "Lipidi (g)": "grassi",
    "Colesterolo (mg)": "colesterolo",
    "Carboidrati disponibili (g)": "carboidrati",
    "Zuccheri solubili (g)": "zuccheri",
    "Fruttosio (g)": "fruttosio",
    "Glucosio (g)": "glucosio",
    "Lattosio (g)": "lattosio",
    "Alcool (g)": "alcol",
    "Fibra totale (g)": "fibre",
    "Sodio (mg)": "sodio",
    "Potassio (mg)": "potassio",
    "Calcio (mg)": "calcio",
    "Magnesio (mg)": "magnesio",
    "Ferro (mg)": "ferro",
    "Zinco (mg)": "zinco",
    "Vitamina C (mg)": "vitamina_c",
    "Vitamina A retinolo equivalente (μg)": "vitamina_a",
    "Vitamina D (μg)": "vitamina_d",
    "Vitamina E (mg)": "vitamina_e",
    "Vitamina B12 (μg)": "vitamina_b12",
    "Folati (μg)": "folati",
}

# Altri valori letti dalla scheda, usati per le classificazioni (FODMAP)
ALTRI = {
    "Acidi grassi Saturi (%)": "saturi_percento",
    "Fruttoligosaccaridi (g)": "fos",
    "Raffinosio (g)": "raffinosio",
}

# Categorie CREA -> categorie dell'app
CATEGORIE = {
    "Bevande alcoliche": "Bevande",
    "Bevande analcoliche": "Bevande",
    "Carni fresche": "Carne",
    "Carni trasformate e conservate": "Carne",
    "Fast-food a base di carne": "Carne",
    "Frattaglie": "Carne",
    "Cereali e derivati": "Cereali",
    "Dolci": "Dolci e Snack",
    "Formaggi e latticini": "Latticini e Uova",
    "Latte e yogurt": "Latticini e Uova",
    "Uova": "Latticini e Uova",
    "Frutta": "Frutta",
    "Frutta secca a guscio e semi oleaginosi": "Legumi/Frutta Secca",
    "Legumi": "Legumi/Frutta Secca",
    "Oli e grassi": "Grassi e Oli",
    "Prodotti della pesca": "Pesce",
    "Verdure e ortaggi": "Verdura",
    "Ricette Italiane": "Piatti e ricette",
    "Alimenti Etnici": "Piatti e ricette",
}

# Alimenti di origine animale (non latticini): niente fruttosio né lattosio
CATEGORIE_ANIMALI = {
    "Carni fresche", "Carni trasformate e conservate", "Frattaglie", "Prodotti della pesca", "Uova",
}

# Latte e derivati: senza zuccheri aggiunti, gli zuccheri sono lattosio
CATEGORIE_LATTICINI = {"Latte e yogurt", "Formaggi e latticini"}

CATEGORIA_PREDEFINITA = "Altri Alimenti"

# Fattori lipidi -> acidi grassi totali (FAO/INFOODS, Guidelines for converting
# units, denominators and expressions, 2012): acidi grassi = lipidi × fattore
FATTORI_ACIDI_GRASSI = {
    "latte": 0.945,
    "uova": 0.83,
    "oli": 0.956,
    "frutta_verdura": 0.80,
    "frutta_secca": 0.956,
    "carne_magra": 0.916,
    "carne_grassa": 0.953,
    "pollame": 0.945,
    "pesce_magro": 0.70,
    "pesce_grasso": 0.90,
    "cereali": 0.72,
    "misto": 0.90,
}

POLLAME_RE = re.compile(r"\b(pollo|tacchino|faraona|gallina|cappone|anatra|oca|piccione|quaglia|fagiano)", re.I)


class ErroreCrea(Exception):
    pass


# ---------------------------------------------------------------
# LETTURA DELLE PAGINE
# ---------------------------------------------------------------

def _testo(frammento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", frammento))).strip()


def leggi_indice(pagina: str) -> dict[str, str]:
    """
    {codice: nome} dalla pagina "Ricerca per ordine alfabetico".
    """
    voci = {}

    for codice, nome in re.findall(r'href="/tabelle-nutrizionali/([0-9A-Z]{6})"[^>]*>(.*?)</a>', pagina, re.S):
        voci[codice] = _testo(nome).strip('"|')

    return voci


def leggi_valore(testo: str) -> float | None:
    """
    Valore di una cella: "tr" (tracce) vale 0, "" o simboli None.
    """
    testo = testo.strip().replace(",", ".")

    if testo.lower() in ("tr", "tracce"):
        return 0.0

    try:
        return float(testo)
    except ValueError:
        return None


def leggi_scheda(pagina: str, codice: str) -> dict[str, Any]:
    """
    Dati di una scheda alimento: nome, categoria CREA, nome inglese,
    porzione, parte edibile e {etichetta CREA: valore per 100 g}.
    """
    testo = "|" + "|".join(_testo(p) for p in re.split(r"<[^>]+>", pagina) if _testo(p)) + "|"

    def dopo(etichetta: str) -> str | None:
        trovato = re.search(r"\|" + re.escape(etichetta) + r"\|([^|]+)\|", testo)
        return trovato.group(1).strip() if trovato else None

    titolo = re.search(r'<h1 class="article-title"[^>]*>(.*?)</h1>', pagina, re.S)
    nome = _testo(titolo.group(1)) if titolo else None
    categoria = dopo("Categoria")

    if not nome or not categoria or dopo("Codice Alimento") != codice:
        raise ErroreCrea(f"Scheda CREA {codice} non riconosciuta")

    valori: dict[str, float | None] = {}

    for riga in re.findall(r"<tr[^>]*>(.*?)</tr>", pagina, re.S):
        celle = [_testo(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", riga, re.S)]

        if len(celle) > 2 and (celle[0] in NUTRIENTI or celle[0] in ALTRI):
            valori.setdefault(celle[0], leggi_valore(celle[2]))

    porzione = re.match(r"(\d+(?:[.,]\d+)?)\s*g", dopo("Porzione") or "")
    edibile = re.match(r"(\d+(?:[.,]\d+)?)", dopo("Parte Edibile") or "")
    resa = re.match(r"(\d+(?:[.,]\d+)?)", dopo("Variazione Peso (Y.F.)") or "")

    return {
        "codice": codice,
        "nome": nome,
        "categoria": categoria,
        "nome_inglese": dopo("English Name"),
        "nome_scientifico": dopo("Nome Scientifico"),
        "porzione": float(porzione.group(1).replace(",", ".")) if porzione else None,
        "parte_edibile": float(edibile.group(1).replace(",", ".")) if edibile else None,
        "valori": valori,
        "ingredienti": leggi_ingredienti(pagina),
        "resa": float(resa.group(1).replace(",", ".")) if resa else None,
    }


INGREDIENTE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(g|ml|kg|l)$", re.IGNORECASE)


def leggi_ingredienti(pagina: str) -> list[dict[str, Any]]:
    """
    Ingredienti di una ricetta CREA: [{"nome", "quantita", "unita"}], con le
    quantità in g o ml (kg e l convertiti). Le righe senza quantità (es.
    «PER 10 PERSONE», «q.b.») restano fuori.
    """
    blocco = re.search(r'<td class="ingredienti">(.*?)</table>', pagina, re.S)

    if not blocco:
        return []

    ingredienti = []

    for riga in re.findall(r'<tr class="corporicetta">(.*?)</tr>', blocco.group(1), re.S):
        celle = [_testo(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", riga, re.S)]

        if len(celle) < 2:
            continue

        quantita = INGREDIENTE_RE.match(celle[1].strip())

        if not celle[0] or not quantita:
            continue

        valore = float(quantita.group(1).replace(",", "."))
        unita = quantita.group(2).lower()

        if unita in ("kg", "l"):
            valore *= 1000
            unita = "g" if unita == "kg" else "ml"

        ingredienti.append({"nome": celle[0], "quantita": valore, "unita": unita})

    return ingredienti


# ---------------------------------------------------------------
# DOWNLOAD
# ---------------------------------------------------------------

def _scarica(url: str, timeout: float) -> str:
    try:
        risposta = requests.get(url, headers=INTESTAZIONI_HTTP, timeout=timeout)
    except requests.RequestException as exc:
        raise ErroreCrea(f"Sito CREA non raggiungibile: {exc}") from None

    if risposta.status_code == 404:
        raise ErroreCrea(f"Pagina CREA non trovata: {url}")

    if risposta.status_code != 200:
        raise ErroreCrea(f"Il sito CREA ha risposto {risposta.status_code} per {url}")

    risposta.encoding = "utf-8"
    return risposta.text


def scarica_indice(timeout: float = 30) -> dict[str, str]:
    voci = leggi_indice(_scarica(URL_INDICE, timeout))

    if not voci:
        raise ErroreCrea("Indice CREA vuoto: la pagina potrebbe essere cambiata")

    return voci


def scarica_schede(
    codici: Iterable[str],
    cache: Path | None = None,
    timeout: float = 30,
    avanzamento: Callable[[int, int], object] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    (schede lette, errori). Con cache le pagine scaricate si salvano in una
    cartella e non si riscaricano; tra due richieste c'è una pausa.
    """
    codici = list(dict.fromkeys(codici))
    schede, errori = [], []

    for numero, codice in enumerate(codici, start=1):
        if not CODICE_RE.match(codice):
            errori.append(f"{codice}: codice CREA non valido")
            continue

        file_cache = cache / f"{codice}.html" if cache else None

        try:
            if file_cache and file_cache.is_file() and file_cache.stat().st_size:
                pagina = file_cache.read_text(encoding="utf-8")
            else:
                pagina = _scarica(URL_SCHEDA.format(codice=codice), timeout)

                if file_cache:
                    file_cache.parent.mkdir(parents=True, exist_ok=True)
                    file_cache.write_text(pagina, encoding="utf-8")

                if numero < len(codici):
                    time.sleep(PAUSA_SECONDI)

            schede.append(leggi_scheda(pagina, codice))
        except ErroreCrea as exc:
            errori.append(str(exc))

        if avanzamento:
            avanzamento(numero, len(codici))

    return schede, errori


# ---------------------------------------------------------------
# CONVERSIONE NEI CAMPI DELL'APP
# ---------------------------------------------------------------

BEVANDE_RE = re.compile(r"^(?:aranciata|chinotto|gassosa|succo)|\bbevanda\b", re.I)


def categoria_app(categoria_crea: str, nome: str = "") -> str:
    """
    Categoria dell'app; tra i "Prodotti vari" del CREA le bevande vanno in Bevande.
    """
    if categoria_crea == "Prodotti vari" and BEVANDE_RE.search(nome):
        return "Bevande"

    return CATEGORIE.get(categoria_crea, CATEGORIA_PREDEFINITA)


def fattore_acidi_grassi(scheda: dict[str, Any]) -> float:
    categoria = scheda["categoria"]
    nome = scheda["nome"]
    lipidi = scheda["valori"].get("Lipidi (g)") or 0

    if categoria in ("Formaggi e latticini", "Latte e yogurt") or re.search(r"\b(burro|panna)\b", nome, re.I):
        return FATTORI_ACIDI_GRASSI["latte"]

    if categoria == "Uova":
        return FATTORI_ACIDI_GRASSI["uova"]

    if categoria == "Oli e grassi":
        return FATTORI_ACIDI_GRASSI["oli"]

    if categoria == "Frutta secca a guscio e semi oleaginosi" or re.search(r"\b(avocado|olive)\b", nome, re.I):
        return FATTORI_ACIDI_GRASSI["frutta_secca"]

    if categoria in ("Frutta", "Verdure e ortaggi", "Legumi"):
        return FATTORI_ACIDI_GRASSI["frutta_verdura"]

    if categoria in ("Carni fresche", "Frattaglie", "Carni trasformate e conservate"):
        if POLLAME_RE.search(nome):
            return FATTORI_ACIDI_GRASSI["pollame"]

        return FATTORI_ACIDI_GRASSI["carne_grassa" if lipidi >= 10 else "carne_magra"]

    if categoria == "Prodotti della pesca":
        return FATTORI_ACIDI_GRASSI["pesce_grasso" if lipidi >= 5 else "pesce_magro"]

    if categoria == "Cereali e derivati" and lipidi < 5:
        return FATTORI_ACIDI_GRASSI["cereali"]

    return FATTORI_ACIDI_GRASSI["misto"]


def valori(scheda: dict[str, Any]) -> dict[str, Any]:
    """
    Campi dell'app per una scheda CREA (solo i valori presenti nella scheda;
    i grassi saturi stimati dalla percentuale degli acidi grassi).
    """
    letti = scheda["valori"]
    risultato: dict[str, Any] = {
        campo: letti[etichetta] for etichetta, campo in NUTRIENTI.items() if letti.get(etichetta) is not None
    }

    percentuale = letti.get("Acidi grassi Saturi (%)")
    lipidi = letti.get("Lipidi (g)")

    if lipidi is not None and lipidi <= 0:
        risultato["grassi_saturi"] = 0.0
    elif percentuale is not None and lipidi is not None:
        risultato["grassi_saturi"] = round(lipidi * fattore_acidi_grassi(scheda) * percentuale / 100, 2)

    risultato.update({
        "alimento": scheda["nome"],
        "categoria": categoria_app(scheda["categoria"], scheda["nome"]),
        "codice_crea": scheda["codice"],
        "porzione": scheda.get("porzione"),
        "fonte_nutrienti": FONTE,
        "url_fonte": URL_SCHEDA.format(codice=scheda["codice"]),
    })

    return risultato
