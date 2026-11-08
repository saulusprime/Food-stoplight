"""Ricerca e consultazione: ricerca tollerante, filtri a intervallo, «solo sicuri», ordinamento multiplo, paginazione, confronto."""

import csv
import io
import re

import pytest
from werkzeug.datastructures import MultiDict

import archivio
import ricerca
from tests.aiuti import ASPARAGI, applicazione, conta, id_di, messaggi, solo_testo

NOMI = [
    {"id": 1, "alimento": "Melanzane, crude"},
    {"id": 2, "alimento": "Mele, fresche, golden"},
    {"id": 3, "alimento": "Pesche, fresche"},
    {"id": 4, "alimento": "Pesce gatto"},
    {"id": 5, "alimento": "Mozzarella di vacca"},
    {"id": 6, "alimento": "Arance succo, fresco"},
    {"id": 7, "alimento": "Caffe' tostato"},
    {"id": 8, "alimento": "Pasta all'uovo, secca"},
    {"id": 9, "alimento": "Uova di gallina, intero"},
]


def cerca(testo):
    trovati = ricerca.cerca(NOMI, testo)
    trovati.sort(key=lambda coppia: -coppia[1])
    return [a["alimento"] for a, _ in trovati]


def nomi_tabella(html):
    tabella = html.split('class="table table-hover')[1]       # senza le classifiche sopra la tabella
    return re.findall(r'class="nome-alimento" href="/alimento/\d+">([^<]+)</a>', tabella)


# ---------------------------------------------------------------
# Ricerca per nome
# ---------------------------------------------------------------

def test_normalizza_e_varianti():
    assert ricerca.normalizza("  Caffè, TOSTATO!  ") == "caffe tostato"
    assert ricerca.varianti("mela") == {"mele"}
    assert ricerca.varianti("pesca") == {"pesche"}       # solo la desinenza più lunga: non «pesce»
    assert ricerca.varianti("arancia") == {"arance", "arancie"}
    assert ricerca.varianti("pera") == {"pere"}
    assert ricerca.varianti("uvo") == set()               # parole corte: niente varianti


@pytest.mark.parametrize(("a", "b", "massimo", "attesa"), [
    ("mozarella", "mozzarella", 2, 1),
    ("parmigaino", "parmigiano", 2, 1),   # due lettere invertite
    ("pesca", "pesce", 1, 1),
    ("mela", "melanzane", 1, 2),          # oltre il massimo: massimo + 1
])
def test_distanza(a, b, massimo, attesa):
    assert ricerca.distanza(a, b, massimo) == attesa


@pytest.mark.parametrize(("testo", "primo", "esclusi"), [
    ("mela", "Mele, fresche, golden", {"Pesce gatto"}),
    ("mel", "Mele, fresche, golden", set()),              # inizio di parola: prima la parola più corta
    ("pesca", "Pesche, fresche", {"Pesce gatto"}),
    ("mozarella", "Mozzarella di vacca", set()),            # errore di battitura
    ("zarell", "Mozzarella di vacca", set()),               # parte di parola
    ("caffè", "Caffe' tostato", set()),                     # accenti indifferenti
    ("uovo", "Uova di gallina, intero", set()),             # le uova prima della pasta all'uovo
    ("succo arancia", "Arance succo, fresco", set()),       # parole in qualsiasi ordine
])
def test_ricerca_tollerante(testo, primo, esclusi):
    trovati = cerca(testo)
    assert trovati[0] == primo
    assert not esclusi & set(trovati)


def test_ricerca_senza_corrispondenze():
    # ogni parola ha corrispondenze esatte altrove: niente parole «simili» a caso
    assert cerca("succo mela") == []
    assert cerca("xyzq") == []
    assert len(cerca("   ")) == len(NOMI)


# ---------------------------------------------------------------
# Paginazione
# ---------------------------------------------------------------

def test_pagina_e_numeri():
    assert ricerca.pagina(900, 6, 50)["numeri"] == [1, None, 4, 5, 6, 7, 8, None, 18]
    assert ricerca.pagina(900, 1, 50)["numeri"] == [1, 2, 3, None, 18]
    assert ricerca.pagina(900, 5, 50)["numeri"][:3] == [1, 2, 3]   # un solo numero saltato si mostra
    ultima = ricerca.pagina(120, 99, 50)
    assert (ultima["numero"], ultima["inizio"], ultima["fine"]) == (3, 100, 120)
    assert ricerca.pagina(120, 2, None)["pagine"] == 1


@pytest.mark.parametrize(("testo", "attesa"), [("25", 25), ("tutti", None), ("7", 50), ("", 50), ("abc", 50)])
def test_righe_per_pagina(testo, attesa):
    assert ricerca.leggi_per_pagina(testo) == attesa


# ---------------------------------------------------------------
# Lettura dei filtri e dell'ordinamento
# ---------------------------------------------------------------

def test_leggi_filtri_intervalli_e_sicuri():
    filtri, sort, direction = archivio.leggi_filtri(MultiDict({
        "kcal_max": "120,5", "fibre_min": "-3", "zuccheri_min": "abc", "sicuri": "on", "q": "  mele   fresche ",
    }))
    assert filtri["kcal_max"] == "120.5"
    assert filtri["fibre_min"] == "" and filtri["zuccheri_min"] == ""
    assert filtri["sicuri"] == "1"
    assert filtri["q"] == "mele fresche"
    assert (sort, direction) == ("pertinenza", "desc")   # con un testo cercato: per pertinenza


@pytest.mark.parametrize(("argomenti", "attesa"), [
    ({"sort": "categoria,kcal", "dir": "asc,desc"}, ("categoria,kcal", "asc,desc")),
    ({"sort": "kcal,kcal,boh,fibre,sodio,zuccheri"}, ("kcal,fibre,sodio", "asc,asc,asc")),
    ({"sort": "pertinenza"}, ("alimento", "asc")),        # senza testo cercato non vale
    ({"sort": "kcal,pertinenza", "q": "mela"}, ("kcal", "asc")),  # solo come primo criterio
    ({}, ("alimento", "asc")),
])
def test_ordinamenti(argomenti, attesa):
    _, sort, direction = archivio.leggi_filtri(MultiDict(argomenti))
    assert (sort, direction) == attesa


def test_ordinamento_da_menu_ripetuti():
    argomenti = MultiDict([("sort", "categoria"), ("sort", ""), ("sort", "kcal"),
                           ("dir", "asc"), ("dir", "desc"), ("dir", "desc")])
    assert archivio.leggi_filtri(argomenti)[1:] == ("categoria,kcal", "asc,desc")


# ---------------------------------------------------------------
# Tabella della home
# ---------------------------------------------------------------

def test_home_paginata(client):
    html = client.get("/").data.decode()
    assert len(nomi_tabella(html)) == 50
    assert "righe 1–50" in html
    assert 'href="/?pagina=2" rel="next"' in html

    tutte = client.get("/?per_pagina=tutti").data.decode()
    assert len(nomi_tabella(tutte)) == conta()
    assert 'class="pagination-wrapper' not in tutte

    oltre = client.get("/?pagina=999&per_pagina=100").data.decode()
    assert "aria-current=\"page\">9<" in oltre        # 900 alimenti: si mostra l'ultima pagina


def test_home_ricerca_per_pertinenza(client):
    html = client.get("/?q=mela").data.decode()
    nomi = nomi_tabella(html)
    assert nomi[0].startswith("Mele")
    assert all("mel" in n.lower() for n in nomi)
    assert '<option value="pertinenza" selected>' in html
    assert "Ricerca: «mela»" in solo_testo(html.encode())

    vuota = solo_testo(client.get("/?q=xyzq").data)
    assert "Nessun alimento trovato per «xyzq»" in vuota


def test_home_solo_sicuri(client):
    html = client.get("/?sicuri=1&per_pagina=tutti").data.decode()
    righe = nomi_tabella(html)
    attesi = conta(
        "SELECT COUNT(*) FROM alimenti WHERE "
        + " AND ".join(f"{c} IN ('Trascurabile', 'Basso')" for c in archivio.analisi.CAMPI_RISCHIO)
    )
    assert len(righe) == attesi > 0
    assert 'id="filtro-sicuri" name="sicuri" value="1"' in html and "checked>" in html


def test_home_intervalli(client):
    html = client.get("/?kcal_max=50&fruttosio_min=1&per_pagina=tutti").data.decode()
    attesi = conta("SELECT COUNT(*) FROM alimenti WHERE kcal <= 50 AND fruttosio >= 1")
    assert len(nomi_tabella(html)) == attesi > 0
    assert "<details class=\"filtri-valori\" open>" in html
    assert "2 attivi" in html
    # chi non ha il fruttosio resta fuori
    assert conta("SELECT COUNT(*) FROM alimenti WHERE kcal <= 50 AND fruttosio IS NULL") > 0


def test_home_ordinamento_multiplo(client):
    html = client.get("/?sort=categoria,kcal&dir=asc,desc&per_pagina=tutti").data.decode()
    righe = re.findall(
        r'<td class="col-categoria">([^<]*)</td>.*?<td class="text-end col-valore col-kcal">([^<]*)</td>', html, re.S
    )
    valori = [(c, float(k.replace(".", "").replace(",", "."))) for c, k in righe]
    assert len(valori) == conta()
    for (c1, k1), (c2, k2) in zip(valori, valori[1:], strict=False):
        assert c1 < c2 or (c1 == c2 and k1 >= k2)
    assert html.count('class="sort-ordine"') == 2


def test_home_menu_ripetuti_diventano_indirizzo_compatto(client):
    risposta = client.get("/?sort=categoria&sort=kcal&sort=&dir=asc&dir=desc&dir=asc&q=mele")
    assert risposta.status_code == 302
    assert risposta.headers["Location"] == "/?q=mele&sort=categoria,kcal&dir=asc,desc"


def test_home_rischi_in_ordine_di_livello(client):
    html = client.get("/?sort=rischio_colesterolo&per_pagina=tutti").data.decode()
    livelli = re.findall(r'<td class="col-rischio col-colesterolo">(?:<span[^>]*>([^<]+)</span>|-)</td>', html)
    visti = [liv for i, liv in enumerate(livelli) if liv and (i == 0 or liv != livelli[i - 1])]
    assert visti == ["Trascurabile", "Basso", "Medio", "Alto"]
    assert livelli[-1] == ""            # non classificati in fondo


def test_intestazioni_con_maiusc_clic(client):
    html = client.get("/?sort=categoria&dir=asc").data.decode()
    assert 'href="/?sort=kcal&amp;dir=asc"' in html                                  # clic: solo questa colonna
    assert 'data-url-aggiungi="/?sort=categoria,kcal&amp;dir=asc,asc"' in html       # Maiusc+clic: aggiunge
    assert 'href="/?sort=categoria&amp;dir=desc"' in html                            # la prima si inverte


def test_export_con_ricerca_e_intervalli(client):
    risposta = client.get("/esporta/csv?q=mele&kcal_max=60&sort=kcal&dir=desc")
    righe = list(csv.DictReader(io.StringIO(risposta.data.decode("utf-8-sig")), delimiter=";"))
    assert righe and all(r["Alimento"].startswith("Mele") for r in righe)
    kcal = [float(r["Kcal"].replace(",", ".")) for r in righe]
    assert kcal == sorted(kcal, reverse=True) and max(kcal) <= 60

    with applicazione.app.test_request_context():
        info = applicazione.info_export({"q": "mele", "sicuri": "1", "kcal_max": "60.5"}, "categoria,kcal", "asc,desc", 3)
    assert ("Ricerca", "mele") in info["filtri"]
    assert ("Solo alimenti sicuri", "sì") in info["filtri"]
    assert ("Kcal fino a", "60,5") in info["filtri"]
    assert info["ordinamento"] == "Categoria (crescente), poi Kcal (decrescente)"


def test_api_ricerca_e_filtri(client):
    dati = client.get("/api/alimenti?q=mozarella&kcal_max=300").get_json()
    assert dati["totale"] >= 1
    assert all("ozzarella" in r["alimento"] for r in dati["risultati"])

    sicuri = client.get("/api/alimenti?sicuri=1&sort=categoria,kcal&dir=asc,desc&limit=500").get_json()
    assert sicuri["totale"] > 0
    assert all(r["rischio_diabete"] in ("Trascurabile", "Basso") for r in sicuri["risultati"])
    assert "sicuri" in client.get("/api").get_json()["parametri_alimenti"]


# ---------------------------------------------------------------
# Confronto
# ---------------------------------------------------------------

def test_confronto(client):
    mele = id_di("Mele, fresche, golden")
    html = client.get(f"/confronta?id={ASPARAGI}&id={mele}").data.decode()
    testo = solo_testo(html.encode())
    assert "Asparagi di campo, crudi" in testo and "Mele, fresche, golden" in testo
    assert html.count('class="confronto-alimento"') == 2
    assert "Rischio diabete" in testo and "Indice glicemico" in testo
    assert "Vitamine e sali minerali" in testo
    assert f'href="/confronta?id={mele}"' in html             # «Togli» gli asparagi


def test_confronto_massimo_e_mancanti(client):
    ids = [ASPARAGI, *(id_di(n) for n in ("Burro", "Pane bianco", "Mele, fresche, golden", "Aranciata"))]
    risposta = client.get("/confronta?" + "&".join(f"id={i}" for i in ids))
    assert risposta.status_code == 302
    assert risposta.headers["Location"].count("id=") == applicazione.CONFRONTO_MAX

    risposta = client.get(f"/confronta?id={ASPARAGI}&id=999999")
    assert risposta.headers["Location"] == f"/confronta?id={ASPARAGI}"
    assert any("non sono più nel database" in m for m in messaggi(client))


def test_confronto_aggiunta_dal_campo(client):
    burro = id_di("Burro")
    risposta = client.get(f"/confronta?id={ASPARAGI}&cerca=Burro · Grassi e Oli · 717 Kcal · %23{burro}")
    assert risposta.headers["Location"] == f"/confronta?id={ASPARAGI}&id={burro}"

    risposta = client.get(f"/confronta?id={ASPARAGI}&cerca=%23{ASPARAGI}")
    assert risposta.headers["Location"] == f"/confronta?id={ASPARAGI}"
    assert any("già nel confronto" in m for m in messaggi(client))


def test_confronto_vuoto_e_collegamenti(client):
    assert "Nessun alimento da confrontare." in solo_testo(client.get("/confronta").data)
    assert f'href="/confronta?id={ASPARAGI}"' in client.get(f"/alimento/{ASPARAGI}").data.decode()

    html = client.get("/?q=asparagi").data.decode()
    assert f'name="id" value="{ASPARAGI}"' in html and 'form="form-confronto"' in html
    assert 'id="form-confronto"' in html


def test_service_worker_salva_la_tabella_completa(client):
    testo = client.get("/sw.js").data.decode()
    assert 'const TABELLA_COMPLETA = "/?per_pagina=tutti";' in testo
    assert '["/?per_pagina=tutti", "/"]' in testo
