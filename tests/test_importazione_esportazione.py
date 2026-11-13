"""Lettura di CSV ed Excel, riconoscimento delle colonne, piano dell'import, export."""

import csv
import io
import sqlite3
from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook

import archivio
import database
import esportazione
import importazione
import lingue
from tests.aiuti import ASPARAGI, DB, sql


def piano(contenuto, nome="prova.csv", modalita="aggiorna"):
    letto = importazione.leggi_file(nome, contenuto)
    conn = database.connetti_alimenti(str(DB))

    try:
        voci = importazione.pianifica(conn, letto, modalita)
    finally:
        conn.close()

    return letto, voci, importazione.riepilogo(voci)


def xlsx(righe, formati=None):
    cartella = Workbook()
    foglio = cartella.worksheets[0]

    for riga in righe:
        foglio.append(riga)

    for cella, formato in (formati or {}).items():
        foglio[cella].number_format = formato

    buffer = io.BytesIO()
    cartella.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(("intestazione", "campo"), [
    ("Alimento (per 100g)", "alimento"), ("Nome prodotto", "alimento"), ("ID", "id"), ("#", None),
    ("Kcal Totali", "kcal"), ("TEF Stimato (Kcal)", "tef_kcal"), ("TEF (%)", "tef_percent"), ("Kcal Nette", "kcal_nette"),
    ("Fruttosio (g/100g)", "fruttosio"), ("Fibre (g)", "fibre"), ("Rapporto F/F", "rapporto"),
    ("Rischio Colesterolo", "rischio_colesterolo"), ("Colesterolo (mg)", "colesterolo"), ("Rischio Malassorb.", "rischio_malassorbimento"),
    ("Diabete", "rischio_diabete"), ("Grassi saturi (g)", "grassi_saturi"), ("Grassi (g)", "grassi"),
    ("Vit. C", "vitamina_c"), ("Vitamina B12 (µg)", "vitamina_b12"), ("Acido folico", "folati"),
    ("Indice glicemico", "indice_glicemico"), ("IG", "indice_glicemico"), ("Carico glicemico", None),
    ("Gruppo NOVA", "nova"), ("FODMAP GOS", "fodmap_gos"), ("Fruttosio in eccesso", "fodmap_fruttosio"),
    ("FDC ID", "fdc_id"), ("URL fonte", "url_fonte"), ("Fonte nutrienti", "fonte_nutrienti"), ("Fonte Kcal", None),
    ("Note", "note"), ("Punteggio", None), ("Aggiornato il", None), ("Innovazione", None),
])
def test_campo_colonna(intestazione, campo):
    assert importazione.campo_colonna(intestazione) == campo


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_tutte_le_colonne_esportate_si_reimportano(lingua):
    derivate = set(esportazione.CAMPI_DERIVATI)
    for campo, intestazione, _ in esportazione.intestazioni(lambda testo: lingue.traduci_in(testo, lingua)):
        atteso = None if campo in derivate else campo
        assert importazione.campo_colonna(intestazione) == atteso, intestazione


def test_csv_separatore_e_valori():
    contenuto = "Alimento;Categoria;Kcal;TEF (%);Rischio Diabete;Rischio Tumorale\n**Mela**;Frutta;52;10%;🟡 basso;Protettivo\n"
    letto = importazione.leggi_file("x.csv", contenuto.encode())
    riga = letto["righe"][0]
    assert letto["dettaglio"] == "separatore: punto e virgola"
    assert riga["valori"] == {"alimento": "Mela", "categoria": "Frutta", "kcal": 52.0, "tef_percent": 10.0,
                              "rischio_diabete": "Basso", "rischio_tumorale": "Trascurabile"}


def test_csv_cp1252_e_titolo_sopra_intestazione():
    contenuto = "Tabella alimenti\n\nAlimento,Kcal\nCaffè,2\n".encode("cp1252")
    letto = importazione.leggi_file("x.csv", contenuto)
    assert letto["righe"][0]["valori"]["alimento"] == "Caffè"


def test_xlsx_percentuali_e_primo_foglio_utile():
    contenuto = xlsx([["Alimento", "Kcal", "TEF (%)"], ["Pane", 250, 0.1]], {"C2": "0%"})
    letto = importazione.leggi_file("x.xlsx", contenuto)
    assert letto["righe"][0]["valori"]["tef_percent"] == 10.0


@pytest.mark.parametrize(("nome", "contenuto", "messaggio"), [
    ("note.txt", b"x", "Formato non supportato"),
    ("finto.xlsx", b"non zip", "non è un foglio Excel"),
    ("vecchio.xls", b"x", ".xls"),
    ("vuoto.csv", b"", "vuoto"),
    ("intestazione.csv", b"Alimento;Kcal\n", "righe di dati"),
    ("senza.csv", b"Foo;Bar\n1;2\n", "Alimento"),
])
def test_file_non_validi(nome, contenuto, messaggio):
    with pytest.raises(importazione.ErroreImport, match=messaggio):
        importazione.leggi_file(nome, contenuto)


def test_avvisi_di_normalizzazione():
    contenuto = (b"Alimento;Kcal;Rischio Colesterolo;Indice glicemico;URL fonte;ID\n"
                 b"Prova;abc;boh;150;javascript:alert(1);x\n")
    avvisi = importazione.leggi_file("x.csv", contenuto)["righe"][0]["avvisi"]
    testo = " | ".join(avvisi)
    for parola in ("abc", "boh", "fuori scala", "http", "ID «x»"):
        assert parola in testo


def test_round_trip_export_import_invariato(app):
    with app.test_request_context():
        alimenti = archivio.get_alimenti()
    _, _, sommario = piano(esportazione.csv_bytes(alimenti))
    assert sommario["invariato"] == len(alimenti)
    assert sommario["scritture"] == 0

    info = {"filtri": [], "ordinamento": "Alimento (crescente)", "data": datetime.now(),
            "totale": len(alimenti)}
    _, _, sommario = piano(esportazione.xlsx_bytes(alimenti, info), nome="x.xlsx")
    assert sommario["invariato"] == len(alimenti)


def test_aggiornamento_per_id_e_derivati(app):
    with app.test_request_context():
        alimenti = archivio.get_alimenti()[:2]
    righe = list(csv.reader(io.StringIO(esportazione.csv_bytes(alimenti).decode("utf-8-sig")), delimiter=";"))
    h = righe[0]
    righe[1][h.index("Kcal")] = "999"
    righe[2][1] += " (rinominato)"
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerows(righe)

    _, voci, sommario = piano(buffer.getvalue().encode())
    assert sommario["aggiornato"] == 2
    kcal = next(v for v in voci if "kcal" in v["modificati"])
    assert {"tef_kcal", "kcal_nette"} <= set(kcal["modificati"])
    assert any("il nome cambia" in a for v in voci for a in v["avvisi"])


def test_modalita_aggiungi_e_doppioni():
    _, _, sommario = piano(b"Alimento;Categoria;Kcal\nBurro;Grassi e Oli;717\nNuovissimo;Test;1\n", modalita="aggiungi")
    assert (sommario["nuovo"], sommario["doppioni"]) == (2, 1)


def test_file_senza_categoria_ambiguo():
    # Due alimenti con lo stesso nome in categorie diverse
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO alimenti (alimento, categoria) VALUES ('Trota', 'Pesce'), ('Trota', 'Test')")
    conn.commit()
    conn.close()
    _, voci, sommario = piano(b"Alimento;Kcal\nTrota;100\n")
    assert sommario["saltato"] == 1
    assert "aggiungi la colonna Categoria" in voci[0]["avvisi"][-1]


def test_righe_ripetute_unite():
    _, voci, sommario = piano(b"Alimento;Categoria;Kcal;Proteine (g)\nNuovo;Test;10;\nNuovo;Test;;3\n")
    assert (sommario["nuovo"], sommario["unito"]) == (1, 1)
    nuovo = next(v for v in voci if v["azione"] == "nuovo")
    assert (nuovo["valori"]["kcal"], nuovo["valori"]["proteine"]) == (10.0, 3.0)


def test_vuoto_e_zero_nei_nutrienti_sono_diversi(app):
    senza = sql("SELECT id, alimento, categoria FROM alimenti WHERE vitamina_c IS NULL ORDER BY id LIMIT 1")[0]
    contenuto = f"ID;Alimento;Categoria;Vitamina C (mg)\n{senza['id']};{senza['alimento']};{senza['categoria']};0\n"
    _, voci, _ = piano(contenuto.encode())
    assert voci[0]["modificati"] == ["vitamina_c"]


def test_applica_sostituisci():
    letto = importazione.leggi_file("x.csv", b"Alimento;Kcal\nUno;1\nDue;2\n")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    voci = importazione.pianifica(conn, letto, "sostituisci")
    eliminati = importazione.applica(conn, voci, "sostituisci", "2026-01-01 00:00:00")
    conn.commit()
    assert eliminati == 1100
    assert conn.execute("SELECT COUNT(*) FROM alimenti").fetchone()[0] == 2
    conn.close()


# ---------------------------------------------------------------
# Export
# ---------------------------------------------------------------

def test_csv_formato_italiano_e_protezione_formule():
    alimenti = [{"id": 1, "alimento": "=HYPERLINK(\"x\")", "categoria": "Test", "kcal": 7.7, "punteggio": None}]
    testo = esportazione.csv_bytes(alimenti).decode("utf-8")
    assert testo.startswith("﻿ID;Alimento;")
    assert '"\'=HYPERLINK' in testo
    assert ";7,7;" in testo


def test_xlsx_testo_non_diventa_formula_e_livelli_colorati():
    alimenti = [{"id": 1, "alimento": "=1+1", "rischio_diabete": "Alto", "kcal": 10}]
    info = {"filtri": [("Categoria", "Test")], "ordinamento": "Kcal (decrescente)",
            "data": datetime(2026, 1, 1), "totale": 1}
    cartella = load_workbook(io.BytesIO(esportazione.xlsx_bytes(alimenti, info)))
    foglio = cartella["Alimenti"]
    intestazioni = [c.value for c in foglio[1]]
    assert foglio.cell(row=2, column=2).data_type == "s"
    cella = foglio.cell(row=2, column=intestazioni.index("Rischio diabete") + 1)
    assert cella.fill.fgColor.rgb.upper().endswith("D03B3B")
    assert cartella.sheetnames == ["Alimenti", "Informazioni"]


def test_pdf_tabella_e_scheda(app):
    with app.test_request_context():
        alimenti = archivio.get_alimenti()
        asparagi = archivio.get_alimento(ASPARAGI)
    info = {"filtri": [], "ordinamento": "Alimento (crescente)", "data": datetime.now(),
            "totale": len(alimenti)}
    assert esportazione.pdf_tabella(alimenti, info).startswith(b"%PDF")
    assert esportazione.pdf_tabella([], info).startswith(b"%PDF")
    assert esportazione.pdf_scheda(asparagi, [], 10, info["data"]).startswith(b"%PDF")


def test_testo_pdf_e_contrasto():
    assert esportazione.testo_pdf("− ≥ 5 g ✓ “ok” ő") == "- >= 5 g “ok” o"
    assert esportazione.colore_testo("f9be1a") == esportazione.INCHIOSTRO
    assert esportazione.colore_testo("d03b3b") == "ffffff"
