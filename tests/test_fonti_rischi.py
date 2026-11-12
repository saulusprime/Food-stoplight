"""Fonti esterne (CREA, USDA, Open Food Facts), classificazioni e rischi calcolati."""

import sqlite3

import pytest

import classificazioni
import crea
import fonti
import importazione
import openfoodfacts
import rischi
import sincronizzazione
import usda
from tests.aiuti import ASPARAGI, DB, messaggi, solo_testo, sql

SCHEDA_CREA = """
<h1 class="article-title" itemprop="name">
    Albicocche, fresche <meta itemprop="url" content="x" />
</h1>
<table>
<tr><td>Categoria</td><td>Frutta</td></tr><tr><td>Codice Alimento</td><td>007000</td></tr>
<tr><td>English Name</td><td>Apricots, fresh</td></tr><tr><td>Parte Edibile</td><td>94 %</td></tr>
<tr><td>Porzione</td><td>150 g</td></tr>
</table>
<table>
<tr><td>Energia (kcal)</td><td>kcal</td><td>42</td></tr>
<tr><td>Proteine (g)</td><td>g</td><td>0.4</td></tr>
<tr><td>Lipidi (g)</td><td>g</td><td>0.1</td></tr>
<tr><td>Colesterolo (mg)</td><td>mg</td><td>tr</td></tr>
<tr><td>Carboidrati disponibili (g)</td><td>g</td><td>9.8</td></tr>
<tr><td>Zuccheri solubili (g)</td><td>g</td><td>9.8</td></tr>
<tr><td>Fibra totale (g)</td><td>g</td><td>1.5</td></tr>
<tr><td>Acidi grassi Saturi (%)</td><td>%</td><td>20</td></tr>
</table>
"""

USDA_ALBICOCCHE = {
    "fdcId": 171697, "description": "Apricots, raw", "dataType": "SR Legacy",
    "foodNutrients": [
        {"number": "269", "amount": 9.24, "unitName": "G"},
        {"number": "212", "amount": 0.94, "unitName": "G"},
        {"number": "211", "amount": 2.37, "unitName": "G"},
        {"number": "307", "amount": 1.0, "unitName": "MG"},
        {"number": "203", "amount": 1.4, "unitName": "G"},
    ],
}


@pytest.fixture
def contesto(app):
    with app.app_context():
        yield


# ---------------------------------------------------------------
# CREA, USDA, Open Food Facts
# ---------------------------------------------------------------

def test_scheda_crea_letta_e_convertita():
    scheda = crea.leggi_scheda(SCHEDA_CREA, "007000")
    assert (scheda["nome"], scheda["categoria"], scheda["porzione"]) == ("Albicocche, fresche", "Frutta", 150.0)
    valori = crea.valori(scheda)
    assert valori["colesterolo"] == 0.0                     # "tr" (tracce) vale 0
    assert valori["grassi_saturi"] == round(0.1 * 0.80 * 20 / 100, 2)  # fattore FAO frutta e verdura
    assert valori["url_fonte"].endswith("/tabelle-nutrizionali/007000")
    assert "fruttosio" not in valori                        # il CREA non lo pubblica per questo alimento
    with pytest.raises(crea.ErroreCrea):
        crea.leggi_scheda(SCHEDA_CREA, "999999")


def test_crea_piu_usda_riproporziona_gli_zuccheri(contesto):
    alimento = fonti.da_crea(crea.leggi_scheda(SCHEDA_CREA, "007000"), USDA_ALBICOCCHE)
    # Fruttosio e glucosio USDA riportati ai 9,8 g di zuccheri del CREA
    assert alimento["fruttosio"] == round(0.94 * 9.8 / 9.24, 2)
    assert alimento["glucosio"] == round(2.37 * 9.8 / 9.24, 2)
    # Le proteine vengono dal CREA, il sodio (assente nel CREA) da USDA
    assert (alimento["proteine"], alimento["sodio"]) == (0.4, 1.0)
    assert alimento["campi_usda"].split(",") == ["fruttosio", "glucosio", "sodio"]
    assert alimento["fdc_id"] == 171697 and "USDA" in alimento["fonte_nutrienti"]
    assert alimento["rischio_malassorbimento"] == "Basso"   # glucosio > fruttosio
    assert alimento["nova"] == 1 and alimento["tef_kcal"] > 0


def test_regole_zuccheri_per_composizione():
    carne = {"zuccheri": 0.5}
    fonti.regole_zuccheri(carne, "Carni fresche", "Manzo")
    assert (carne["fruttosio"], carne["lattosio"]) == (0.0, 0.0)
    latte = {"zuccheri": 4.9}
    fonti.regole_zuccheri(latte, "Latte e yogurt", "Latte di vacca, intero")
    assert (latte["fruttosio"], latte["lattosio"]) == (0.0, 4.9)
    yogurt = {"zuccheri": 10.5}
    fonti.regole_zuccheri(yogurt, "Latte e yogurt", "Yogurt da latte intero, alla frutta")
    assert "fruttosio" not in yogurt                        # zuccheri aggiunti: serve il dato misurato


def test_usda_valori_carboidrati_disponibili():
    valori = usda.valori({"foodNutrients": [
        {"number": "205", "amount": 11.1, "unitName": "G"},
        {"number": "291", "amount": 2.0, "unitName": "G"},
        {"number": "958", "amount": 50, "unitName": "KCAL"},
    ]})
    assert (valori["carboidrati"], valori["fibre"], valori["kcal"]) == (9.1, 2.0, 50.0)
    assert usda.chiave_valida("abc") and not usda.chiave_valida("DEMO_KEY") and not usda.chiave_valida("")
    assert usda.leggi_campi("fruttosio, xyz,glucosio") == ["fruttosio", "glucosio"]


def test_open_food_facts_valori():
    prodotto = {
        "code": "8076800195057", "product_name_it": "Spaghetti n.5", "brands": "Barilla", "nova_group": 1,
        "serving_quantity": "85", "categories_tags": ["en:cereals-and-potatoes", "en:pastas"],
        "nutriments": {"energy-kcal_100g": 359, "carbohydrates_100g": 71, "sodium_100g": 0.004,
                       "vitamin-c_100g": 0.001, "alcohol_100g": 5},
    }
    valori = openfoodfacts.valori(prodotto)
    assert valori["alimento"] == "Spaghetti n.5 (Barilla)"
    assert (valori["categoria"], valori["nova"], valori["porzione"]) == ("Cereali", 1, 85.0)
    assert (valori["sodio"], valori["vitamina_c"], valori["alcol"]) == (4.0, 1.0, 3.95)
    assert valori["url_fonte"] == "https://world.openfoodfacts.org/product/8076800195057"
    with pytest.raises(openfoodfacts.ErroreOpenFoodFacts):
        openfoodfacts.scarica("12ab")


# ---------------------------------------------------------------
# Classificazioni
# ---------------------------------------------------------------

@pytest.mark.parametrize(("nome", "categoria", "gruppo"), [
    ("Mele, fresche", "Frutta", 1),
    ("Olio di oliva extra vergine", "Grassi e Oli", 2),
    ("Parmigiano Reggiano DOP", "Latticini e Uova", 3),
    ("Bevanda alcolica, Birra chiara", "Bevande", 3),
    ("Merendine, tipo brioche, industriale", "Dolci e Snack", 4),
    ("Lasagne al forno", "Piatti e ricette", None),
])
def test_nova_per_regole(nome, categoria, gruppo):
    assert classificazioni.gruppo_nova({"alimento": nome, "categoria": categoria}) == gruppo


def test_carne_rossa_lavorata_e_frattaglie():
    def carne(nome):
        return {"alimento": nome, "categoria": "Carne"}

    assert classificazioni.e_carne_lavorata(carne("Prosciutto crudo di Parma"))
    assert classificazioni.e_carne_rossa(carne("Bovino adulto, filetto, crudo"))
    assert not classificazioni.e_carne_rossa(carne("Fegato di bovini"))
    assert not classificazioni.e_carne_rossa(carne("Pollo, petto, crudo"))


def test_fodmap_misurati_e_da_letteratura():
    misurato = classificazioni.fodmap({"alimento": "Mela", "porzione": 150, "fruttosio": 5.9, "glucosio": 2.4,
                                       "lattosio": 0})
    assert (misurato["fodmap_fruttosio"], misurato["fodmap_lattosio"]) == ("Alto", "Basso")
    assert classificazioni.fodmap({"alimento": "Lenticchie, secche"})["fodmap_gos"] == "Alto"
    assert set(classificazioni.fodmap({"alimento": "Sogliola", "categoria": "Pesce", "carboidrati": 0}).values()) \
        == {"Basso"}
    assert classificazioni.fodmap({"alimento": "Fragole"})["fodmap_polioli"] is None


def test_zuccheri_liberi():
    assert classificazioni.zuccheri_liberi({"alimento": "Mele", "categoria": "Frutta", "zuccheri": 10, "nova": 1}) == 0
    assert classificazioni.zuccheri_liberi({"alimento": "Arance succo", "categoria": "Frutta", "zuccheri": 8}) == 8
    assert classificazioni.zuccheri_liberi({"alimento": "Latte intero", "categoria": "Latticini e Uova",
                                            "zuccheri": 4.9}) == 0


# ---------------------------------------------------------------
# Rischi
# ---------------------------------------------------------------

def livelli(alimento):
    valori = dict(alimento)
    rischi.assegna(valori)
    return {campo: valori[campo] for campo in rischi.REGOLE}


def test_rischi_dalle_regole(contesto):
    salame = livelli({"alimento": "Salame Milano", "categoria": "Carne", "kcal": 425, "grassi": 35,
                      "grassi_saturi": 12, "carboidrati": 0, "zuccheri": 0, "sodio": 1500, "nova": 3})
    assert salame["rischio_tumorale"] == "Alto"            # carne lavorata, IARC gruppo 1
    assert salame["rischio_colesterolo"] == "Alto"         # saturi oltre 5 g
    assert salame["rischio_metabolico"] == "Alto"          # oltre 275 kcal per 100 g
    assert salame["rischio_diabete"] == "Trascurabile"

    vino = livelli({"alimento": "Vino rosso", "categoria": "Bevande", "kcal": 75, "alcol": 10, "zuccheri": 0})
    assert vino["rischio_tumorale"] == "Alto"

    lenticchie = livelli({"alimento": "Lenticchie", "categoria": "Legumi/Frutta Secca", "kcal": 291,
                          "carboidrati": 51, "zuccheri": 1.8, "fibre": 13.8, "indice_glicemico": 32,
                          "porzione": 50, "nova": 1, "grassi": 1, "grassi_saturi": 0.2})
    # Carico glicemico 32 × 25,5 g ÷ 100 = 8,2 (Basso), meno un livello per le fibre
    assert lenticchie["rischio_diabete"] == "Trascurabile"
    assert lenticchie["rischio_tumorale"] == "Trascurabile"  # fonte di fibre

    assert livelli({"alimento": "Senza dati"})["rischio_colesterolo"] == ""


@pytest.mark.parametrize(("fruttosio", "glucosio", "livello"), [
    (0.1, 0.0, "Trascurabile"),   # 0,1 g nella porzione da 100 g: sotto 0,15 g
    (5.0, 6.0, "Basso"),          # bilanciato dal glucosio
    (3.1, 3.0, "Basso"),          # eccesso 0,1 g, entro la soglia
    (3.25, 3.0, "Medio"),         # eccesso 0,25 g: con mezza porzione sotto la soglia
    (5.9, 2.4, "Alto"),
])
def test_scala_malassorbimento(contesto, fruttosio, glucosio, livello):
    assert livelli({"alimento": "x", "fruttosio": fruttosio, "glucosio": glucosio})["rischio_malassorbimento"] == livello


def test_motivi_e_fonti(contesto):
    valutazione = rischi.valuta({"alimento": "Prosciutto crudo", "categoria": "Carne", "grassi_saturi": 7})
    tumorale = valutazione["rischio_tumorale"]
    assert tumorale["livello"]["etichetta"] == "Alto"
    assert "IARC" in tumorale["motivi"][0] and "iarc_carni" in tumorale["fonti"]
    assert all(chiave in rischi.RIFERIMENTI for esito in valutazione.values() for chiave in esito["fonti"])


# ---------------------------------------------------------------
# Web: form, scheda, import, sincronizzazione
# ---------------------------------------------------------------

def test_form_compila_da_una_fonte(admin, monkeypatch):
    trovato = {"alimento": "Spaghetti n.5 (Barilla)", "categoria": "Cereali", "kcal": 359.0,
               "codice_barre": "8076800195057", "fonte_nutrienti": openfoodfacts.FONTE}
    monkeypatch.setattr(fonti, "cerca", lambda fonte, codice, api_key=None: trovato)
    contenuto = admin.get("/nuovo?fonte=off&codice=8076800195057").data.decode()
    assert 'value="Spaghetti n.5 (Barilla)"' in contenuto and 'value="8076800195057"' in contenuto
    assert "controllali e salva" in contenuto

    def errore(*_a, **_k):
        raise fonti.ErroreFonte("Prodotto 1 non trovato su Open Food Facts.")

    monkeypatch.setattr(fonti, "cerca", errore)
    assert "Dati non presi dalla fonte" in admin.get("/nuovo?fonte=off&codice=12345678").data.decode()


def test_form_mostra_i_rischi_calcolati(admin):
    contenuto = solo_testo(admin.get(f"/modifica/{ASPARAGI}").data)
    assert "si calcolano dai valori nutrizionali" in contenuto
    assert "Fruttosio in eccesso sul glucosio" in contenuto
    assert 'name="rischio_diabete"' not in admin.get(f"/modifica/{ASPARAGI}").data.decode()


def test_import_ignora_le_colonne_dei_rischi():
    letto = importazione.leggi_file("x.csv", b"Alimento;Categoria;Kcal;Rischio Tumorale\nProva;Test;50;Alto\n")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    voci = importazione.pianifica(conn, letto, "aggiungi")
    conn.close()
    assert voci[0]["valori"]["rischio_tumorale"] == "Basso"


def test_pagina_import_e_sincronizzazione(admin, app, monkeypatch):
    contenuto = solo_testo(admin.get("/importa").data)
    assert "Sincronizzazione con USDA FoodData Central" in contenuto
    assert "DEMO_KEY non basta" in contenuto

    admin.post("/sincronizza")
    assert any("chiave USDA personale" in m for m in messaggi(admin))

    avviate = []
    monkeypatch.setitem(app.config, "USDA_API_KEY", "chiave-di-prova")
    monkeypatch.setattr(sincronizzazione, "avvia_in_background", lambda *a: avviate.append(a) or True)
    admin.post("/sincronizza")
    assert avviate and any("avviata" in m for m in messaggi(admin))


def test_sincronizzazione_una_alla_volta(tmp_path):
    percorso = str(tmp_path / "alimenti.db")
    open(percorso, "w").close()

    with sincronizzazione._blocco(percorso):
        assert sincronizzazione.in_corso(percorso)

        with pytest.raises(sincronizzazione.GiaInCorso):
            sincronizzazione.esegui(percorso, str(tmp_path / "backup"), "chiave")

    assert not sincronizzazione.in_corso(percorso)


def test_sincronizzazione_automatica_solo_con_chiave():
    assert not sincronizzazione.avvia_automatica(str(DB), "x", "DEMO_KEY", 30)
    assert not sincronizzazione.avvia_automatica(str(DB), "x", "chiave", 0)


def test_guida_con_regole_e_riferimenti(client):
    contenuto = solo_testo(client.get("/guida").data)
    assert "Atkinson" in contenuto and "Varney" in contenuto and "IARC" in contenuto
    assert "Tabelle di composizione degli alimenti del CREA" in contenuto


def test_scheda_mostra_indice_glicemico_e_fonte(client):
    mele = sql("SELECT id FROM alimenti WHERE codice_crea = '007120'")[0]["id"]
    contenuto = solo_testo(client.get(f"/alimento/{mele}").data)
    assert "voce «Apple, raw»" in contenuto


@pytest.fixture
def usda_rifiuta(monkeypatch):
    """USDA rifiuta le richieste; le pagine CREA non devono nemmeno essere lette."""
    def rifiuta(*_args, **_kwargs):
        raise usda.ErroreUsda("Limite di richieste USDA raggiunto: riprova più tardi o usa una chiave personale.")

    def non_leggere(*_args, **_kwargs):
        raise AssertionError("pagine CREA lette nonostante l'errore USDA")

    monkeypatch.setattr(usda, "scarica", rifiuta)
    monkeypatch.setattr(crea, "scarica_schede", non_leggere)
    return sql("SELECT codice_crea FROM alimenti WHERE fdc_id IS NOT NULL AND codice_crea IS NOT NULL "
               "ORDER BY codice_crea LIMIT 1")[0]["codice_crea"]


def test_import_crea_si_ferma_se_usda_non_risponde(usda_rifiuta):
    # Riscritti senza USDA, gli alimenti abbinati perderebbero fruttosio, FDC ID e gli altri campi presi da lì
    prima = dict(sql("SELECT * FROM alimenti WHERE codice_crea = ?", (usda_rifiuta,))[0])
    conn = sqlite3.connect(DB)

    try:
        with pytest.raises(usda.ErroreUsda):
            fonti.importa_crea(conn, [usda_rifiuta], "2026-11-11 10:00:00")
        conn.commit()
    finally:
        conn.close()

    assert dict(sql("SELECT * FROM alimenti WHERE codice_crea = ?", (usda_rifiuta,))[0]) == prima


def test_comando_crea_importa_annullato_se_usda_non_risponde(app, usda_rifiuta):
    esito = app.test_cli_runner().invoke(args=["crea-importa", usda_rifiuta])
    assert esito.exit_code != 0
    assert "Import annullato prima di leggere il CREA, nessuna modifica scritta" in esito.output
