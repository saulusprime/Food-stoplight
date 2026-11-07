"""Calcoli condivisi: numeri, arrotondamento, energia, TEF, rapporto F/F."""

import pytest

import calcoli


@pytest.mark.parametrize(("testo", "atteso"), [
    ("5,9", (5.9, True)),
    ("5.9", (5.9, True)),
    ("1.234,5", (1234.5, True)),
    ("1,234.5", (1234.5, True)),
    ("23,9%", (23.9, True)),
    ("5,9 g", (5.9, True)),
    ("52kcal", (52.0, True)),
    ("-3", (-3.0, True)),
    (".5", (0.5, True)),
    ("", (None, True)),
    ("N/A", (None, True)),
    ("nd", (None, True)),
    ("-", (None, True)),
    ("∞", (None, True)),
    ("abc", (None, False)),
    ("5,9,1", (None, False)),
    (None, (None, True)),
])
def test_leggi_numero(testo, atteso):
    assert calcoli.leggi_numero(testo) == atteso


@pytest.mark.parametrize(("valore", "cifre", "atteso"), [
    (2.8125, 3, 2.813),   # come ROUND() di SQLite, round() di Python darebbe 2.812
    (0.1 + 0.2, 2, 0.3),
    (12.045, 2, 12.05),
    (-1.005, 2, -1.01),
    (7.0, 0, 7.0),
])
def test_arrotonda(valore, cifre, atteso):
    assert calcoli.arrotonda(valore, cifre) == atteso


def test_kcal_da_macronutrienti():
    assert calcoli.kcal_da_macronutrienti(9, 49, 3.2) == pytest.approx(260.8)
    assert calcoli.kcal_da_macronutrienti(None, 10, None) == 40
    assert calcoli.kcal_da_macronutrienti(None, None, None) is None


def test_tef_da_macronutrienti_pesa_i_coefficienti():
    # solo proteine: 25%; solo carboidrati: 10%; solo grassi: 5%
    assert calcoli.tef_da_macronutrienti(100, 25, 0, 0) == (25.0, 25.0)
    assert calcoli.tef_da_macronutrienti(100, 0, 25, 0) == (10.0, 10.0)
    assert calcoli.tef_da_macronutrienti(90, 0, 0, 10) == (4.5, 5.0)
    tef_kcal, percentuale = calcoli.tef_da_macronutrienti(260.8, 9, 49, 3.2)
    assert (tef_kcal, percentuale) == (30.04, 11.52)


def test_tef_senza_energia_dai_macronutrienti():
    assert calcoli.tef_da_macronutrienti(100, 0, 0, 0) is None
    assert calcoli.tef_da_macronutrienti(100, None, None, None) is None


def test_rapporto_fruttosio_fibre():
    assert calcoli.rapporto_fruttosio_fibre(5.9, 2.4) == 2.458
    assert calcoli.rapporto_fruttosio_fibre(3, 0) == 0.0
    assert calcoli.rapporto_fruttosio_fibre(3, None) == 0.0


def test_completa_energia_nuovo_da_macronutrienti():
    valori = {"kcal": 0.0, "tef_kcal": 0.0, "tef_percent": 0.0, "kcal_nette": 0.0,
              "proteine": 9, "carboidrati": 49, "grassi": 3.2, "fruttosio": 0, "fibre": 6}
    calcoli.completa_energia(valori, {"proteine", "carboidrati", "grassi", "fibre"}, nuovo=True)
    assert valori["kcal"] == 260.8
    assert (valori["tef_kcal"], valori["tef_percent"]) == (30.04, 11.52)
    assert valori["kcal_nette"] == 230.76
    assert valori["rapporto"] == 0.0


def test_completa_energia_tef_da_percentuale():
    valori = {"kcal": 120.5, "tef_kcal": 0.0, "tef_percent": 10.0, "kcal_nette": 0.0, "fruttosio": 3, "fibre": 1.5}
    calcoli.completa_energia(valori, {"kcal", "tef_percent", "fruttosio", "fibre"}, nuovo=True)
    assert (valori["tef_kcal"], valori["kcal_nette"], valori["rapporto"]) == (12.05, 108.45, 2.0)


def test_completa_energia_percentuale_da_tef():
    valori = {"kcal": 200.0, "tef_kcal": 30.0, "tef_percent": 0.0, "kcal_nette": 0.0}
    calcoli.completa_energia(valori, {"kcal", "tef_kcal"}, nuovo=True)
    assert valori["tef_percent"] == 15.0
    assert valori["kcal_nette"] == 170.0


def test_completa_energia_aggiornamento_kcal_scala_il_tef():
    valori = {"kcal": 999.0, "tef_kcal": 7.7, "tef_percent": 11.1, "kcal_nette": 61.3, "fruttosio": 0, "fibre": 5}
    calcoli.completa_energia(valori, {"kcal"}, nuovo=False)
    assert valori["tef_kcal"] == 110.89
    assert valori["kcal_nette"] == 888.11


def test_completa_energia_aggiornamento_senza_cambi_non_tocca_nulla():
    valori = {"kcal": 69.0, "tef_kcal": 7.7, "tef_percent": 11.1, "kcal_nette": 61.3,
              "fruttosio": 0.0, "fibre": 5.3, "rapporto": 0.0, "proteine": 1.5}
    prima = dict(valori)
    calcoli.completa_energia(valori, set(), nuovo=False)
    assert valori == prima


def test_completa_energia_non_sovrascrive_tef_misurato():
    valori = {"kcal": 100.0, "tef_kcal": 8.0, "tef_percent": 8.0, "kcal_nette": 92.0, "proteine": 20}
    calcoli.completa_energia(valori, {"proteine"}, nuovo=False)
    assert (valori["tef_kcal"], valori["tef_percent"]) == (8.0, 8.0)
