"""Lingue (italiano e inglese), app installabile (PWA) ed esperienza utente: notifiche, conferme, guida, tabella."""

import csv
import io
import shutil
from datetime import date
from pathlib import Path

import pytest
from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_dir
from babel.messages.mofile import read_mo
from babel.messages.pofile import read_po

import importazione
import pwa
from tests.aiuti import PROGETTO, id_di, messaggi, solo_testo

CATALOGO = PROGETTO / "translations" / "en" / "LC_MESSAGES"


def in_inglese(cliente):
    cliente.set_cookie("lingua", "en")
    return cliente


# ---------------------------------------------------------------
# Catalogo delle traduzioni
# ---------------------------------------------------------------

def estrai_testi():
    """
    Testi da tradurre estratti da codice e template con la configurazione di babel.cfg.
    """
    try:
        from babel.messages.frontend import parse_mapping_cfg
    except ImportError:  # Babel < 2.13
        from babel.messages.frontend import parse_mapping as parse_mapping_cfg

    with open(PROGETTO / "babel.cfg", encoding="utf-8") as f:
        metodi, opzioni = parse_mapping_cfg(f)

    return {
        voce[2] if isinstance(voce[2], str) else tuple(voce[2])
        for voce in extract_from_dir(str(PROGETTO), metodi, opzioni, keywords=DEFAULT_KEYWORDS)
    }


def test_ogni_testo_ha_la_traduzione_inglese():
    """
    Se fallisce: pybabel extract/update (vedi lingue.py), tradurre le voci nuove, pybabel compile.
    """
    with open(CATALOGO / "messages.po", "rb") as f:
        catalogo = read_po(f)

    tradotti = {
        (m.id if isinstance(m.id, str) else tuple(m.id)): m
        for m in catalogo if m.id
    }
    testi = estrai_testi()

    mancanti = sorted(str(t) for t in testi if t not in tradotti)
    assert not mancanti, f"testi senza voce nel catalogo: {mancanti}"

    vuoti = [str(i) for i, m in tradotti.items() if i in testi and (not m.string or m.fuzzy or (
        isinstance(m.string, tuple) and not all(m.string)))]
    assert not vuoti, f"testi senza traduzione: {vuoti}"

    obsoleti = sorted(str(i) for i in tradotti if i not in testi)
    assert not obsoleti, f"voci del catalogo non più usate: {obsoleti}"

    errori = [(m.id, e) for m, e in catalogo.check()]
    assert not errori, f"segnaposto diversi tra italiano e inglese: {errori}"


def test_mo_compilato_dal_po():
    def voci(catalogo):
        return {
            tuple(m.id) if isinstance(m.id, (list, tuple)) else m.id:
            tuple(m.string) if isinstance(m.string, (list, tuple)) else m.string
            for m in catalogo if m.id
        }

    with open(CATALOGO / "messages.po", "rb") as f:
        po = voci(read_po(f))

    with open(CATALOGO / "messages.mo", "rb") as f:
        mo = voci(read_mo(f))

    assert mo == po, "messages.mo non aggiornato: pybabel compile -d translations"


# ---------------------------------------------------------------
# Scelta della lingua
# ---------------------------------------------------------------

def test_italiano_predefinito_e_inglese_dal_browser(client):
    assert '<html lang="it">' in client.get("/").data.decode()
    html = client.get("/", headers={"Accept-Language": "en-GB,en;q=0.9"}).data.decode()
    assert '<html lang="en">' in html and "Food Database" in html


def test_cambio_lingua_dal_menu(client):
    risposta = client.get("/lingua/en?next=/guida")
    assert risposta.headers["Location"] == "/guida"
    cookie = risposta.headers["Set-Cookie"]
    assert "lingua=en" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Guide to the data" in solo_testo(client.get("/guida").data)

    # la scelta vale più della lingua del browser
    assert '<html lang="en">' in client.get("/", headers={"Accept-Language": "it"}).data.decode()


@pytest.mark.parametrize(("url", "stato", "destinazione"), [
    ("/lingua/en?next=https://evil.example/", 302, "/"),
    ("/lingua/en?next=//evil.example", 302, "/"),
    ("/lingua/de", 404, None),
])
def test_cambio_lingua_sicuro(client, url, stato, destinazione):
    risposta = client.get(url)
    assert risposta.status_code == stato
    assert risposta.headers.get("Location") == destinazione


def test_cookie_non_valido_ignorato(client):
    client.set_cookie("lingua", "xx")
    assert '<html lang="it">' in client.get("/").data.decode()


# ---------------------------------------------------------------
# Pagine, messaggi e numeri in inglese
# ---------------------------------------------------------------

DATI_FORM = {
    "alimento": "Prova nutrienti", "categoria": "Frutta", "kcal": "200", "carboidrati": "30", "fibre": "5",
    "indice_glicemico": "60", "rischio_diabete": "Basso",
}


def test_scheda_in_inglese(admin):
    admin.post("/nuovo", data=DATI_FORM)
    contenuto = solo_testo(in_inglese(admin).get(f"/alimento/{id_di('Prova nutrienti')}?grammi=150").data)
    assert "Values per 150 g" in contenuto
    assert "22.5 · High" in contenuto            # punto decimale e livello tradotto
    assert "Fruit ·" in contenuto                # categoria del database tradotta
    assert "Diabetes" in contenuto and "Low" in contenuto


def test_messaggi_e_errori_in_inglese(client, admin):
    risposta = in_inglese(client).post("/login", data={"username": "admin_t", "password": "sbagliata"})
    assert "Invalid username or password." in solo_testo(risposta.data)

    risposta = in_inglese(admin).post("/nuovo", data={**DATI_FORM, "kcal": "abc", "nova": "7"})
    contenuto = solo_testo(risposta.data)
    assert "Kcal: “abc” is not valid" in contenuto
    assert "NOVA: choose a group from 1 to 4." in contenuto


def test_date_e_numeri_in_inglese(app, modulo):
    with app.test_request_context("/", headers={"Accept-Language": "en"}):
        assert modulo.filtro_data_estesa(date(2026, 11, 7)) == "Saturday, November 7, 2026"
        assert modulo.filtro_numero(12.5) == "12.5"
        assert modulo.filtro_migliaia(20000) == "20,000"

    with app.test_request_context("/"):
        assert modulo.filtro_data_estesa(date(2026, 11, 7)) == "sabato 7 novembre 2026"
        assert modulo.filtro_numero(12.5) == "12,5"
        assert modulo.filtro_migliaia(20000) == "20.000"


def test_export_e_api_restano_in_italiano(client):
    in_inglese(client)
    righe = list(csv.reader(io.StringIO(client.get("/esporta/csv").data.decode("utf-8-sig")), delimiter=";"))
    assert righe[0][:3] == ["ID", "Alimento", "Categoria"]

    dati = client.get("/api/alimenti/787").get_json()
    assert dati["livello_medio"] == "Trascurabile"

    assert client.get("/api/inesistente").get_json()["errore"] == "Risorsa non trovata."


def test_riga_di_comando_resta_in_italiano():
    with pytest.raises(importazione.ErroreImport, match="Formato non supportato"):
        importazione.leggi_file("dati.txt", b"x")


@pytest.mark.parametrize(("url", "titolo_it", "titolo_en"), [
    ("/alimento/999999", "Pagina non trovata", "Page not found"),
])
def test_pagine_di_errore(client, url, titolo_it, titolo_en):
    risposta = client.get(url)
    assert risposta.status_code == 404 and titolo_it in risposta.data.decode()
    assert titolo_en in in_inglese(client).get(url).data.decode()


def test_pagina_403(visitatore):
    risposta = visitatore.get("/nuovo")
    assert risposta.status_code == 403
    assert "Operazione riservata agli amministratori." in solo_testo(risposta.data)


# ---------------------------------------------------------------
# Guida, legenda, tabella
# ---------------------------------------------------------------

def test_guida(client):
    contenuto = solo_testo(client.get("/guida").data)
    assert "Livelli di rischio" in contenuto and "Punteggio complessivo" in contenuto
    # coefficienti del TEF letti da calcoli.py
    assert "25% per le proteine, 10% per i carboidrati, 5% per i grassi" in contenuto

    inglese = solo_testo(in_inglese(client).get("/guida").data)
    assert "25% for protein, 10% for carbohydrates, 5% for fat" in inglese
    assert "TEF: 25% of 36" in inglese


def test_home_legenda_e_ordinamento_mobile(client):
    html = client.get("/?categoria=Frutta&sort=kcal&dir=desc").data.decode()
    assert "Come leggere la tabella" in html
    mobile = html.split('class="ordina-mobile')[1].split("</form>")[0]
    assert '<input type="hidden" name="categoria" value="Frutta">' in mobile
    assert '<option value="kcal" selected>' in mobile
    assert '<option value="desc" selected>' in mobile


def test_colonne_secondarie_segnate(client):
    html = client.get("/").data.decode()
    intestazioni = html.split('class="table table-hover')[1].split("</thead>")[0]
    assert intestazioni.count("col-secondaria") == 5
    assert 'id="mostra-colonne"' in html


# ---------------------------------------------------------------
# Notifiche e conferme
# ---------------------------------------------------------------

def test_notifiche(admin):
    html = admin.get("/").data.decode()  # messaggio del login
    assert 'class="notifica notifica-success" data-tipo="success"' in html
    assert "Accesso effettuato come admin_t." in solo_testo(html.encode())


def test_conferme_con_finestra(admin, visitatore):
    assert 'data-conferma="Eliminare «Asparagus, raw» dal database?' in admin.get("/").data.decode()
    assert "data-conferma=" in admin.get("/alimento/787").data.decode()

    visitatore.post("/diario/aggiungi", data={"pasto": "pranzo", "alimento_id": 787, "grammi": "100"})
    assert "dal diario di questo giorno?" in visitatore.get("/diario").data.decode()

    visitatore.post("/pasto/aggiungi", data={"alimento_id": 787, "grammi": "100"})
    assert 'data-conferma="Togliere 1 alimento dal pasto?"' in visitatore.get("/pasto").data.decode()


# ---------------------------------------------------------------
# App installabile
# ---------------------------------------------------------------

def test_manifest(client):
    risposta = in_inglese(client).get("/manifest.webmanifest")
    assert risposta.mimetype == "application/manifest+json"
    dati = risposta.get_json()
    assert (dati["start_url"], dati["display"], dati["lang"]) == ("/", "standalone", "en")
    assert any(icona.get("purpose") == "maskable" for icona in dati["icons"])

    for icona in dati["icons"]:
        assert (PROGETTO / icona["src"].lstrip("/")).is_file()


def test_service_worker(app, client):
    risposta = client.get("/sw.js")
    assert risposta.mimetype == "text/javascript"
    assert risposta.headers["Cache-Control"] == "no-cache"
    testo = risposta.data.decode()

    with app.app_context():
        assert f'const VERSIONE = "{pwa.versione()}";' in testo

    assert '"food-stoplight-pagine"' in testo

    for percorso in pwa.STATICI:
        assert (PROGETTO / "static" / percorso).is_file(), percorso


def test_versione_cambia_con_i_file_statici(tmp_path):
    for percorso in pwa.STATICI:
        destinazione = tmp_path / "static" / percorso
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROGETTO / "static" / percorso, destinazione)

    shutil.copytree(PROGETTO / "templates", tmp_path / "templates")
    shutil.copytree(PROGETTO / "translations", tmp_path / "translations")

    prima = pwa._calcola_versione(tmp_path)
    assert prima == pwa._calcola_versione(Path(PROGETTO))

    css = tmp_path / "static" / "css" / "app.css"
    css.write_text(css.read_text() + "\n/* modifica */\n")
    assert pwa._calcola_versione(tmp_path) != prima


def test_pagina_offline(client):
    html = client.get("/offline").data.decode()
    assert 'data-cache-pagine="food-stoplight-pagine"' in html
    assert "Sei offline" in html


def test_precaricamento_non_consuma_i_messaggi(admin):
    admin.post("/backup/crea")
    html = admin.get("/", headers={"X-Precarica": "1"}).data.decode()
    assert "Backup salvato" not in html
    assert any("Backup salvato" in m for m in messaggi(admin))
    assert "Backup salvato" in admin.get("/").data.decode()


def test_uscita_cancella_le_pagine_salvate(admin):
    admin.post("/logout")
    assert "data-svuota-cache" in admin.get("/").data.decode()
    assert "data-svuota-cache" not in admin.get("/").data.decode()


def test_accesso_privato_lascia_raggiungibili_manifest_e_service_worker(app, client):
    app.config["ACCESSO_PUBBLICO"] = False

    for url in ("/manifest.webmanifest", "/sw.js", "/offline", "/static/icone/icona-192.png"):
        assert client.get(url).status_code == 200, url

    assert client.get("/lingua/en?next=/login").headers["Location"] == "/login"
    assert "/login" in client.get("/guida").headers["Location"]


def test_etichette_delle_schede_mobile(client, modulo):
    html = in_inglese(client).get("/").data.decode()
    assert '.tabella-alimenti .col-kcal_nette::before { content: "Net Kcal" " "; }' in html
    assert "data-etichetta" not in html
    # stringa CSS sicura anche con caratteri speciali
    assert str(modulo.filtro_css_testo('a"b\\c</style>')) == '"a\\"b\\\\c\\3c /style\\3e "'
