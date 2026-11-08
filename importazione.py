"""
Import di alimenti da file CSV o Excel (.xlsx), in tre passaggi:

1. leggi_file()  legge il file, riconosce le colonne e normalizza ogni riga
                 (numeri con virgola o punto, livelli di rischio, nomi);
2. pianifica()   confronta le righe con il database e decide per ciascuna
                 nuovo / aggiornato / invariato / unito / saltato,
                 secondo la modalità scelta: è ciò che mostra l'anteprima;
3. applica()     scrive il piano nel database (una sola transazione).
"""

from __future__ import annotations

import csv
import io
import math
import re
import sqlite3
import zipfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time
from typing import Any

from flask_babel import gettext
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

import analisi
import calcoli
import crea
import nutrienti
import openfoodfacts
import rischi
import usda
from calcoli import arrotonda, leggi_numero  # noqa: F401  (usati anche da altri moduli)
from lingue import N_, traduci

# Limite di righe di dati per file (oltre si chiede di dividerlo)
MAX_RIGHE = 20000

# Righe iniziali in cui cercare l'intestazione (sopra può esserci un titolo)
RIGHE_RICERCA_INTESTAZIONE = 10

# Dopo tante righe vuote consecutive il foglio Excel si considera finito
RIGHE_VUOTE_FINE_FOGLIO = 1000

CAMPI_TESTO = ("alimento", "categoria")
CAMPI_NUMERICI = ("kcal", "tef_kcal", "tef_percent", "kcal_nette", "fruttosio", "fibre")

# Colonne scritte nella tabella alimenti (rapporto è sempre ricalcolato)
CAMPI = (
    *CAMPI_TESTO,
    *CAMPI_NUMERICI,
    "rapporto",
    *analisi.CAMPI_RISCHIO,
    # Dati nutrizionali: None = non disponibile, anche dopo l'import
    *nutrienti.CAMPI_NULLABILI,
)

# Il fruttosio può mancare (None = non disponibile), e con lui il rapporto F/F
CAMPI_NULLABILI = set(nutrienti.CAMPI_NULLABILI) | {"fruttosio", "rapporto"}

# Campi energia e fibre: vuoti valgono 0
CAMPI_ZERO = tuple(c for c in CAMPI_NUMERICI if c != "fruttosio")

# Etichette dei campi (in italiano: l'export le usa così; l'interfaccia le traduce)
ETICHETTE = {
    "id": N_("ID"),
    "alimento": N_("Alimento"),
    "categoria": N_("Categoria"),
    "kcal": N_("Kcal"),
    "tef_kcal": N_("TEF (Kcal)"),
    "tef_percent": N_("TEF (%)"),
    "kcal_nette": N_("Kcal nette"),
    "fruttosio": N_("Fruttosio (g)"),
    "fibre": N_("Fibre (g)"),
    "rapporto": N_("Rapporto F/F"),
    "rischio_diabete": N_("Rischio diabete"),
    "rischio_colesterolo": N_("Rischio colesterolo"),
    "rischio_malassorbimento": N_("Rischio malassorbimento"),
    "rischio_metabolico": N_("Rischio metabolico"),
    "rischio_tumorale": N_("Rischio tumorale"),
    **nutrienti.ETICHETTE,
}

MODALITA = {
    "aggiorna": {
        "titolo": N_("Aggiorna o aggiungi"),
        "descrizione": N_(
            "Le righe già presenti (stesso ID, oppure stesso nome e categoria) vengono "
            "aggiornate con i valori non vuoti del file; le altre vengono aggiunte."
        ),
    },
    "aggiungi": {
        "titolo": N_("Aggiungi tutte come nuove"),
        "descrizione": N_("Ogni riga diventa un nuovo alimento, anche se esiste già."),
    },
    "sostituisci": {
        "titolo": N_("Sostituisci l'intera tabella"),
        "descrizione": N_("Elimina tutti gli alimenti attuali e inserisce quelli del file."),
    },
}

MODALITA_PREDEFINITA = "aggiorna"

# Valori da trattare come cella vuota
VALORI_ASSENTI = calcoli.VALORI_ASSENTI


class ErroreImport(Exception):
    """
    Problema del file da mostrare all'utente così com'è.
    """


# (numero di riga nel file, celle come testo)
Riga = tuple[int, list[str]]

# Voce del piano di import: {riga, azione, valori, id, modificati, precedente, avvisi}
Voce = dict[str, Any]


# ---------------------------------------------------------------
# RICONOSCIMENTO DEL FILE E DELLE COLONNE
# ---------------------------------------------------------------

def normalize_header(value: object) -> str:
    """
    Normalizza l'intestazione di una colonna.
    Esempio: "Fruttosio (g/100g)" -> "fruttosio g 100g"
    """
    value = str(value or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def campo_colonna(intestazione: object) -> str | None:
    """
    Campo del database corrispondente a un'intestazione, oppure None.
    """
    norm = normalize_header(intestazione)
    originale = str(intestazione or "").lower()

    if not norm:
        return None

    if norm == "id":
        return "id"

    # Valori derivati, ricalcolati dall'app: si ignorano
    if "carico" in norm or norm in ("fodmap", "punteggio"):
        return None

    if "fodmap" in norm or "eccesso" in norm:
        return _campo_fodmap(norm)

    if "fdc" in norm:
        return "fdc_id"

    if "usda" in norm and "campi" in norm:
        return "campi_usda"

    if "crea" in norm.split():
        return "codice_crea"

    if "barre" in norm or norm in ("ean", "barcode", "codice ean"):
        return "codice_barre"

    if "porzione" in norm:
        return "porzione"

    if "url" in norm or "link" in norm:
        return "url_fonte"

    if norm in ("note", "nota", "annotazioni"):
        return "note"

    if "fonte" in norm:
        # Le vecchie colonne Fonte Kcal / Fonte TEF di update.py non sono nella web app
        return None if ("kcal" in norm or "tef" in norm) else "fonte_nutrienti"

    if "rischio" in norm:
        return _campo_rischio(norm)

    if "glicemic" in norm or norm in ("ig", "gi"):
        return "indice_glicemico"

    if "nova" in norm.split():
        return "nova"

    nutriente = _campo_nutriente(norm)

    if nutriente:
        return nutriente

    if "rapporto" in norm:
        return "rapporto"

    if "tef" in norm and ("%" in originale or "percent" in norm):
        return "tef_percent"

    if "tef" in norm and "kcal" in norm:
        return "tef_kcal"

    if "tef" in norm:
        return "tef_percent"

    if "nette" in norm:
        return "kcal_nette"

    if "kcal" in norm:
        return "kcal"

    if "fruttosio" in norm:
        return "fruttosio"

    if "fibre" in norm or "fibra" in norm:
        return "fibre"

    if "categoria" in norm:
        return "categoria"

    # Rischi anche senza la parola "rischio" (file vecchi), tranne il colesterolo,
    # che senza "rischio" è il nutriente in mg
    rischio = _campo_rischio(norm, colesterolo=False)

    if rischio:
        return rischio

    if "alimento" in norm or "nome" in norm:
        return "alimento"

    return None


def _campo_rischio(norm: str, colesterolo: bool = True) -> str | None:
    if "diabete" in norm:
        return "rischio_diabete"

    if colesterolo and "colesterolo" in norm:
        return "rischio_colesterolo"

    if "malassorb" in norm:
        return "rischio_malassorbimento"

    if "metabolic" in norm:
        return "rischio_metabolico"

    if "tumoral" in norm:
        return "rischio_tumorale"

    return None


def _campo_fodmap(norm: str) -> str | None:
    if "fruttan" in norm:
        return "fodmap_fruttani"

    if "gos" in norm.split() or "galatto" in norm:
        return "fodmap_gos"

    if "lattosio" in norm:
        return "fodmap_lattosio"

    if "fruttosio" in norm:
        return "fodmap_fruttosio"

    if "polioli" in norm or "poliolo" in norm or "sorbitolo" in norm or "mannitolo" in norm:
        return "fodmap_polioli"

    return None


# Parole chiave dei nutrienti nelle intestazioni (dopo normalize_header)
_NUTRIENTI_RE = (
    (re.compile(r"\bsatur"), "grassi_saturi"),
    (re.compile(r"\b(grassi|lipidi)\b"), "grassi"),
    (re.compile(r"\bprotein"), "proteine"),
    (re.compile(r"\bzuccher"), "zuccheri"),
    (re.compile(r"\bglucosio\b"), "glucosio"),
    (re.compile(r"\blattosio\b"), "lattosio"),
    (re.compile(r"\balcol"), "alcol"),
    (re.compile(r"\bcarboidrat"), "carboidrati"),
    (re.compile(r"\bcolesterolo\b"), "colesterolo"),
    (re.compile(r"\bvit(amina)? a\b"), "vitamina_a"),
    (re.compile(r"\bvit(amina)? c\b"), "vitamina_c"),
    (re.compile(r"\bvit(amina)? d\b"), "vitamina_d"),
    (re.compile(r"\bvit(amina)? e\b"), "vitamina_e"),
    (re.compile(r"\bvit(amina)? b12\b"), "vitamina_b12"),
    (re.compile(r"\bfolat|\bacido folico"), "folati"),
    (re.compile(r"\bcalcio\b"), "calcio"),
    (re.compile(r"\bferro\b"), "ferro"),
    (re.compile(r"\bmagnesio\b"), "magnesio"),
    (re.compile(r"\bpotassio\b"), "potassio"),
    (re.compile(r"\bsodio\b"), "sodio"),
    (re.compile(r"\bzinco\b"), "zinco"),
)


def _campo_nutriente(norm: str) -> str | None:
    for espressione, campo in _NUTRIENTI_RE:
        if espressione.search(norm):
            return campo

    return None


def mappa_colonne(intestazioni: Sequence[object]) -> dict[str, int]:
    """
    {campo: indice di colonna}; se due colonne indicano lo stesso campo vale la prima.
    """
    mappa: dict[str, int] = {}

    for indice, intestazione in enumerate(intestazioni):
        campo = campo_colonna(intestazione)

        if campo:
            mappa.setdefault(campo, indice)

    return mappa


def decode_csv_bytes(raw: bytes) -> str:
    """
    Prova a decodificare il CSV con diversi encoding.
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("latin-1", errors="replace")


def guess_delimiter(sample: str) -> str:
    """
    Riconosce il separatore del CSV tra virgola, punto e virgola e tabulazione.
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


NOMI_SEPARATORI = {",": N_("virgola"), ";": N_("punto e virgola"), "\t": N_("tabulazione")}


def _righe_csv(raw: bytes) -> tuple[list[Riga], str]:
    testo = decode_csv_bytes(raw)
    separatore = guess_delimiter(testo[:4096])
    lettore = csv.reader(io.StringIO(testo), delimiter=separatore)

    righe = []
    piene = 0

    try:
        for celle in lettore:
            celle = [c.strip() for c in celle]
            righe.append((lettore.line_num, celle))
            piene += any(celle)
            _controlla_limite(piene)
    except csv.Error as exc:
        raise ErroreImport(
            gettext("CSV non leggibile alla riga %(riga)d: %(errore)s.", riga=lettore.line_num, errore=exc)
        ) from None

    return righe, gettext("separatore: %(nome)s", nome=traduci(NOMI_SEPARATORI.get(separatore, separatore)))


def _cella_excel(cella: Any) -> str:
    """
    Valore di una cella Excel come testo, come se fosse stato letto da un CSV.
    """
    valore = cella.value

    if valore is None:
        return ""

    if isinstance(valore, bool):
        return "1" if valore else "0"

    if isinstance(valore, (int, float)):
        # Celle in formato percentuale: 0,239 visualizzato come 23,9%
        if "%" in (getattr(cella, "number_format", "") or ""):
            valore = valore * 100

        if isinstance(valore, float) and not math.isfinite(valore):
            return ""

        if float(valore).is_integer() and abs(valore) < 1e15:
            return str(int(valore))

        return format(valore, ".10g")

    if isinstance(valore, (datetime, date, time)):
        return valore.isoformat()

    return str(valore).strip()


def _righe_xlsx(raw: bytes) -> tuple[list[Riga], str]:
    """
    Righe del primo foglio che contiene la colonna Alimento.
    """
    try:
        cartella = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise ErroreImport(gettext(
            "Il file non è un foglio Excel .xlsx valido "
            "(il vecchio formato .xls non è supportato: salvalo come .xlsx o .csv)."
        )) from None

    try:
        primo = None

        for foglio in cartella.worksheets:
            righe = []
            piene = 0
            vuote_di_fila = 0

            for numero, riga in enumerate(foglio.iter_rows(), start=1):
                celle = [_cella_excel(c) for c in riga]

                if any(celle):
                    righe.append((numero, celle))
                    piene += 1
                    vuote_di_fila = 0
                    _controlla_limite(piene)
                else:
                    # Fogli con formattazione su colonne intere: migliaia di righe vuote in coda
                    vuote_di_fila += 1

                    if vuote_di_fila > RIGHE_VUOTE_FINE_FOGLIO:
                        break

            if primo is None:
                primo = (righe, foglio.title)

            if _trova_intestazione(righe)[1].get("alimento") is not None:
                return righe, gettext("foglio: %(nome)s", nome=foglio.title)

        if primo is None:
            raise ErroreImport(gettext("Il file Excel non contiene fogli."))

        return primo[0], gettext("foglio: %(nome)s", nome=primo[1])
    finally:
        cartella.close()


def troppe_righe() -> str:
    return gettext("Il file supera le %(n)d righe: dividilo in più file.", n=MAX_RIGHE)


def _controlla_limite(righe_piene: int) -> None:
    if righe_piene > MAX_RIGHE + RIGHE_RICERCA_INTESTAZIONE:
        raise ErroreImport(troppe_righe())


def _trova_intestazione(righe: list[Riga]) -> tuple[int | None, dict[str, int]]:
    """
    (posizione, mappa) della prima riga che contiene la colonna Alimento
    tra le prime righe non vuote; altrimenti la prima riga non vuota.
    """
    non_vuote = [(i, celle) for i, (_, celle) in enumerate(righe) if any(celle)]

    for i, celle in non_vuote[:RIGHE_RICERCA_INTESTAZIONE]:
        mappa = mappa_colonne(celle)

        if "alimento" in mappa:
            return i, mappa

    if non_vuote:
        i, celle = non_vuote[0]
        return i, mappa_colonne(celle)

    return None, {}


# ---------------------------------------------------------------
# NORMALIZZAZIONE DEI VALORI
# ---------------------------------------------------------------

def togli_protezione_formula(testo: str) -> str:
    """
    L'export antepone un apostrofo ai testi che iniziano con = + - @
    (protezione dalle formule in Excel): qui lo si toglie.
    """
    if len(testo) > 1 and testo[0] == "'" and testo[1] in "=+-@":
        return testo[1:]

    return testo


def pulisci_nome(testo: str) -> str:
    """
    Spazi multipli e grassetto markdown (**Nome**) tolti dal nome dell'alimento.
    """
    testo = re.sub(r"^\*+|\*+$", "", testo.strip())
    return re.sub(r"\s+", " ", testo).strip()


def leggi_livello(testo: str) -> str | None:
    """
    Etichetta canonica del livello di rischio ("Basso"...), anche se preceduta
    da emoji o simboli ("🔴 Alto", "⚠️ Aumentato"); None se non riconosciuto.
    """
    solo_testo = re.sub(r"^[\W_]+|[\W_]+$", "", testo)
    liv = analisi.livello(solo_testo)
    return liv["etichetta"] if liv else None


def normalizza_riga(numero: int, celle: list[str], mappa: dict[str, int]) -> dict[str, Any]:
    """
    {"riga", "id", "valori", "forniti", "avvisi"} per una riga di dati.
    "forniti" elenca i campi con un valore nel file: solo questi
    sovrascrivono i dati esistenti in modalità aggiorna.
    """
    valori: dict[str, Any] = {}
    forniti = []
    avvisi = []

    def grezzo(campo: str) -> str:
        indice = mappa.get(campo)

        if indice is None or indice >= len(celle):
            return ""

        return togli_protezione_formula(celle[indice].strip())

    id_riga = None
    testo_id = grezzo("id")

    if testo_id:
        numero_id, _ = leggi_numero(testo_id)

        if numero_id is not None and numero_id > 0 and float(numero_id).is_integer():
            id_riga = int(numero_id)
        else:
            avvisi.append(gettext("ID «%(testo)s» non valido: ignorato", testo=testo_id))

    for campo in CAMPI_TESTO:
        testo = grezzo(campo)

        if campo == "alimento":
            testo = pulisci_nome(testo)

        if testo:
            valori[campo] = testo
            forniti.append(campo)

    for campo in CAMPI_NUMERICI:
        testo = grezzo(campo)

        if not testo:
            continue

        valore, valido = leggi_numero(testo)

        if not valido:
            avvisi.append(gettext(
                "%(campo)s: «%(testo)s» non è un numero, ignorato", campo=traduci(ETICHETTE[campo]), testo=testo
            ))
        elif valore is not None and valore < 0:
            avvisi.append(gettext(
                "%(campo)s: valore negativo (%(testo)s), ignorato", campo=traduci(ETICHETTE[campo]), testo=testo
            ))
        elif valore is not None:
            valori[campo] = valore
            forniti.append(campo)

    # Il rapporto F/F non si legge: si ricalcola da fruttosio e fibre
    if grezzo("rapporto"):
        forniti.append("rapporto")

    for campo in analisi.CAMPI_RISCHIO:
        testo = grezzo(campo)

        if not testo or testo.lower() in VALORI_ASSENTI:
            continue

        etichetta = leggi_livello(testo)

        if etichetta:
            valori[campo] = etichetta
            forniti.append(campo)
        else:
            avvisi.append(gettext(
                "%(campo)s: livello «%(testo)s» non riconosciuto, ignorato",
                campo=traduci(ETICHETTE[campo]), testo=testo,
            ))

    _normalizza_nutrienti(grezzo, valori, forniti, avvisi)

    return {
        "riga": numero,
        "id": id_riga,
        "valori": valori,
        "forniti": forniti,
        "avvisi": avvisi,
    }


def _normalizza_nutrienti(
    grezzo: Callable[[str], str], valori: dict[str, Any], forniti: list[str], avvisi: list[str]
) -> None:
    """
    Macro e micronutrienti, indice glicemico, NOVA, FODMAP e fonte.
    """
    def assente(testo: str) -> bool:
        return not testo or testo.lower() in VALORI_ASSENTI

    for campo in nutrienti.CAMPI_NUTRIENTI:
        testo = grezzo(campo)

        if assente(testo):
            continue

        valore, valido = leggi_numero(testo)

        if not valido or valore is None or valore < 0:
            avvisi.append(gettext(
                "%(campo)s: «%(testo)s» non è un numero valido, ignorato", campo=traduci(ETICHETTE[campo]), testo=testo
            ))
        else:
            valori[campo] = valore
            forniti.append(campo)

    testo = grezzo("indice_glicemico")

    if not assente(testo):
        valore, valido = leggi_numero(testo)

        if valido and valore is not None and 0 <= valore <= 100:
            valori["indice_glicemico"] = valore
            forniti.append("indice_glicemico")
        else:
            avvisi.append(gettext("Indice glicemico: «%(testo)s» fuori scala (0-100), ignorato", testo=testo))

    testo = grezzo("nova")

    if not assente(testo):
        gruppo = nutrienti.leggi_nova(testo)

        if gruppo:
            valori["nova"] = gruppo
            forniti.append("nova")
        else:
            avvisi.append(gettext("NOVA: «%(testo)s» non è un gruppo da 1 a 4, ignorato", testo=testo))

    for campo in nutrienti.CAMPI_FODMAP:
        testo = grezzo(campo)

        if assente(testo):
            continue

        livello_fodmap = nutrienti.livello_fodmap(testo)

        if livello_fodmap:
            valori[campo] = livello_fodmap["etichetta"]
            forniti.append(campo)
        else:
            avvisi.append(gettext(
                "%(campo)s: livello «%(testo)s» non riconosciuto, ignorato",
                campo=traduci(ETICHETTE[campo]), testo=testo,
            ))

    testo = grezzo("fonte_nutrienti")

    if not assente(testo):
        valori["fonte_nutrienti"] = testo
        forniti.append("fonte_nutrienti")

    testo = grezzo("note")

    if not assente(testo):
        valori["note"] = testo[:2000]
        forniti.append("note")

    testo = grezzo("url_fonte")

    if not assente(testo):
        if nutrienti.URL_RE.match(testo):
            valori["url_fonte"] = testo
            forniti.append("url_fonte")
        else:
            avvisi.append(gettext("URL fonte: «%(testo)s» non è un indirizzo http(s), ignorato", testo=testo[:60]))

    testo = grezzo("fdc_id")

    if not assente(testo):
        valore, _ = leggi_numero(testo)

        if valore is not None and valore > 0 and float(valore).is_integer():
            valori["fdc_id"] = int(valore)
            forniti.append("fdc_id")
        else:
            avvisi.append(gettext("FDC ID: «%(testo)s» non valido, ignorato", testo=testo))

    testo = grezzo("porzione")

    if not assente(testo):
        valore, valido = leggi_numero(testo)

        if valido and valore is not None and nutrienti.GRAMMI_MIN <= valore <= nutrienti.GRAMMI_MAX:
            valori["porzione"] = valore
            forniti.append("porzione")
        else:
            avvisi.append(gettext("Porzione: «%(testo)s» non valida, ignorata", testo=testo))

    testo = grezzo("codice_crea").upper()

    if not assente(testo):
        if crea.CODICE_RE.match(testo):
            valori["codice_crea"] = testo
            forniti.append("codice_crea")
        else:
            avvisi.append(gettext("Codice CREA: «%(testo)s» non valido, ignorato", testo=testo))

    testo = grezzo("codice_barre")

    if not assente(testo):
        if openfoodfacts.CODICE_RE.match(testo):
            valori["codice_barre"] = testo
            forniti.append("codice_barre")
        else:
            avvisi.append(gettext("Codice a barre: «%(testo)s» non valido, ignorato", testo=testo))

    testo = grezzo("campi_usda")

    if not assente(testo):
        valori["campi_usda"] = ",".join(usda.leggi_campi(testo)) or None
        forniti.append("campi_usda")


def leggi_file(nome_file: str, raw: bytes) -> dict[str, Any]:
    """
    Legge un file .csv o .xlsx e restituisce un dizionario serializzabile in JSON:
    nome_file, formato, dettaglio, colonne [{nome, campo}], righe normalizzate.
    """
    estensione = nome_file.rsplit(".", 1)[-1].lower() if "." in nome_file else ""

    if estensione == "csv":
        righe, dettaglio = _righe_csv(raw)
    elif estensione == "xlsx":
        righe, dettaglio = _righe_xlsx(raw)
    elif estensione == "xls":
        raise ErroreImport(gettext("Il vecchio formato .xls non è supportato: salva il file come .xlsx o .csv."))
    else:
        raise ErroreImport(gettext("Formato non supportato: carica un file .csv oppure .xlsx."))

    posizione, mappa = _trova_intestazione(righe)

    if posizione is None:
        raise ErroreImport(gettext("Il file è vuoto."))

    if "alimento" not in mappa:
        raise ErroreImport(gettext("Colonna «Alimento» non trovata: controlla le intestazioni del file."))

    intestazioni = righe[posizione][1]
    campi_per_indice = {indice: campo for campo, indice in mappa.items()}

    colonne = [
        {"nome": nome or gettext("(colonna %(n)d senza nome)", n=indice + 1), "campo": campi_per_indice.get(indice)}
        for indice, nome in enumerate(intestazioni)
        if nome or indice in campi_per_indice
    ]

    dati = [
        normalizza_riga(numero, celle, mappa)
        for numero, celle in righe[posizione + 1:]
        if any(celle)
    ]

    if not dati:
        raise ErroreImport(gettext("Il file non contiene righe di dati sotto l'intestazione."))

    if len(dati) > MAX_RIGHE:
        raise ErroreImport(troppe_righe())

    return {
        "nome_file": nome_file,
        "formato": estensione,
        "dettaglio": dettaglio,
        "colonne": colonne,
        "categoria_presente": "categoria" in mappa,
        "righe": dati,
    }


# ---------------------------------------------------------------
# PIANO DELL'IMPORT (anteprima)
# ---------------------------------------------------------------

VUOTO = {
    "alimento": "",
    "categoria": "",
    **dict.fromkeys(CAMPI_ZERO, 0.0),
    "fruttosio": None,
    "rapporto": None,
    **dict.fromkeys(analisi.CAMPI_RISCHIO, ""),
    **dict.fromkeys(nutrienti.CAMPI_NULLABILI),
}


def completa_derivati(
    base: Mapping[str, Any], valori: Mapping[str, Any], forniti: set[str], nuovo: bool
) -> dict[str, Any]:
    """
    Unisce i valori del file a quelli di partenza e ricalcola i campi derivati
    come il form (calcoli.completa_energia): Kcal e TEF dai macronutrienti,
    TEF (Kcal) <-> TEF (%), Kcal nette, rapporto fruttosio/fibre.
    Un campo derivato si ricalcola solo se è cambiato qualcosa da cui dipende,
    così una riga identica al database resta invariata.
    I livelli di rischio si ricalcolano sempre dai dati (rischi.py): quelli
    scritti nel file si ignorano.
    """
    if not nuovo:
        # Contano solo i valori che cambiano davvero: TEF e Kcal nette ricopiati
        # invariati da un export non devono impedire il ricalcolo se cambiano le Kcal
        forniti = {c for c in forniti if c not in valori or _diverso(valori[c], base.get(c), c)}

    v = dict(base)
    v.update(valori)

    for campo in CAMPI_ZERO:
        v[campo] = float(v.get(campo) or 0)

    v["fruttosio"] = None if v.get("fruttosio") in (None, "") else float(v["fruttosio"])

    for campo in CAMPI_TESTO:
        v[campo] = v.get(campo) or ""

    calcoli.completa_energia(v, forniti, nuovo)
    rischi.assegna(v)

    return v


def _come_numero(valore: object) -> float:
    return float(valore) if isinstance(valore, (int, float)) else 0.0


def _diverso(a: object, b: object, campo: str | None = None) -> bool:
    # Nei dati nutrizionali "non disponibile" (None) è diverso da 0
    if campo in CAMPI_NULLABILI and (a is None) != (b is None):
        return True

    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        return abs(_come_numero(a) - _come_numero(b)) > 1e-9

    return str(a or "").strip() != str(b or "").strip()


def _chiave_nome(alimento: object) -> str:
    return str(alimento or "").strip().casefold()


def _chiave(alimento: object, categoria: object) -> tuple[str, str]:
    return (_chiave_nome(alimento), str(categoria or "").strip().casefold())


def _voce(riga: dict[str, Any], azione: str, valori: dict[str, Any] | None = None, **extra: Any) -> Voce:
    return {
        "riga": riga["riga"],
        "azione": azione,
        "valori": valori,
        "id": None,
        "modificati": [],
        "precedente": None,
        "avvisi": list(riga["avvisi"]),
        **extra,
    }


def pianifica(conn: sqlite3.Connection, letto: dict[str, Any], modalita: str) -> list[Voce]:
    """
    Lista di voci {riga, azione, valori, id, modificati, precedente, avvisi}.
    Azioni: nuovo, aggiornato, invariato, unito (riga ripetuta nel file,
    fusa con una precedente), saltato.
    """
    if modalita not in MODALITA:
        raise ValueError(f"Modalità non valida: {modalita}")

    esistenti = {
        row["id"]: dict(row)
        for row in conn.execute(f"SELECT id, {', '.join(CAMPI)} FROM alimenti")
    }

    per_chiave: dict[tuple[str, str], int] = {}
    per_nome: dict[str, list[int]] = {}

    for row in esistenti.values():
        per_chiave.setdefault(_chiave(row["alimento"], row["categoria"]), row["id"])
        per_nome.setdefault(_chiave_nome(row["alimento"]), []).append(row["id"])

    con_categoria = letto.get("categoria_presente", True)

    voci: list[Voce] = []
    nuovi: dict[object, Voce] = {}

    for riga in letto["righe"]:
        valori = riga["valori"]
        forniti = set(riga["forniti"])
        nome = valori.get("alimento", "")

        if modalita == "aggiorna":
            esistente = None
            avvisi_extra = []

            if riga["id"] is not None:
                esistente = esistenti.get(riga["id"])

                if esistente and nome and _chiave_nome(nome) != _chiave_nome(esistente["alimento"]):
                    avvisi_extra.append(gettext(
                        "ID %(id)d: il nome cambia da «%(prima)s» a «%(dopo)s»",
                        id=riga["id"], prima=esistente["alimento"], dopo=nome,
                    ))
                elif esistente is None:
                    avvisi_extra.append(gettext("ID %(id)d non presente nel database: cerco per nome", id=riga["id"]))

            if esistente is None and nome:
                if con_categoria:
                    id_trovato = per_chiave.get(_chiave(nome, valori.get("categoria")))
                else:
                    # File senza colonna Categoria: abbina per nome se non è ambiguo
                    trovati = per_nome.get(_chiave_nome(nome), [])

                    if len(trovati) > 1:
                        voce = _voce(riga, "saltato")
                        voce["avvisi"] += avvisi_extra + [gettext(
                            "«%(nome)s» corrisponde a %(n)d alimenti: aggiungi la colonna Categoria per distinguerli",
                            nome=nome, n=len(trovati),
                        )]
                        voci.append(voce)
                        continue

                    id_trovato = trovati[0] if trovati else None

                esistente = esistenti.get(id_trovato) if id_trovato else None

            if esistente is not None:
                aggiornato = completa_derivati(esistente, valori, forniti, nuovo=False)
                modificati = [c for c in CAMPI if _diverso(aggiornato[c], esistente[c], c)]

                voce = _voce(
                    riga,
                    "aggiornato" if modificati else "invariato",
                    aggiornato,
                    id=esistente["id"],
                    modificati=modificati,
                    precedente={c: esistente[c] for c in modificati},
                )
                voce["avvisi"] += avvisi_extra
                voci.append(voce)

                # Le righe successive per lo stesso alimento partono dai valori aggiornati
                esistenti[esistente["id"]] = {"id": esistente["id"], **aggiornato}
                continue

            if nome:
                chiave = _chiave(nome, valori.get("categoria")) if con_categoria else _chiave_nome(nome)
                precedente = nuovi.get(chiave)

                if precedente is not None:
                    # Stesso alimento ripetuto nel file: si fonde con la prima riga
                    unione_forniti = forniti | set(precedente["forniti"])
                    precedente["valori"] = completa_derivati(
                        precedente["valori"], valori, unione_forniti, nuovo=True
                    )
                    precedente["forniti"] = sorted(unione_forniti)

                    voce = _voce(riga, "unito")
                    voce["avvisi"] += avvisi_extra + [gettext(
                        "«%(nome)s» è già alla riga %(riga)d del file: valori uniti a quella riga",
                        nome=nome, riga=precedente["riga"],
                    )]
                    voci.append(voce)
                    continue

        if not nome:
            voce = _voce(riga, "saltato")
            voce["avvisi"].append(gettext("Alimento vuoto"))
            voci.append(voce)
            continue

        voce = _voce(
            riga,
            "nuovo",
            completa_derivati(VUOTO, valori, forniti, nuovo=True),
            forniti=sorted(forniti),
        )

        if modalita == "aggiorna":
            voce["avvisi"] += avvisi_extra
            chiave = _chiave(nome, valori.get("categoria")) if con_categoria else _chiave_nome(nome)
            nuovi[chiave] = voce
        elif modalita == "aggiungi":
            if con_categoria:
                id_doppione = per_chiave.get(_chiave(nome, valori.get("categoria")))
            else:
                omonimi = per_nome.get(_chiave_nome(nome)) or []
                id_doppione = omonimi[0] if omonimi else None

            if id_doppione:
                voce["avvisi"].append(gettext("Già presente nel database (ID %(id)d): sarà duplicato", id=id_doppione))
                voce["doppione"] = True

        voci.append(voce)

    return voci


def riepilogo(voci: list[Voce]) -> dict[str, int]:
    conteggi = Counter(voce["azione"] for voce in voci)

    return {
        "nuovo": conteggi["nuovo"],
        "aggiornato": conteggi["aggiornato"],
        "invariato": conteggi["invariato"],
        "unito": conteggi["unito"],
        "saltato": conteggi["saltato"],
        "doppioni": sum(1 for voce in voci if voce.get("doppione")),
        "con_avvisi": sum(1 for voce in voci if voce["avvisi"]),
        "scritture": conteggi["nuovo"] + conteggi["aggiornato"],
    }


# ---------------------------------------------------------------
# SCRITTURA
# ---------------------------------------------------------------

def applica(conn: sqlite3.Connection, voci: list[Voce], modalita: str, adesso: str) -> int:
    """
    Esegue il piano. Non fa commit: lo decide chi chiama.
    Restituisce il numero di alimenti eliminati (solo in modalità sostituisci).
    """
    eliminati = 0

    if modalita == "sostituisci":
        eliminati = conn.execute("DELETE FROM alimenti").rowcount

    colonne = (*CAMPI, "aggiornato_il")

    for voce in voci:
        if voce["azione"] == "nuovo":
            conn.execute(
                f"INSERT INTO alimenti ({', '.join(colonne)}) "
                f"VALUES ({', '.join('?' for _ in colonne)})",
                [voce["valori"][c] for c in CAMPI] + [adesso],
            )
        elif voce["azione"] == "aggiornato":
            conn.execute(
                f"UPDATE alimenti SET {', '.join(f'{c} = ?' for c in colonne)} WHERE id = ?",
                [voce["valori"][c] for c in CAMPI] + [adesso, voce["id"]],
            )

    return eliminati
