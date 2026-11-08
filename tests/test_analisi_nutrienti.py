"""Livelli di rischio, punteggio, medaglie, grafici, radar e calcoli nutrizionali."""

import pytest

import analisi
import nutrienti

RISCHI = analisi.CAMPI_RISCHIO


def tutti(livello, **altri):
    return {**dict.fromkeys(RISCHI, livello), **altri}


@pytest.mark.parametrize(("valore", "chiave"), [
    ("Basso", "basso"), ("  alto ", "alto"), ("Protettivo", "trascurabile"),
    ("Neutro", "trascurabile"), ("Aumentato", "alto"), ("Elevato", "alto"),
])
def test_livello_e_sinonimi(valore, chiave):
    assert analisi.livello(valore)["chiave"] == chiave


def test_livello_non_riconosciuto():
    assert analisi.livello("boh") is None
    assert analisi.stato("boh") == "nd"
    assert analisi.stato(None) == "nd"


def test_punteggio():
    assert analisi.calcola_punteggio("Trascurabile", "Trascurabile") == 100
    assert analisi.calcola_punteggio("Alto", "Alto", "Alto") == 0
    assert analisi.calcola_punteggio("Basso", "Medio", None, "", "boh") == 50
    assert analisi.calcola_punteggio(None, "") is None


@pytest.mark.parametrize(("punteggio", "etichetta"), [
    (100, "Trascurabile"), (84, "Trascurabile"), (83, "Basso"), (51, "Basso"),
    (50, "Medio"), (17, "Medio"), (16, "Alto"), (0, "Alto"), (None, "Non classificato"),
])
def test_livello_punteggio(punteggio, etichetta):
    assert analisi.livello_punteggio(punteggio)["etichetta"] == etichetta


def test_medaglie_e_classifica():
    alimenti = [
        {"id": 1, "alimento": "A", "punteggio": 100, "fibre": 2, "fruttosio": 2, "kcal": 50},
        {"id": 2, "alimento": "B", "punteggio": 100, "fibre": 9, "fruttosio": 1, "kcal": 0},
        {"id": 3, "alimento": "C", "punteggio": 40, "fibre": 1, "fruttosio": 5, "kcal": 30},
    ]
    protettivi = analisi.MEDAGLIE_PER_CHIAVE["protettivi"]
    assert [a["id"] for a, _ in analisi.classifica(alimenti, protettivi, 2)] == [2, 1]
    leggeri = analisi.MEDAGLIE_PER_CHIAVE["leggeri"]
    assert [a["id"] for a, _ in analisi.classifica(alimenti, leggeri, 5)] == [3, 1]  # 0 Kcal escluso
    medaglie = analisi.medaglie_per_alimento(alimenti, posti=1)
    assert [m["chiave"] for m in medaglie[2]] == ["protettivi", "fruttosio"]


def test_distribuzioni():
    alimenti = [tutti("Basso", categoria="Frutta"), tutti("Alto", categoria="Frutta"), tutti(None, categoria="")]
    categorie = analisi.distribuzione_categorie(alimenti)
    assert [(c["categoria"], c["n"]) for c in categorie] == [("Frutta", 2), ("Senza categoria", 1)]
    assert categorie[0]["larghezza"] == 100
    rischi = analisi.distribuzione_rischi(alimenti)
    assert len(rischi) == 5
    assert {s["chiave"]: s["n"] for s in rischi[0]["segmenti"]}["basso"] == 1


def test_radar_livelli_e_punti_medi():
    geometria = analisi.radar(tutti("Alto"))
    assert len(geometria["vertici"]) == 5
    assert all(v["stato"] == "critical" for v in geometria["vertici"])

    medio = analisi.radar({}, punti={"rischio_diabete": 1.4, "rischio_colesterolo": None,
                                     "rischio_malassorbimento": 0, "rischio_metabolico": 3,
                                     "rischio_tumorale": 2.5})
    assert [v["stato"] for v in medio["vertici"]] == ["warning", "nd", "good", "critical", "critical"]
    assert medio["vertici"][0]["valore"] == "Basso (1,4 su 3)"


def test_carico_glicemico_e_livelli():
    # Carboidrati disponibili: le fibre non si sottraggono più
    cibo = {"carboidrati": 25, "fibre": 5, "indice_glicemico": 60}
    assert nutrienti.carico_glicemico(cibo) == 15.0
    assert nutrienti.carico_glicemico(cibo, 150) == 22.5
    assert nutrienti.carico_glicemico({"carboidrati": 10}) is None
    assert nutrienti.livello_indice_glicemico(55)["etichetta"] == "Basso"
    assert nutrienti.livello_indice_glicemico(56)["etichetta"] == "Medio"
    assert nutrienti.livello_indice_glicemico(70)["etichetta"] == "Alto"
    assert nutrienti.livello_carico_glicemico(10)["etichetta"] == "Basso"
    assert nutrienti.livello_carico_glicemico(19.9)["etichetta"] == "Medio"
    assert nutrienti.livello_carico_glicemico(20)["etichetta"] == "Alto"


@pytest.mark.parametrize(("testo", "gruppo"), [
    ("4", 4), ("NOVA 2", 2), ("gruppo 3 - trasformati", 3), (1, 1), ("5", None), ("12", None), (None, None),
])
def test_leggi_nova(testo, gruppo):
    assert nutrienti.leggi_nova(testo) == gruppo


def test_fodmap():
    assert nutrienti.livello_fodmap("🔴 rosso")["etichetta"] == "Alto"
    assert nutrienti.livello_fodmap("verde")["etichetta"] == "Basso"
    assert nutrienti.livello_fodmap("boh") is None
    assert nutrienti.fodmap_complessivo({"fodmap_gos": "Basso", "fodmap_polioli": "Medio"})["etichetta"] == "Medio"
    assert nutrienti.fodmap_complessivo({}) is None


@pytest.mark.parametrize(("testo", "grammi"), [
    ("150", 150.0), ("12,5", 12.5), ("1", 1.0), ("2000", 2000.0), ("0", None), ("2001", None), ("abc", None),
])
def test_leggi_grammi(testo, grammi):
    assert nutrienti.leggi_grammi(testo) == grammi


def test_porzione_e_totali():
    cibo = {"kcal": 100, "proteine": 10, "vitamina_c": None}
    porzione = nutrienti.per_porzione(cibo, 150)
    assert (porzione["kcal"], porzione["proteine"], porzione["vitamina_c"]) == (150, 15, None)

    somme, mancanti = nutrienti.totali([({"kcal": 100, "proteine": 10}, 150), ({"kcal": 50, "proteine": None}, 100)])
    assert (somme["kcal"], somme["proteine"], somme["grammi"], mancanti["proteine"]) == (200, 15, 250, 1)


def test_profilo_pesato_sulle_kcal():
    burro = tutti("Alto", alimento="Burro", kcal=717)
    insalata = tutti("Trascurabile", alimento="Insalata", kcal=15)
    profilo = nutrienti.profilo_rischio([(burro, 10), (insalata, 300)])
    diabete = profilo["rischi"][0]
    # 71,7 Kcal di burro contro 45 di insalata: 3 × 71,7 / 116,7 = 1,84
    assert (profilo["pesato_su"], diabete["punti"], diabete["livello"]["etichetta"], diabete["principale"]) == (
        "Kcal", 1.84, "Medio", "Burro")


def test_profilo_alimenti_senza_kcal():
    acqua = tutti("Trascurabile", alimento="Acqua", kcal=0)
    burro = tutti("Alto", alimento="Burro", kcal=717)
    assert nutrienti.profilo_rischio([(acqua, 500), (burro, 10)])["rischi"][0]["punti"] == 3.0

    tutto_a_zero = nutrienti.profilo_rischio([(acqua, 300), ({**acqua, "rischio_diabete": "Alto"}, 100)])
    assert tutto_a_zero["pesato_su"] == "grammi"
    assert tutto_a_zero["rischi"][0]["punti"] == 0.75


def test_alternative():
    base = {"id": 1, "alimento": "Trota", "categoria": "Pesce", "punteggio": 50, "kcal": 100}
    alimenti = [
        base,
        {"id": 2, "alimento": "Trota", "categoria": "Pesce", "punteggio": 90, "kcal": 100},     # omonimo
        {"id": 3, "alimento": "Orata", "categoria": "pesce", "punteggio": 90, "kcal": 300},
        {"id": 4, "alimento": "Salmone", "categoria": "Pesce", "punteggio": 90, "kcal": 110},
        {"id": 5, "alimento": "Salmone", "categoria": "Pesce", "punteggio": 80, "kcal": 100},    # già visto
        {"id": 6, "alimento": "Mela", "categoria": "Frutta", "punteggio": 100, "kcal": 50},     # altra categoria
        {"id": 7, "alimento": "Polpo", "categoria": "Pesce", "punteggio": 40, "kcal": 80},      # peggiore
    ]
    scelte = nutrienti.alternative(base, alimenti)
    assert [a["id"] for a in scelte] == [4, 3]
    assert scelte[0]["guadagno"] == 40
    assert nutrienti.alternative({**base, "punteggio": None}, alimenti) == []
