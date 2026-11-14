"""Valori mancanti dal CREA dalla tabella francese Ciqual 2025 e glucosio di carne e pesce in ricette e pasti pronti."""

import csv

import pytest

import ciqual
import classificazioni
import cofid
import crea
import fonti
import importazione
from tests.aiuti import id_di, solo_testo, sql
from tests.test_fonti_rischi import SCHEDA_CREA, USDA_ALBICOCCHE

ALBICOCCHE_CIQUAL = {
    "codice": "13000", "nome": "Abricot, cru", "zuccheri": "8", "fruttosio": "< 0.5", "galattosio": "-",
    "glucosio": "2", "lattosio": "< 0.1", "maltosio": "-", "saccarosio": "5", "grassi": "0.2", "saturi": "0.06",
}


@pytest.fixture
def con_ciqual(monkeypatch):
    """Albicocche CREA (007000) abbinate all'alimento Ciqual di prova, senza CoFID."""
    monkeypatch.setattr(cofid, "abbinamenti", lambda: {})
    monkeypatch.setattr(ciqual, "alimenti", lambda: {"13000": ALBICOCCHE_CIQUAL})
    monkeypatch.setattr(ciqual, "abbinamenti", lambda: {"007000": {ciqual.ZUCCHERI: "13000", ciqual.SATURI: "13000"}})


def test_valori_ciqual():
    assert ciqual.valore("0,3") == (0.3, False)
    assert ciqual.valore("< 0,2") == (0.2, True)
    assert ciqual.valore("<\n0,00018") == (0.00018, True)
    assert ciqual.valore("traces") == (0.0, False)
    assert ciqual.valore("-") == (None, False)
    assert ciqual.normalizza("<\n0,2") == "< 0.2"
    assert ciqual.CODICE_RE.match("24006") and not ciqual.CODICE_RE.match("11-1145")


def test_profilo_con_valori_sotto_il_limite():
    # Fruttosio < 0,5: il limite, perché gli zuccheri non spiegati (8 − 2 − 5) sono di più; lattosio < 0,1: 0
    assert ciqual.composizione_zuccheri(ALBICOCCHE_CIQUAL) == {
        "totale": 8.0, "fruttosio": 0.5, "glucosio": 2.0, "lattosio": 0.0}
    assert ciqual.profilo_zuccheri(ALBICOCCHE_CIQUAL, 9.8) == {"fruttosio": 0.61, "glucosio": 2.45, "lattosio": 0.0}

    # Zuccheri tutti spiegati dal glucosio misurato: fruttosio 0 (salvia fresca)
    salvia = {"zuccheri": "0.3", "fruttosio": "< 0.2", "glucosio": "0.3", "lattosio": "< 0.2", "saccarosio": "< 0.2"}
    assert ciqual.composizione_zuccheri(salvia)["fruttosio"] == 0.0

    # Senza fruttosio o glucosio, con zuccheri nulli o sotto il limite: nessun profilo
    assert ciqual.profilo_zuccheri({**ALBICOCCHE_CIQUAL, "glucosio": "-"}, 9.8) == {}
    assert ciqual.profilo_zuccheri({**ALBICOCCHE_CIQUAL, "zuccheri": "0"}, 9.8) == {}
    assert ciqual.profilo_zuccheri({**ALBICOCCHE_CIQUAL, "zuccheri": "< 0.5"}, 9.8) == {}
    assert ciqual.profilo_zuccheri(ALBICOCCHE_CIQUAL, None) == {}


def test_saturi_e_zuccheri_totali():
    cuore = {"grassi": "9.33", "saturi": "2.66"}
    assert ciqual.saturi(cuore, 5.1) == round(5.1 * 2.66 / 9.33, 2)
    assert ciqual.saturi({"grassi": "1", "saturi": "< 0.01"}, 2.0) == 0.02       # sotto il limite: il limite
    assert ciqual.saturi({"grassi": "< 0.5", "saturi": "< 0.01"}, 2.0) is None   # quota non calcolabile
    assert ciqual.saturi({"grassi": "0", "saturi": "0"}, 2.0) is None
    assert ciqual.saturi({"grassi": "9.33", "saturi": "-"}, 2.0) is None
    assert ciqual.saturi(cuore, None) is None

    assert ciqual.zuccheri_totali(ALBICOCCHE_CIQUAL, 6.0) == 6.0                # non oltre i carboidrati del CREA
    assert ciqual.zuccheri_totali(ALBICOCCHE_CIQUAL, None) == 8.0
    assert ciqual.zuccheri_totali({"zuccheri": "< 0.5"}, 6.0) is None


def test_crea_con_ciqual_prima_di_usda(con_ciqual):
    scheda = crea.leggi_scheda(SCHEDA_CREA, "007000")
    scheda["valori"].pop("Acidi grassi Saturi (%)")
    alimento = fonti.da_crea(scheda, USDA_ALBICOCCHE)

    # Profilo Ciqual riportato ai 9,8 g di zuccheri del CREA; saturi con la quota sui grassi (0,06 su 0,2)
    assert (alimento["fruttosio"], alimento["glucosio"], alimento["lattosio"]) == (0.61, 2.45, 0.0)
    assert alimento["grassi_saturi"] == 0.03
    assert alimento["codice_ciqual"] == "13000"
    assert alimento["campi_ciqual"] == "fruttosio,glucosio,lattosio,grassi_saturi"
    assert alimento["campi_usda"] == "sodio"
    assert "Ciqual 2025 · 13000 Abricot, cru" in alimento["fonte_nutrienti"]


def test_cofid_prima_di_ciqual(con_ciqual, monkeypatch):
    cofid_albicocche = {"codice": "14-001", "nome": "Apricots, raw", "zuccheri": 8.0, "fruttosio": 2.0,
                        "glucosio": 2.0, "lattosio": None, "grassi": 0.1, "saturi_su_acidi": 30.0}
    monkeypatch.setattr(cofid, "alimenti", lambda: {"14-001": cofid_albicocche})
    monkeypatch.setattr(cofid, "abbinamenti", lambda: {"007000": {cofid.ZUCCHERI: "14-001"}})
    scheda = crea.leggi_scheda(SCHEDA_CREA, "007000")
    scheda["valori"].pop("Acidi grassi Saturi (%)")
    alimento = fonti.da_crea(scheda)

    # Zuccheri da CoFID (anche il lattosio, non analizzato, resta riservato), saturi da Ciqual
    assert (alimento["fruttosio"], alimento["lattosio"]) == (2.45, None)
    assert alimento["campi_cofid"] == "fruttosio,glucosio"
    assert alimento["campi_ciqual"] == "grassi_saturi"


def test_ciqual_estrai_excel(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    libro = openpyxl.Workbook()
    foglio = libro.active
    foglio.title = "composition nutritionnelle"
    foglio.append(["alim_grp_code", "alim_code", "alim_nom_fr", "Glucides\n(g\n100 g)", "Lipides\n(g\n100 g)",
                   "Sucres\n(g\n100 g)", "Fructose\n(g\n100 g)", "Galactose\n(g\n100 g)", "Glucose\n(g\n100 g)",
                   "Lactose\n(g\n100 g)", "Maltose\n(g\n100 g)", "Saccharose\n(g\n100 g)",
                   "AG\nsaturés\n(g\n100 g)", "AG 4:0,\nbutyrique\n(g\n100 g)"])
    foglio.append(["01", 11069, "Sauge, fraîche", "1", "< 0,5", "0,3", "<\n0,2", "-", "0,3", "< 0,2",
                   "< 0,2", "< 0,2", "< 0,01", "0"])
    foglio.append(["01", 99999, "Autre", *["1"] * 11])
    percorso = tmp_path / "ciqual.xlsx"
    libro.save(percorso)

    assert ciqual.estrai_excel(percorso, ["11069"]) == [{
        "codice": "11069", "nome": "Sauge, fraîche", "grassi": "< 0.5", "zuccheri": "0.3", "fruttosio": "< 0.2",
        "galattosio": "-", "glucosio": "0.3", "lattosio": "< 0.2", "maltosio": "< 0.2", "saccarosio": "< 0.2",
        "saturi": "< 0.01",
    }]


def test_dati_ciqual_del_progetto_coerenti():
    abbinati = ciqual.abbinamenti()
    assert abbinati, "dati/crea_ciqual.csv vuoto"

    with ciqual.FILE_ABBINAMENTI.open(encoding="utf-8", newline="") as f:
        righe = list(csv.DictReader(f))

    for riga in righe:
        assert ciqual.alimenti()[riga["codice_ciqual"]]["nome"] == riga["nome_ciqual"], riga["codice_ciqual"]
        assert riga["nota"], riga["codice_crea"]

    # Un gruppo di campi viene da una tabella sola
    da_cofid = {(codice, gruppo) for codice, gruppi in cofid.abbinamenti().items() for gruppo in gruppi}
    assert not da_cofid & {(codice, gruppo) for codice, gruppi in abbinati.items() for gruppo in gruppi}

    # Nel database ogni alimento abbinato ha preso i valori da Ciqual
    for codice in abbinati:
        riga = sql("SELECT campi_ciqual, codice_ciqual FROM alimenti WHERE codice_crea = ?", (codice,))
        assert riga and riga[0]["campi_ciqual"] and riga[0]["codice_ciqual"], codice


def test_scheda_import_e_form_con_ciqual(client, admin):
    testo = solo_testo(client.get(f"/alimento/{id_di('Panettone')}").data)
    assert "Ciqual 2025" in testo and "7719" in testo

    assert importazione.campo_colonna("Codice Ciqual") == "codice_ciqual"
    assert importazione.campo_colonna("Campi da Ciqual") == "campi_ciqual"

    html = admin.get(f"/modifica/{id_di('Panettone')}").data.decode()
    assert 'id="codice_ciqual"' in html and 'name="campi_ciqual" value="grassi_saturi"' in html


# ---------------------------------------------------------------
# Glucosio di carne e pesce
# ---------------------------------------------------------------

def test_glucosio_di_carne_e_pesce():
    pesce = {"categoria": "Pesce", "zuccheri": 1.5, "fruttosio": 0.0, "glucosio": None}
    assert classificazioni.glucosio(pesce) == 1.5
    assert classificazioni.glucosio({**pesce, "categoria": "Carne", "glucosio": 0.4}) == 0.4     # dato misurato
    assert classificazioni.glucosio({**pesce, "fruttosio": None}) is None
    assert classificazioni.glucosio({**pesce, "categoria": "Verdura"}) is None


def test_ricette_e_pasti_pronti_con_pesce_classificati():
    alici = sql("SELECT glucosio, campi_ricetta, rischio_malassorbimento FROM alimenti WHERE alimento = 'Alici marinate'")[0]
    assert alici["glucosio"] is not None and "glucosio" in alici["campi_ricetta"]
    assert alici["rischio_malassorbimento"] == "Basso"

    calamari = sql("SELECT glucosio, rischio_malassorbimento FROM alimenti WHERE alimento = 'Calamari fritti'")[0]
    assert calamari["glucosio"] is not None and calamari["rischio_malassorbimento"]
