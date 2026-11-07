"""
Import di alimenti da file CSV o Excel (.xlsx), in tre passaggi:

1. leggi_file()  legge il file, riconosce le colonne e normalizza ogni riga
                 (numeri con virgola o punto, livelli di rischio, nomi);
2. pianifica()   confronta le righe con il database e decide per ciascuna
                 nuovo / aggiornato / invariato / unito / saltato,
                 secondo la modalità scelta: è ciò che mostra l'anteprima;
3. applica()     scrive il piano nel database (una sola transazione).
"""

import csv
import io
import math
import re
import zipfile
from collections import Counter
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

import analisi

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
)

ETICHETTE = {
    "id": "ID",
    "alimento": "Alimento",
    "categoria": "Categoria",
    "kcal": "Kcal",
    "tef_kcal": "TEF (Kcal)",
    "tef_percent": "TEF (%)",
    "kcal_nette": "Kcal nette",
    "fruttosio": "Fruttosio (g)",
    "fibre": "Fibre (g)",
    "rapporto": "Rapporto F/F",
    **{campo: f"Rischio {etichetta.lower()}" for campo, etichetta in analisi.RISCHI},
}

MODALITA = {
    "aggiorna": {
        "titolo": "Aggiorna o aggiungi",
        "descrizione": (
            "Le righe già presenti (stesso ID, oppure stesso nome e categoria) vengono "
            "aggiornate con i valori non vuoti del file; le altre vengono aggiunte."
        ),
    },
    "aggiungi": {
        "titolo": "Aggiungi tutte come nuove",
        "descrizione": "Ogni riga diventa un nuovo alimento, anche se esiste già.",
    },
    "sostituisci": {
        "titolo": "Sostituisci l'intera tabella",
        "descrizione": "Elimina tutti gli alimenti attuali e inserisce quelli del file.",
    },
}

MODALITA_PREDEFINITA = "aggiorna"

# Valori da trattare come cella vuota
VALORI_ASSENTI = {"", "-", "–", "—", "na", "n/a", "nd", "n/d", "n.d.", "null", "none"}


class ErroreImport(Exception):
    """
    Problema del file da mostrare all'utente così com'è.
    """


# ---------------------------------------------------------------
# RICONOSCIMENTO DEL FILE E DELLE COLONNE
# ---------------------------------------------------------------

def normalize_header(value):
    """
    Normalizza l'intestazione di una colonna.
    Esempio: "Fruttosio (g/100g)" -> "fruttosio g 100g"
    """
    value = str(value or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def campo_colonna(intestazione):
    """
    Campo del database corrispondente a un'intestazione, oppure None.
    """
    norm = normalize_header(intestazione)
    originale = str(intestazione or "").lower()

    if not norm:
        return None

    if norm == "id":
        return "id"

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

    if "diabete" in norm:
        return "rischio_diabete"

    if "colesterolo" in norm:
        return "rischio_colesterolo"

    if "malassorb" in norm:
        return "rischio_malassorbimento"

    if "metabolic" in norm:
        return "rischio_metabolico"

    if "tumoral" in norm:
        return "rischio_tumorale"

    if "alimento" in norm or "nome" in norm:
        return "alimento"

    return None


def mappa_colonne(intestazioni):
    """
    {campo: indice di colonna}; se due colonne indicano lo stesso campo vale la prima.
    """
    mappa = {}

    for indice, intestazione in enumerate(intestazioni):
        campo = campo_colonna(intestazione)

        if campo:
            mappa.setdefault(campo, indice)

    return mappa


def decode_csv_bytes(raw):
    """
    Prova a decodificare il CSV con diversi encoding.
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("latin-1", errors="replace")


def guess_delimiter(sample):
    """
    Riconosce il separatore del CSV tra virgola, punto e virgola e tabulazione.
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


NOMI_SEPARATORI = {",": "virgola", ";": "punto e virgola", "\t": "tabulazione"}


def _righe_csv(raw):
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
        raise ErroreImport(f"CSV non leggibile alla riga {lettore.line_num}: {exc}.") from None

    return righe, f"separatore: {NOMI_SEPARATORI.get(separatore, separatore)}"


def _cella_excel(cella):
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


def _righe_xlsx(raw):
    """
    Righe del primo foglio che contiene la colonna Alimento.
    """
    try:
        cartella = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise ErroreImport(
            "Il file non è un foglio Excel .xlsx valido "
            "(il vecchio formato .xls non è supportato: salvalo come .xlsx o .csv)."
        ) from None

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
                return righe, f"foglio: {foglio.title}"

        if primo is None:
            raise ErroreImport("Il file Excel non contiene fogli.")

        return primo[0], f"foglio: {primo[1]}"
    finally:
        cartella.close()


def _controlla_limite(righe_piene):
    if righe_piene > MAX_RIGHE + RIGHE_RICERCA_INTESTAZIONE:
        raise ErroreImport(
            f"Il file supera le {MAX_RIGHE} righe: dividilo in più file."
        )


def _trova_intestazione(righe):
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

def leggi_numero(testo):
    """
    (valore, valido): valore None se la cella è vuota o assente (valido=True)
    oppure se non è un numero (valido=False). Accetta virgola o punto decimale,
    separatore delle migliaia, % e unità di misura in coda ("5,9 g").
    """
    testo = str(testo or "").strip().replace(" ", "").replace(" ", "")

    if testo.lower() in VALORI_ASSENTI or testo.lower() in ("inf", "infinity", "∞"):
        return None, True

    testo = testo.rstrip("%")

    if "," in testo and "." in testo:
        # Il separatore decimale è l'ultimo dei due: 1.234,5 oppure 1,234.5
        if testo.rfind(",") > testo.rfind("."):
            testo = testo.replace(".", "").replace(",", ".")
        else:
            testo = testo.replace(",", "")
    else:
        testo = testo.replace(",", ".")

    corrispondenza = re.fullmatch(r"(-?\d+(?:\.\d+)?|-?\.\d+)(?:[a-zA-Zµ]{1,4})?", testo)

    if not corrispondenza:
        return None, False

    valore = float(corrispondenza.group(1))
    return (valore, True) if math.isfinite(valore) else (None, True)


def togli_protezione_formula(testo):
    """
    L'export antepone un apostrofo ai testi che iniziano con = + - @
    (protezione dalle formule in Excel): qui lo si toglie.
    """
    if len(testo) > 1 and testo[0] == "'" and testo[1] in "=+-@":
        return testo[1:]

    return testo


def pulisci_nome(testo):
    """
    Spazi multipli e grassetto markdown (**Nome**) tolti dal nome dell'alimento.
    """
    testo = re.sub(r"^\*+|\*+$", "", testo.strip())
    return re.sub(r"\s+", " ", testo).strip()


def leggi_livello(testo):
    """
    Etichetta canonica del livello di rischio ("Basso"...), anche se preceduta
    da emoji o simboli ("🔴 Alto", "⚠️ Aumentato"); None se non riconosciuto.
    """
    solo_testo = re.sub(r"^[\W_]+|[\W_]+$", "", testo)
    liv = analisi.livello(solo_testo)
    return liv["etichetta"] if liv else None


def normalizza_riga(numero, celle, mappa):
    """
    {"riga", "id", "valori", "forniti", "avvisi"} per una riga di dati.
    "forniti" elenca i campi con un valore nel file: solo questi
    sovrascrivono i dati esistenti in modalità aggiorna.
    """
    valori = {}
    forniti = []
    avvisi = []

    def grezzo(campo):
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
            avvisi.append(f"ID «{testo_id}» non valido: ignorato")

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
            avvisi.append(f"{ETICHETTE[campo]}: «{testo}» non è un numero, ignorato")
        elif valore is not None and valore < 0:
            avvisi.append(f"{ETICHETTE[campo]}: valore negativo ({testo}), ignorato")
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
            avvisi.append(f"{ETICHETTE[campo]}: livello «{testo}» non riconosciuto, ignorato")

    return {
        "riga": numero,
        "id": id_riga,
        "valori": valori,
        "forniti": forniti,
        "avvisi": avvisi,
    }


def leggi_file(nome_file, raw):
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
        raise ErroreImport("Il vecchio formato .xls non è supportato: salva il file come .xlsx o .csv.")
    else:
        raise ErroreImport("Formato non supportato: carica un file .csv oppure .xlsx.")

    posizione, mappa = _trova_intestazione(righe)

    if posizione is None:
        raise ErroreImport("Il file è vuoto.")

    if "alimento" not in mappa:
        raise ErroreImport(
            "Colonna «Alimento» non trovata: controlla le intestazioni del file."
        )

    intestazioni = righe[posizione][1]
    campi_per_indice = {indice: campo for campo, indice in mappa.items()}

    colonne = [
        {"nome": nome or f"(colonna {indice + 1} senza nome)", "campo": campi_per_indice.get(indice)}
        for indice, nome in enumerate(intestazioni)
        if nome or indice in campi_per_indice
    ]

    dati = [
        normalizza_riga(numero, celle, mappa)
        for numero, celle in righe[posizione + 1:]
        if any(celle)
    ]

    if not dati:
        raise ErroreImport("Il file non contiene righe di dati sotto l'intestazione.")

    if len(dati) > MAX_RIGHE:
        raise ErroreImport(f"Il file supera le {MAX_RIGHE} righe: dividilo in più file.")

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
    **{campo: 0.0 for campo in CAMPI_NUMERICI},
    "rapporto": 0.0,
    **{campo: "" for campo in analisi.CAMPI_RISCHIO},
}


def arrotonda(valore, cifre):
    """
    Arrotondamento "alla pari per eccesso" come ROUND() di SQLite
    (con cui è stato normalizzato il database): 2,8125 -> 2,813,
    dove round() di Python darebbe 2,812.
    """
    passo = Decimal(1).scaleb(-cifre)
    return float(Decimal(repr(float(valore))).quantize(passo, rounding=ROUND_HALF_UP))


def completa_derivati(base, valori, forniti, nuovo):
    """
    Unisce i valori del file a quelli di partenza e ricalcola i campi derivati,
    come il form: TEF (Kcal) <-> TEF (%), Kcal nette, rapporto fruttosio/fibre.
    Un campo derivato si ricalcola solo se è cambiato qualcosa da cui dipende,
    così una riga identica al database resta invariata.
    """
    if not nuovo:
        # Contano solo i valori che cambiano davvero: TEF e Kcal nette ricopiati
        # invariati da un export non devono impedire il ricalcolo se cambiano le Kcal
        forniti = {c for c in forniti if c not in valori or _diverso(valori[c], base.get(c))}

    v = dict(base)
    v.update(valori)

    for campo in (*CAMPI_NUMERICI, "rapporto"):
        v[campo] = float(v.get(campo) or 0)

    for campo in (*CAMPI_TESTO, *analisi.CAMPI_RISCHIO):
        v[campo] = v.get(campo) or ""

    kcal = v["kcal"]

    if "tef_kcal" in forniti and "tef_percent" not in forniti:
        v["tef_percent"] = arrotonda(v["tef_kcal"] / kcal * 100, 2) if kcal else 0.0
    elif "tef_percent" in forniti and "tef_kcal" not in forniti:
        v["tef_kcal"] = arrotonda(kcal * v["tef_percent"] / 100, 2)
    elif "kcal" in forniti and not {"tef_kcal", "tef_percent"} & forniti and v["tef_percent"]:
        v["tef_kcal"] = arrotonda(kcal * v["tef_percent"] / 100, 2)

    if "kcal_nette" not in forniti and (nuovo or {"kcal", "tef_kcal", "tef_percent"} & forniti):
        v["kcal_nette"] = arrotonda(kcal - v["tef_kcal"], 2)

    if nuovo or {"fruttosio", "fibre", "rapporto"} & forniti:
        v["rapporto"] = arrotonda(v["fruttosio"] / v["fibre"], 3) if v["fibre"] > 0 else 0.0

    return v


def _diverso(a, b):
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        return abs(float(a or 0) - float(b or 0)) > 1e-9

    return str(a or "").strip() != str(b or "").strip()


def _chiave_nome(alimento):
    return str(alimento or "").strip().casefold()


def _chiave(alimento, categoria):
    return (_chiave_nome(alimento), str(categoria or "").strip().casefold())


def _voce(riga, azione, valori=None, **extra):
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


def pianifica(conn, letto, modalita):
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

    per_chiave = {}
    per_nome = {}

    for row in esistenti.values():
        per_chiave.setdefault(_chiave(row["alimento"], row["categoria"]), row["id"])
        per_nome.setdefault(_chiave_nome(row["alimento"]), []).append(row["id"])

    con_categoria = letto.get("categoria_presente", True)

    voci = []
    nuovi = {}

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
                    avvisi_extra.append(
                        f"ID {riga['id']}: il nome cambia da «{esistente['alimento']}» a «{nome}»"
                    )
                elif esistente is None:
                    avvisi_extra.append(
                        f"ID {riga['id']} non presente nel database: cerco per nome"
                    )

            if esistente is None and nome:
                if con_categoria:
                    id_trovato = per_chiave.get(_chiave(nome, valori.get("categoria")))
                else:
                    # File senza colonna Categoria: abbina per nome se non è ambiguo
                    trovati = per_nome.get(_chiave_nome(nome), [])

                    if len(trovati) > 1:
                        voce = _voce(riga, "saltato")
                        voce["avvisi"] += avvisi_extra + [
                            f"«{nome}» corrisponde a {len(trovati)} alimenti: "
                            "aggiungi la colonna Categoria per distinguerli"
                        ]
                        voci.append(voce)
                        continue

                    id_trovato = trovati[0] if trovati else None

                esistente = esistenti.get(id_trovato) if id_trovato else None

            if esistente is not None:
                aggiornato = completa_derivati(esistente, valori, forniti, nuovo=False)
                modificati = [c for c in CAMPI if _diverso(aggiornato[c], esistente[c])]

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
                    voce["avvisi"] += avvisi_extra + [
                        f"«{nome}» è già alla riga {precedente['riga']} del file: valori uniti a quella riga"
                    ]
                    voci.append(voce)
                    continue

        if not nome:
            voce = _voce(riga, "saltato")
            voce["avvisi"].append("Alimento vuoto")
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
                id_doppione = (per_nome.get(_chiave_nome(nome)) or [None])[0]

            if id_doppione:
                voce["avvisi"].append(f"Già presente nel database (ID {id_doppione}): sarà duplicato")
                voce["doppione"] = True

        voci.append(voce)

    return voci


def riepilogo(voci):
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

def applica(conn, voci, modalita, adesso):
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
