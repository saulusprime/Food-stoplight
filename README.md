# 🥗 Food-stoplight

**Food-stoplight** è una web app per consultare e gestire un database nutrizionale di oltre 1000 alimenti, con un sistema "a semaforo" (🟢 Basso / 🟡 Medio / 🔴 Alto) che classifica ogni alimento in base a cinque profili di rischio per la salute.

Sviluppata in **Python + Flask** con database **SQLite** e interfaccia basata su **Bootstrap Italia**.

## ✨ Funzionalità

- **Tabella interattiva** di tutti gli alimenti con ordinamento su ogni colonna e filtri combinabili per categoria e livelli di rischio.
- **Sistema a semaforo** per cinque indicatori di rischio:
  - 🩸 Rischio Diabete
  - 🫀 Rischio Colesterolo
  - 🌾 Rischio Malassorbimento (fruttosio/FODMAP)
  - ⚖️ Rischio Metabolico
  - 🛡️ Rischio Tumorale (Protettivo / Neutro / Aumentato)
- **Dati energetici avanzati** per ogni alimento:
  - Kcal totali
  - **TEF** (Effetto Termico del Cibo), in Kcal e in percentuale
  - **Kcal Nette** (Kcal − TEF)
  - Fruttosio, Fibre e **Rapporto Fruttosio/Fibre**
- **CRUD completo**: inserimento, modifica ed eliminazione degli alimenti tramite form web, con calcolo automatico dei campi derivati (TEF, Kcal nette, rapporto F/F).
- **Import CSV intelligente** dall'interfaccia web:
  - riconoscimento automatico dell'encoding (UTF-8, CP1252, Latin-1)
  - riconoscimento automatico del separatore (`,` `;` tab)
  - mappatura flessibile delle intestazioni di colonna
  - opzione di svuotamento tabella prima dell'import
- **Statistiche** in home page: totale alimenti, alimenti con dati TEF, risultati filtrati.

## 📂 Struttura del progetto

```
Food-stoplight/
├── app.py              # Applicazione Flask principale (route, CRUD, import CSV)
├── update.py           # CLI per aggiornamento massivo del DB da CSV ed export dei dati mancanti
├── autogen.py          # Generatore del dataset: dati reali USDA FoodData Central + alimenti integrativi
├── alimenti.db         # Database SQLite precaricato (~1000 alimenti)
├── templates/          # Template Jinja2
│   ├── base.html       # Layout comune (navbar, stili, flash message)
│   ├── index.html      # Tabella alimenti con filtri e ordinamento
│   ├── form.html       # Form nuovo/modifica alimento
│   └── import.html     # Pagina di import CSV
├── static/
│   └── bootstrap-italia/   # Bootstrap Italia 2.18.3 (CSS, JS, font, icone)
└── docs/               # Dataset di esempio (CSV/XLSX) e prototipi HTML
```

## 🚀 Installazione e avvio

Requisiti: **Python 3.10+**

```bash
# 1. Clona il repository
git clone https://github.com/<tuo-utente>/Food-stoplight.git
cd Food-stoplight

# 2. Crea e attiva l'ambiente virtuale
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Installa le dipendenze
pip install -r requirements.txt

# 4. Avvia l'applicazione
python app.py
```

L'app sarà disponibile su **http://127.0.0.1:5000**.

Al primo avvio, se il database non esiste, viene creato automaticamente con lo schema corretto. Il repository include comunque `alimenti.db` già popolato con ~1000 alimenti.

## 🛠️ Strumenti a riga di comando

### `update.py` — aggiornamento massivo del database

Aggiorna o inserisce alimenti da un file CSV, con calcolo automatico dei campi mancanti (Kcal dai macronutrienti, TEF, Kcal nette, rapporto F/Fibre):

```bash
# Import/aggiornamento da CSV
python update.py --csv dati.csv

# Simulazione senza scrivere sul database
python update.py --csv dati.csv --dry-run

# Esporta gli alimenti con dati incompleti da integrare
python update.py --esporta-mancanti da_completare.csv

# Database alternativo
python update.py --db altro.db --csv dati.csv
```

### `autogen.py` — generazione del dataset

Genera il file `1000_foods_complete.csv` combinando:

1. **Dati reali** dall'API [USDA FoodData Central](https://fdc.nal.usda.gov/) (dataset Foundation e SR Legacy)
2. **Alimenti integrativi** generati con distribuzioni nutrizionali realistiche per categoria

```bash
python autogen.py
```

## 🧮 Note metodologiche

- **TEF (Thermic Effect of Food)**: stimato pesando i macronutrienti con i coefficienti standard — proteine ~25%, carboidrati ~7,5–10%, grassi ~2,5–5% dell'energia.
- **Kcal Nette** = Kcal totali − TEF (Kcal).
- **Rapporto Fruttosio/Fibre**: indicatore utile per la valutazione del malassorbimento del fruttosio; le fibre ne favoriscono la tolleranza.
- **Indicatori di rischio**: assegnati tramite punteggi basati su soglie di zuccheri, grassi saturi, colesterolo, fibre e fruttosio, con riferimento alle indicazioni OMS/WCRF per il rischio tumorale.

> ⚠️ **Disclaimer**: i dati e le classificazioni hanno finalità informative e di studio. Non sostituiscono il parere di un medico o di un nutrizionista.

## 🧰 Tecnologie

| Componente | Tecnologia |
|---|---|
| Backend | Python 3, Flask 3 |
| Database | SQLite 3 |
| Frontend | Jinja2, Bootstrap Italia 2.18.3 |
| Dati | USDA FoodData Central API |

## 👨‍💻 Sviluppatore

**Paolo Pierno**

## 📄 Licenza

Questo progetto include [Bootstrap Italia](https://italia.github.io/bootstrap-italia/), distribuito con la propria licenza (vedi `static/bootstrap-italia/LICENSE`).
