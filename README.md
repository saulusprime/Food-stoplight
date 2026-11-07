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
- **Accesso con ruoli**: la consultazione può essere pubblica, mentre le operazioni di scrittura (nuovo, modifica, elimina, import) sono riservate agli amministratori. Form protetti da CSRF.
- **Import CSV intelligente** dall'interfaccia web:
  - riconoscimento automatico dell'encoding (UTF-8, CP1252, Latin-1)
  - riconoscimento automatico del separatore (`,` `;` tab)
  - mappatura flessibile delle intestazioni di colonna
  - opzione di svuotamento tabella prima dell'import
- **Statistiche** in home page: totale alimenti, alimenti con dati TEF, risultati filtrati.

## 📂 Struttura del progetto

```
Food-stoplight/
├── app.py              # Applicazione Flask principale (route, CRUD, import CSV, login, comandi utenti)
├── config.py           # Configurazione da variabili d'ambiente / .env (sviluppo e produzione)
├── .env.example        # Modello del file .env
├── update.py           # CLI per aggiornamento massivo del DB da CSV ed export dei dati mancanti
├── autogen.py          # Generatore del dataset: dati reali USDA FoodData Central + alimenti integrativi
├── alimenti.db         # Database SQLite precaricato (~1000 alimenti)
├── utenti.db           # Utenti e password (creato al primo avvio, escluso da git)
├── templates/          # Template Jinja2
│   ├── base.html       # Layout comune (navbar, stili, flash message)
│   ├── index.html      # Tabella alimenti con filtri e ordinamento
│   ├── form.html       # Form nuovo/modifica alimento
│   ├── import.html     # Pagina di import CSV
│   └── login.html      # Pagina di accesso
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

# 4. Crea il file di configurazione e genera la chiave segreta
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # incolla il valore in FLASK_SECRET_KEY

# 5. Crea il primo amministratore (la password viene chiesta a terminale)
flask --app app crea-utente admin

# 6. Avvia l'applicazione
python app.py
```

L'app sarà disponibile su **http://127.0.0.1:5000** (indirizzo e porta configurabili, vedi sotto).

Al primo avvio, se il database non esiste, viene creato automaticamente con lo schema corretto. Il repository include comunque `alimenti.db` già popolato con ~1000 alimenti.

## ⚙️ Configurazione

La configurazione si legge dalle variabili d'ambiente oppure dal file `.env` nella cartella del progetto (vedi [`.env.example`](.env.example)). Le variabili già impostate nell'ambiente hanno la precedenza su `.env`.

| Variabile | Default | Descrizione |
|---|---|---|
| `APP_ENV` | `sviluppo` | `sviluppo` oppure `produzione` |
| `FLASK_SECRET_KEY` | — | Chiave segreta per firmare le sessioni. **Obbligatoria in produzione** (almeno 32 caratteri); in sviluppo, se manca, ne viene generata una temporanea |
| `APP_HOST` / `APP_PORT` | `127.0.0.1` / `5000` | Indirizzo e porta di `python app.py` |
| `APP_DEBUG` | attivo in sviluppo | In produzione il debug è **sempre disattivato** |
| `ACCESSO_PUBBLICO` | `true` | `false`: serve il login anche solo per consultare la tabella |
| `SESSION_COOKIE_SECURE` | attivo in produzione | Cookie di sessione inviati solo su HTTPS |
| `DATABASE_PATH` / `UTENTI_DB_PATH` | `alimenti.db` / `utenti.db` | Percorsi dei database (relativi alla cartella del progetto) |
| `MAX_UPLOAD_MB` | `10` | Dimensione massima dei CSV importati |

## 👤 Utenti e ruoli

| Ruolo | Permessi |
|---|---|
| `admin` | Consultazione e gestione completa: nuovo, modifica, elimina, import CSV |
| `visitatore` | Sola consultazione (utile con `ACCESSO_PUBBLICO=false`) |

Gli utenti si gestiscono da riga di comando; le password sono salvate come hash in `utenti.db`, separato da `alimenti.db` ed escluso da git.

```bash
flask --app app crea-utente mario                      # amministratore (default)
flask --app app crea-utente lucia --ruolo visitatore   # sola consultazione
flask --app app imposta-password mario
flask --app app elenco-utenti
flask --app app elimina-utente lucia
```

## 🚢 Produzione

- Imposta `APP_ENV=produzione` e una `FLASK_SECRET_KEY` robusta: senza, l'app non parte.
- Servi l'app in **HTTPS**: in produzione i cookie di sessione sono `Secure` e su HTTP semplice il login non funziona (si può disattivare con `SESSION_COOKIE_SECURE=false`, sconsigliato).
- `python app.py` usa il server di sviluppo di Flask: per un deploy reale usa un server WSGI, ad esempio `waitress-serve --host 0.0.0.0 --port 8000 app:app` oppure `gunicorn app:app`.

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
| Sicurezza | Flask-Login (sessioni e ruoli), Flask-WTF (CSRF), python-dotenv |
| Database | SQLite 3 |
| Frontend | Jinja2, Bootstrap Italia 2.18.3 |
| Dati | USDA FoodData Central API |

## 👨‍💻 Sviluppatore

**Paolo Pierno**

## 📄 Licenza

Questo progetto include [Bootstrap Italia](https://italia.github.io/bootstrap-italia/), distribuito con la propria licenza (vedi `static/bootstrap-italia/LICENSE`).
