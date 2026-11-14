"""Pagine web: accesso e ruoli, CSRF, CRUD, export, import con anteprima, backup."""

import csv
import io
import os
import sqlite3

import pytest
from openpyxl import load_workbook

from tests.aiuti import ASPARAGI, BACKUP_DIR, DB, carica, conta, id_di, messaggi, piano_in_attesa, solo_testo, sql

# ---------------------------------------------------------------
# Accesso, ruoli e sicurezza
# ---------------------------------------------------------------

PAGINE_ADMIN = ["/nuovo", f"/modifica/{ASPARAGI}", "/importa", "/backup", "/backup/scarica"]


@pytest.mark.parametrize("url", PAGINE_ADMIN)
def test_anonimo_va_al_login(client, url):
    risposta = client.get(url)
    assert risposta.status_code == 302
    assert "/login" in risposta.headers["Location"]


@pytest.mark.parametrize("url", PAGINE_ADMIN)
def test_visitatore_riceve_403(visitatore, url):
    assert visitatore.get(url).status_code == 403


@pytest.mark.parametrize("url", ["/", f"/alimento/{ASPARAGI}", "/pasto", "/esporta/csv", f"/alimento/{ASPARAGI}/pdf"])
def test_consultazione_pubblica(client, url):
    assert client.get(url).status_code == 200


def test_accesso_privato_richiede_login(app, client, visitatore):
    app.config["ACCESSO_PUBBLICO"] = False
    assert "/login" in client.get("/").headers["Location"]
    assert client.get("/login").status_code == 200
    assert client.get("/salute").status_code == 200
    assert visitatore.get("/").status_code == 200


def test_login_errato_e_logout_solo_post(client, admin):
    risposta = client.post("/login", data={"username": "admin_t", "password": "sbagliata"})
    assert risposta.status_code == 401 and b"/logout" not in risposta.data
    assert admin.get("/logout").status_code == 405
    assert admin.post("/logout").status_code == 302
    assert admin.get("/nuovo").status_code == 302


def test_login_non_segue_redirect_esterni(client):
    risposta = client.post("/login?next=https://evil.example/", data={"username": "admin_t", "password": "password-di-prova"})
    assert risposta.headers["Location"] == "/"


def test_intestazioni_di_sicurezza(client):
    intestazioni = client.get("/").headers
    assert intestazioni["X-Content-Type-Options"] == "nosniff"
    assert intestazioni["X-Frame-Options"] == "DENY"


@pytest.mark.usefixtures("csrf_attivo")
@pytest.mark.parametrize(("url", "dati"), [
    ("/nuovo", {"alimento": "Senza token"}),
    (f"/elimina/{ASPARAGI}", {}),
    ("/importa/conferma", {"modalita": "aggiorna"}),
    ("/backup/crea", {}),
    ("/pasto/svuota", {}),
    ("/profilo", {"condizioni": "diabete"}),
    ("/spesa/genera", {"reparti": "Verdura"}),
])
def test_csrf_obbligatorio(admin, url, dati):
    prima = conta()
    risposta = admin.post(url, data=dati)
    assert risposta.status_code == 302
    assert any("Sessione scaduta" in m for m in messaggi(admin))
    assert conta() == prima


# ---------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------

DATI_FORM = {
    "alimento": "Prova nutrienti", "categoria": "Test", "kcal": "200", "carboidrati": "30", "fibre": "5",
    "proteine": "7,5", "grassi": "0", "vitamina_c": "12", "indice_glicemico": "60", "nova": "3",
    "fodmap_lattosio": "Alto", "fonte_nutrienti": "Etichetta", "url_fonte": "https://esempio.it/x",
    "rischio_diabete": "Basso", "note": "Valori da etichetta",
}


def test_nuovo_alimento_completo(admin):
    risposta = admin.post("/nuovo", data=DATI_FORM)
    assert risposta.status_code == 302 and "/alimento/" in risposta.headers["Location"]
    riga = dict(sql("SELECT * FROM alimenti WHERE alimento = 'Prova nutrienti'")[0])
    assert (riga["proteine"], riga["grassi"], riga["zuccheri"], riga["nova"], riga["note"]) == (
        7.5, 0.0, None, 3, "Valori da etichetta")
    # TEF stimato dai macronutrienti, Kcal nette e rapporto calcolati
    assert riga["tef_kcal"] > 0 and riga["kcal_nette"] == pytest.approx(200 - riga["tef_kcal"])
    # Fruttosio non indicato: non disponibile, e così il rapporto F/F
    assert (riga["fruttosio"], riga["rapporto"]) == (None, None)
    # Il livello scritto nel form si ignora: carico glicemico 60 × 30 g ÷ 100 = 18 -> Medio
    assert riga["rischio_diabete"] == "Medio"


def test_nuovo_kcal_stimate_dai_macronutrienti(admin):
    admin.post("/nuovo", data={"alimento": "Pane di prova", "proteine": "9", "carboidrati": "49", "grassi": "3,2"})
    riga = sql("SELECT kcal, tef_percent FROM alimenti WHERE alimento = 'Pane di prova'")[0]
    assert (riga["kcal"], riga["tef_percent"]) == (260.8, 11.52)


@pytest.mark.parametrize(("campo", "valore", "messaggio"), [
    ("alimento", "", "obbligatorio"),
    ("kcal", "abc", "Kcal"),
    ("tef_percent", "150", "TEF"),
    ("url_fonte", "javascript:alert(1)", "http"),
    ("indice_glicemico", "150", "Indice glicemico"),
    ("proteine", "-3", "Proteine"),
    ("nova", "7", "NOVA"),
    ("fodmap_gos", "boh", "FODMAP"),
])
def test_form_rifiuta_valori_non_validi(admin, campo, valore, messaggio):
    prima = conta()
    risposta = admin.post("/nuovo", data={**DATI_FORM, campo: valore})
    assert risposta.status_code == 200
    assert messaggio in risposta.data.decode()
    assert conta() == prima


def test_modifica_e_svuota_campo(admin):
    admin.post("/nuovo", data=DATI_FORM)
    id_prova = id_di("Prova nutrienti")
    admin.post(f"/modifica/{id_prova}", data={**DATI_FORM, "proteine": "", "vitamina_c": "15"})
    riga = sql("SELECT proteine, vitamina_c FROM alimenti WHERE id = ?", (id_prova,))[0]
    assert (riga["proteine"], riga["vitamina_c"]) == (None, 15.0)
    html = admin.get(f"/modifica/{id_prova}").data.decode()
    assert 'value="3" selected' in html and 'value="Alto" selected' in html


def test_elimina(admin):
    prima = conta()
    assert admin.post(f"/elimina/{ASPARAGI}").status_code == 302
    assert conta() == prima - 1
    assert admin.post(f"/elimina/{ASPARAGI}").status_code == 404


# ---------------------------------------------------------------
# Home e scheda
# ---------------------------------------------------------------

def test_home_filtri_e_ordinamento(client):
    html = client.get("/?categoria=Frutta&sort=kcal&dir=desc").data.decode()
    assert "Esporta con i filtri:" in html
    assert 'href="/esporta/csv?categoria=Frutta&amp;sort=kcal&amp;dir=desc"' in html


def test_scheda_porzione_e_indicatori(admin, client):
    admin.post("/nuovo", data=DATI_FORM)
    id_prova = id_di("Prova nutrienti")
    contenuto = solo_testo(client.get(f"/alimento/{id_prova}?grammi=150").data)
    assert "Valori per 150 g" in contenuto
    assert "27 · Alto" in contenuto           # carico glicemico della porzione
    assert "NOVA 3 · Alimenti trasformati" in contenuto
    assert "Valori da etichetta" in contenuto
    assert "Valori per 100 g" in solo_testo(client.get(f"/alimento/{id_prova}?grammi=-5").data)


def test_scheda_crea_e_senza_micronutrienti(client):
    contenuto = solo_testo(client.get(f"/alimento/{ASPARAGI}").data)
    assert "Potassio (mg) 260" in contenuto
    assert "CREA, Tabelle di composizione degli alimenti 2019, alimento 005040" in contenuto
    assert "Da USDA FoodData Central" in contenuto and "FDC 168389" in contenuto
    assert "Perché questi livelli" in contenuto
    conn = sqlite3.connect(DB)
    nuovo_id = conn.execute("INSERT INTO alimenti (alimento, categoria) VALUES ('Solo nome', 'Test')").lastrowid
    conn.commit()
    conn.close()
    assert "Vitamine e sali minerali non disponibili" in solo_testo(client.get(f"/alimento/{nuovo_id}").data)
    assert client.get("/alimento/999999").status_code == 404


# ---------------------------------------------------------------
# Export
# ---------------------------------------------------------------

def test_export_csv(client):
    risposta = client.get("/esporta/csv?categoria=Frutta")
    assert "alimenti_filtrati_" in risposta.headers["Content-Disposition"]
    assert risposta.headers["Cache-Control"] == "no-store"
    righe = list(csv.reader(io.StringIO(risposta.data.decode("utf-8-sig")), delimiter=";"))
    assert len(righe) - 1 == conta("SELECT COUNT(*) FROM alimenti WHERE categoria = 'Frutta'")


def test_export_excel_e_pdf(client):
    cartella = load_workbook(io.BytesIO(client.get("/esporta/xlsx?rischio_diabete=Alto").data))
    assert cartella["Alimenti"].max_row - 1 == conta("SELECT COUNT(*) FROM alimenti WHERE rischio_diabete = 'Alto'")
    assert client.get("/esporta/pdf").data.startswith(b"%PDF")
    assert client.get(f"/alimento/{ASPARAGI}/pdf").data.startswith(b"%PDF")
    assert client.get("/esporta/doc").status_code == 404


# ---------------------------------------------------------------
# Import con anteprima
# ---------------------------------------------------------------

def test_import_anteprima_e_conferma(admin):
    contenuto = b"Alimento;Categoria;Kcal\nNuovo di prova;Test;10\n"
    risposta = carica(admin, "prova.csv", contenuto)
    assert risposta.headers["Location"].endswith("/importa/anteprima")
    assert admin.get("/importa/anteprima").status_code == 200
    _, _, sommario = piano_in_attesa(admin)
    assert sommario["nuovo"] == 1

    prima = conta()
    admin.post("/importa/conferma", data={"modalita": "aggiorna"})
    assert conta() == prima + 1
    assert any("Import completato" in m for m in messaggi(admin))
    assert len(os.listdir(BACKUP_DIR)) == 1
    assert admin.get("/importa/anteprima").status_code == 302  # file in attesa eliminato


def test_import_sostituisci_richiede_conferma(admin):
    carica(admin, "due.csv", b"Alimento;Kcal\nUno;1\nDue;2\n")
    admin.post("/importa/conferma", data={"modalita": "sostituisci"})
    assert conta() == 1100
    admin.post("/importa/conferma", data={"modalita": "sostituisci", "conferma_sostituisci": "1"})
    assert conta() == 2


def test_import_sostituisci_senza_righe_valide(admin):
    carica(admin, "vuoto.csv", b"Alimento;Kcal\n;5\n")
    admin.post("/importa/conferma", data={"modalita": "sostituisci", "conferma_sostituisci": "1"})
    assert conta() == 1100


def test_import_annulla_e_token_manomesso(admin):
    carica(admin, "x.csv", b"Alimento\nMela\n")
    admin.post("/importa/annulla")
    assert admin.get("/importa/anteprima").status_code == 302
    with admin.session_transaction() as sessione:
        sessione["import_token"] = "../../../etc/passwd"
    assert admin.get("/importa/anteprima").status_code == 302


def test_import_file_troppo_grande(app, admin):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    risposta = carica(admin, "grande.csv", b"Alimento;Kcal\n" + b"x;1\n" * 1000)
    assert risposta.headers["Location"].endswith("/importa")
    assert any("troppo grande" in m for m in messaggi(admin))


# ---------------------------------------------------------------
# Backup
# ---------------------------------------------------------------

def test_backup_scarica_crea_ripristina(admin):
    copia = admin.get("/backup/scarica").data
    assert copia.startswith(b"SQLite format 3")

    admin.post("/backup/crea")
    nome = os.listdir(BACKUP_DIR)[0]
    assert nome in admin.get("/backup").data.decode()

    admin.post(f"/elimina/{ASPARAGI}")
    admin.post(f"/backup/ripristina/{nome}")
    assert conta("SELECT COUNT(*) FROM alimenti WHERE id = ?", (ASPARAGI,)) == 1

    carica(admin, "x.db", b"non un database", url="/backup/ripristina", conferma="1")
    assert any("non è un database SQLite" in m for m in messaggi(admin))

    prima = conta()
    carica(admin, "copia.db", copia, url="/backup/ripristina")
    assert any("spunta" in m for m in messaggi(admin)) and conta() == prima


@pytest.mark.parametrize("nome", ["../alimenti.db", "utenti.db", "alimenti_x.db"])
def test_backup_nomi_non_validi(admin, nome):
    assert admin.get(f"/backup/scarica/{nome}").status_code == 404
    assert admin.post(f"/backup/ripristina/{nome}").status_code == 404
