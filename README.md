# 🥗 Food-stoplight

**Food-stoplight** è una web app per consultare e gestire un database nutrizionale di oltre 1000 alimenti, con un sistema "a semaforo" a quattro livelli (🟢 Trascurabile / 🟡 Basso / 🟠 Medio / 🔴 Alto) che classifica ogni alimento in base a cinque profili di rischio per la salute.

Sviluppata in **Python + Flask** con database **SQLite** e interfaccia basata su **Bootstrap Italia**.

## ✨ Funzionalità

- **Tabella interattiva** di tutti gli alimenti con ordinamento su ogni colonna e filtri combinabili per categoria e livelli di rischio.
- **Sistema a semaforo** per cinque indicatori di rischio:
  - 🩸 Rischio Diabete
  - 🫀 Rischio Colesterolo
  - 🌾 Rischio Malassorbimento (fruttosio/FODMAP)
  - ⚖️ Rischio Metabolico
  - 🛡️ Rischio Tumorale
- **Dati energetici avanzati** per ogni alimento:
  - Kcal totali
  - **TEF** (Effetto Termico del Cibo), in Kcal e in percentuale
  - **Kcal Nette** (Kcal − TEF)
  - Fruttosio, Fibre e **Rapporto Fruttosio/Fibre**
- **CRUD completo**: inserimento, modifica ed eliminazione degli alimenti tramite form web, con calcolo automatico dei campi derivati (TEF, Kcal nette, rapporto F/F).
- **Accesso con ruoli**: la consultazione può essere pubblica, mentre le operazioni di scrittura (nuovo, modifica, elimina, import, backup) sono riservate agli amministratori. Form protetti da CSRF.
- **Import CSV ed Excel (.xlsx) con anteprima** dall'interfaccia web:
  - riconoscimento automatico di encoding (UTF-8, CP1252, Latin-1) e separatore (`,` `;` tab) dei CSV
  - mappatura flessibile delle intestazioni di colonna; numeri con virgola o punto, livelli anche con emoji
  - anteprima prima di scrivere: righe nuove, aggiornate (con le celle che cambiano), invariate e saltate, avvisi riga per riga
  - tre modalità: **aggiorna o aggiungi** (upsert per ID oppure per nome e categoria), aggiungi tutte come nuove, sostituisci l'intera tabella
  - backup automatico del database prima di ogni import
- **Export** della tabella filtrata e ordinata in **CSV**, **Excel** (livelli colorati, foglio con filtri e legenda) e **PDF**; **PDF della scheda alimento** con punteggio, valori e radar.
- **Backup e ripristino** del database dall'interfaccia: download, backup sul server, ripristino da file o da un backup salvato (con verifica del file e copia di sicurezza del database attuale).
- **Riepilogo grafico** in home page, aggiornato in base ai filtri: alimenti per categoria, distribuzione dei livelli per ciascun rischio, punteggio medio e classifiche "top alimenti". Ogni grafico ha la sua vista tabellare.
- **Punteggio complessivo 0–100** per alimento, ordinabile in tabella: 100 = tutti i rischi trascurabili, 0 = tutti alti.
- **Medaglie** 🛡️ più protettivi · 🍃 miglior rapporto fruttosio/fibre · 🪶 meno calorici, assegnate ai primi 10 di ciascuna classifica.
- **Scheda alimento** con punteggio, valori nutrizionali e grafico radar del profilo di rischio.
- **Modalità scura**: segue il sistema operativo oppure si attiva con il pulsante 🌙 nella barra in alto.
- **Dati nutrizionali completi** nella scheda, nel form e in import/export: macronutrienti (proteine, carboidrati, zuccheri, grassi, saturi, colesterolo), 12 tra vitamine e sali minerali, indice e carico glicemico, FODMAP per categoria e grado di processazione NOVA, con fonte e link.
- **Calcolatore della porzione** nella scheda: tutti i valori ricalcolati per i grammi scelti (es. 150 g invece di 100 g).
- **Alternative migliori**: nella scheda, gli alimenti della stessa categoria con punteggio più alto.
- **Componi un pasto**: somma più alimenti con le loro porzioni e mostra totali e profilo di rischio del pasto.
- **Diario alimentare** per ogni utente registrato: pasti del giorno, totali di Kcal, Kcal nette e TEF, profilo di rischio della giornata e riepilogo degli ultimi 7 giorni.

## 📂 Struttura del progetto

```
Food-stoplight/
├── app.py              # Applicazione Flask principale (route, CRUD, import/export, backup, login, comandi utenti)
├── analisi.py          # Livelli di rischio, punteggio, medaglie e dati per i grafici
├── importazione.py     # Lettura di CSV/Excel, riconoscimento colonne, piano dell'import (anteprima)
├── esportazione.py     # Export CSV, Excel e PDF (tabella e scheda alimento)
├── backup.py           # Backup, verifica e ripristino del database alimenti
├── nutrienti.py        # Campi nutrizionali, carico glicemico, porzioni, profilo dei pasti, alternative
├── usda.py             # Macro e micronutrienti da USDA FoodData Central
├── config.py           # Configurazione da variabili d'ambiente / .env (sviluppo e produzione)
├── .env.example        # Modello del file .env
├── update.py           # CLI per aggiornamento massivo del DB da CSV ed export dei dati mancanti
├── autogen.py          # Generatore del dataset: dati reali USDA FoodData Central + alimenti integrativi
├── alimenti.db         # Database SQLite precaricato (~1000 alimenti)
├── utenti.db           # Utenti e password (creato al primo avvio, escluso da git)
├── diario.db           # Diario alimentare degli utenti (creato al primo avvio, escluso da git)
├── instance/           # Backup del database e file in attesa di import (creata all'uso, esclusa da git)
├── templates/          # Template Jinja2
│   ├── base.html       # Layout comune (navbar, tema chiaro/scuro, flash message)
│   ├── index.html      # Riepilogo grafico e tabella alimenti con filtri e ordinamento
│   ├── scheda.html     # Scheda del singolo alimento: porzione, nutrienti, radar, alternative
│   ├── pasto.html      # Composizione di un pasto
│   ├── diario.html     # Diario alimentare giornaliero
│   ├── _radar.html, _riepilogo_pasto.html, _elenco_alimenti.html  # Parti in comune
│   ├── form.html       # Form nuovo/modifica alimento
│   ├── import.html     # Caricamento del file da importare (CSV o Excel)
│   ├── import_anteprima.html  # Anteprima dell'import e scelta della modalità
│   ├── backup.html     # Backup e ripristino del database
│   └── login.html      # Pagina di accesso
├── static/
│   ├── css/app.css     # Stili dell'app, colori dei livelli, modalità scura
│   ├── js/app.js       # Pulsante del tema e tooltip dei grafici
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
| `DATABASE_PATH` / `UTENTI_DB_PATH` / `DIARIO_DB_PATH` | `alimenti.db` / `utenti.db` / `diario.db` | Percorsi dei database (relativi alla cartella del progetto) |
| `USDA_API_KEY` | `DEMO_KEY` | Chiave USDA FoodData Central per `flask --app app usda-nutrienti` |
| `BACKUP_DIR` | `instance/backup` | Cartella dei backup del database alimenti (si conservano gli ultimi 20) |
| `MAX_UPLOAD_MB` | `10` | Dimensione massima dei file importati e dei backup da ripristinare |

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
flask --app app elimina-utente lucia                   # elimina anche il suo diario
```

## 📥 Import, export e backup

- **Modificare i dati in Excel**: esporta la tabella in Excel o CSV, modifica il file e reimportalo con la modalità *Aggiorna o aggiungi*. Le righe si abbinano per **ID** (colonna presente nei file esportati), altrimenti per **nome e categoria**; se il file non ha la colonna Categoria, per nome soltanto quando non è ambiguo. Vengono scritti solo i valori non vuoti del file e le righe identiche al database restano invariate.
- **Campi calcolati**: il rapporto fruttosio/fibre viene sempre ricalcolato; TEF (Kcal) e TEF (%) si completano a vicenda e le Kcal nette si ricalcolano quando cambiano Kcal o TEF. Le colonne Punteggio e Aggiornato il dei file esportati vengono ignorate.
- **Livelli di rischio** accettati: Trascurabile, Basso, Medio, Alto, anche preceduti da emoji («🔴 Alto»); i valori non riconosciuti vengono segnalati nell'anteprima e non importati.
- **Backup**: prima di ogni import e di ogni ripristino viene salvata una copia del database in `BACKUP_DIR`. Il ripristino accetta solo database SQLite integri con la tabella `alimenti` (senza trigger né viste) e aggiunge le colonne mancanti a quelli delle versioni precedenti. `utenti.db` non fa mai parte dei backup.
- **PDF**: usano i font standard del formato, quindi le emoji e i caratteri fuori dall'alfabeto latino occidentale non compaiono.

## 🍽️ Pasti e diario

- **Pasto**: dalla scheda di un alimento («Aggiungi al pasto», con la porzione scelta) o dalla pagina *Pasto* con la ricerca. Il pasto resta nella sessione del browser (fino a 30 alimenti) ed è disponibile anche senza login.
- **Diario**: per gli utenti registrati, sia amministratori sia visitatori; ognuno vede solo il proprio. Si aggiungono alimenti a colazione, pranzo, cena o spuntino, oppure si salva un pasto intero. Ogni voce conserva i valori dell'alimento al momento dell'inserimento, quindi il diario non cambia se l'alimento viene poi modificato o eliminato.
- Il diario sta in `diario.db`, separato dagli altri database ed escluso da git e dai backup.

## 🥦 Dati nutrizionali da USDA

```bash
flask --app app usda-nutrienti --prova      # mostra cosa cambierebbe
flask --app app usda-nutrienti              # compila i campi vuoti (backup automatico prima)
flask --app app usda-nutrienti --pagine 2 --sovrascrivi
```

Il comando scarica l'elenco USDA usato da `autogen.py` (dataset Foundation e SR Legacy) e abbina gli alimenti per nome esatto, salvando fonte, link alla scheda USDA e FDC ID. Senza `USDA_API_KEY` usa la chiave pubblica `DEMO_KEY`, limitata a poche richieste l'ora; la chiave personale è gratuita: <https://fdc.nal.usda.gov/api-key-signup>.

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
- **Rapporto Fruttosio/Fibre** = fruttosio ÷ fibre (0 se le fibre sono 0): indicatore utile per la valutazione del malassorbimento del fruttosio; più è basso, meglio è, perché le fibre ne favoriscono la tolleranza.
- **Indicatori di rischio**: assegnati tramite punteggi basati su soglie di zuccheri, grassi saturi, colesterolo, fibre e fruttosio, con riferimento alle indicazioni OMS/WCRF per il rischio tumorale. Valori accettati: Trascurabile, Basso, Medio, Alto (sono riconosciuti anche Protettivo e Neutro come Trascurabile, Elevato e Aumentato come Alto).
- **Punteggio complessivo** = 100 × (1 − media dei punti ÷ 3), con Trascurabile = 0, Basso = 1, Medio = 2, Alto = 3 punti, calcolato sui rischi disponibili. Il colore del punteggio corrisponde al livello medio: oltre 83 Trascurabile, 51–83 Basso, 17–50 Medio, fino a 16 Alto.
- **Medaglie**: primi 10 dell'intero database per punteggio (a parità, più fibre), per rapporto fruttosio/fibre (solo alimenti con almeno 1 g di fruttosio) e per Kcal (esclusi i valori a 0, che indicano dati mancanti).
- **Origine dei dati**: dei 1004 alimenti, 199 vengono da USDA FoodData Central con macro e micronutrienti reali; gli altri 805 sono stati generati da `autogen.py` con valori casuali verosimili per categoria (per questo ci sono omonimi, es. «Trota», con valori diversi) e non hanno macro né micronutrienti. Indice glicemico, FODMAP e NOVA non hanno una fonte aperta e vanno inseriti dal form o con l'import.
- **Dati nutrizionali**: valori per 100 g; un campo vuoto significa «non disponibile», 0 è un valore misurato.
- **Carico glicemico** = indice glicemico × carboidrati disponibili (carboidrati − fibre) della porzione ÷ 100. Soglie: indice basso fino a 55, medio 56–69, alto da 70; carico per porzione basso fino a 10, medio 11–19, alto da 20.
- **FODMAP**: livello Basso / Medio / Alto per fruttani, GOS, lattosio, fruttosio in eccesso e polioli, come il semaforo delle tabelle Monash; il complessivo è il più alto dei cinque.
- **NOVA**: 1 non trasformati o minimamente trasformati, 2 ingredienti culinari trasformati, 3 alimenti trasformati, 4 ultra-trasformati.
- **Profilo di rischio di pasti e giornate**: per ogni rischio, media dei punti dei livelli (0–3) pesata sulle Kcal che ogni alimento apporta (su grammi se nessun alimento ha Kcal); il punteggio segue la stessa formula di quello degli alimenti.
- **Alternative**: stessa categoria, punteggio più alto; a parità, Kcal più vicine; un solo alimento per nome.

> ⚠️ **Disclaimer**: i dati e le classificazioni hanno finalità informative e di studio. Non sostituiscono il parere di un medico o di un nutrizionista.

## 🧰 Tecnologie

| Componente | Tecnologia |
|---|---|
| Backend | Python 3, Flask 3 |
| Sicurezza | Flask-Login (sessioni e ruoli), Flask-WTF (CSRF), python-dotenv |
| Database | SQLite 3 |
| Frontend | Jinja2, Bootstrap Italia 2.18.3 |
| Import / Export | openpyxl (Excel), fpdf2 (PDF) |
| Dati | USDA FoodData Central API (requests) |

## 👨‍💻 Sviluppatore

**Paolo Pierno**

## 📄 Licenza

Questo progetto include [Bootstrap Italia](https://italia.github.io/bootstrap-italia/), distribuito con la propria licenza (vedi `static/bootstrap-italia/LICENSE`).
