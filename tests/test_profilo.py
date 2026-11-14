"""Profilo personale e semaforo per te: regole, salvataggio, tabella, scheda, pasto, confronto, export."""

import csv
import io
import json
import shutil
import sqlite3
import subprocess
from itertools import product

import pytest
from werkzeug.datastructures import MultiDict

import analisi
import archivio
import database
import nutrienti
import profilo
from tests.aiuti import ASPARAGI, LAVORO, PASSWORD, UTENTI_DB, accedi, applicazione, id_di, solo_testo, sql
from tests.test_tabella_offline import SCRIPT, vista
from web import import_export


def condizioni_salvate(username):
    conn = sqlite3.connect(UTENTI_DB)

    try:
        return conn.execute("SELECT condizioni FROM utenti WHERE username = ?", (username,)).fetchone()[0]
    finally:
        conn.close()


def sessione(cliente):
    with cliente.session_transaction() as s:
        return dict(s)


def punti_per_te(alimento, condizioni):
    return profilo.punti_per_te(*(alimento[c] for c in profilo.campi(condizioni)))


def adatto(alimento, condizioni):
    punti = punti_per_te(alimento, condizioni)
    return punti is not None and punti <= profilo.PUNTI_ADATTI


# Cella della colonna «Per te» nella tabella
CELLA_PER_TE = 'class="col-rischio col-per_te"'


# ---------------------------------------------------------------
# Regole
# ---------------------------------------------------------------

def test_condizioni_lette_e_salvate():
    assert profilo.leggi("fruttosio, diabete,xyz,diabete") == ("diabete", "fruttosio")
    assert profilo.leggi(["COLESTEROLO"]) == ("colesterolo",)
    assert profilo.leggi(None) == ()
    assert profilo.testo(["fruttosio", "diabete"]) == "diabete,fruttosio"
    assert profilo.campi(["fruttosio", "diabete"]) == ("rischio_diabete", "rischio_malassorbimento")


@pytest.mark.parametrize(("valori", "atteso"), [
    (("Basso", "Medio"), 2),
    (("trascurabile",), 0),
    (("Alto", None), 3),        # un rischio Alto basta, anche se un altro non è classificato
    (("Basso", ""), None),      # altrimenti senza un livello il semaforo per te non è classificato
    (("Medio", "BASSO", "Trascurabile"), 2),
    ((), None),
])
def test_punti_per_te(valori, atteso):
    assert profilo.punti_per_te(*valori) == atteso


def test_semaforo_per_te_di_un_alimento():
    alimento = {"rischio_diabete": "Basso", "rischio_colesterolo": "Medio", "rischio_malassorbimento": None}

    esito = profilo.per_te(alimento, ["colesterolo", "diabete"])
    assert esito["livello"]["chiave"] == "medio" and not esito["adatto"]
    assert [v["chiave"] for v in esito["voci"]] == ["diabete", "colesterolo"]
    assert [v["chiave"] for v in esito["decisive"]] == ["colesterolo"]

    assert profilo.per_te(alimento, ["diabete"])["adatto"]
    assert profilo.per_te(alimento, ["fruttosio"])["livello"] is analisi.NON_CLASSIFICATO
    assert profilo.per_te(alimento, []) is None


def test_semaforo_per_te_di_un_pasto():
    rischi = [
        {"campo": "rischio_diabete", "punti": 1.4},
        {"campo": "rischio_colesterolo", "punti": 2.6},
        {"campo": "rischio_malassorbimento", "punti": None},
    ]
    assert profilo.per_te_profilo(rischi, ["diabete"])["livello"]["chiave"] == "basso"
    assert profilo.per_te_profilo(rischi, ["diabete", "fruttosio"])["punti"] is None
    assert profilo.per_te_profilo(rischi, ["colesterolo", "fruttosio"])["livello"]["chiave"] == "alto"
    assert profilo.per_te_profilo(rischi, []) is None


def test_alternative_per_te():
    def voce(id_, nome, diabete, punteggio):
        return {"id": id_, "alimento": nome, "categoria": "Frutta", "kcal": 50,
                "rischio_diabete": diabete, "punteggio": punteggio}

    uva = voce(1, "Uva", "Alto", 60)
    alimenti = [uva, voce(2, "Mela", "Basso", 50), voce(3, "Pera", "Alto", 80),
                voce(4, "Kiwi", "Trascurabile", 40), voce(5, "Fico", None, 90)]

    assert [a["alimento"] for a in nutrienti.alternative(uva, alimenti)] == ["Fico", "Pera"]

    # Con il profilo: prima il semaforo per te più basso, anche con un punteggio più basso
    personali = nutrienti.alternative(uva, alimenti, condizioni=("diabete",))
    assert [a["alimento"] for a in personali] == ["Kiwi", "Mela", "Pera"]
    assert personali[0]["per_te"]["livello"]["chiave"] == "trascurabile" and personali[0]["guadagno"] == -20


# ---------------------------------------------------------------
# Query: filtro e ordinamento
# ---------------------------------------------------------------

def test_filtro_e_ordinamento_per_te(app):
    condizioni = ("diabete", "fruttosio")

    with app.app_context():
        tutti = archivio.get_alimenti()
        filtrati = archivio.get_alimenti({"per_te": "1"}, condizioni=condizioni)
        ordinati = archivio.get_alimenti({}, "per_te,alimento", "asc,asc", condizioni)
        senza_profilo = archivio.get_alimenti({"per_te": "1"})

    attesi = {a["id"] for a in tutti if adatto(a, condizioni)}
    assert {a["id"] for a in filtrati} == attesi and 0 < len(attesi) < len(tutti)

    punti = [punti_per_te(a, condizioni) for a in ordinati]
    noti = [p for p in punti if p is not None]
    assert noti == sorted(noti) and all(p is None for p in punti[len(noti):])
    assert len(senza_profilo) == len(tutti)


def test_filtro_e_ordinamento_per_te_solo_con_profilo():
    argomenti = MultiDict({"per_te": "1", "sort": "per_te", "dir": "desc"})

    filtri, sort, _direction = archivio.leggi_filtri(argomenti)
    assert filtri["per_te"] == "" and sort == "alimento"

    filtri, sort, direction = archivio.leggi_filtri(argomenti, ("diabete",))
    assert filtri["per_te"] == "1" and (sort, direction) == ("per_te", "desc")


# ---------------------------------------------------------------
# Profilo: sessione, account, migrazione
# ---------------------------------------------------------------

def test_profilo_senza_accesso_nella_sessione(client):
    assert CELLA_PER_TE not in client.get("/").data.decode()

    risposta = client.post("/profilo", data={"condizioni": ["diabete", "inesistente"]})
    assert risposta.status_code == 302 and risposta.headers["Location"].endswith("/profilo")
    dati = sessione(client)
    assert dati["profilo"] == "diabete" and dati["svuota_cache"]

    html = client.get("/").data.decode()
    assert 'id="filtro-per_te"' in html and CELLA_PER_TE in html and "1 condizione nel profilo" in html
    assert 'id="condizione-diabete" name="condizioni" value="diabete"' in client.get("/profilo").data.decode()

    client.post("/profilo", data={})
    assert "profilo" not in sessione(client)
    assert CELLA_PER_TE not in client.get("/").data.decode()


def test_profilo_salvato_nell_account(app, visitatore):
    visitatore.post("/profilo", data={"condizioni": ["fruttosio", "colesterolo"]})
    assert condizioni_salvate("anna_t") == "colesterolo,fruttosio"
    assert "profilo" not in sessione(visitatore)

    # Il profilo segue l'account a ogni accesso; gli altri utenti non lo vedono
    assert "2 condizioni nel profilo" in accedi(app, "anna_t").get("/profilo").data.decode()
    assert "condizioni nel profilo" not in accedi(app, "bruno_t").get("/").data.decode()


def test_accesso_e_uscita_tolgono_il_profilo_della_sessione(client):
    client.post("/profilo", data={"condizioni": "diabete"})
    client.post("/login", data={"username": "anna_t", "password": PASSWORD})
    assert "profilo" not in sessione(client)
    assert "condizione nel profilo" not in client.get("/").data.decode()

    client.post("/profilo", data={"condizioni": "diabete"})
    assert condizioni_salvate("anna_t") == "diabete"

    client.post("/logout")
    assert "profilo" not in sessione(client)
    assert "condizione nel profilo" not in client.get("/").data.decode()


def test_migrazione_aggiunge_le_condizioni_agli_utenti():
    percorso = LAVORO / "utenti_v1.db"
    percorso.unlink(missing_ok=True)
    conn = sqlite3.connect(percorso)
    database._utenti_1_schema_di_base(conn)
    conn.execute("INSERT INTO utenti (username, password_hash) VALUES ('vecchio', 'x')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    assert database.migra(str(percorso), "utenti") == ["utenti 2: Profilo personale: condizioni per il semaforo per te"]
    assert database.stato(str(percorso), "utenti") == (2, 2)

    conn = sqlite3.connect(percorso)
    assert conn.execute("SELECT condizioni FROM utenti").fetchone()[0] == ""
    conn.close()


# ---------------------------------------------------------------
# Pagine
# ---------------------------------------------------------------

def test_tabella_con_il_semaforo_per_te(client):
    condizioni = ("diabete", "fruttosio")
    client.post("/profilo", data={"condizioni": list(condizioni)})

    html = client.get("/?per_te=1&per_pagina=tutti&sort=per_te").data.decode()
    righe = html.count("<tr data-id=")
    attesi = [a for a in map(dict, sql("SELECT * FROM alimenti")) if adatto(a, condizioni)]
    assert righe == len(attesi)
    assert "Solo sicuri per il mio profilo ✕" in solo_testo(html.encode())

    dati = vista(html)
    assert dati["per_te"] == ["rischio_diabete", "rischio_malassorbimento"]
    assert "per_te" in dati["ordinabili"]
    assert '<option value="per_te" selected>' in html


def test_scheda_con_il_semaforo_per_te(client):
    assert 'id="titolo-per-te"' not in client.get(f"/alimento/{ASPARAGI}").data.decode()

    condizioni = ("diabete", "fruttosio")
    client.post("/profilo", data={"condizioni": list(condizioni)})
    atteso = profilo.per_te(dict(sql("SELECT * FROM alimenti WHERE id = ?", (ASPARAGI,))[0]), condizioni)

    html = client.get(f"/alimento/{ASPARAGI}").data.decode()
    assert 'id="titolo-per-te"' in html
    assert f'per-te-card stato-{atteso["livello"]["stato"]}' in html
    assert html.count("nel tuo profilo") == 2


def test_pasto_con_il_semaforo_per_te(client):
    client.post("/pasto/aggiungi", data={"alimento_id": ASPARAGI, "grammi": "150"})
    assert "per-te-nota" not in client.get("/pasto").data.decode()

    client.post("/profilo", data={"condizioni": "diabete"})
    html = client.get("/pasto").data.decode()
    assert "per-te-nota" in html and html.count("nel tuo profilo") == 1


def test_confronto_e_pasti_pronti_con_il_semaforo_per_te(client):
    burro = id_di("Burro")
    assert 'class="riga-per-te"' not in client.get(f"/confronta?id={ASPARAGI}&id={burro}").data.decode()
    assert 'value="per_te"' not in client.get("/pasti-pronti").data.decode()

    client.post("/profilo", data={"condizioni": "colesterolo"})
    assert 'class="riga-per-te"' in client.get(f"/confronta?id={ASPARAGI}&id={burro}").data.decode()

    html = client.get("/pasti-pronti?ordina=per_te").data.decode()
    assert '<option value="per_te" selected>' in html and "Per te: " in html


def test_export_con_il_filtro_per_te(client):
    client.post("/profilo", data={"condizioni": "colesterolo"})
    risposta = client.get("/esporta/csv?per_te=1")
    righe = list(csv.DictReader(io.StringIO(risposta.data.decode("utf-8-sig")), delimiter=";"))
    attesi = sql("SELECT COUNT(*) FROM alimenti WHERE LOWER(rischio_colesterolo) IN ('trascurabile', 'basso')")[0][0]
    assert len(righe) == attesi
    assert {r["Rischio colesterolo"] for r in righe} <= {"Trascurabile", "Basso"}

    with applicazione.app.test_request_context():
        assert import_export.filtro_esportato("per_te", "1") == ("Solo sicuri per il mio profilo", "sì")


def test_guida_e_menu(client):
    assert 'id="per-te"' in client.get("/guida").data.decode()
    assert 'href="/profilo"' in client.get("/").data.decode()


# ---------------------------------------------------------------
# Tabella offline: stessa regola in JavaScript
# ---------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js non disponibile")
def test_semaforo_per_te_javascript_uguale_a_python():
    livelli = [None, 0, 1, 2, 3]
    casi = [list(c) for n in range(4) for c in product(livelli, repeat=n)]
    codice = (
        f"const R = require({json.dumps(str(SCRIPT))});"
        f"console.log(JSON.stringify({json.dumps(casi)}.map(R.puntiPerTe)));"
    )
    da_js = json.loads(subprocess.run(["node", "-e", codice], capture_output=True, text=True, check=True).stdout)

    nomi = {liv["punti"]: liv["etichetta"] for liv in analisi.LIVELLI}
    da_python = [profilo.punti_per_te(*(nomi.get(p) for p in caso)) for caso in casi]
    assert da_js == da_python
