"""Piano settimanale dei pasti: posti, bilanciamento dei rischi, modifiche con ribilanciamento, pagine."""

import re

import pytest

import analisi
import piano
import profilo
from tests.aiuti import messaggi, solo_testo, sql

T, B, M, A = "Trascurabile", "Basso", "Medio", "Alto"


def piatto(id_, nome, portata, rischi=(T,) * 5, kcal=100.0):
    """Piatto di prova: porzione da 100 g, quindi peso nel bilanciamento = kcal."""
    return {
        "id": id_, "alimento": nome, "portata": portata, "kcal": kcal, "porzione": 100.0,
        **dict(zip(analisi.CAMPI_RISCHIO, rischi, strict=True)),
    }


def piano_di(cliente):
    with cliente.session_transaction() as sessione:
        return dict(sessione.get("piano") or {})


def portata_di(alimento_id):
    return sql("SELECT portata FROM pasti_pronti WHERE alimento_id = ?", (alimento_id,))[0]["portata"]


# ---------------------------------------------------------------
# Posti e costo
# ---------------------------------------------------------------

def test_posti():
    posti = piano.posti(2, {"cena": ["contorno", "secondo"], "pranzo": ["primo"], "colazione": ["primo"]})
    assert posti == [(0, "pranzo", "primo"), (0, "cena", "secondo"), (0, "cena", "contorno"),
                     (1, "pranzo", "primo"), (1, "cena", "secondo"), (1, "cena", "contorno")]
    assert len(piano.posti(99, piano.PORTATE_PREDEFINITE)) == piano.GIORNI_MAX * 4
    assert piano.posti(3, {}) == []


def test_tolleranza():
    assert piano.migliore((0, 0, 0, 1.0), (0, 0, 0, 1.06))
    assert not piano.migliore((0, 0, 0, 1.0), (0, 0, 0, 1.04))        # entro la tolleranza: pari
    assert piano.migliore((0, 0, 0, 9.0), (0, 0, 1, 0.0))             # prima le collisioni
    assert piano.migliore((0, 3, 2, 9.0), (1, 0, 0, 0.0))             # prima i piatti alti per te


# ---------------------------------------------------------------
# Bilanciamento
# ---------------------------------------------------------------

def test_rischi_distribuiti_tra_i_piatti():
    # Con un primo a diabete Medio, il secondo con un altro rischio Medio fa medie 1 e 1
    # (quadrati 2) invece di 2 e 0 (quadrati 4)
    piatti = [
        piatto(1, "Primo", "primo", (M, T, T, T, T)),
        piatto(2, "Secondo dolce", "secondo", (M, T, T, T, T)),
        piatto(3, "Secondo grasso", "secondo", (T, M, T, T, T)),
    ]
    posti = piano.posti(1, {"pranzo": ["primo", "secondo"]})
    assert piano.ribilancia(piatti, posti, [1, None], fissi=[0]) == [1, 3]


def test_mai_lo_stesso_rischio_alto_due_volte_nello_stesso_giorno():
    piatti = [
        piatto(1, "Pasta", "primo", (A, T, T, T, T)),
        piatto(2, "Riso", "primo", (A, T, T, T, T)),
        piatto(3, "Polenta fritta", "secondo", (A, T, T, T, T), kcal=50),
        piatto(4, "Pollo", "secondo", (B, B, B, B, B), kcal=400),
    ]
    scelti = piano.genera(piatti, piano.posti(1, {"pranzo": ["primo", "secondo"]}))
    # Il pollo ha medie più alte, ma la polenta darebbe diabete Alto due volte nello stesso giorno
    assert scelti[1] == 4


def test_genera_senza_ripetizioni_e_ripetibile_con_il_seme():
    piatti = [piatto(i, f"Primo {i}", "primo") for i in range(1, 8)] + [
        piatto(10 + i, f"Contorno {i}", "contorno") for i in range(1, 8)]
    posti = piano.posti(3, {"pranzo": ["primo", "contorno"]})
    scelti = piano.genera(piatti, posti, seme=7)

    assert len(scelti) == 6 and len(set(scelti)) == 6
    assert all(piatti_per_id(piatti)[i]["portata"] == posto[2] for i, posto in zip(scelti, posti, strict=True))
    assert piano.genera(piatti, posti, seme=7) == scelti
    # Piatti tutti pari: semi diversi danno piani diversi
    assert len({tuple(piano.genera(piatti, posti, seme=s)) for s in range(10)}) > 1


def piatti_per_id(piatti):
    return {p["id"]: p for p in piatti}


def test_portata_senza_piatti_o_con_pochi_piatti():
    piatti = [piatto(1, "Unico primo", "primo")]
    scelti = piano.genera(piatti, piano.posti(2, {"pranzo": ["primo", "antipasto"]}))
    assert scelti == [None, 1, None, 1]       # senza antipasti; il primo si ripete: non ce ne sono altri


def test_profilo_prima_i_piatti_adatti():
    piatti = [
        piatto(1, "Pasta", "primo", (A, T, T, T, T), kcal=100),
        piatto(2, "Zuppa", "primo", (M, T, T, T, T), kcal=600),
        piatto(3, "Gnocchi", "primo", (A, T, T, T, T), kcal=100),
    ]
    posti = piano.posti(2, {"pranzo": ["primo"]})
    # Senza profilo il diabete Alto della pasta pesa poco (poche Kcal); con il diabete si usa
    # prima la zuppa, poi un piatto Alto per te perché gli altri non bastano
    con_profilo = piano.genera(piatti, posti, ("diabete",))
    assert 2 in con_profilo
    assert sum(1 for i in con_profilo if profilo.punti_per_te(piatti[i - 1]["rischio_diabete"]) == 3) == 1


def test_ribilancia_con_meno_cambi_e_senza_doppioni():
    piatti = [piatto(i, f"Primo {i}", "primo") for i in range(1, 6)]
    posti = piano.posti(4, {"pranzo": ["primo"]})
    scelti = piano.genera(piatti, posti)

    # Piatti tutti pari: niente da migliorare, il piano resta com'è
    assert piano.ribilancia(piatti, posti, scelti) == scelti

    # Un piatto scelto a mano che era già nel piano: l'altro posto cambia
    doppio = [scelti[1], *scelti[1:]]
    ribilanciato = piano.ribilancia(piatti, posti, doppio, fissi=[0])
    assert ribilanciato[0] == scelti[1] and len(set(ribilanciato)) == 4

    # I posti fissi non cambiano, quelli vuoti si riempiono
    assert piano.ribilancia(piatti, posti, [5, None, None, None], fissi=[0])[0] == 5
    assert None not in piano.ribilancia(piatti, posti, [5, None, None, None], fissi=[0])


def test_alternative_e_successivo():
    piatti = [
        piatto(1, "Buono", "secondo", (T, T, T, T, T)),
        piatto(2, "Medio", "secondo", (B, B, T, T, T)),
        piatto(3, "Pesante", "secondo", (M, M, M, T, T)),
        piatto(4, "Altro giorno", "secondo", (T, T, T, T, T)),
        piatto(9, "Primo", "primo"),
    ]
    posti = piano.posti(2, {"cena": ["secondo"]})
    scelti = [1, 4]

    # Dal più bilanciato; il piatto dell'altro giorno è escluso
    assert piano.alternative(piatti, posti, scelti, 0) == [1, 2, 3]
    assert piano.successivo(piatti, posti, scelti, 0) == 2
    assert piano.successivo(piatti, posti, [3, 4], 0) == 1             # dopo l'ultimo si ricomincia
    assert piano.alternative(piatti, posti, scelti, 5) == []
    assert piano.successivo(piatti[:2], posti[:1], [1], 0) == 2
    assert piano.successivo(piatti[:1], posti[:1], [1], 0) is None     # nessun altro piatto


# ---------------------------------------------------------------
# Pagine
# ---------------------------------------------------------------

def test_genera_il_piano(client):
    assert "Nessun piano" in solo_testo(client.get("/piano").data)

    client.post("/piano/genera", data={"inizio": "2026-11-16", "giorni": "7",
                                       "portate_pranzo": ["primo", "contorno"], "portate_cena": ["secondo", "contorno"]})
    dati = piano_di(client)
    posti = piano.posti(7, piano.PORTATE_PREDEFINITE)

    assert len(dati["piatti"]) == 28 and len(set(dati["piatti"])) == 28 and dati["fissi"] == []
    assert all(portata_di(i) == posto[2] for i, posto in zip(dati["piatti"], posti, strict=True))
    assert any("Piano pronto: 28 piatti" in m for m in messaggi(client))

    testo = solo_testo(client.get("/piano").data)
    assert "Lunedì 16 novembre" in testo and "Domenica 22 novembre" in testo
    assert "Rischi giorno per giorno" in testo and "Profilo di rischio della settimana" in testo
    assert "Grammi crudi per 1 persona" in testo
    html = client.get("/piano").data.decode()
    assert '<datalist id="piatti-primo">' in html and 'id="posto-27"' in html

    # Le opzioni restano per il piano successivo
    assert re.search(r'name="portate_cena"\s+value="secondo" checked', html) and 'value="2026-11-16"' in html
    assert not re.search(r'name="portate_cena"\s+value="primo" checked', html)


def test_genera_senza_portate_o_con_pochi_giorni(client):
    client.post("/piano/genera", data={"giorni": "3"})
    assert piano_di(client)["piatti"] == [] and any("almeno una portata" in m for m in messaggi(client))

    client.post("/piano/genera", data={"giorni": "3", "portate_pranzo": ["primo"]})
    assert len(piano_di(client)["piatti"]) == 3


def test_cambia_scegli_libera(client):
    client.post("/piano/genera", data={"giorni": "7", "portate_pranzo": ["primo"], "portate_cena": ["secondo"]})
    prima = piano_di(client)["piatti"]

    risposta = client.post("/piano/cambia/0")
    assert risposta.headers["Location"].endswith("/piano#posto-0")
    dati = piano_di(client)
    assert dati["piatti"][0] != prima[0] and portata_di(dati["piatti"][0]) == "primo" and dati["fissi"] == [0]

    carbonara = sql("SELECT alimento_id FROM pasti_pronti WHERE nome = 'Spaghetti alla carbonara'")[0]["alimento_id"]
    client.post("/piano/scegli/2", data={"piatto": "spaghetti alla CARBONARA"})
    dati = piano_di(client)
    assert dati["piatti"][2] == carbonara and dati["fissi"] == [0, 2]
    assert dati["piatti"].count(carbonara) == 1

    client.post("/piano/scegli/1", data={"piatto": "Spaghetti alla carbonara"})      # è un primo, non un secondo
    assert any("Piatto non trovato" in m for m in messaggi(client)) and piano_di(client)["fissi"] == [0, 2]

    client.post("/piano/libera/0")
    assert piano_di(client)["fissi"] == [2]

    assert client.post("/piano/cambia/99").status_code == 302             # posto inesistente
    assert "scelto da te" in solo_testo(client.get("/piano").data)


def test_profilo_diabete_primi_alti_solo_se_servono(client):
    with client.session_transaction() as sessione:
        sessione["profilo"] = "diabete"

    client.post("/piano/genera", data={"giorni": "7", "portate_pranzo": ["primo"]})
    primi = sql("SELECT a.id, a.rischio_diabete FROM pasti_pronti p JOIN alimenti a ON a.id = p.alimento_id "
                "WHERE p.portata = 'primo'")
    alti = {r["id"] for r in primi if r["rischio_diabete"] == "Alto"}
    adatti = len(primi) - len(alti)

    scelti = piano_di(client)["piatti"]
    assert sum(1 for i in scelti if i in alti) == max(0, 7 - adatti)

    if adatti < 7:
        assert "sono Alto per te" in solo_testo(client.get("/piano").data)


def test_persone_testo_e_svuota(client):
    client.post("/piano/genera", data={"giorni": "2", "inizio": "2026-11-16",
                                       "portate_pranzo": ["primo"], "portate_cena": ["secondo"]})
    client.post("/piano/persone", data={"persone": "3"})
    assert piano_di(client)["persone"] == 3

    risposta = client.get("/piano/testo")
    assert risposta.mimetype == "text/plain" and "piano-dei-pasti.txt" in risposta.headers["Content-Disposition"]
    testo = risposta.data.decode()
    assert testo.startswith("Piano dei pasti dal 16/11/26\n\nLunedì 16 novembre\nPranzo\n- Primo: ")
    assert "\nIngredienti per 3 persone\n" in testo and " g\n" in testo

    inglese = client.get("/piano/testo", headers={"Accept-Language": "en"})
    assert "meal-plan.txt" in inglese.headers["Content-Disposition"]
    assert "\nMonday 16 November\nLunch\n- First course: " in inglese.data.decode()

    client.post("/piano/svuota")
    dati = piano_di(client)
    assert dati["piatti"] == [] and dati["persone"] == 3


def test_piano_in_sessione_non_valido(client):
    with client.session_transaction() as sessione:
        sessione["piano"] = {"giorni": "x", "portate": 5, "piatti": ["a", True], "fissi": [9], "inizio": 3}

    assert client.get("/piano").status_code == 200
    assert client.post("/piano/cambia/0").status_code == 302


@pytest.mark.parametrize("url", ["/sw.js", "/offline", "/guida", "/"])
def test_piano_offline_menu_e_guida(client, url):
    html = client.get(url).data.decode()
    atteso = {"/sw.js": "/^piano$/", "/offline": 'href="/piano"', "/guida": 'id="piano"', "/": 'href="/piano"'}
    assert atteso[url] in html
