"""API REST in sola lettura, controllo di salute, comandi da riga di comando e update.py."""

import sqlite3

import pytest

import update
import usda
from tests.aiuti import ASPARAGI, DB, DIARIO_DB, LAVORO, conta, sql

# ---------------------------------------------------------------
# API
# ---------------------------------------------------------------


def test_api_indice(client):
    dati = client.get("/api").get_json()
    assert dati["versione"] == 1
    assert dati["risorse"]["alimenti"].endswith("/api/alimenti")


def test_api_elenco_filtri_ricerca_paginazione(client):
    dati = client.get("/api/alimenti?q=mele&sort=kcal&dir=desc&limit=2").get_json()
    assert dati["totale"] == conta("SELECT COUNT(*) FROM alimenti WHERE instr(LOWER(alimento), 'mele') > 0")
    assert len(dati["risultati"]) == 2
    kcal = [a["kcal"] for a in dati["risultati"]]
    assert kcal == sorted(kcal, reverse=True)
    assert dati["precedente"] is None and "offset=2" in dati["successiva"]

    frutta = client.get("/api/alimenti?categoria=frutta&rischio_diabete=Basso&limit=500").get_json()
    assert all(a["categoria"] == "Frutta" and a["rischio_diabete"] == "Basso" for a in frutta["risultati"])


def test_api_alimento(client):
    dati = client.get(f"/api/alimenti/{ASPARAGI}").get_json()
    assert dati["alimento"] == "Asparagi di campo, crudi"
    assert (dati["potassio"], dati["codice_crea"], dati["porzione"]) == (260.0, "005040", 200.0)
    # Rischi calcolati: Basso, Trascurabile, Alto, Trascurabile, Basso -> media 1 punto
    assert (dati["punteggio"], dati["livello_medio"]) == (67, "Basso")
    assert dati["url"].endswith(f"/alimento/{ASPARAGI}")
    assert "fonte_kcal" not in dati


@pytest.mark.parametrize(("url", "stato"), [
    ("/api/alimenti/999999", 404),
    ("/api/inesistente", 404),
    ("/api/alimenti?limit=abc", 400),
    ("/api/alimenti?limit=0", 400),
    ("/api/alimenti?limit=501", 400),
    ("/api/alimenti?offset=-1", 400),
])
def test_api_errori_json(client, url, stato):
    risposta = client.get(url)
    assert risposta.status_code == stato
    assert risposta.get_json()["stato"] == stato


def test_api_sola_lettura(client):
    risposta = client.post("/api/alimenti")
    assert risposta.status_code == 405
    assert "sola lettura" in risposta.get_json()["errore"]


def test_api_categorie(client):
    categorie = client.get("/api/categorie").get_json()
    assert sum(c["alimenti"] for c in categorie) == conta("SELECT COUNT(*) FROM alimenti WHERE TRIM(COALESCE(categoria, '')) <> ''")


def test_api_accesso_privato(app, client, visitatore):
    app.config["ACCESSO_PUBBLICO"] = False
    risposta = client.get("/api/alimenti")
    assert risposta.status_code == 401
    assert risposta.get_json()["stato"] == 401
    assert visitatore.get("/api/alimenti").status_code == 200


def test_salute(client):
    assert client.get("/salute").get_json() == {"stato": "ok", "schema_alimenti": 6, "schema_aggiornato": True}


# ---------------------------------------------------------------
# Comandi flask
# ---------------------------------------------------------------

@pytest.fixture
def cli(app):
    return app.test_cli_runner()


def test_crea_utente_e_elenco(cli):
    risultato = cli.invoke(args=["crea-utente", "carla_t", "--ruolo", "visitatore", "--password", "password-lunga"])
    assert risultato.exit_code == 0, risultato.output
    assert "carla_t" in cli.invoke(args=["elenco-utenti"]).output
    assert cli.invoke(args=["crea-utente", "x", "--password", "password-lunga"]).exit_code != 0


def test_elimina_utente_cancella_il_suo_diario(cli, visitatore):
    visitatore.post("/diario/aggiungi", data={"pasto": "pranzo", "alimento_id": ASPARAGI, "grammi": "100"})
    risultato = cli.invoke(args=["elimina-utente", "anna_t"], input="y\n")
    assert risultato.exit_code == 0 and "voci di diario" in risultato.output
    conn = sqlite3.connect(DIARIO_DB)
    assert conn.execute("SELECT COUNT(*) FROM diario").fetchone()[0] == 0
    conn.close()


def test_db_stato(cli):
    assert "alimenti  versione 6 di 6" in cli.invoke(args=["db-stato"]).output


def test_usda_sincronizza_senza_rete(cli, monkeypatch):
    riga = sql("SELECT fdc_id, zuccheri, fruttosio FROM alimenti WHERE id = ?", (ASPARAGI,))[0]
    # USDA con il doppio degli zuccheri: fruttosio e glucosio si riportano agli zuccheri CREA
    finto = {riga["fdc_id"]: {"fdcId": riga["fdc_id"], "dataType": "SR Legacy", "foodNutrients": [
        {"number": "269", "amount": riga["zuccheri"] * 2, "unitName": "G"},
        {"number": "212", "amount": 3.0, "unitName": "G"},
        {"number": "211", "amount": 0.4, "unitName": "G"},
        {"number": "203", "amount": 99, "unitName": "G"},
    ]}}
    monkeypatch.setattr(usda, "scarica", lambda *a, **k: finto)

    senza_chiave = cli.invoke(args=["usda-sincronizza", "--api-key", "DEMO_KEY"])
    assert senza_chiave.exit_code != 0 and "chiave USDA personale" in senza_chiave.output

    risultato = cli.invoke(args=["usda-sincronizza", "--api-key", "chiave-di-prova"])
    assert risultato.exit_code == 0, risultato.output
    # Lo stesso alimento USDA completa più alimenti CREA (asparagi di bosco, di campo, di serra)
    stesso_fdc = conta("SELECT COUNT(*) FROM alimenti WHERE fdc_id = ?", (riga["fdc_id"],))
    assert f"{stesso_fdc} alimenti aggiornati" in risultato.output

    dopo = sql("SELECT fruttosio, glucosio, proteine, rischio_malassorbimento FROM alimenti WHERE id = ?", (ASPARAGI,))[0]
    # Fruttosio e glucosio dimezzati; le proteine vengono dal CREA e non cambiano
    assert (dopo["fruttosio"], dopo["glucosio"]) == (1.5, 0.2)
    assert dopo["proteine"] != 99
    assert dopo["rischio_malassorbimento"] == "Alto"

    storico = sql("SELECT esito, aggiornati FROM sincronizzazioni ORDER BY id DESC LIMIT 1")[0]
    assert (storico["esito"], storico["aggiornati"]) == ("riuscita", stesso_fdc)


def test_usda_valori_e_conversioni():
    valori = usda.valori({"foodNutrients": [
        {"number": "203", "amount": 2.5, "unitName": "G"},
        {"number": "601", "amount": 0.01, "unitName": "G"},
        {"number": "418", "amount": 0.0, "unitName": "UG"},
        {"number": "401", "amount": None, "unitName": "MG"},
        {"number": "306", "amount": 5, "unitName": "IU"},
    ]})
    assert valori == {"proteine": 2.5, "colesterolo": 10.0, "vitamina_b12": 0.0}


# ---------------------------------------------------------------
# update.py
# ---------------------------------------------------------------

def test_update_importa_e_esporta_mancanti(tmp_path, capsys):
    db = tmp_path / "copia.db"
    db.write_bytes(DB.read_bytes())
    sorgente = tmp_path / "macro.csv"
    sorgente.write_text("Alimento;Categoria;Proteine (g);Carboidrati (g);Grassi (g)\nPane di prova;Cereali;9;49;3,2\n")
    argomenti = ["--db", str(db), "--backup-dir", str(tmp_path / "bk")]

    assert update.main([*argomenti, "--csv", str(sorgente), "--dry-run"]) == 0
    assert "Nuovi: 1" in capsys.readouterr().out

    assert update.main([*argomenti, "--csv", str(sorgente)]) == 0
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT kcal, tef_percent FROM alimenti WHERE alimento = 'Pane di prova'").fetchone() == (260.8, 11.52)
    conn.close()

    mancanti = tmp_path / "mancanti.csv"
    assert update.main([*argomenti, "--esporta-mancanti", str(mancanti)]) == 0
    assert mancanti.read_text(encoding="utf-8-sig").startswith("ID;Alimento;")


def test_update_file_non_valido(tmp_path):
    sorgente = tmp_path / "x.csv"
    sorgente.write_text("Foo;Bar\n1;2\n")
    assert update.main(["--db", str(LAVORO / "alimenti.db"), "--csv", str(sorgente)]) == 1


def test_crea_admin_iniziale(cli, monkeypatch):
    assert "non impostate" in cli.invoke(args=["crea-admin-iniziale"]).output
    monkeypatch.setenv("ADMIN_USERNAME", "primo_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "password-lunga")
    # gli utenti di prova contengono già un amministratore
    assert "Esiste già un amministratore" in cli.invoke(args=["crea-admin-iniziale"]).output

    from tests.aiuti import UTENTI_DB
    conn = sqlite3.connect(UTENTI_DB)
    conn.execute("DELETE FROM utenti WHERE ruolo = 'admin'")
    conn.commit()
    conn.close()
    risultato = cli.invoke(args=["crea-admin-iniziale"])
    assert risultato.exit_code == 0 and "primo_admin" in risultato.output

    monkeypatch.setenv("ADMIN_PASSWORD", "corta")
    assert cli.invoke(args=["crea-admin-iniziale"]).exit_code != 0
