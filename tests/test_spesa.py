"""Lista della spesa a semaforo verde: regole di scelta, generazione, modifiche, testo, pagine."""

import pytest

import analisi
import spesa
from tests.aiuti import id_di, messaggi, solo_testo, sql

T, B, M, A = "Trascurabile", "Basso", "Medio", "Alto"


def alimento(id_, nome, categoria="Verdura", rischi=(T,) * 5, porzione=200.0):
    return {
        "id": id_, "alimento": nome, "categoria": categoria, "porzione": porzione,
        "punteggio": analisi.calcola_punteggio(*rischi), **dict(zip(analisi.CAMPI_RISCHIO, rischi, strict=True)),
    }


def lista_di(cliente):
    with cliente.session_transaction() as sessione:
        return list(sessione.get("spesa", []))


# ---------------------------------------------------------------
# Regole
# ---------------------------------------------------------------

def test_verde_proponibile_e_tipo():
    assert spesa.verde(alimento(1, "Carote", rischi=(T, T, T, B, B)))           # punteggio 87
    assert not spesa.verde(alimento(1, "Carote", rischi=(B, B, B, B, T)))       # punteggio 73: giallo
    assert not spesa.verde(alimento(1, "Pane", rischi=(M, T, T, T, T)))         # un rischio Medio
    assert spesa.accettabile(alimento(1, "Pane", rischi=(M, T, T, T, T)))
    assert not spesa.accettabile(alimento(1, "Olio", rischi=(T, A, T, A, T)))  # rischi alti
    assert not spesa.accettabile(alimento(1, "Cicoria", rischi=(T, T, None, T, T)))   # non classificato

    assert not spesa.acquistabile(alimento(1, "Fagioli, Borlotti, freschi, cotti, bolliti"))
    assert spesa.acquistabile(alimento(1, "Prosciutto cotto"))                  # «cotto» è il nome del prodotto
    assert not spesa.acquistabile(alimento(1, "Hummus", categoria="Piatti e ricette"))
    assert not spesa.proponibile(alimento(1, "Basilico, fresco", porzione=5.0))  # erbe e condimenti
    assert spesa.proponibile(alimento(1, "Carote", porzione=None))              # senza porzione: 100 g

    assert spesa.tipo(alimento(1, "Mele, golden, fresche")) == "mele"
    assert spesa.tipo(alimento(1, "Àgrumi misti")) == "agrumi"


def test_candidati_verdi_prima_un_tipo_ciascuno_e_profilo():
    alimenti = [
        alimento(1, "Zucchine, crude", rischi=(B, T, T, T, T)),         # 93
        alimento(2, "Carote, crude", rischi=(T, T, T, T, T)),           # 100
        alimento(3, "Carote, novelle, crude", rischi=(T, T, T, T, T)),  # stesso tipo: fuori
        alimento(4, "Patate, crude", rischi=(M, T, T, T, T)),           # non verde: in fondo
        alimento(5, "Mele", categoria="Frutta"),                        # altro reparto
        alimento(6, "Cipolle, crude", rischi=(T, T, A, T, T)),          # rischio alto: mai
    ]
    assert [a["id"] for a in spesa.candidati(alimenti, "Verdura")] == [2, 1, 4]

    # Carote con malassorbimento Basso: punteggio 93 come le zucchine, prima per nome;
    # con il profilo «fruttosio» prima le zucchine, che lì sono Trascurabili
    for carote in alimenti[1:3]:
        carote["rischio_malassorbimento"] = B
        carote["punteggio"] = analisi.calcola_punteggio(T, T, B, T, T)
    assert [a["id"] for a in spesa.candidati(alimenti, "Verdura")] == [2, 1, 4]
    assert [a["id"] for a in spesa.candidati(alimenti, "Verdura", ("fruttosio",))] == [1, 2, 4]


def test_genera_reparti_ordinati_e_completati():
    alimenti = [
        alimento(1, "Mele", categoria="Frutta"),
        alimento(2, "Carote"), alimento(3, "Zucchine"), alimento(4, "Finocchi"),
        alimento(5, "Pane integrale", categoria="Cereali", rischi=(M, T, T, B, T)),
        alimento(6, "Olio di oliva", categoria="Grassi e Oli", rischi=(T, A, T, A, T)),
    ]
    ids = spesa.genera(alimenti, ["Grassi e Oli", "Frutta", "Cereali", "Verdura"], per_reparto=2)
    # Ordine del supermercato; i cereali senza verdi con la scelta migliore; niente oli (rischi alti)
    assert ids == [2, 4, 1, 5]

    # Con un seme: verdi scelti a caso nel reparto, sempre gli stessi con lo stesso seme
    con_seme = spesa.genera(alimenti, ["Verdura"], per_reparto=2, seme=42)
    assert len(con_seme) == 2 and set(con_seme) <= {2, 3, 4}
    assert spesa.genera(alimenti, ["Verdura"], per_reparto=2, seme=42) == con_seme

    assert spesa.genera(alimenti, ["Verdura"], per_reparto=99) == [2, 4, 3]     # al massimo i candidati


def test_sostituto():
    carote, finocchi, zucchine = alimento(2, "Carote"), alimento(3, "Finocchi"), alimento(4, "Zucchine")
    patate = alimento(5, "Patate", rischi=(M, T, T, T, T))
    alimenti = [carote, finocchi, zucchine, patate]

    assert spesa.sostituto(alimenti, carote, [2])["id"] == 3
    assert spesa.sostituto(alimenti, carote, [2, 3])["id"] == 4          # finocchi già in lista
    assert spesa.sostituto(alimenti, zucchine, [4])["id"] == 2           # dopo l'ultimo si ricomincia
    assert spesa.sostituto(alimenti, patate, [5])["id"] == 2             # non verde: il primo verde
    assert spesa.sostituto(alimenti, patate, [5, 2, 3, 4]) is None       # verdi tutti in lista

    # Reparto senza verdi (cereali): si passa al successivo non verde
    pane, riso = (alimento(i, nome, categoria="Cereali", rischi=(M, T, T, T, T)) for i, nome in ((6, "Pane"), (7, "Riso")))
    assert spesa.sostituto([pane, riso], pane, [6])["id"] == 7


def test_raggruppa_e_testo():
    voci = [alimento(1, "Mele", categoria="Frutta"), alimento(2, "Carote"), alimento(3, "Zucchine")]
    gruppi = spesa.raggruppa(voci)
    assert [(r, [v["id"] for v in vv]) for r, vv in gruppi] == [("Verdura", [2, 3]), ("Frutta", [1])]
    assert spesa.testo(gruppi, "Spesa", str.upper) == "Spesa\n\nVERDURA\n- Carote\n- Zucchine\n\nFRUTTA\n- Mele\n"


# ---------------------------------------------------------------
# Pagine
# ---------------------------------------------------------------

def test_genera_la_lista(client):
    assert "La lista è vuota" in solo_testo(client.get("/spesa").data)

    client.post("/spesa/genera", data={"reparti": ["Verdura", "Frutta", "Grassi e Oli"], "per_reparto": "2"})
    ids = lista_di(client)
    assert 0 < len(ids) <= 4
    assert any("Grassi e Oli" in m for m in messaggi(client))         # niente senza rischi alti

    righe = {r["id"]: dict(r) for r in sql(
        f"SELECT * FROM alimenti WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))}
    for riga in righe.values():
        riga["punteggio"] = analisi.calcola_punteggio(*(riga[c] for c in analisi.CAMPI_RISCHIO))
        assert spesa.proponibile(riga) and riga["categoria"] in ("Verdura", "Frutta")

    html = client.get("/spesa").data.decode()
    assert f"{len(ids)} alimenti nella lista della spesa" in html and "data-spesa-preso" in html

    # Le opzioni restano per la lista successiva
    assert 'value="Grassi e Oli" checked' in html and '<option value="2" selected>' in html


def test_genera_senza_reparti(client):
    client.post("/spesa/genera", data={"per_reparto": "3"})
    assert lista_di(client) == [] and any("almeno un reparto" in m for m in messaggi(client))


def test_aggiungi_alternativa_cambia_togli_svuota(client):
    burro = id_di("Parmigiano Reggiano DOP")       # colesterolo Alto: non verde
    client.post("/spesa/aggiungi", data={"cerca": f"Parmigiano Reggiano DOP · Latticini e Uova · #{burro}"})
    assert lista_di(client) == [burro]

    client.post("/spesa/aggiungi", data={"alimento_id": burro})
    assert any("già nella lista" in m for m in messaggi(client))

    html = client.get("/spesa").data.decode()
    assert "non verde" in solo_testo(html.encode()) and "alternativa verde" in html
    alternativa = int(html.split('name="con" value="')[1].split('"')[0])

    client.post(f"/spesa/cambia/{burro}", data={"con": alternativa})
    assert lista_di(client) == [alternativa]

    client.post(f"/spesa/cambia/{alternativa}")
    cambiato = lista_di(client)
    assert len(cambiato) == 1 and cambiato != [alternativa]

    client.post(f"/spesa/togli/{cambiato[0]}")
    assert lista_di(client) == []

    client.post("/spesa/aggiungi", data={"alimento_id": burro})
    with client.session_transaction() as sessione:
        versione = sessione.get("spesa_versione")
    client.post("/spesa/svuota")
    with client.session_transaction() as sessione:
        assert "spesa" not in sessione and sessione["spesa_versione"] != versione


def test_scarica_testo(client):
    client.post("/spesa/aggiungi", data={"alimento_id": id_di("Parmigiano Reggiano DOP")})
    risposta = client.get("/spesa/testo")
    assert risposta.mimetype == "text/plain" and "lista-della-spesa.txt" in risposta.headers["Content-Disposition"]
    testo = risposta.data.decode()
    assert testo.startswith("Lista della spesa del ") and "\nLatticini e Uova\n- Parmigiano Reggiano DOP\n" in testo

    inglese = client.get("/spesa/testo", headers={"Accept-Language": "en"})
    assert "shopping-list.txt" in inglese.headers["Content-Disposition"]
    assert inglese.data.decode().startswith("Shopping list of ")


@pytest.mark.parametrize("url", ["/sw.js", "/offline", "/guida", "/"])
def test_spesa_offline_menu_e_guida(client, url):
    html = client.get(url).data.decode()
    atteso = {"/sw.js": "/^spesa$/", "/offline": 'href="/spesa"', "/guida": 'id="spesa"', "/": 'href="/spesa"'}
    assert atteso[url] in html
