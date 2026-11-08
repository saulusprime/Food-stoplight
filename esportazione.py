"""
Export della tabella alimenti (CSV, Excel, PDF) e della scheda alimento (PDF).

I file CSV ed Excel usano le stesse intestazioni accettate dall'import,
così si possono modificare e reimportare (le righe si abbinano per ID).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, TypedDict

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import analisi
import nutrienti
from analisi import Alimento


class InfoExport(TypedDict):
    """
    Contesto dell'export: filtri applicati, ordinamento, data, numero di alimenti.
    """
    filtri: list[tuple[str, str]]
    ordinamento: str
    data: datetime
    totale: int

def _intestazione_nutriente(campo: str) -> str:
    """
    "Grassi saturi (g)", "Vitamina C (mg)": intestazioni riconosciute anche dall'import.
    """
    _, _, unita, _, _ = nutrienti.PER_CAMPO[campo]
    return f"{nutrienti.ETICHETTE[campo]} ({unita})"


def _formato_excel(decimali: int) -> str:
    return "0" if decimali == 0 else "0." + "0" * decimali


# Colonne esportate: (campo, intestazione, formato numerico Excel)
COLONNE = (
    ("id", "ID", "0"),
    ("alimento", "Alimento", None),
    ("categoria", "Categoria", None),
    ("punteggio", "Punteggio", "0"),
    ("kcal", "Kcal", "0.0"),
    ("tef_kcal", "TEF (Kcal)", "0.0"),
    ("tef_percent", "TEF (%)", "0.0"),
    ("kcal_nette", "Kcal Nette", "0.0"),
    ("fruttosio", "Fruttosio (g/100g)", "0.00"),
    ("fibre", "Fibre (g/100g)", "0.00"),
    ("rapporto", "Rapporto F/Fibre", "0.000"),
    *((campo, f"Rischio {etichetta}", None) for campo, etichetta in analisi.RISCHI),
    # Dati nutrizionali per 100 g (vuoti = non disponibili)
    *((campo, _intestazione_nutriente(campo), _formato_excel(decimali))
      for campo, _, _, decimali, _ in nutrienti.NUTRIENTI),
    ("indice_glicemico", "Indice glicemico", "0"),
    ("carico_glicemico", "Carico glicemico (per 100 g)", "0.0"),
    ("nova", "NOVA", "0"),
    *((campo, nutrienti.ETICHETTE[campo], None) for campo in nutrienti.CAMPI_FODMAP),
    ("fonte_nutrienti", "Fonte nutrienti", None),
    ("url_fonte", "URL fonte", None),
    ("fdc_id", "FDC ID", "0"),
    ("codice_crea", "Codice CREA", None),
    ("codice_barre", "Codice a barre", None),
    ("campi_usda", "Campi da USDA", None),
    ("porzione", "Porzione tipica (g)", "0"),
    ("note", "Note", None),
    ("aggiornato_il", "Aggiornato il", None),
)

CAMPI_NUMERICI = {campo for campo, _, formato in COLONNE if formato}

# Colori dei livelli, gli stessi di static/css/app.css (--stato-*)
COLORI_STATO = {
    "good": "0ca30c",
    "warning": "f9be1a",
    "serious": "ec835a",
    "critical": "d03b3b",
}

INCHIOSTRO = "1a1a19"
INCHIOSTRO_SECONDARIO = "5f5e5a"
GRIGLIA = "d9d8d4"
SFONDO_INTESTAZIONE = "efeeea"
SFONDO_RIGA_ALTERNA = "f7f7f5"
ACCENTO = "2a78d6"
TRACCIA_METRO = "e3e2de"

DISCLAIMER = (
    "Dati a scopo informativo e di studio: non sostituiscono "
    "il parere di un medico o di un nutrizionista."
)


def _rgb(esadecimale: str) -> tuple[int, int, int]:
    rosso, verde, blu = (int(esadecimale[i:i + 2], 16) for i in (0, 2, 4))
    return rosso, verde, blu


def _luminanza(esadecimale: str) -> float:
    def canale(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canale(c) for c in _rgb(esadecimale))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def colore_testo(sfondo: str) -> str:
    """
    Inchiostro scuro o bianco, quello col contrasto WCAG maggiore sullo sfondo.
    In stampa e a corpo piccolo il contrasto conta più che a schermo.
    """
    l_sfondo = _luminanza(sfondo)
    contrasto_scuro = (l_sfondo + 0.05) / (_luminanza(INCHIOSTRO) + 0.05)
    contrasto_bianco = 1.05 / (l_sfondo + 0.05)
    return INCHIOSTRO if contrasto_scuro >= contrasto_bianco else "ffffff"


def colori_livello(valore: object) -> tuple[str, str] | None:
    """
    (sfondo, testo) esadecimali per un valore di rischio, None se non classificato.
    """
    stato = analisi.stato(valore)

    if stato not in COLORI_STATO:
        return None

    sfondo = COLORI_STATO[stato]
    return sfondo, colore_testo(sfondo)


def numero_it(valore: float | str | None, decimali: int | None = None) -> str:
    """
    Numero con virgola decimale; senza decimali indicati usa la forma compatta.
    """
    if valore is None or valore == "":
        return "–"

    numero = float(valore)
    testo = f"{numero:g}" if decimali is None else f"{numero:.{decimali}f}"
    return testo.replace(".", ",")


# ---------------------------------------------------------------
# DESCRIZIONE DEI FILTRI (intestazione di Excel e PDF)
# ---------------------------------------------------------------

def descrivi(info: InfoExport) -> str:
    """
    Riga di contesto: numero di alimenti, filtri, ordinamento, data.
    """
    parti = [f"{info['totale']} alimenti"]

    if info["filtri"]:
        parti.append("filtri: " + ", ".join(f"{nome} {valore}" for nome, valore in info["filtri"]))
    else:
        parti.append("nessun filtro")

    parti.append(f"ordinati per {info['ordinamento']}")
    parti.append(f"esportato il {info['data']:%d/%m/%Y %H:%M}")
    return " · ".join(parti)


# ---------------------------------------------------------------
# CSV
# ---------------------------------------------------------------

def proteggi_formula(testo: str) -> str:
    """
    Un testo che inizia con = + - @ verrebbe eseguito come formula da Excel
    (CSV injection): si antepone un apostrofo, che l'import poi toglie.
    """
    if testo[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + testo

    return testo


def valore_colonna(alimento: Alimento, campo: str) -> Any:
    """
    Valore di una colonna esportata; il carico glicemico si calcola al momento.
    """
    if campo == "carico_glicemico":
        return nutrienti.carico_glicemico(alimento)

    return alimento.get(campo)


def _valore_csv(campo: str, valore: object) -> str:
    if valore is None:
        return ""

    if campo in CAMPI_NUMERICI and isinstance(valore, (int, float)):
        testo = f"{float(valore):.6f}".rstrip("0").rstrip(".")
        return testo.replace(".", ",")

    return proteggi_formula(str(valore))


def csv_bytes(alimenti: list[Alimento]) -> bytes:
    """
    CSV con separatore punto e virgola e virgola decimale, come lo apre
    Excel in italiano; UTF-8 con BOM per gli accenti.
    """
    buffer = io.StringIO()
    scrittore = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    scrittore.writerow([intestazione for _, intestazione, _ in COLONNE])

    for alimento in alimenti:
        scrittore.writerow([_valore_csv(campo, valore_colonna(alimento, campo)) for campo, _, _ in COLONNE])

    return ("﻿" + buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------
# EXCEL
# ---------------------------------------------------------------

LARGHEZZE_EXCEL = {
    "fonte_nutrienti": 30,
    "url_fonte": 48,
    "note": 40,
    "id": 7,
    "alimento": 46,
    "categoria": 20,
    "punteggio": 11,
    "aggiornato_il": 19,
}


def _testo_excel(valore: object) -> str:
    return ILLEGAL_CHARACTERS_RE.sub("", str(valore))


def _scrivi_testo(cella: Any, valore: object) -> None:
    cella.value = _testo_excel(valore)

    # openpyxl tratta come formula ogni testo che inizia con "="
    cella.data_type = "s"


def xlsx_bytes(alimenti: list[Alimento], info: InfoExport) -> bytes:
    cartella = Workbook()
    foglio = cartella.worksheets[0]
    foglio.title = "Alimenti"

    grassetto = Font(bold=True, color=INCHIOSTRO)
    sfondo_intestazione = PatternFill("solid", fgColor=SFONDO_INTESTAZIONE)
    bordo_intestazione = Border(bottom=Side(style="thin", color=INCHIOSTRO_SECONDARIO))
    a_capo = Alignment(vertical="center", wrap_text=True)

    riempimenti = {
        stato: (PatternFill("solid", fgColor=colore), Font(color=colore_testo(colore)))
        for stato, colore in COLORI_STATO.items()
    }

    for colonna, (campo, intestazione, _) in enumerate(COLONNE, start=1):
        cella = foglio.cell(row=1, column=colonna, value=intestazione)
        cella.font = grassetto
        cella.fill = sfondo_intestazione
        cella.border = bordo_intestazione
        cella.alignment = a_capo

        lettera = get_column_letter(colonna)
        foglio.column_dimensions[lettera].width = LARGHEZZE_EXCEL.get(
            campo, 17 if campo.startswith("rischio_") else 12
        )

    for riga, alimento in enumerate(alimenti, start=2):
        for colonna, (campo, _, formato) in enumerate(COLONNE, start=1):
            valore = valore_colonna(alimento, campo)
            cella_dato = foglio.cell(row=riga, column=colonna)

            if valore is None or valore == "":
                continue

            if formato:
                cella_dato.value = valore
                cella_dato.number_format = formato
            else:
                _scrivi_testo(cella_dato, valore)

            if campo.startswith("rischio_"):
                stato = analisi.stato(valore)

                if stato in riempimenti:
                    cella_dato.fill, cella_dato.font = riempimenti[stato]

    foglio.freeze_panes = "C2"
    foglio.auto_filter.ref = f"A1:{get_column_letter(len(COLONNE))}{max(len(alimenti) + 1, 2)}"
    foglio.row_dimensions[1].height = 30

    _foglio_informazioni(cartella, info, riempimenti)

    buffer = io.BytesIO()
    cartella.save(buffer)
    return buffer.getvalue()


def _foglio_informazioni(
    cartella: Workbook, info: InfoExport, riempimenti: dict[str, tuple[PatternFill, Font]]
) -> None:
    foglio = cartella.create_sheet("Informazioni")
    foglio.column_dimensions["A"].width = 22
    foglio.column_dimensions["B"].width = 90

    righe = [
        ("Food-stoplight", ""),
        ("Esportato il", f"{info['data']:%d/%m/%Y %H:%M}"),
        ("Alimenti", str(info["totale"])),
        ("Filtri", "; ".join(f"{nome}: {valore}" for nome, valore in info["filtri"]) or "nessuno"),
        ("Ordinamento", info["ordinamento"]),
        ("", ""),
        ("Livelli di rischio", ""),
    ]

    for liv in analisi.LIVELLI:
        righe.append((liv["etichetta"], f"{liv['punti']} punti"))

    righe += [
        ("", ""),
        ("Punteggio", "100 × (1 − media dei punti ÷ 3), sui rischi disponibili: "
                      "100 = tutti trascurabili, 0 = tutti alti."),
        ("Rapporto F/Fibre", "Fruttosio ÷ fibre (0 se le fibre sono 0)."),
        ("Nutrienti", "Valori per 100 g; celle vuote = dato non disponibile. "
                      "Fonte e link nelle colonne Fonte nutrienti e URL fonte."),
        ("Carico glicemico", "Indice glicemico × (carboidrati − fibre) ÷ 100, per 100 g."),
        ("NOVA", "1 non trasformati, 2 ingredienti culinari, 3 trasformati, 4 ultra-trasformati."),
        (
            "Reimportare",
            "Il foglio «Alimenti» si può modificare e reimportare da «Importa» con la modalità "
            "«Aggiorna o aggiungi»: le righe si abbinano per ID. Le colonne Punteggio, "
            "Rapporto F/Fibre, Carico glicemico e Aggiornato il vengono ricalcolate.",
        ),
        ("Nota", DISCLAIMER),
    ]

    stati = {liv["etichetta"]: liv["stato"] for liv in analisi.LIVELLI}

    for numero, (etichetta, valore) in enumerate(righe, start=1):
        cella_a = foglio.cell(row=numero, column=1)
        _scrivi_testo(cella_a, etichetta)
        cella_a.font = Font(bold=True, size=14 if numero == 1 else 11)

        cella_b = foglio.cell(row=numero, column=2)
        _scrivi_testo(cella_b, valore)
        cella_b.alignment = Alignment(wrap_text=True, vertical="top")

        if etichetta in stati and valore.endswith("punti"):
            cella_a.fill, font = riempimenti[stati[etichetta]]
            cella_a.font = Font(bold=True, color=font.color)


# ---------------------------------------------------------------
# PDF
# ---------------------------------------------------------------

# Simboli comuni fuori da Windows-1252, resi con equivalenti leggibili
SOSTITUZIONI_PDF = {"−": "-", "≤": "<=", "≥": ">=", "→": "->", "←": "<-", "≈": "~", "\u00a0": " "}


def testo_pdf(testo: object) -> str:
    """
    I font standard del PDF coprono solo Windows-1252: le lettere accentate
    fuori set perdono l'accento, emoji e simboli vengono tolti.
    """
    testo = str(testo or "")

    for simbolo, sostituto in SOSTITUZIONI_PDF.items():
        testo = testo.replace(simbolo, sostituto)

    try:
        testo.encode("cp1252")
        return testo
    except UnicodeEncodeError:
        pass

    risultato = []

    for carattere in testo:
        try:
            carattere.encode("cp1252")
            risultato.append(carattere)
            continue
        except UnicodeEncodeError:
            pass

        base = unicodedata.normalize("NFKD", carattere).encode("cp1252", "ignore").decode("cp1252")

        if base:
            risultato.append(base)
        elif unicodedata.category(carattere)[0] not in ("S", "M", "C"):
            risultato.append("?")

    return re.sub(r"\s{2,}", " ", "".join(risultato)).strip()


class _Documento(FPDF):
    def __init__(self, titolo: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.core_fonts_encoding = "windows-1252"
        self.set_margins(12, 12, 12)
        self.set_auto_page_break(True, margin=16)
        self.set_title(testo_pdf(titolo))
        self.set_author("Food-stoplight")
        self.set_creator("Food-stoplight")
        self.set_draw_color(*_rgb(GRIGLIA))
        self.set_line_width(0.15)

    def footer(self) -> None:
        self.set_y(-11)
        self.set_font("Helvetica", size=7)
        self.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
        self.cell(0, 4, testo_pdf(f"Food-stoplight · {DISCLAIMER}"), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 4, f"Pagina {self.page_no()} di {{nb}}", align="R")

    def titolo(self, testo: str, sottotitolo: str | None = None, corpo: float = 16) -> None:
        self.set_text_color(*_rgb(INCHIOSTRO))
        self.set_font("Helvetica", "B", corpo)
        self.multi_cell(0, corpo * 0.45, testo_pdf(testo), new_x="LMARGIN", new_y="NEXT")

        if sottotitolo:
            self.ln(1)
            self.set_font("Helvetica", size=8.5)
            self.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
            self.multi_cell(0, 4.2, testo_pdf(sottotitolo), new_x="LMARGIN", new_y="NEXT")

        self.set_text_color(*_rgb(INCHIOSTRO))

    def sezione(self, testo: str, x: float, larghezza: float) -> None:
        self.set_xy(x, self.get_y())
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*_rgb(INCHIOSTRO))
        self.cell(larghezza, 6, testo_pdf(testo), new_x="LEFT", new_y="NEXT")


# Colonne del PDF della tabella: (campo, intestazione, larghezza relativa, allineamento, decimali)
COLONNE_PDF = (
    ("alimento", "Alimento", 55, "LEFT", None),
    ("categoria", "Categoria", 27, "LEFT", None),
    ("punteggio", "Punt.", 10, "RIGHT", 0),
    ("kcal", "Kcal", 10, "RIGHT", None),
    ("tef_kcal", "TEF kcal", 12.5, "RIGHT", None),
    ("tef_percent", "TEF %", 10.5, "RIGHT", None),
    ("kcal_nette", "Kcal nette", 15, "RIGHT", None),
    ("fruttosio", "Frutt. g", 12, "RIGHT", None),
    ("fibre", "Fibre g", 11, "RIGHT", None),
    ("rapporto", "F/F", 11, "RIGHT", 2),
    ("rischio_diabete", "Diabete", 19.6, "CENTER", None),
    ("rischio_colesterolo", "Colesterolo", 19.6, "CENTER", None),
    ("rischio_malassorbimento", "Malassorb.", 19.6, "CENTER", None),
    ("rischio_metabolico", "Metabolico", 19.6, "CENTER", None),
    ("rischio_tumorale", "Tumorale", 19.6, "CENTER", None),
)


def _a_capo(pdf: FPDF, testo: str, larghezza: float) -> list[str]:
    """
    Righe di testo che stanno nella larghezza data (parole intere,
    spezzate solo se una parola da sola non ci sta).
    """
    righe = []
    corrente = ""

    for parola in testo.split():
        prova = f"{corrente} {parola}" if corrente else parola

        if pdf.get_string_width(prova) <= larghezza:
            corrente = prova
            continue

        if corrente:
            righe.append(corrente)

        while pdf.get_string_width(parola) > larghezza and len(parola) > 1:
            taglio = len(parola) - 1

            while taglio > 1 and pdf.get_string_width(parola[:taglio]) > larghezza:
                taglio -= 1

            righe.append(parola[:taglio])
            parola = parola[taglio:]

        corrente = parola

    if corrente or not righe:
        righe.append(corrente)

    return righe


def pdf_tabella(alimenti: list[Alimento], info: InfoExport) -> bytes:
    """
    Tabella filtrata in A4 orizzontale, intestazione ripetuta su ogni pagina.
    Disegnata cella per cella: il motore di tabelle di fpdf2 impiega
    decine di secondi su un migliaio di righe.
    """
    pdf = _Documento("Food-stoplight - Tabella alimenti", orientation="L", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.titolo("Food-stoplight · Tabella alimenti", descrivi(info))
    pdf.ln(3)

    if not alimenti:
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 8, "Nessun alimento con i filtri correnti.")
        return bytes(pdf.output())

    corpo = 7
    interlinea = 3.3
    margine_v = 0.9
    margine_o = 1.2
    fondo_pagina = pdf.h - 16

    peso_totale = sum(c[2] for c in COLONNE_PDF)
    larghezze = [pdf.epw * c[2] / peso_totale for c in COLONNE_PDF]
    posizioni = [pdf.l_margin + sum(larghezze[:i]) for i in range(len(COLONNE_PDF))]
    linea_base = interlinea / 2 + corpo * 0.3528 * 0.35

    def scrivi(testo: str, indice: int, y: float, allineamento: str) -> None:
        x, larghezza = posizioni[indice], larghezze[indice]

        if allineamento == "LEFT":
            x += margine_o
        else:
            ampiezza = pdf.get_string_width(testo)
            x += (larghezza - ampiezza - margine_o) if allineamento == "RIGHT" else (larghezza - ampiezza) / 2

        pdf.text(x, y, testo)

    def intestazione() -> None:
        y = pdf.get_y()
        altezza = interlinea + 2 * margine_v
        pdf.set_fill_color(*_rgb(SFONDO_INTESTAZIONE))
        pdf.rect(pdf.l_margin, y, pdf.epw, altezza, style="F")
        pdf.set_font("Helvetica", "B", corpo)
        pdf.set_text_color(*_rgb(INCHIOSTRO))

        for i, (_, etichetta, _, allineamento, _) in enumerate(COLONNE_PDF):
            scrivi(etichetta, i, y + margine_v + linea_base, allineamento)

        pdf.set_draw_color(*_rgb(INCHIOSTRO_SECONDARIO))
        pdf.line(pdf.l_margin, y + altezza, pdf.l_margin + pdf.epw, y + altezza)
        pdf.set_draw_color(*_rgb(GRIGLIA))
        pdf.set_font("Helvetica", size=corpo)
        pdf.set_y(y + altezza)

    intestazione()

    for numero, alimento in enumerate(alimenti):
        celle = []

        for i, (campo, _, _, allineamento, decimali) in enumerate(COLONNE_PDF):
            valore = alimento.get(campo)

            if campo in ("alimento", "categoria"):
                righe = _a_capo(pdf, testo_pdf(valore or ""), larghezze[i] - 2 * margine_o)
            elif campo.startswith("rischio_"):
                righe = [testo_pdf(valore or "–")]
            else:
                righe = [numero_it(valore, decimali)]

            celle.append((righe, colori_livello(valore) if campo.startswith("rischio_") else None, allineamento))

        linee = max(len(righe) for righe, _, _ in celle)
        altezza = linee * interlinea + 2 * margine_v

        if pdf.get_y() + altezza > fondo_pagina:
            pdf.add_page()
            intestazione()

        y = pdf.get_y()

        if numero % 2:
            pdf.set_fill_color(*_rgb(SFONDO_RIGA_ALTERNA))
            pdf.rect(pdf.l_margin, y, pdf.epw, altezza, style="F")

        for i, (righe, colori, allineamento) in enumerate(celle):
            if colori:
                sfondo, inchiostro = colori
                pdf.set_fill_color(*_rgb(sfondo))
                pdf.rect(posizioni[i] + 0.3, y + 0.3, larghezze[i] - 0.6, altezza - 0.6, style="F")
                pdf.set_text_color(*_rgb(inchiostro))
            else:
                pdf.set_text_color(*_rgb(INCHIOSTRO))

            # Testo centrato in verticale nella riga
            y_testo = y + margine_v + (linee - len(righe)) * interlinea / 2

            for k, testo in enumerate(righe):
                scrivi(testo, i, y_testo + k * interlinea + linea_base, allineamento)

        pdf.line(pdf.l_margin, y + altezza, pdf.l_margin + pdf.epw, y + altezza)
        pdf.set_y(y + altezza)

    return bytes(pdf.output())


def pdf_scheda(item: Alimento, medaglie: list[dict[str, Any]], posti_medaglia: int, data: datetime) -> bytes:
    """
    Scheda alimento in A4 verticale: punteggio, valori, radar e rischi, medaglie.
    """
    pdf = _Documento(f"Food-stoplight - {item['alimento']}", orientation="P", format="A4")
    pdf.set_margins(15, 14, 15)
    pdf.add_page()

    sottotitolo = item.get("categoria") or "Senza categoria"

    if item.get("aggiornato_il"):
        sottotitolo += f" · aggiornato il {item['aggiornato_il']}"

    sottotitolo += f" · esportato il {data:%d/%m/%Y %H:%M}"
    pdf.titolo(item["alimento"], sottotitolo, corpo=18)
    pdf.ln(5)

    x_sx, x_dx, larghezza = 15, 110, 85
    y_riga = pdf.get_y()

    # --- Punteggio complessivo -------------------------------------------
    pdf.set_y(y_riga)
    pdf.sezione("Punteggio complessivo", x_sx, larghezza)
    pdf.set_x(x_sx)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
    pdf.multi_cell(larghezza, 4, "Sintesi dei cinque rischi: 100 = tutti trascurabili, 0 = tutti alti.",
                   new_x="LEFT", new_y="NEXT")
    pdf.ln(2)

    punteggio = item.get("punteggio")
    livello = analisi.livello_punteggio(punteggio)

    if punteggio is not None:
        y = pdf.get_y()
        pdf.set_text_color(*_rgb(INCHIOSTRO))
        pdf.set_font("Helvetica", "B", 30)
        larghezza_numero = pdf.get_string_width(str(punteggio))
        pdf.text(x_sx, y + 10, str(punteggio))
        pdf.set_font("Helvetica", size=12)
        pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
        pdf.text(x_sx + larghezza_numero + 1.2, y + 10, "/100")

        y_metro = y + 14
        pdf.set_fill_color(*_rgb(TRACCIA_METRO))
        pdf.rect(x_sx, y_metro, larghezza, 3, style="F", round_corners=True, corner_radius=1.5)

        colori = COLORI_STATO.get(livello["stato"])

        if colori and punteggio > 0:
            pdf.set_fill_color(*_rgb(colori))
            pdf.rect(x_sx, y_metro, max(larghezza * punteggio / 100, 3), 3,
                     style="F", round_corners=True, corner_radius=1.5)

        pdf.set_y(y_metro + 6)
        _etichetta_livello(pdf, x_sx, f"Livello medio: {livello['etichetta']}", livello["stato"])
    else:
        pdf.set_x(x_sx)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(larghezza, 6, "Nessun rischio classificato.", new_x="LEFT", new_y="NEXT")

    # --- Indice glicemico, NOVA, FODMAP ------------------------------------
    pdf.ln(5)
    pdf.sezione("Indice glicemico, NOVA e FODMAP", x_sx, larghezza)
    pdf.ln(0.5)
    _indicatori(pdf, x_sx, item)

    y_fine_sx = pdf.get_y()

    # --- Valori per 100 g ------------------------------------------------
    pdf.set_y(y_riga)
    pdf.sezione("Valori per 100 g", x_dx, larghezza)
    valori = [
        ("Kcal", numero_it(item.get("kcal"))),
        ("TEF (Kcal)", numero_it(item.get("tef_kcal"))),
        ("TEF (%)", numero_it(item.get("tef_percent"))),
        ("Kcal nette", numero_it(item.get("kcal_nette"))),
    ]
    valori += [
        (f"{etichetta} ({unita})", _valore_nutriente(item.get(campo), decimali))
        for campo, etichetta, unita, decimali, _ in nutrienti.MACRO
    ]
    valori += [
        ("Fibre (g)", numero_it(item.get("fibre"), 2)),
        ("Fruttosio (g)", numero_it(item.get("fruttosio"), 2)),
        ("Rapporto fruttosio/fibre", numero_it(item.get("rapporto"), 2)),
    ]
    _tabella_chiave_valore(pdf, x_dx, larghezza, valori, altezza=5.3)
    y_fine_dx = pdf.get_y()

    # --- Radar e rischi --------------------------------------------------
    y_riga = max(y_fine_sx, y_fine_dx) + 8

    if y_riga > 175:
        pdf.add_page()
        y_riga = pdf.get_y()

    pdf.set_y(y_riga)
    pdf.sezione("Profilo di rischio", x_sx, larghezza)
    y_radar = pdf.get_y()
    _radar(pdf, item, centro=(x_sx + 45, y_radar + 34), raggio=26)

    # Le etichette degli anelli coprirebbero i vertici: stanno in didascalia
    pdf.set_xy(x_sx, y_radar + 66)
    pdf.set_font("Helvetica", size=7.5)
    pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
    pdf.multi_cell(
        larghezza, 3.6,
        "Anelli dal centro verso l'esterno: Trascurabile, Basso, Medio, Alto. "
        "I rischi non classificati restano al centro.",
        align="L", new_x="LEFT", new_y="NEXT",
    )
    y_fine_radar = pdf.get_y()

    pdf.set_y(y_riga)
    pdf.sezione("Livelli di rischio", x_dx, larghezza)
    rischi = [(etichetta, item.get(campo)) for campo, etichetta in analisi.RISCHI]
    _tabella_rischi(pdf, x_dx, larghezza, rischi)

    if nutrienti.fodmap_complessivo(item):
        pdf.ln(4)
        pdf.sezione("FODMAP per categoria", x_dx, larghezza)
        _tabella_rischi(pdf, x_dx, larghezza, [
            (etichetta.split(" (")[0], item.get(campo)) for campo, etichetta in nutrienti.FODMAP
        ], colori=_colori_fodmap)

    pdf.set_y(max(pdf.get_y(), y_fine_radar) + 6)

    # --- Micronutrienti e fonte -----------------------------------------
    micro = [
        (f"{etichetta} ({unita})", _valore_nutriente(item.get(campo), decimali))
        for campo, etichetta, unita, decimali, _ in nutrienti.MICRO
    ]

    if any(item.get(campo) is not None for campo in nutrienti.CAMPI_NUTRIENTI[len(nutrienti.MACRO):]):
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()

        pdf.sezione("Vitamine e sali minerali per 100 g", x_sx, 180)
        y_micro = pdf.get_y()
        meta = (len(micro) + 1) // 2
        _tabella_chiave_valore(pdf, x_sx, larghezza, micro[:meta], altezza=5.3)
        y_fine_micro = pdf.get_y()
        pdf.set_y(y_micro)
        _tabella_chiave_valore(pdf, x_dx, larghezza, micro[meta:], altezza=5.3)
        pdf.set_y(max(pdf.get_y(), y_fine_micro) + 3)

    if item.get("fonte_nutrienti") or item.get("url_fonte"):
        pdf.set_x(x_sx)
        pdf.set_font("Helvetica", size=7.5)
        pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
        fonte = item.get("fonte_nutrienti") or "Fonte"
        if item.get("fdc_id"):
            fonte += f" (FDC {item['fdc_id']})"
        if item.get("url_fonte"):
            fonte += f": {item['url_fonte']}"
        pdf.multi_cell(180, 3.6, testo_pdf(f"Fonte dei nutrienti: {fonte}"), align="L",
                       new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # --- Medaglie --------------------------------------------------------
    if medaglie:
        pdf.sezione("Medaglie", x_sx, 180)
        pdf.set_x(x_sx)
        pdf.set_font("Helvetica", size=8)
        pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
        pdf.cell(180, 4.5, f"Tra i primi {posti_medaglia} dell'intero database.", new_x="LEFT", new_y="NEXT")
        pdf.ln(1)

        for medaglia in medaglie:
            pdf.set_x(x_sx)
            pdf.set_text_color(*_rgb(INCHIOSTRO))
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, testo_pdf(medaglia["titolo"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_x(x_sx)
            pdf.set_font("Helvetica", size=8)
            pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
            pdf.cell(0, 4.5, testo_pdf(medaglia["descrizione"]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

        pdf.ln(4)

    _come_leggere(pdf, x_sx, 180)
    return bytes(pdf.output())


def _come_leggere(pdf: _Documento, x: float, larghezza: float) -> None:
    """
    Legenda in fondo alla scheda: livelli, punteggio e significato dei valori.
    """
    if pdf.get_y() > pdf.h - 75:
        pdf.add_page()

    pdf.set_draw_color(*_rgb(GRIGLIA))
    pdf.line(x, pdf.get_y(), x + larghezza, pdf.get_y())
    pdf.ln(4)
    pdf.sezione("Come leggere la scheda", x, larghezza)
    pdf.ln(1)

    # Livelli: pallino colorato + etichetta + punti, su una riga
    y = pdf.get_y()
    pdf.set_font("Helvetica", size=8.5)
    posizione = x

    for liv in analisi.LIVELLI:
        pdf.set_fill_color(*_rgb(COLORI_STATO[liv["stato"]]))
        pdf.circle(posizione + 1.5, y + 2.4, 1.5, style="F")
        pdf.set_text_color(*_rgb(INCHIOSTRO))
        testo = f"{liv['etichetta']} ({liv['punti']} punti)"
        pdf.text(posizione + 4.5, y + 3.4, testo)
        posizione += 4.5 + pdf.get_string_width(testo) + 7

    pdf.set_y(y + 7)

    voci = (
        ("Punteggio", "100 x (1 - media dei punti / 3), calcolato sui rischi classificati: "
                      "100 = tutti trascurabili, 0 = tutti alti. Il colore segue il livello medio: "
                      "oltre 83 Trascurabile, 51-83 Basso, 17-50 Medio, fino a 16 Alto."),
        ("Valori", "Riferiti a 100 g di alimento. TEF = effetto termico del cibo, "
                   "l'energia spesa per digerirlo; Kcal nette = Kcal - TEF."),
        ("Fruttosio/fibre", "Fruttosio diviso fibre (0 se le fibre sono 0): più è basso, "
                            "meglio è tollerato il fruttosio."),
        ("Indice glicemico", "Basso fino a 55, medio 56-69, alto da 70. Carico glicemico = indice x "
                             "carboidrati disponibili (carboidrati - fibre) / 100; per porzione basso "
                             "fino a 10, medio 11-19, alto da 20."),
        ("NOVA", "Grado di processazione: 1 non trasformati, 2 ingredienti culinari, "
                 "3 trasformati, 4 ultra-trasformati."),
    )

    for titolo, testo in voci:
        pdf.set_x(x)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_rgb(INCHIOSTRO))
        pdf.cell(28, 4, testo_pdf(titolo))
        pdf.set_font("Helvetica", size=8)
        pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
        pdf.multi_cell(larghezza - 28, 4, testo_pdf(testo), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.2)


def _etichetta_livello(pdf: FPDF, x: float, testo: str, stato: str) -> None:
    """
    Pallino colorato + etichetta, come i badge della web app.
    """
    y = pdf.get_y()
    colore = COLORI_STATO.get(stato)

    if colore:
        pdf.set_fill_color(*_rgb(colore))
        pdf.circle(x + 1.6, y + 2.6, 1.6, style="F")

    pdf.set_xy(x + 4.5, y)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_rgb(INCHIOSTRO))
    pdf.cell(80, 5.2, testo_pdf(testo), new_x="LMARGIN", new_y="NEXT")


def _valore_nutriente(valore: float | None, decimali: int) -> str:
    return "–" if valore is None else numero_it(round(valore, decimali))


def _colori_fodmap(valore: object) -> tuple[str, str] | None:
    liv = nutrienti.livello_fodmap(valore)

    if not liv:
        return None

    sfondo = COLORI_STATO[liv["stato"]]
    return sfondo, colore_testo(sfondo)


def _indicatori(pdf: FPDF, x: float, item: Alimento) -> None:
    """
    Indice glicemico, carico glicemico (100 g), NOVA e FODMAP complessivo:
    pallino colorato + testo, oppure "non disponibile".
    """
    ig = item.get("indice_glicemico")
    cg = nutrienti.carico_glicemico(item)
    nova = nutrienti.gruppo_nova(item)
    fodmap = nutrienti.fodmap_complessivo(item)

    voci: list[tuple[str, str | None]] = []

    liv_ig = nutrienti.livello_indice_glicemico(ig)
    liv_cg = nutrienti.livello_carico_glicemico(cg)

    if ig is not None and liv_ig:
        voci.append((f"Indice glicemico: {numero_it(ig)} ({liv_ig['etichetta'].lower()})", liv_ig["stato"]))
    else:
        voci.append(("Indice glicemico: non disponibile", None))

    if cg is not None and liv_cg:
        voci.append((f"Carico glicemico per 100 g: {numero_it(cg)} ({liv_cg['etichetta'].lower()})", liv_cg["stato"]))

    if nova:
        voci.append((f"NOVA {nova['gruppo']}: {nova['etichetta']}", nova["stato"]))
    else:
        voci.append(("NOVA: non disponibile", None))

    if fodmap:
        voci.append((f"FODMAP complessivo: {fodmap['etichetta']}", fodmap["stato"]))
    else:
        voci.append(("FODMAP: non classificato", None))

    for testo, stato in voci:
        if stato:
            _etichetta_livello(pdf, x, testo, stato)
        else:
            pdf.set_xy(x + 4.5, pdf.get_y())
            pdf.set_font("Helvetica", size=9)
            pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
            pdf.cell(80, 5.2, testo_pdf(testo), new_x="LMARGIN", new_y="NEXT")


def _tabella_chiave_valore(
    pdf: FPDF, x: float, larghezza: float, righe: Sequence[tuple[str, str]], altezza: float = 6
) -> None:
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_rgb(INCHIOSTRO))

    for etichetta, valore in righe:
        pdf.set_x(x)
        pdf.cell(larghezza * 0.65, altezza, testo_pdf(etichetta), border="B")
        pdf.cell(larghezza * 0.35, altezza, valore, border="B", align="R", new_x="LMARGIN", new_y="NEXT")


def _tabella_rischi(
    pdf: FPDF,
    x: float,
    larghezza: float,
    rischi: Sequence[tuple[str, object]],
    colori: Callable[[object], tuple[str, str] | None] = colori_livello,
) -> None:
    pdf.set_font("Helvetica", size=9)
    calcola_colori = colori

    for etichetta, valore in rischi:
        pdf.set_x(x)
        pdf.set_text_color(*_rgb(INCHIOSTRO))
        pdf.cell(larghezza * 0.55, 7, testo_pdf(etichetta), border="B")

        coppia = calcola_colori(valore)
        testo = testo_pdf(valore) if valore else "Non classificato"

        if coppia:
            sfondo, inchiostro = coppia
            pdf.set_fill_color(*_rgb(sfondo))
            pdf.set_text_color(*_rgb(inchiostro))
            pdf.cell(larghezza * 0.45, 7, testo, border="B", align="C", fill=True,
                     new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_text_color(*_rgb(INCHIOSTRO_SECONDARIO))
            pdf.cell(larghezza * 0.45, 7, testo, border="B", align="C",
                     new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(*_rgb(INCHIOSTRO))


def _radar(pdf: FPDF, item: Alimento, centro: tuple[float, float], raggio: float) -> None:
    """
    Radar dei 5 rischi: stessa geometria della scheda web (analisi.radar),
    riportata in millimetri.
    """
    geometria = analisi.radar(item, raggio=110, centro=(0, 0))
    scala = raggio / 110
    cx, cy = centro

    def mm(x: float, y: float) -> tuple[float, float]:
        return (cx + x * scala, cy + y * scala)

    def punti(stringa: str) -> list[tuple[float, float]]:
        return [mm(*map(float, coppia.split(","))) for coppia in stringa.split()]

    pdf.set_draw_color(*_rgb(GRIGLIA))
    pdf.set_line_width(0.2)

    for anello in geometria["anelli"]:
        pdf.polygon(punti(anello["punti"]), style="D")

    for asse in geometria["assi"]:
        pdf.line(cx, cy, *mm(*asse["fine"]))

    area = punti(geometria["poligono"])

    with pdf.local_context(fill_opacity=0.14):
        pdf.set_fill_color(*_rgb(ACCENTO))
        pdf.polygon(area, style="F")

    pdf.set_draw_color(*_rgb(ACCENTO))
    pdf.set_line_width(0.5)
    pdf.polygon(area, style="D")

    # Vertici colorati per livello, con anello bianco
    pdf.set_draw_color(255, 255, 255)
    pdf.set_line_width(0.4)

    for vertice in geometria["vertici"]:
        x, y = mm(vertice["x"], vertice["y"])
        colore = COLORI_STATO.get(vertice["stato"], "898781")
        pdf.set_fill_color(*_rgb(colore))
        pdf.circle(x, y, 1.5, style="DF")

    # Nomi degli assi
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*_rgb(INCHIOSTRO))

    for asse in geometria["assi"]:
        x, y = mm(*asse["etichetta_xy"])
        testo = testo_pdf(asse["etichetta"])
        larghezza = pdf.get_string_width(testo)

        if asse["ancora"] == "middle":
            x -= larghezza / 2
        elif asse["ancora"] == "end":
            x -= larghezza

        pdf.text(x, y + 1, testo)

    pdf.set_draw_color(*_rgb(GRIGLIA))
    pdf.set_line_width(0.15)
