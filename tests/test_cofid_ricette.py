"""Valori mancanti dal CREA: CoFID (profilo degli zuccheri, grassi saturi), ricette dagli ingredienti, indice glicemico."""

import json

import pytest

import archivio
import classificazioni
import cofid
import crea
import fonti
import importazione
import ricette
import usda
from tests.aiuti import ASPARAGI, applicazione, solo_testo, sql
from tests.test_fonti_rischi import SCHEDA_CREA, USDA_ALBICOCCHE
from web import comune

ALBICOCCHE_COFID = {
    "codice": "14-001", "nome": "Apricots, raw", "zuccheri": 8.0, "fruttosio": 2.0, "glucosio": 2.0,
    "lattosio": None, "saccarosio": 4.0, "maltosio": 0.0, "grassi": 0.1, "saturi_su_acidi": 30.0,
}


@pytest.fixture
def con_cofid(monkeypatch):
    """Albicocche CREA (007000) abbinate all'alimento CoFID di prova, per zuccheri e saturi."""
    monkeypatch.setattr(cofid, "alimenti", lambda: {"14-001": ALBICOCCHE_COFID})
    monkeypatch.setattr(cofid, "abbinamenti", lambda: {"007000": {cofid.ZUCCHERI: "14-001", cofid.SATURI: "14-001"}})


# ---------------------------------------------------------------
# CoFID
# ---------------------------------------------------------------

def test_cofid_valori_tracce_e_non_analizzati():
    assert cofid.numero("Tr") == 0.0
    assert cofid.numero("N") is None
    assert cofid.numero(" 2.5 ") == 2.5
    assert cofid.CODICE_RE.match("11-1145") and not cofid.CODICE_RE.match("1145")


def test_cofid_profilo_e_saturi():
    profilo = cofid.profilo_zuccheri(ALBICOCCHE_COFID, 9.8)
    assert profilo == {"fruttosio": 2.45, "glucosio": 2.45, "lattosio": None}   # 25% degli zuccheri ciascuno
    assert cofid.profilo_zuccheri({**ALBICOCCHE_COFID, "fruttosio": None}, 9.8) == {}
    assert cofid.profilo_zuccheri(ALBICOCCHE_COFID, None) == {}
    assert cofid.saturi(ALBICOCCHE_COFID, 10.0, 0.8) == 2.4                    # 10 g × 0,8 × 30%
    assert cofid.saturi({"saturi_su_acidi": 90}, 1.0, 1.0) == 0.9


def test_cofid_saturi_per_100_g_senza_percentuale():
    # CoFID con i soli saturi per 100 g: quota dei saturi sui grassi CoFID, applicata ai grassi del CREA
    salvia = {"grassi": 4.6, "saturi": 2.6, "saturi_su_acidi": None}
    assert cofid.saturi(salvia, 9.2, 0.8) == 5.2
    assert cofid.saturi({**salvia, "saturi": None}, 9.2, 0.8) is None
    assert cofid.saturi({**salvia, "grassi": 0.0}, 9.2, 0.8) is None      # grassi in tracce: quota non calcolabile
    assert cofid.saturi(salvia, None, 0.8) is None
    # La percentuale sugli acidi grassi, se c'è, ha la precedenza
    assert cofid.saturi({**salvia, "saturi_su_acidi": 50.0}, 9.2, 0.8) == 3.68


def test_cofid_zuccheri_totali():
    assert cofid.zuccheri_totali(ALBICOCCHE_COFID, 15.0) == 8.0
    assert cofid.zuccheri_totali(ALBICOCCHE_COFID, 6.0) == 6.0              # non oltre i carboidrati del CREA
    assert cofid.zuccheri_totali(ALBICOCCHE_COFID, None) == 8.0
    assert cofid.zuccheri_totali({**ALBICOCCHE_COFID, "zuccheri": None}, 15.0) is None


def test_crea_con_cofid_prima_di_usda(con_cofid):
    scheda = crea.leggi_scheda(SCHEDA_CREA, "007000")
    scheda["valori"].pop("Acidi grassi Saturi (%)")
    alimento = fonti.da_crea(scheda, USDA_ALBICOCCHE)

    # Profilo degli zuccheri CoFID riportato ai 9,8 g del CREA, non quello USDA
    assert (alimento["fruttosio"], alimento["glucosio"]) == (2.45, 2.45)
    # Il lattosio non analizzato in CoFID non si prende da USDA: profilo da una sola fonte
    assert alimento["lattosio"] is None
    assert alimento["grassi_saturi"] == round(0.1 * 0.80 * 30 / 100, 2)
    assert alimento["codice_cofid"] == "14-001"
    assert alimento["campi_cofid"] == "fruttosio,glucosio,grassi_saturi"
    assert alimento["campi_usda"] == "sodio"
    assert "CoFID 2021" in alimento["fonte_nutrienti"] and "USDA" in alimento["fonte_nutrienti"]


def scheda_senza_zuccheri():
    scheda = crea.leggi_scheda(SCHEDA_CREA, "007000")
    scheda["valori"].pop("Zuccheri solubili (g)")
    return scheda


def test_cofid_zuccheri_totali_se_mancano_in_crea_e_usda(con_cofid):
    usda_senza_zuccheri = {**USDA_ALBICOCCHE, "foodNutrients": [
        n for n in USDA_ALBICOCCHE["foodNutrients"] if n["number"] not in ("269", "212")
    ]}
    alimento = fonti.da_crea(scheda_senza_zuccheri(), usda_senza_zuccheri)

    assert alimento["zuccheri"] == 8.0
    assert (alimento["fruttosio"], alimento["glucosio"]) == (2.0, 2.0)
    assert alimento["campi_cofid"] == "zuccheri,fruttosio,glucosio"
    assert "zuccheri" not in (alimento["campi_usda"] or "")


def test_cofid_profilo_sugli_zuccheri_usda_se_il_crea_non_li_pubblica(con_cofid):
    alimento = fonti.da_crea(scheda_senza_zuccheri(), USDA_ALBICOCCHE)

    # Zuccheri totali USDA (9,24 g), con il profilo CoFID (25% fruttosio, 25% glucosio)
    assert alimento["zuccheri"] == 9.24
    assert (alimento["fruttosio"], alimento["glucosio"]) == (2.31, 2.31)
    assert alimento["campi_usda"].split(",")[0] == "zuccheri"
    assert alimento["campi_cofid"] == "fruttosio,glucosio"


def test_cofid_non_sostituisce_i_valori_crea(con_cofid):
    alimento = fonti.da_crea(crea.leggi_scheda(SCHEDA_CREA, "007000"))
    assert alimento["grassi_saturi"] == round(0.1 * 0.80 * 20 / 100, 2)   # dal CREA
    assert alimento["campi_cofid"] == "fruttosio,glucosio"


def test_cofid_estrai_excel(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    libro = openpyxl.Workbook()
    foglio = libro.active
    foglio.title = "1.3 Proximates"
    foglio.append(["Food Code", "Food Name", "Description", *list(cofid.COLONNE_EXCEL)[2:]])
    foglio.append(["11-1145", "Bread, white, average", "x", "3.0", "Tr", "0.2", "Tr", "2.8", "0", "1.9", "N", "0.4"])
    foglio.append(["99-999", "Altro", "x", *["1"] * 9])
    percorso = tmp_path / "cofid.xlsx"
    libro.save(percorso)

    righe = cofid.estrai_excel(percorso, ["11-1145"])
    assert righe == [{
        "codice": "11-1145", "nome": "Bread, white, average", "zuccheri": "3.0", "glucosio": "Tr",
        "fruttosio": "0.2", "saccarosio": "Tr", "maltosio": "2.8", "lattosio": "0", "grassi": "1.9",
        "saturi_su_acidi": "N", "saturi": "0.4",
    }]


def test_dati_cofid_del_progetto_coerenti():
    abbinati = cofid.abbinamenti()
    assert abbinati, "dati/crea_cofid.csv vuoto"
    mancanti = {codice for gruppi in abbinati.values() for codice in gruppi.values()} - set(cofid.alimenti())
    assert not mancanti, f"codici CoFID abbinati ma non in dati/cofid.csv: {mancanti}"


# ---------------------------------------------------------------
# Ricette dagli ingredienti
# ---------------------------------------------------------------

PASTA = {"categoria": "Cereali", "zuccheri": 2.0, "fruttosio": 0.1, "glucosio": 0.1, "lattosio": 0.0,
         "grassi": 1.0, "grassi_saturi": 0.2}
POMODORO = {"categoria": "Verdura", "zuccheri": 3.0, "fruttosio": 1.5, "glucosio": 1.2, "lattosio": 0.0,
            "grassi": 0.2, "grassi_saturi": 0.04}
OLIO = {"categoria": "Grassi e Oli", "zuccheri": 0.0, "grassi": 99.9, "grassi_saturi": 15.0}
MISTERO = {"categoria": "Altri Alimenti", "zuccheri": 5.0, "fruttosio": None, "glucosio": None, "lattosio": None,
           "grassi": 0.0, "grassi_saturi": 0.0}


@pytest.fixture
def ingredienti_prova(monkeypatch):
    monkeypatch.setattr(ricette, "ingredienti_crea", lambda: {
        "Pasta": "P", "Pomodoro": "T", "Olio": "O", "Sale": ricette.NESSUNO, "Mistero": "M",
    })
    return {"P": PASTA, "T": POMODORO, "O": OLIO, "M": MISTERO}


def test_ingredienti_letti_dalla_pagina_crea():
    pagina = """<td class="ingredienti"><table>
        <tr class="corporicetta"><td>PER 4 PERSONE</td><td></td></tr>
        <tr class="corporicetta"><td>Farina</td><td>570 g</td></tr>
        <tr class="corporicetta"><td>Olio extravergine di oliva</td><td>60 ml</td></tr>
        <tr class="corporicetta"><td>Latte</td><td>1 l</td></tr>
        <tr class="corporicetta"><td>Sale</td><td>q.b.</td></tr>
    </table></td>"""
    assert crea.leggi_ingredienti(pagina) == [
        {"nome": "Farina", "quantita": 570.0, "unita": "g"},
        {"nome": "Olio extravergine di oliva", "quantita": 60.0, "unita": "ml"},
        {"nome": "Latte", "quantita": 1000.0, "unita": "ml"},
    ]


def test_composizione_della_ricetta(ingredienti_prova):
    voci = [{"nome": "Pasta", "quantita": 100, "unita": "g"}, {"nome": "Pomodoro", "quantita": 200, "unita": "g"},
            {"nome": "Olio", "quantita": 10, "unita": "ml"}, {"nome": "Sale", "quantita": 5, "unita": "g"}]
    quote = ricette.composizione(voci, ingredienti_prova)
    # zuccheri: pasta 2 g + pomodoro 6 g; fruttosio 0,1 + 3 g
    assert quote["fruttosio"] == pytest.approx(3.1 / 8)
    assert quote["glucosio"] == pytest.approx(2.5 / 8)
    # grassi: pasta 1 + pomodoro 0,4 + olio 9,2 (10 ml × 0,92)
    grassi = 1 + 0.4 + 10 * ricette.DENSITA_OLI * 0.999
    assert quote["grassi_saturi"] == pytest.approx((0.2 + 0.08 + 10 * ricette.DENSITA_OLI * 0.15) / grassi)


def test_ricetta_con_ingrediente_ignoto(ingredienti_prova):
    poco = [{"nome": "Pomodoro", "quantita": 1000, "unita": "g"}, {"nome": "Mistero", "quantita": 10, "unita": "g"}]
    assert ricette.composizione(poco, ingredienti_prova)["fruttosio"] == pytest.approx(0.5)   # 0,5 g su 30: 1,6%
    tanto = [{"nome": "Pomodoro", "quantita": 100, "unita": "g"}, {"nome": "Mistero", "quantita": 100, "unita": "g"}]
    assert ricette.composizione(tanto, ingredienti_prova)["fruttosio"] is None             # 5 g su 8: troppo
    ignoto = [{"nome": "Pomodoro", "quantita": 100, "unita": "g"}, {"nome": "Brodo", "quantita": 500, "unita": "ml"}]
    assert ricette.composizione(ignoto, ingredienti_prova)["fruttosio"] is None             # non abbinato


def test_ricetta_completata(ingredienti_prova):
    ricetta = {"codice_crea": "PC9999", "alimento": "Pasta al pomodoro", "categoria": "Piatti e ricette",
               "zuccheri": 2.0, "fruttosio": None, "glucosio": None, "lattosio": 0.1, "grassi": 4.0,
               "grassi_saturi": None, "fibre": 1.0, "kcal": 120, "porzione": 250,
               "ingredienti": json.dumps([{"nome": "Pasta", "quantita": 100, "unita": "g"},
                                          {"nome": "Pomodoro", "quantita": 200, "unita": "g"}])}
    calcolati = ricette.completa(ricetta, ingredienti_prova)
    assert calcolati == ["fruttosio", "glucosio", "grassi_saturi"]   # il lattosio del CREA resta
    assert ricetta["fruttosio"] == round(3.1 / 8 * 2.0, 2)
    assert ricetta["lattosio"] == 0.1
    assert ricetta["campi_ricetta"] == "fruttosio,glucosio,grassi_saturi"
    assert ricetta["rapporto"] == round(ricetta["fruttosio"] / 1.0, 3)
    assert ricetta["rischio_malassorbimento"]
    # Ricalcolo: i campi già calcolati si aggiornano, quelli delle fonti no
    assert ricette.completa(ricetta, ingredienti_prova) == calcolati


def test_dati_ingredienti_del_progetto():
    codici = {r["codice_crea"] for r in sql("SELECT codice_crea FROM alimenti WHERE codice_crea IS NOT NULL")}
    abbinati = ricette.ingredienti_crea()
    assert abbinati
    assert {c for c in abbinati.values() if c != ricette.NESSUNO} <= codici


def test_ricette_del_database_calcolate():
    righe = sql("SELECT alimento, ingredienti, campi_ricetta, fruttosio FROM alimenti WHERE ingredienti IS NOT NULL")
    assert len(righe) >= 50
    calcolate = [r for r in righe if r["campi_ricetta"]]
    assert len(calcolate) >= 30
    assert all(r["fruttosio"] is not None for r in calcolate if "fruttosio" in r["campi_ricetta"])


def test_ricalcolo_ricette_dopo_modifica(admin):
    pasta = sql("SELECT id, fruttosio FROM alimenti WHERE codice_crea = '000800'")[0]
    sugo = sql("SELECT fruttosio, campi_ricetta FROM alimenti WHERE codice_crea = 'PC0016'")[0]
    assert "fruttosio" in (sugo["campi_ricetta"] or "")

    with applicazione.app.app_context():
        conn = archivio.get_db()
        conn.execute("UPDATE alimenti SET fruttosio = ?, glucosio = 0 WHERE id = ?", (2.0, pasta["id"]))
        conn.commit()
        conn.close()
        comune.aggiorna_ricette()

    dopo = sql("SELECT fruttosio FROM alimenti WHERE codice_crea = 'PC0016'")[0]["fruttosio"]
    assert dopo > sugo["fruttosio"]


# ---------------------------------------------------------------
# Indice glicemico, sincronizzazione USDA, scheda, import ed export
# ---------------------------------------------------------------

def test_indice_glicemico_dall_appendice():
    indici = classificazioni.indici_glicemici()
    assert len(indici) > 150
    appendice = [ig for ig in indici.values() if ig.voci_appendice]
    assert appendice and all(v.isdigit() or v.startswith("M") for ig in appendice for v in ig.voci_appendice.split(","))
    assert indici["000530"].voci_appendice == ""      # pane bianco: tabella 1


def test_sincronizzazione_non_tocca_i_crea_senza_campi_usda():
    assert usda.campi_da_aggiornare({"codice_crea": "162400", "fdc_id": 1, "campi_usda": None}) == []
    assert usda.campi_da_aggiornare({"codice_crea": None, "codice_barre": None, "fdc_id": 1, "campi_usda": None})
    assert usda.campi_da_aggiornare({"codice_crea": "007000", "campi_usda": "fruttosio"}) == ["fruttosio"]


def test_scheda_con_cofid_e_ricetta(client):
    cofid_id = sql("SELECT id FROM alimenti WHERE campi_cofid IS NOT NULL ORDER BY id LIMIT 1")[0]["id"]
    testo = solo_testo(client.get(f"/alimento/{cofid_id}").data)
    assert "CoFID 2021" in testo

    ricetta = sql("SELECT id FROM alimenti WHERE codice_crea = 'PC0016'")[0]["id"]
    html = client.get(f"/alimento/{ricetta}").data.decode()
    assert "Calcolati dagli ingredienti della ricetta CREA" in solo_testo(html.encode())
    assert "Ingredienti della ricetta CREA" in html and "Passata di pomodoro" in html


def test_scheda_indice_glicemico_appendice(client):
    codice, ig = next((c, i) for c, i in classificazioni.indici_glicemici().items() if i.voci_appendice)
    riga = sql("SELECT id FROM alimenti WHERE codice_crea = ?", (codice,))[0]
    testo = solo_testo(client.get(f"/alimento/{riga['id']}").data)
    assert "appendice, tabella A1" in testo


def test_import_riconosce_le_nuove_colonne():
    assert importazione.campo_colonna("Codice CoFID") == "codice_cofid"
    assert importazione.campo_colonna("Campi da CoFID") == "campi_cofid"
    assert importazione.campo_colonna("Campi calcolati dagli ingredienti") == "campi_ricetta"
    assert importazione.campo_colonna("Ingredienti della ricetta") == "ingredienti"


def test_form_conserva_provenienza(admin):
    riga = sql("SELECT * FROM alimenti WHERE codice_crea = 'PC0016'")[0]
    html = admin.get(f"/modifica/{riga['id']}").data.decode()
    assert 'name="ingredienti"' in html and 'name="campi_ricetta"' in html and 'id="codice_cofid"' in html


def test_api_ingredienti_come_elenco(client):
    riga = sql("SELECT id FROM alimenti WHERE codice_crea = 'PC0016'")[0]
    dati = client.get(f"/api/alimenti/{riga['id']}").get_json()
    assert isinstance(dati["ingredienti"], list) and dati["ingredienti"][0]["nome"]
    assert client.get(f"/api/alimenti/{ASPARAGI}").get_json()["ingredienti"] == []
