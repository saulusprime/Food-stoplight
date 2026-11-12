"""
Pasti pronti: lettura dei file, calcolo del piatto dagli ingredienti,
caricamento nel database, pagina dell'elenco, scheda e aggiunta al pasto.
"""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import database
import fonti
import nutrienti
import pasti_pronti
from tests.aiuti import DB, PROGETTO

ADESSO = "2026-11-12 12:00:00"

PASTA, OLIO, AGLIO, VINO = "000800", "009210", "005000", "405010"


def ricetta(**cambi: Any) -> dict[str, Any]:
    base = {
        "codice": "pasta-aglio-e-vino",
        "nome": "Pasta aglio, olio e vino di prova",
        "portata": "primo",
        "porzioni": 4,
        "fonte": "Wikibooks",
        "url_fonte": "https://it.wikibooks.org/wiki/Libro_di_cucina/Ricette/Prova",
        "note": None,
        "ingredienti": [
            {"ingrediente": "spaghetti, 320 g", "codice_crea": PASTA, "grammi": 320.0, "resa": 1.95, "nota": None},
            {"ingrediente": "olio, 40 g", "codice_crea": OLIO, "grammi": 40.0, "resa": 1.0, "nota": None},
            {"ingrediente": "aglio, 2 spicchi", "codice_crea": AGLIO, "grammi": 8.0, "resa": 1.0, "nota": None},
            {"ingrediente": "vino bianco, 1 bicchiere", "codice_crea": VINO, "grammi": 150.0, "resa": 0.5, "nota": None},
            {"ingrediente": "acqua di cottura, 100 g", "codice_crea": None, "grammi": 100.0, "resa": 0.5, "nota": None},
            {"ingrediente": "sale, q.b.", "codice_crea": None, "grammi": None, "resa": 1.0, "nota": None},
        ],
    }
    base.update(cambi)
    return base


def connessione() -> sqlite3.Connection:
    return database.connetti_alimenti(str(DB))


def alimenti_crea(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {r["codice_crea"]: dict(r) for r in conn.execute("SELECT * FROM alimenti WHERE codice_crea IS NOT NULL")}


@pytest.fixture
def caricato() -> dict[str, Any]:
    """
    Nel database di prova solo la ricetta di prova (le altre si eliminano).
    """
    conn = connessione()

    try:
        esito = fonti.carica_pasti_pronti(conn, [ricetta()], ADESSO)
        conn.commit()
        riga = conn.execute("SELECT * FROM pasti_pronti WHERE codice = 'pasta-aglio-e-vino'").fetchone()
        return {"esito": esito, "alimento_id": riga["alimento_id"]}
    finally:
        conn.close()


# ---------------------------------------------------------------
# Calcolo
# ---------------------------------------------------------------

def test_piatto_diviso_per_il_peso_cotto_con_alcol_ridotto() -> None:
    conn = connessione()
    alimenti = alimenti_crea(conn)
    conn.close()

    r = ricetta()
    valori = pasti_pronti.calcola(r, alimenti)
    cotto = 320 * 1.95 + 40 + 8 + 150 * 0.5 + 100 * 0.5
    assert pasti_pronti.peso_cotto(r) == pytest.approx(cotto)
    assert valori["porzione"] == round(cotto / 4)

    proteine = sum(alimenti[c]["proteine"] * g / 100 for c, g in ((PASTA, 320), (OLIO, 40), (AGLIO, 8), (VINO, 150))
                   if alimenti[c]["proteine"] is not None)
    assert valori["proteine"] == pytest.approx(proteine / cotto * 100, abs=0.01)

    alcol = alimenti[VINO]["alcol"] * 150 / 100
    assert valori["alcol"] == pytest.approx(alcol * pasti_pronti.RITENZIONE_ALCOL / cotto * 100, abs=0.01)

    kcal = sum(alimenti[c]["kcal"] * g / 100 for c, g in ((PASTA, 320), (OLIO, 40), (AGLIO, 8), (VINO, 150)))
    kcal -= alcol * (1 - pasti_pronti.RITENZIONE_ALCOL) * pasti_pronti.KCAL_ALCOL
    assert valori["kcal"] == pytest.approx(kcal / cotto * 100, abs=0.01)
    assert valori["categoria"] == pasti_pronti.CATEGORIA
    assert valori["url_fonte"].startswith("https://it.wikibooks.org/")


def test_valore_non_disponibile_se_manca_per_troppi_ingredienti() -> None:
    alimenti = {
        "A": {"kcal": 100, "grassi": 10, "grassi_saturi": 2, "zuccheri": 0, "vitamina_c": None},
        "B": {"kcal": 50, "grassi": 10, "grassi_saturi": None, "zuccheri": 0, "vitamina_c": 5},
        "C": {"kcal": 10, "grassi": 0, "grassi_saturi": None, "zuccheri": 0, "vitamina_c": 1},
    }
    voci = [
        {"ingrediente": "a", "codice_crea": "A", "grammi": 100.0, "resa": 1.0},
        {"ingrediente": "b", "codice_crea": "B", "grammi": 100.0, "resa": 1.0},
        {"ingrediente": "c", "codice_crea": "C", "grammi": 100.0, "resa": 1.0},
    ]
    valori = pasti_pronti.calcola(ricetta(ingredienti=voci, porzioni=1), alimenti)

    # B porta metà dei grassi senza il dato dei saturi; C non ha grassi e non conta
    assert valori["grassi_saturi"] is None
    # Senza zuccheri non c'è fruttosio da stimare: zero, non "non disponibile"
    assert valori["fruttosio"] == 0
    # La vitamina C manca per un terzo del peso
    assert valori["vitamina_c"] is None
    assert valori["kcal"] == pytest.approx(160 / 300 * 100, abs=0.01)

    voci[1]["grammi"] = 2.0   # ora B porta meno del 5% dei grassi: si estende la quota nota
    valori = pasti_pronti.calcola(ricetta(ingredienti=voci, porzioni=1), alimenti)
    assert valori["grassi_saturi"] == pytest.approx(2 * (10 + 0.2) / 10 / 202 * 100, abs=0.01)


def test_ingrediente_inesistente() -> None:
    voci = [{"ingrediente": "x", "codice_crea": "999999", "grammi": 10.0, "resa": 1.0}]

    with pytest.raises(pasti_pronti.IngredientiMancanti) as errore:
        pasti_pronti.calcola(ricetta(ingredienti=voci), {})

    assert errore.value.codici == ["999999"]


def test_nome_del_piatto_omonimo() -> None:
    assert pasti_pronti.nome_piatto("Pasta e fagioli", {"pasta e fagioli"}) == "Pasta e fagioli (pasto pronto)"
    assert pasti_pronti.nome_piatto("Ribollita", {"pasta e fagioli"}) == "Ribollita"


def test_grammi_per_porzione() -> None:
    voci = pasti_pronti.per_porzione(ricetta(), porzioni=2)
    assert [v["codice_crea"] for v in voci] == [PASTA, OLIO, AGLIO, VINO]
    assert voci[0]["grammi_porzione"] == 160


# ---------------------------------------------------------------
# File
# ---------------------------------------------------------------

def scrivi_csv(percorso: Path, intestazione: list[str], righe: list[list[str]]) -> Path:
    with percorso.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(intestazione)
        scrittore.writerows(righe)
    return percorso


def test_leggi_dati_segnala_tutti_gli_errori(tmp_path: Path) -> None:
    pasti = scrivi_csv(tmp_path / "p.csv", ["codice", "nome", "portata", "porzioni", "fonte", "url", "note"], [
        ["buona", "Buona", "primo", "2", "Wikibooks", "https://x", ""],
        ["buona", "Doppia", "primo", "2", "Wikibooks", "", ""],
        ["Male Scritto", "X", "primo", "2", "Wikibooks", "", ""],
        ["portata-strana", "Y", "dolce", "0", "Altro", "", ""],
    ])
    ingredienti = scrivi_csv(tmp_path / "i.csv", ["codice", "ingrediente", "codice_crea", "grammi", "resa", "nota"], [
        ["buona", "pasta, 200 g", PASTA, "200", "1.95", ""],
        ["buona", "olio", OLIO, "", "1", ""],
        ["inesistente", "aglio", AGLIO, "4", "1", ""],
        ["portata-strana", "acqua", "", "100", "0", ""],
    ])

    with pytest.raises(pasti_pronti.ErroreDati) as errore:
        pasti_pronti.leggi_dati(pasti, ingredienti)

    testo = "\n".join(errore.value.errori)
    for atteso in ("codice ripetuto", "codice non valido", "portata non valida", "fonte non valida",
                   "porzioni non valide", "alimento senza grammi", "ricetta inesistente", "resa non valida",
                   "«portata-strana» senza ingredienti abbinati"):
        assert atteso in testo


# ---------------------------------------------------------------
# Database
# ---------------------------------------------------------------

def test_carica_crea_il_piatto_e_poi_resta_invariato(caricato: dict[str, Any]) -> None:
    assert caricato["esito"]["nuovi"] == 1
    conn = connessione()

    try:
        piatto = dict(conn.execute("SELECT * FROM alimenti WHERE id = ?", (caricato["alimento_id"],)).fetchone())
        assert piatto["categoria"] == "Piatti e ricette"
        assert piatto["alimento"] == "Pasta aglio, olio e vino di prova"
        assert piatto["porzione"] > 0 and piatto["kcal"] > 0
        assert all(piatto[c] for c in ("rischio_diabete", "rischio_metabolico", "rischio_tumorale"))
        assert conn.execute("SELECT COUNT(*) FROM pasti_pronti").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pasti_pronti_ingredienti").fetchone()[0] == 6

        esito = fonti.carica_pasti_pronti(conn, [ricetta()], ADESSO)
        assert (esito["nuovi"], esito["aggiornati"], esito["invariati"]) == (0, 0, 1)

        # Una ricetta tolta dai file sparisce con il suo piatto
        altra = ricetta(codice="altra", nome="Altra ricetta di prova")
        esito = fonti.carica_pasti_pronti(conn, [altra], ADESSO)
        assert esito["eliminati"] == 1
        assert conn.execute("SELECT COUNT(*) FROM alimenti WHERE id = ?", (caricato["alimento_id"],)).fetchone()[0] == 0
    finally:
        conn.rollback()
        conn.close()


def test_carica_rifiuta_codici_inesistenti() -> None:
    conn = connessione()

    try:
        voci = [{"ingrediente": "x", "codice_crea": "ZZ9999", "grammi": 10.0, "resa": 1.0, "nota": None}]

        with pytest.raises(pasti_pronti.IngredientiMancanti):
            fonti.carica_pasti_pronti(conn, [ricetta(ingredienti=voci)], ADESSO)
    finally:
        conn.rollback()
        conn.close()


def test_ricalcolo_segue_gli_ingredienti(caricato: dict[str, Any]) -> None:
    conn = connessione()

    try:
        prima = conn.execute("SELECT kcal FROM alimenti WHERE id = ?", (caricato["alimento_id"],)).fetchone()[0]
        conn.execute("UPDATE alimenti SET kcal = kcal + 100 WHERE codice_crea = ?", (OLIO,))
        assert fonti.ricalcola_ricette(conn, ADESSO) >= 1
        dopo = conn.execute("SELECT kcal FROM alimenti WHERE id = ?", (caricato["alimento_id"],)).fetchone()[0]
        assert dopo > prima

        # Piatto eliminato a mano: il ricalcolo non lo ricrea, il caricamento sì
        conn.execute("DELETE FROM alimenti WHERE id = ?", (caricato["alimento_id"],))
        assert fonti.aggiorna_pasti_pronti(conn, ADESSO)["nuovi"] == 0
        assert fonti.aggiorna_pasti_pronti(conn, ADESSO, crea_mancanti=True)["nuovi"] == 1
    finally:
        conn.rollback()
        conn.close()


def test_comando_pasti_importa(app: Any) -> None:
    risultato = app.test_cli_runner().invoke(args=["pasti-importa", "--prova"])
    assert risultato.exit_code == 0, risultato.output
    assert "Prova: nessuna modifica scritta." in risultato.output


# ---------------------------------------------------------------
# Pagine
# ---------------------------------------------------------------

def test_elenco_per_portata(client: Any, caricato: dict[str, Any]) -> None:
    html = client.get("/pasti-pronti").data.decode()
    assert "Pasta aglio, olio e vino di prova" in html
    assert f'href="/alimento/{caricato["alimento_id"]}"' in html
    assert "/pasti-pronti/pasta-aglio-e-vino/aggiungi" in html
    assert "CC BY-SA 4.0" in html

    html = client.get("/pasti-pronti?portata=secondo").data.decode()
    assert "Pasta aglio, olio e vino di prova" not in html

    assert client.get("/pasti-pronti?portata=xyz&ordina=abc").status_code == 200


def test_aggiungi_ingredienti_al_pasto(client: Any, caricato: dict[str, Any]) -> None:
    risposta = client.post("/pasti-pronti/pasta-aglio-e-vino/aggiungi", data={"porzioni": "2"})
    assert risposta.status_code == 302 and risposta.headers["Location"].endswith("/pasto")

    with client.session_transaction() as sessione:
        pasto = sessione["pasto"]

    conn = connessione()
    ids = {r["codice_crea"]: r["id"] for r in conn.execute("SELECT id, codice_crea FROM alimenti WHERE codice_crea IN (?, ?, ?, ?)",
                                                          (PASTA, OLIO, AGLIO, VINO))}
    conn.close()
    grammi = {voce["id"]: voce["grammi"] for voce in pasto}
    assert grammi == {ids[PASTA]: 160, ids[OLIO]: 20, ids[AGLIO]: 4, ids[VINO]: 75}

    # Di nuovo: i grammi si sommano, gli alimenti restano quattro
    client.post("/pasti-pronti/pasta-aglio-e-vino/aggiungi", data={"porzioni": "1"})
    with client.session_transaction() as sessione:
        assert {voce["id"]: voce["grammi"] for voce in sessione["pasto"]}[ids[PASTA]] == 240


def test_aggiungi_porzioni_non_valide_e_pasto_pieno(client: Any, caricato: dict[str, Any]) -> None:
    html = client.post("/pasti-pronti/pasta-aglio-e-vino/aggiungi", data={"porzioni": "99"},
                       follow_redirects=True).data.decode()
    assert "Porzioni non valide" in html

    with client.session_transaction() as sessione:
        sessione["pasto"] = [{"id": i, "grammi": 10} for i in range(1, 30)]

    html = client.post("/pasti-pronti/pasta-aglio-e-vino/aggiungi", data={"porzioni": "1"},
                       follow_redirects=True).data.decode()
    assert "al massimo 30 alimenti" in html

    with client.session_transaction() as sessione:
        assert len(sessione["pasto"]) == 29

    assert client.post("/pasti-pronti/non-esiste/aggiungi").status_code == 404


def test_quantita_minime_salgono_al_grammo(client: Any) -> None:
    voci = ricetta()["ingredienti"]
    voci[2] = {**voci[2], "grammi": 1.0}   # aglio: 0,25 g a porzione
    conn = connessione()
    fonti.carica_pasti_pronti(conn, [ricetta(ingredienti=voci)], ADESSO)
    conn.commit()
    aglio = conn.execute("SELECT id FROM alimenti WHERE codice_crea = ?", (AGLIO,)).fetchone()[0]
    conn.close()

    client.post("/pasti-pronti/pasta-aglio-e-vino/aggiungi", data={"porzioni": "1"})

    with client.session_transaction() as sessione:
        assert {voce["id"]: voce["grammi"] for voce in sessione["pasto"]}[aglio] == nutrienti.GRAMMI_MIN


def test_scheda_del_piatto_con_ingredienti(client: Any, caricato: dict[str, Any]) -> None:
    html = client.get(f"/alimento/{caricato['alimento_id']}").data.decode()
    assert "Ingredienti per una porzione" in html
    assert "spaghetti, 320 g" in html and "80.0 g" not in html   # 80,0 g in italiano
    assert "80,0 g" in html
    assert "non conteggiato" in html and "solo peso" in html
    assert "Wikibooks, Libro di cucina" in html
    assert "/pasti-pronti/pasta-aglio-e-vino/aggiungi" in html


# ---------------------------------------------------------------
# Dati del progetto
# ---------------------------------------------------------------

def test_dati_del_progetto_validi_e_caricati() -> None:
    """
    I file in dati/ si leggono senza errori, hanno 100 ricette divise tra le
    portate e alimenti.db del progetto è allineato: ricaricarli non cambia nulla.
    """
    ricette = pasti_pronti.leggi_dati()
    assert len(ricette) == 100
    assert Counter(r["portata"] for r in ricette) == {"antipasto": 20, "primo": 30, "secondo": 30, "contorno": 20}
    assert all(r["url_fonte"] and r["url_fonte"].startswith("https://") for r in ricette)

    conn = database.connetti_alimenti(str(PROGETTO / "alimenti.db"))

    try:
        nomi = Counter(r[0].casefold() for r in conn.execute("SELECT alimento FROM alimenti"))
        piatti = {r["codice"]: dict(r) for r in conn.execute(
            "SELECT p.codice, a.alimento, a.porzione FROM pasti_pronti p JOIN alimenti a ON a.id = p.alimento_id")}
        assert set(piatti) == {r["codice"] for r in ricette}
        # Ogni piatto ha un nome solo suo (le omonimie con le ricette CREA prendono il suffisso)
        assert all(nomi[piatto["alimento"].casefold()] == 1 for piatto in piatti.values())
        assert all(60 <= piatto["porzione"] <= 700 for piatto in piatti.values())

        esito = fonti.carica_pasti_pronti(conn, ricette, ADESSO)
        assert (esito["nuovi"], esito["aggiornati"], esito["eliminati"]) == (0, 0, 0), esito
        assert not esito["errori"]
    finally:
        conn.rollback()
        conn.close()
