# 🥗 Food-stoplight

**Food-stoplight** è una web app per consultare e gestire un database nutrizionale di 900 alimenti italiani (Tabelle di composizione del CREA), con un sistema "a semaforo" a quattro livelli (🟢 Trascurabile / 🟡 Basso / 🟠 Medio / 🔴 Alto) che classifica ogni alimento in base a cinque profili di rischio per la salute.

Sviluppata in **Python + Flask** con database **SQLite** e interfaccia basata su **Bootstrap Italia**.

## ✨ Funzionalità

- **Tabella interattiva** di tutti gli alimenti con ordinamento su ogni colonna e filtri combinabili per categoria e livelli di rischio.
- **Dati reali e tracciabili**: i 900 alimenti delle Tabelle di composizione degli alimenti del CREA (2019), con i valori che il CREA non pubblica (soprattutto fruttosio e glucosio) presi dall'alimento corrispondente di USDA FoodData Central; ogni scheda dice da dove viene ogni dato.
- **Compila da una fonte**: nel form un alimento si riempie da un codice CREA, da un codice a barre (Open Food Facts) o da un FDC ID USDA.
- **Sincronizzazione periodica con USDA**: l'app aggiorna da sola i valori presi da USDA (con una chiave personale), con backup prima e storico nella pagina Importa.
- **Sistema a semaforo** per cinque indicatori di rischio, **calcolati dai valori nutrizionali** con regole documentate e riferimenti bibliografici (Reg. CE 1924/2006, semaforo FSA, OMS, EFSA, LARN, IARC, WCRF, tabelle internazionali dell'indice glicemico, soglie FODMAP):
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
- **Riepilogo grafico** in home page, aggiornato in base ai filtri: alimenti per categoria, distribuzione dei livelli per ciascun rischio e classifiche "top alimenti". Ogni grafico ha la sua vista tabellare.
- **Punteggio complessivo 0–100** per alimento, ordinabile in tabella: 100 = tutti i rischi trascurabili, 0 = tutti alti.
- **Medaglie** 🛡️ più protettivi · 🍃 miglior rapporto fruttosio/fibre · 🪶 meno calorici, assegnate ai primi 10 di ciascuna classifica.
- **Scheda alimento** con punteggio, valori nutrizionali e grafico radar del profilo di rischio.
- **Modalità scura**: segue il sistema operativo oppure si attiva con il pulsante 🌙 nella barra in alto.
- **Dati nutrizionali completi** nella scheda, nel form e in import/export: macronutrienti (proteine, carboidrati, zuccheri, grassi, saturi, colesterolo), 12 tra vitamine e sali minerali, indice e carico glicemico, FODMAP per categoria e grado di processazione NOVA, con fonte e link.
- **Calcolatore della porzione** nella scheda: tutti i valori ricalcolati per i grammi scelti (es. 150 g invece di 100 g).
- **Alternative migliori**: nella scheda, gli alimenti della stessa categoria con punteggio più alto.
- **Componi un pasto**: somma più alimenti con le loro porzioni e mostra totali e profilo di rischio del pasto.
- **Diario alimentare** per ogni utente registrato: pasti del giorno, totali di Kcal, Kcal nette e TEF, profilo di rischio della giornata e riepilogo degli ultimi 7 giorni.
- **Italiano e inglese**: la lingua segue il browser e si cambia dal menu (🌐). Export, API e riga di comando restano in italiano.
- **App installabile** su telefono e computer: senza connessione restano consultabili la tabella, la guida e le schede già aperte.
- **Guida ai dati** (livelli di rischio, soglie, punteggio, TEF, indice glicemico, FODMAP, NOVA, fonti) e legenda compatta sopra la tabella.
- **Tabella su ogni schermo**: su telefono ogni alimento è una scheda compatta, con un menu per l'ordinamento; da tablet in su si vedono le colonne principali e «Mostra tutte le colonne» aggiunge TEF, fruttosio, fibre e rapporto F/F.
- **Notifiche e conferme**: i messaggi compaiono come notifiche in un angolo (gli errori restano finché non si chiudono); eliminazioni, ripristini e svuotamento del pasto chiedono conferma in una finestra.

## 📂 Struttura del progetto

```
Food-stoplight/
├── app.py              # Applicazione Flask: pagine web, login e ruoli, comandi da riga di comando
├── api.py              # API REST in sola lettura (/api/alimenti, /api/categorie)
├── archivio.py         # Query sugli alimenti (filtri, ordinamento), condivise da pagine e API
├── database.py         # Connessioni ai tre database e migrazioni versionate dello schema
├── calcoli.py          # Calcoli condivisi: numeri, Kcal e TEF dai macronutrienti, Kcal nette, rapporto F/F
├── analisi.py          # Livelli di rischio, punteggio, medaglie e dati per i grafici
├── importazione.py     # Lettura di CSV/Excel, riconoscimento colonne, piano dell'import (anteprima)
├── esportazione.py     # Export CSV, Excel e PDF (tabella e scheda alimento)
├── backup.py           # Backup, verifica e ripristino del database alimenti
├── nutrienti.py        # Campi nutrizionali, carico glicemico, porzioni, profilo dei pasti, alternative
├── crea.py             # Lettura delle schede delle Tabelle di composizione del CREA
├── usda.py             # Valori da USDA FoodData Central per FDC ID
├── openfoodfacts.py    # Prodotti confezionati per codice a barre (Open Food Facts)
├── fonti.py            # Alimenti dalle fonti: CREA + USDA, Open Food Facts, USDA; import e sincronizzazione
├── classificazioni.py  # Bevande, carni rosse e lavorate, zuccheri liberi, NOVA, FODMAP, indice glicemico
├── rischi.py           # Regole dei cinque rischi, con motivi e riferimenti bibliografici
├── sincronizzazione.py # Sincronizzazione periodica con USDA (automatica nell'app, storico, blocco)
├── dati/               # Abbinamenti CREA -> USDA e indice glicemico (Atkinson 2008) per codice CREA
├── lingue.py           # Scelta della lingua (italiano, inglese) e traduzione dei valori mostrati
├── pwa.py              # App installabile: manifest, service worker, pagina offline
├── babel.cfg, translations/   # Estrazione dei testi e traduzione inglese (messages.po / .mo)
├── config.py           # Configurazione da variabili d'ambiente / .env (sviluppo e produzione)
├── .env.example        # Modello del file .env
├── update.py           # Aggiornamento del database da CSV/Excel da riga di comando (stesse regole dell'import web)
├── alimenti.db         # Database SQLite precaricato (900 alimenti CREA)
├── utenti.db           # Utenti e password (creato al primo avvio, escluso da git)
├── diario.db           # Diario alimentare degli utenti (creato al primo avvio, escluso da git)
├── instance/           # Backup del database e file in attesa di import (creata all'uso, esclusa da git)
├── templates/          # Template Jinja2
│   ├── base.html       # Layout comune (navbar, lingua, tema chiaro/scuro, notifiche, finestra di conferma)
│   ├── index.html      # Riepilogo grafico e tabella alimenti con filtri e ordinamento
│   ├── scheda.html     # Scheda del singolo alimento: porzione, nutrienti, radar, alternative
│   ├── pasto.html      # Composizione di un pasto
│   ├── diario.html     # Diario alimentare giornaliero
│   ├── _radar.html, _riepilogo_pasto.html, _elenco_alimenti.html  # Parti in comune
│   ├── form.html       # Form nuovo/modifica alimento
│   ├── import.html     # Caricamento del file da importare (CSV o Excel)
│   ├── import_anteprima.html  # Anteprima dell'import e scelta della modalità
│   ├── backup.html     # Backup e ripristino del database
│   ├── guida.html      # Guida ai dati: livelli, soglie, punteggio, TEF, indicatori, fonti
│   ├── offline.html, errore.html  # Pagina senza connessione e pagine di errore (403, 404)
│   ├── sw.js           # Service worker (generato con la versione dei file statici)
│   └── login.html      # Pagina di accesso
├── static/
│   ├── css/app.css     # Stili dell'app, colori dei livelli, modalità scura
│   ├── js/app.js       # Tema, tooltip, notifiche, conferme, porzione, colonne, service worker
│   ├── icone/          # Icone dell'app (SVG e PNG)
│   └── bootstrap-italia/   # Bootstrap Italia 2.18.3 (CSS, JS, font, icone)
├── tests/              # Test automatici (pytest)
├── docker/avvio.sh     # Avvio del container: prepara /data e l'amministratore iniziale
├── Dockerfile, docker-compose.yml, .dockerignore   # Immagine di produzione (gunicorn)
├── render.yaml         # Blueprint per il deploy su Render
├── .github/workflows/ci.yml   # GitHub Actions: lint, tipi, test e immagine Docker a ogni push
├── pyproject.toml      # Configurazione di ruff, mypy e pytest
├── requirements.txt, requirements-dev.txt   # Dipendenze dell'app e strumenti di sviluppo
└── docs/               # Fogli di esempio (XLSX) e prototipi HTML
```

## 🚀 Installazione e avvio

Requisiti: **Python 3.11+**

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

Al primo avvio i database mancanti vengono creati e quelli esistenti portati allo schema attuale (vedi *Migrazioni*). Il repository include `alimenti.db` già popolato con i 900 alimenti del CREA.

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
| `USDA_API_KEY` | (vuota) | Chiave personale USDA FoodData Central: serve per la sincronizzazione; senza, le ricerche dal form usano `DEMO_KEY` |
| `USDA_SINCRONIZZA_GIORNI` | `30` | Ogni quanti giorni l'app sincronizza da sola i valori USDA (`0` = mai; solo con `USDA_API_KEY`) |
| `BACKUP_DIR` | `instance/backup` | Cartella dei backup del database alimenti (si conservano gli ultimi 20) |
| `MAX_UPLOAD_MB` | `10` | Dimensione massima dei file importati e dei backup da ripristinare |
| `IMPORT_DIR` | `instance/import` | File caricati in attesa di conferma dell'import (eliminati dopo un'ora) |
| `PROXY_ATTENDIBILI` | `0` | Numero di proxy davanti all'app (Render, nginx): con `1` schema e host si leggono da `X-Forwarded-*` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | — | Solo nel container: amministratore creato al primo avvio se non ce n'è nessuno |
| `PORT` / `GUNICORN_WORKERS` | `8000` / `2` | Solo nel container: porta e numero di processi di gunicorn |

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

## 🌐 Lingue

L'interfaccia è in italiano e in inglese. Al primo accesso la lingua segue le preferenze del browser; il link 🌐 nel menu la cambia e la scelta resta in un cookie per un anno. Si traducono pagine, messaggi, errori dei form, livelli, categorie e guida; i nomi degli alimenti restano quelli del database. Export (CSV, Excel, PDF), API e comandi da riga di comando restano in italiano, così i file esportati si reimportano senza cambiare intestazioni.

I testi sono scritti in italiano nel codice e nei template (con `_()` e `{% trans %}`); la traduzione è in `translations/en/LC_MESSAGES/messages.po`. Dopo aver aggiunto o cambiato dei testi:

```bash
pybabel extract -F babel.cfg -o messages.pot --no-location --sort-output .
pybabel update -i messages.pot -d translations --no-fuzzy-matching --ignore-obsolete
# tradurre le voci nuove in messages.po, poi:
pybabel compile -d translations
```

`pytest` segnala i testi senza traduzione, le voci non più usate e un `messages.mo` non ricompilato.

## 📱 App installabile e offline

Il sito si installa come app (Chrome, Edge, Safari su iPhone con «Aggiungi alla schermata Home»). Il service worker conserva sul dispositivo i file statici, la tabella completa e la guida; le schede degli alimenti restano disponibili dopo averle aperte una volta. Senza connessione la tabella mostra l'ultima copia salvata (senza filtri), e le pagine che richiedono la rete (pasto, diario, amministrazione) lasciano il posto a una pagina offline con l'elenco delle schede salvate.

All'uscita dall'account le pagine salvate vengono cancellate, perché possono contenere il nome dell'utente e i pulsanti di amministrazione. A ogni deploy che cambia CSS, JavaScript, icone o traduzioni il service worker si aggiorna da solo. L'app installabile richiede HTTPS (in locale va bene `http://localhost`).

## 🥦 Fonti dei dati

- **CREA** – [Tabelle di composizione degli alimenti](https://www.alimentinutrizione.it/tabelle-nutrizionali), aggiornamento 2019: nomi, categorie, porzione tipica e valori nutrizionali dei 900 alimenti. Il sito non ha API né file da scaricare: si leggono le schede, una al secondo. I dati si riproducono citando la fonte, come chiede il CREA (ogni alimento ha fonte, codice e link alla scheda).
- **USDA FoodData Central** (dominio pubblico) – i valori che il CREA non pubblica, soprattutto fruttosio e glucosio, dall'alimento corrispondente: gli abbinamenti, scelti alimento per alimento, sono in `dati/crea_usda.csv` (441 alimenti). Fruttosio, glucosio e lattosio mantengono la proporzione sugli zuccheri dell'alimento USDA, applicata agli zuccheri del CREA. Negli alimenti di origine animale il fruttosio è 0; nel latte e nei latticini non zuccherati gli zuccheri sono lattosio.
- **Open Food Facts** (licenza ODbL) – prodotti confezionati per codice a barre, dal form.
- **Indice glicemico** – tabella 1 di Atkinson et al., *Diabetes Care* 2008, assegnata agli alimenti CREA corrispondenti (`dati/indice_glicemico.csv`, con la voce della tabella usata).
- **NOVA, FODMAP, rischi** – regole documentate in `classificazioni.py` e `rischi.py`, spiegate nella pagina Guida con i riferimenti.

```bash
flask --app app crea-importa 007000 007120          # importa o aggiorna alcuni alimenti CREA
flask --app app crea-importa --tutti --cache instance/crea   # tutto l'indice (circa 15 minuti)
flask --app app crea-importa --tutti --sostituisci   # elimina prima gli alimenti senza codice CREA
flask --app app usda-sincronizza                    # aggiorna subito i valori USDA (serve USDA_API_KEY)
flask --app app ricalcola-rischi                    # ricalcola i livelli dopo aver cambiato le regole
```

Ogni comando fa un backup del database prima di scrivere. La sincronizzazione automatica parte nell'app stessa ogni `USDA_SINCRONIZZA_GIORNI` giorni (su Render un cron job separato non vedrebbe il disco dei dati); un file di blocco accanto al database evita che due processi la eseguano insieme. Lo stato e il pulsante «Sincronizza ora» sono nella pagina Importa. La chiave personale è gratuita: <https://fdc.nal.usda.gov/api-key-signup>.

## 🔌 API REST

API JSON in sola lettura, con gli stessi permessi della consultazione web (con `ACCESSO_PUBBLICO=false` senza login si riceve `401`).

| Richiesta | Risposta |
|---|---|
| `GET /api` | Indice delle risorse e dei parametri |
| `GET /api/alimenti` | `{totale, limit, offset, successiva, precedente, risultati}` |
| `GET /api/alimenti/<id>` | Un alimento: tutti i campi più punteggio, livello medio, carico glicemico, FODMAP complessivo, link alla scheda |
| `GET /api/categorie` | Categorie con il numero di alimenti |

Parametri di `/api/alimenti`: `q` (testo nel nome), `categoria`, `rischio_diabete` … `rischio_tumorale` (livello), `sort` e `dir` (come la tabella), `limit` (1–500, default 100), `offset`.

```bash
curl "http://127.0.0.1:5000/api/alimenti?q=apple&rischio_diabete=Basso&sort=kcal&dir=desc&limit=5"
```

Gli errori sono JSON: `{"errore": "...", "stato": 404}`. `GET /salute` risponde `200` se il database è leggibile (controllo per Docker e Render).

## 🚢 Produzione

- Imposta `APP_ENV=produzione` e una `FLASK_SECRET_KEY` robusta: senza, l'app non parte.
- Servi l'app in **HTTPS**: in produzione i cookie di sessione sono `Secure` e su HTTP semplice il login non funziona (si può disattivare con `SESSION_COOKIE_SECURE=false`, sconsigliato). Dietro un proxy imposta `PROXY_ATTENDIBILI=1`.
- `python app.py` usa il server di sviluppo di Flask: per un deploy reale usa gunicorn (compreso nei requisiti) o il container Docker.

### Docker

```bash
cp .env.example .env                      # imposta FLASK_SECRET_KEY
docker compose up -d --build              # http://localhost:8000
docker compose exec -u app web flask --app app crea-utente admin
```

L'immagine esegue gunicorn come utente senza privilegi. Database, utenti, diario e backup stanno nel volume `/data`: al primo avvio vi viene copiato l'`alimenti.db` incluso nell'immagine, poi i dati restano tra un aggiornamento e l'altro.

### Render

1. Dashboard di Render → **New → Blueprint** → questo repository: `render.yaml` crea il servizio Docker con un disco persistente su `/data` e una `FLASK_SECRET_KEY` generata.
2. Al primo avvio Render chiede `ADMIN_USERNAME` e `ADMIN_PASSWORD` (amministratore iniziale, creato solo se non ne esiste già uno; dopo il primo deploy la password si può togliere) ed eventualmente `USDA_API_KEY`.
3. I deploy partono a ogni push su GitHub **solo se la CI è passata** (`autoDeployTrigger: checksPass`).

Il disco persistente richiede un piano a pagamento (`plan: 0.5c-512mb`, il più piccolo) e una sola istanza; ogni deploy ha una breve interruzione. Sul piano gratuito i dati andrebbero persi a ogni riavvio.

## 🗄️ Migrazioni del database

Ogni database tiene la versione dello schema in `PRAGMA user_version`; all'avvio dell'app (o di `update.py`) si applicano in ordine le migrazioni mancanti di `database.py`, in un'unica transazione, dopo un backup automatico di `alimenti.db`. Un nuovo cambio di schema è sempre una migrazione nuova in coda alla lista, mai la modifica di una esistente.

```bash
flask --app app db-stato      # versione attuale di alimenti.db, utenti.db, diario.db
```

## 🧪 Sviluppo

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                # test automatici (su copie temporanee dei database)
ruff check .          # lint
mypy                  # controllo dei tipi
```

I test controllano anche che ogni testo dell'interfaccia abbia la traduzione inglese (vedi *Lingue*).

GitHub Actions (`.github/workflows/ci.yml`) esegue lint, tipi e test con Python 3.11, 3.12 e 3.13 a ogni push, poi costruisce l'immagine Docker e ne verifica l'avvio.

## 🛠️ Strumenti a riga di comando

### `update.py` — aggiornamento massivo del database

Le stesse regole dell'import web (file CSV o Excel, abbinamento per ID oppure per nome e categoria, campi derivati ricalcolati, backup automatico prima di scrivere), da riga di comando:

```bash
python update.py --csv dati.csv                     # aggiorna o aggiunge
python update.py --csv dati.xlsx --dry-run          # mostra cosa cambierebbe
python update.py --csv dati.csv --modalita aggiungi # oppure sostituisci
python update.py --esporta-mancanti da_completare.csv   # CSV reimportabile con i dati da completare
python update.py --db altro.db --csv dati.csv
```

## 🧮 Note metodologiche

- **TEF (Thermic Effect of Food)**: quando manca, si stima dai macronutrienti come media dei coefficienti pesata sull'energia di ciascuno — proteine 25%, carboidrati 10%, grassi 5% (gli stessi in web app, import e `update.py`). Se mancano le Kcal si stimano dai macronutrienti (4 / 4 / 9 Kcal per grammo).
- **Kcal Nette** = Kcal totali − TEF (Kcal).
- **Rapporto Fruttosio/Fibre** = fruttosio ÷ fibre (0 se le fibre sono 0): indicatore utile per la valutazione del malassorbimento del fruttosio; più è basso, meglio è, perché le fibre ne favoriscono la tolleranza.
- **Indicatori di rischio**: calcolati dai valori nutrizionali a ogni salvataggio, import e sincronizzazione (`rischi.py`), mai scritti a mano. Per i nutrienti da limitare la scala è comune, per 100 g (bevande per 100 ml): Trascurabile fino alla soglia «senza» del Reg. CE 1924/2006, Basso fino a «a basso contenuto» (verde FSA), Medio nell'ambra e Alto nel rosso del semaforo FSA. Diabete: carico glicemico della porzione e zuccheri liberi, un livello in meno con molte fibre. Colesterolo: grassi saturi, e colesterolo della porzione oltre il limite giornaliero dei LARN. Malassorbimento: fruttosio in eccesso sul glucosio nella porzione rispetto alla soglia FODMAP (Varney 2017). Metabolico: densità energetica (WCRF) e zuccheri liberi. Tumorale: alcol e carni lavorate (IARC gruppo 1), carne rossa, sale, ultra-trasformati, bevande zuccherate; fibre protettive. Regole e riferimenti completi nella Guida.
- **Punteggio complessivo** = 100 × (1 − media dei punti ÷ 3), con Trascurabile = 0, Basso = 1, Medio = 2, Alto = 3 punti, calcolato sui rischi disponibili. Il colore del punteggio corrisponde al livello medio: oltre 83 Trascurabile, 51–83 Basso, 17–50 Medio, fino a 16 Alto.
- **Medaglie**: primi 10 dell'intero database per punteggio (a parità, più fibre), per rapporto fruttosio/fibre (solo alimenti con almeno 1 g di fruttosio) e per Kcal (esclusi i valori a 0, che indicano dati mancanti).
- **Origine dei dati**: vedi *Fonti dei dati*. Dove una fonte non dà un valore il campo resta vuoto e il rischio che ne dipende «Non classificato»: oggi soprattutto grassi saturi di alcune carni e pesci, fruttosio di ricette, biscotti e prodotti da forno.
- **Dati nutrizionali**: valori per 100 g; un campo vuoto significa «non disponibile», 0 è un valore misurato.
- **Carico glicemico** = indice glicemico × carboidrati disponibili della porzione ÷ 100. I carboidrati sono quelli disponibili (senza fibre), come nelle etichette europee e nel CREA; da USDA si sottraggono le fibre. Soglie: indice basso fino a 55, medio 56–69, alto da 70; carico per porzione basso fino a 10, medio 11–19, alto da 20.
- **FODMAP**: livello Basso / Medio / Alto per fruttani, GOS, lattosio, fruttosio in eccesso e polioli, come il semaforo delle tabelle Monash; il complessivo è il più alto dei cinque.
- **NOVA**: 1 non trasformati o minimamente trasformati, 2 ingredienti culinari trasformati, 3 alimenti trasformati, 4 ultra-trasformati.
- **Profilo di rischio di pasti e giornate**: per ogni rischio, media dei punti dei livelli (0–3) pesata sulle Kcal che ogni alimento apporta (su grammi se nessun alimento ha Kcal); il punteggio segue la stessa formula di quello degli alimenti.
- **Alternative**: stessa categoria, punteggio più alto; a parità, Kcal più vicine; un solo alimento per nome.

> ⚠️ **Disclaimer**: i dati e le classificazioni hanno finalità informative e di studio. Non sostituiscono il parere di un medico o di un nutrizionista.

## 🧰 Tecnologie

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.11+, Flask 3, gunicorn |
| Sicurezza | Flask-Login (sessioni e ruoli), Flask-WTF (CSRF), python-dotenv |
| Database | SQLite 3 |
| Frontend | Jinja2, Bootstrap Italia 2.18.3, service worker (app installabile) |
| Lingue | Flask-Babel (italiano, inglese) |
| Import / Export | openpyxl (Excel), fpdf2 (PDF) |
| Dati | CREA (Tabelle di composizione degli alimenti), USDA FoodData Central, Open Food Facts (requests) |
| Qualità | pytest, ruff, mypy, GitHub Actions |
| Deploy | Docker, Render |

## 👨‍💻 Sviluppatore

**Paolo Pierno**

## 📄 Licenza

Questo progetto include [Bootstrap Italia](https://italia.github.io/bootstrap-italia/), distribuito con la propria licenza (vedi `static/bootstrap-italia/LICENSE`).
