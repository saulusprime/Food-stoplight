"""Composizione del pasto (sessione) e diario alimentare (per utente)."""

import sqlite3
from datetime import date, timedelta

import pytest

from tests.aiuti import ASPARAGI, DB, DIARIO_DB, id_di, messaggi, solo_testo, sql


def pasto_di(cliente):
    with cliente.session_transaction() as sessione:
        return sessione.get("pasto", [])


def voci_diario():
    conn = sqlite3.connect(DIARIO_DB)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM diario ORDER BY id").fetchall()
    finally:
        conn.close()





def test_pasto_aggiunta_ricerca_e_somma(client):
    burro = id_di("Burro")
    risposta = client.post("/pasto/aggiungi", data={"alimento_id": ASPARAGI, "grammi": "150",
                                                    "next": f"/alimento/{ASPARAGI}?grammi=150"})
    assert risposta.headers["Location"].endswith(f"/alimento/{ASPARAGI}?grammi=150")
    client.post("/pasto/aggiungi", data={"cerca": f"Burro · Latticini e Uova · 717 Kcal · #{burro}", "grammi": "10"})
    client.post("/pasto/aggiungi", data={"alimento_id": ASPARAGI, "grammi": "50"})
    assert pasto_di(client) == [{"id": ASPARAGI, "grammi": 200.0}, {"id": burro, "grammi": 10.0}]
    contenuto = solo_testo(client.get("/pasto").data)
    assert "Profilo di rischio del pasto" in contenuto


@pytest.mark.parametrize(("dati", "messaggio"), [
    ({"cerca": "Non esiste", "grammi": "100"}, "Nessun alimento"),
    ({"alimento_id": "999999", "grammi": "100"}, "non trovato"),
    ({"alimento_id": str(ASPARAGI), "grammi": "abc"}, "Grammi non validi"),
    ({"alimento_id": str(ASPARAGI), "grammi": "5000"}, "Grammi non validi"),
])
def test_pasto_errori(client, dati, messaggio):
    client.post("/pasto/aggiungi", data=dati)
    assert any(messaggio in m for m in messaggi(client))
    assert pasto_di(client) == []


def test_pasto_nome_ambiguo(client):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO alimenti (alimento, categoria) VALUES ('Trota', 'Pesce'), ('Trota', 'Test')")
    conn.commit()
    conn.close()
    client.post("/pasto/aggiungi", data={"cerca": "Trota", "grammi": "100"})
    assert any("Ci sono" in m for m in messaggi(client))
    assert pasto_di(client) == []


def test_pasto_niente_open_redirect(client):
    risposta = client.post("/pasto/aggiungi", data={"alimento_id": ASPARAGI, "grammi": "10", "next": "https://evil.example/"})
    assert risposta.headers["Location"].endswith("/pasto")


def test_pasto_aggiorna_rimuovi_svuota_massimo(client):
    ids = [r["id"] for r in sql("SELECT id FROM alimenti ORDER BY id LIMIT 31")]
    for alimento_id in ids:
        client.post("/pasto/aggiungi", data={"alimento_id": alimento_id, "grammi": "10"})
    assert len(pasto_di(client)) == 30

    client.post("/pasto/aggiorna", data={"grammi_0": "100", "grammi_1": "20"})
    assert [v["grammi"] for v in pasto_di(client)[:2]] == [100.0, 20.0]
    client.post("/pasto/aggiorna", data={"rimuovi": "0"})
    assert len(pasto_di(client)) == 29
    client.post("/pasto/svuota")
    assert pasto_di(client) == []


def test_diario_richiede_login(client):
    assert "/login" in client.get("/diario").headers["Location"]
    assert client.post("/diario/aggiungi", data={}).status_code == 302


def test_diario_aggiunta_e_totali(visitatore):
    oggi = date.today().isoformat()
    visitatore.post("/diario/aggiungi", data={"data": oggi, "pasto": "pranzo", "alimento_id": ASPARAGI, "grammi": "200"})
    visitatore.post("/diario/aggiungi", data={"data": oggi, "pasto": "merenda", "alimento_id": ASPARAGI, "grammi": "10"})
    assert any("Scegli il pasto" in m for m in messaggi(visitatore))
    contenuto = solo_testo(visitatore.get("/diario").data)
    assert "Pranzo · 66 Kcal" in contenuto        # 33 Kcal per 100 g
    assert "Ultimi 7 giorni" in contenuto


def test_diario_salva_pasto(visitatore):
    visitatore.post("/pasto/aggiungi", data={"alimento_id": ASPARAGI, "grammi": "100"})
    visitatore.post("/pasto/aggiungi", data={"alimento_id": id_di("Burro"), "grammi": "10"})
    visitatore.post("/diario/aggiungi-pasto", data={"data": date.today().isoformat(), "pasto": "cena", "svuota": "1"})
    assert pasto_di(visitatore) == []
    assert [v["pasto"] for v in voci_diario()] == ["cena", "cena"]


def test_diario_valori_congelati_e_alimento_eliminato(admin, visitatore):
    visitatore.post("/diario/aggiungi", data={"pasto": "pranzo", "alimento_id": ASPARAGI, "grammi": "100"})
    admin.post(f"/modifica/{ASPARAGI}", data={"alimento": "Asparagi di campo, crudi", "kcal": "999"})
    assert "Pranzo · 33 Kcal" in solo_testo(visitatore.get("/diario").data)
    admin.post(f"/elimina/{ASPARAGI}")
    assert "(non più nel database)" in solo_testo(visitatore.get("/diario").data)


def test_diario_isolato_tra_utenti(visitatore, altro_visitatore):
    visitatore.post("/diario/aggiungi", data={"pasto": "pranzo", "alimento_id": ASPARAGI, "grammi": "100"})
    voce = voci_diario()[0]["id"]
    assert "Nessun alimento registrato" in solo_testo(altro_visitatore.get("/diario").data)
    assert altro_visitatore.post(f"/diario/voce/{voce}/aggiorna", data={"grammi": "1"}).status_code == 404
    assert altro_visitatore.post(f"/diario/voce/{voce}/elimina").status_code == 404

    visitatore.post(f"/diario/voce/{voce}/aggiorna", data={"grammi": "75"})
    assert voci_diario()[0]["grammi"] == 75
    visitatore.post(f"/diario/voce/{voce}/elimina")
    assert voci_diario() == []


def test_diario_date(visitatore):
    ieri = (date.today() - timedelta(days=1)).isoformat()
    visitatore.post("/diario/aggiungi", data={"data": ieri, "pasto": "cena", "alimento_id": ASPARAGI, "grammi": "100"})
    assert "Cena · 33 Kcal" in solo_testo(visitatore.get(f"/diario?data={ieri}").data)
    assert visitatore.get("/diario?data=2026-13-40").status_code == 200
