"""Tabella senza rete: dati per filtri e ordinamento sul dispositivo e ricerca JavaScript uguale a quella Python."""

import json
import shutil
import subprocess

import pytest

import archivio
import ricerca
from tests.aiuti import ASPARAGI, PROGETTO, sql

SCRIPT = PROGETTO / "static" / "js" / "tabella.js"


def vista(html):
    inizio = html.index("data-vista='") + len("data-vista='")
    return json.loads(html[inizio:html.index("'", inizio)])


def test_righe_con_i_dati_per_il_dispositivo(client):
    html = client.get("/?q=asparagi&sort=kcal&dir=desc").data.decode()
    dati = vista(html)
    assert dati["parametri"] == "q=asparagi&sort=kcal&dir=desc"
    assert dati["valori"] == list(archivio.CAMPI_NUMERICI_ORDINABILI)
    assert dati["intervalli"] == list(archivio.CAMPI_INTERVALLO)

    riga = sql("SELECT * FROM alimenti WHERE id = ?", (ASPARAGI,))[0]
    attributo = html.split(f'<tr data-id="{ASPARAGI}"')[1].split(">")[0]
    assert f'data-c="{riga["categoria"]}"' in attributo
    rischi = "|".join(riga[c] or "" for c in archivio.analisi.CAMPI_RISCHIO)
    assert f'data-r="{rischi}"' in attributo
    valori = dict(zip(dati["valori"], attributo.split('data-v="')[1].split('"')[0].split("|"), strict=True))
    assert float(valori["kcal"]) == riga["kcal"]

    assert 'id="avviso-offline-tabella"' in html and "js/tabella.js" in html


def test_copia_offline_completa_senza_filtri(client):
    html = client.get("/?per_pagina=tutti").data.decode()
    assert vista(html)["parametri"] == ""
    assert html.count("<tr data-id=") == len(sql("SELECT id FROM alimenti"))


def test_script_tra_i_file_salvati_offline(client):
    assert "/static/js/tabella.js" in client.get("/sw.js").data.decode()




@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js non disponibile")
def test_ricerca_javascript_uguale_a_python():
    nomi = [r["alimento"] for r in sql("SELECT alimento FROM alimenti ORDER BY LOWER(alimento), id")]
    ricerche = ["mela", "mele", "pesca", "mozarella", "mozar", "succo mela", "caffè", "uovo", "brocoli",
                "parmiggiano", "pasta all uovo", "prosciuto crudo", "yoghurt", "cecci", "xyzq", "zarell", "Pane"]
    codice = (
        f"const R = require({json.dumps(str(SCRIPT))});"
        f"const nomi = {json.dumps(nomi)};"
        f"const ricerche = {json.dumps(ricerche)};"
        "console.log(JSON.stringify(ricerche.map(q => R.cerca(nomi, q).map(c => [c[0], Math.round(c[1] * 1e6)]))));"
    )
    uscita = subprocess.run(["node", "-e", codice], capture_output=True, text=True, check=True).stdout
    da_js = json.loads(uscita)

    elenco = [{"alimento": n, "i": i} for i, n in enumerate(nomi)]
    for q, risultati_js in zip(ricerche, da_js, strict=True):
        da_python = [[a["i"], round(p * 1e6)] for a, p in ricerca.cerca(elenco, q)]
        assert da_python == risultati_js, q
