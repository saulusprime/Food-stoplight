# 🥗 Food-stoplight

**Food-stoplight** è una web app per consultare e gestire un database nutrizionale di 900 alimenti italiani (Tabelle di composizione del CREA), con un sistema "a semaforo" a quattro livelli (🟢 Trascurabile / 🟡 Basso / 🟠 Medio / 🔴 Alto) che classifica ogni alimento in base a cinque profili di rischio per la salute.

Sviluppata in **Python + Flask** con database **SQLite** e interfaccia basata su **Bootstrap Italia**.

## ✨ Funzionalità

- **Tabella interattiva** di tutti gli alimenti, divisa in pagine (25, 50, 100 righe o tutte), con filtri combinabili per categoria e livelli di rischio.
- **Ricerca per nome** tollerante: trova nomi parziali, senza accenti, al singolare o al plurale (mela → Mele) e con errori di battitura (mozarella → Mozzarella); senza un ordinamento scelto i risultati sono per pertinenza.
- **Filtri per valori** da / fino a, per 100 g: Kcal, zuccheri, fruttosio, fibre, grassi saturi, sodio, rapporto F/F, punteggio; e il filtro rapido **«Solo alimenti sicuri»** (tutti e cinque i rischi classificati e al massimo Bassi).
- **Ordinamento multiplo** fino a tre criteri (es. categoria, poi Kcal decrescenti): dai menu «Ordina per / poi per» o con Maiusc+clic sulle intestazioni. I livelli di rischio si ordinano per gravità, i dati mancanti vanno in fondo.
- **Confronto affiancato** di 2–4 alimenti (`/confronta`): rischi, energia, macro e micronutrienti con barre proporzionali, indice e carico glicemico, NOVA, FODMAP e fonte. Si scelgono con le caselle della tabella (la selezione resta cambiando pagina o ricerca), dalla scheda o dal campo di ricerca della pagina.
- **Dati reali e tracciabili**: i 900 alimenti delle Tabelle di composizione degli alimenti del CREA (2019), con i valori che il CREA non pubblica (fruttosio, glucosio, grassi saturi) presi da un alimento simile della tabella britannica CoFID 2021, della tabella francese Ciqual 2025 o di USDA FoodData Central, oppure calcolati dagli ingredienti delle ricette CREA; ogni scheda dice da dove viene ogni dato.
- **Pasti pronti** (`/pasti-pronti`): 200 ricette della cucina italiana (40 antipasti, 60 primi, 60 secondi, 40 contorni, da Wikibooks e Buttalapasta) già convertite negli alimenti della tabella. Un clic aggiunge al pasto gli ingredienti per le porzioni scelte; ogni ricetta è anche un piatto della tabella, con valori per 100 g, porzione e semaforo calcolati dagli ingredienti.
- **Compila da una fonte**: nel form un alimento si riempie da un codice CREA, da un codice a barre (Open Food Facts) o da un FDC ID USDA.
- **Sincronizzazione periodica con USDA**: l'app aggiorna da sola i valori presi da USDA (con una chiave personale), con backup prima e storico nella pagina Importa.
- **Profilo personale e semaforo «Per te»** (`/profilo`): chi ha diabete, ipercolesterolemia o malassorbimento del fruttosio sceglie le sue condizioni e tabella, schede, confronto, pasti pronti, pasto e diario mostrano il livello più alto tra i rischi che lo riguardano, con il filtro «Solo sicuri per il mio profilo», l'ordinamento «Per te» e le alternative migliori per il profilo. Con l'accesso il profilo sta nell'account, senza nella sessione del browser.
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
- **Piano settimanale bilanciato** (`/piano`): pranzi e cene da 1 a 7 giorni con i pasti pronti, scelti in modo che nessun rischio si accumuli nella settimana e lo stesso rischio alto non capiti due volte nello stesso giorno; con un profilo si evitano prima i piatti alti per te. Ogni piatto si cambia o si sceglie a mano e gli altri si ribilanciano; rischi giorno per giorno, profilo della settimana, ingredienti per il numero di persone, stampa, download come testo e consultazione offline.
- **Lista della spesa a semaforo verde** (`/spesa`): per i reparti scelti propone alimenti con punteggio verde e nessun rischio oltre Basso (dove non ce ne sono, come per cereali e oli, le scelte migliori senza rischi alti, segnate), ogni volta una scelta diversa; voci da cambiare, togliere o aggiungere, con l'alternativa verde per quelle non verdi; spunte salvate sul dispositivo, stampa, download come testo e consultazione offline.
- **Diario alimentare** per ogni utente registrato: pasti del giorno, totali di Kcal, Kcal nette e TEF, profilo di rischio della giornata e riepilogo degli ultimi 7 giorni.
- **Italiano e inglese**: la lingua segue il browser e si cambia dal menu (🌐). Anche export (CSV, Excel, PDF) e messaggi dell'API seguono la lingua; la riga di comando resta in italiano.
- **App installabile** su telefono e computer: senza connessione restano consultabili la tabella, la guida e le schede già aperte.
- **Guida ai dati** (livelli di rischio, soglie, punteggio, TEF, indice glicemico, FODMAP, NOVA, fonti) e legenda compatta sopra la tabella.
- **Tabella su ogni schermo**: su telefono ogni alimento è una scheda compatta, ordinabile dai menu; da tablet in su si vedono le colonne principali e «Mostra tutte le colonne» aggiunge TEF, fruttosio, fibre e rapporto F/F.
- **Notifiche e conferme**: i messaggi compaiono come notifiche in un angolo (gli errori restano finché non si chiudono); eliminazioni, ripristini e svuotamento del pasto chiedono conferma in una finestra.

## 📂 Struttura del progetto

```
Food-stoplight/
├── app.py              # Applicazione Flask (app:app): configurazione, template, errori, blueprint, avvio
├── web/                # Pagine web divise in blueprint Flask
│   ├── pagine.py       # Tabella, scheda, confronto, guida
│   ├── alimenti.py     # Nuovo, modifica, elimina (amministratori)
│   ├── import_export.py  # Export CSV/Excel/PDF, import con anteprima, sincronizzazione USDA
│   ├── backup.py       # Backup e ripristino (amministratori)
│   ├── pasto_diario.py # Pasto e diario alimentare
│   ├── pasti_pronti.py # Pasti pronti: elenco per portata, ingredienti aggiunti al pasto
│   ├── piano.py        # Piano settimanale: generazione, cambi e scelte con ribilanciamento, ingredienti, testo
│   ├── spesa.py        # Lista della spesa: generazione, modifiche, testo da scaricare
│   ├── profilo.py      # Profilo personale: condizioni dell'utente (account o sessione)
│   ├── accesso.py      # Login, logout, lingua, ruoli e controllo dell'accesso
│   ├── comandi.py      # Comandi da riga di comando (flask --app app …)
│   └── comune.py       # Funzioni condivise (database, profilo corrente, file da scaricare, ricerca da un campo)
├── api.py              # API REST in sola lettura (/api/alimenti, /api/categorie)
├── archivio.py         # Query sugli alimenti (filtri, intervalli, ordinamento multiplo), condivise da pagine e API
├── ricerca.py          # Ricerca per nome tollerante (varianti, errori di battitura) e paginazione
├── database.py         # Connessioni ai tre database e migrazioni versionate dello schema
├── calcoli.py          # Calcoli condivisi: numeri, Kcal e TEF dai macronutrienti, Kcal nette, rapporto F/F
├── analisi.py          # Livelli di rischio, punteggio, medaglie e dati per i grafici
├── profilo.py          # Condizioni del profilo e semaforo per te (alimenti, pasti, funzione SQL per_te)
├── importazione.py     # Lettura di CSV/Excel, riconoscimento colonne, piano dell'import (anteprima)
├── esportazione.py     # Export CSV, Excel e PDF (tabella e scheda alimento)
├── backup.py           # Backup, verifica e ripristino del database alimenti
├── nutrienti.py        # Campi nutrizionali, carico glicemico, porzioni, profilo dei pasti, alternative
├── crea.py             # Lettura delle schede delle Tabelle di composizione del CREA
├── usda.py             # Valori da USDA FoodData Central per FDC ID
├── cofid.py            # Tabella britannica CoFID 2021: profilo degli zuccheri, zuccheri totali e grassi saturi
├── ciqual.py           # Tabella francese Ciqual 2025: gli stessi valori dove CoFID non ha un alimento comparabile
├── ricette.py          # Ricette CREA: fruttosio, glucosio, lattosio e saturi calcolati dagli ingredienti
├── pasti_pronti.py     # Pasti pronti: lettura dei file e piatto calcolato dagli ingredienti (peso cotto, alcol)
├── piano.py            # Piano settimanale: posti, costo del bilanciamento dei rischi, generazione e ribilanciamento
├── spesa.py            # Lista della spesa a semaforo verde: alimenti proponibili, scelta per reparto, sostituti
├── openfoodfacts.py    # Prodotti confezionati per codice a barre (Open Food Facts)
├── fonti.py            # Alimenti dalle fonti: CREA + CoFID + USDA + ricette, Open Food Facts, USDA; import e sincronizzazione
├── classificazioni.py  # Bevande, carni rosse e lavorate, zuccheri liberi, NOVA, FODMAP, indice glicemico
├── rischi.py           # Regole dei cinque rischi, con motivi e riferimenti bibliografici
├── sincronizzazione.py # Sincronizzazione periodica con USDA (automatica nell'app, storico, blocco)
├── dati/               # Abbinamenti CREA -> USDA, CoFID e Ciqual, alimenti CoFID e Ciqual usati, ingredienti delle ricette, indice glicemico, pasti pronti
├── lingue.py           # Scelta della lingua (italiano, inglese) e traduzione dei valori mostrati
├── pwa.py              # App installabile: manifest, service worker, pagina offline
├── babel.cfg, translations/   # Estrazione dei testi e traduzione inglese (messages.po / .mo)
├── config.py           # Configurazione da variabili d'ambiente / .env (sviluppo e produzione)
├── .env.example        # Modello del file .env
├── update.py           # Aggiornamento del database da CSV/Excel da riga di comando (stesse regole dell'import web)
├── alimenti.db         # Database SQLite precaricato (900 alimenti CREA e i 200 piatti dei pasti pronti)
├── utenti.db           # Utenti, password e profili (creato al primo avvio, escluso da git)
├── diario.db           # Diario alimentare degli utenti (creato al primo avvio, escluso da git)
├── instance/           # Backup del database e file in attesa di import (creata all'uso, esclusa da git)
├── templates/          # Template Jinja2
│   ├── base.html       # Layout comune (navbar, lingua, tema chiaro/scuro, notifiche, finestra di conferma)
│   ├── index.html      # Riepilogo grafico e tabella alimenti con filtri e ordinamento
│   ├── scheda.html     # Scheda del singolo alimento: porzione, nutrienti, radar, alternative
│   ├── confronto.html  # Confronto affiancato di 2–4 alimenti
│   ├── pasto.html      # Composizione di un pasto
│   ├── piano.html      # Piano settimanale dei pasti
│   ├── spesa.html      # Lista della spesa a semaforo verde
│   ├── diario.html     # Diario alimentare giornaliero
│   ├── profilo.html    # Profilo personale: condizioni per il semaforo per te
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
└── docs/               # Dossier per la revisione delle regole (revisione_regole.md), fogli di esempio e prototipi HTML
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

Al primo avvio i database mancanti vengono creati e quelli esistenti portati allo schema attuale (vedi *Migrazioni*). Il repository include `alimenti.db` già popolato con i 900 alimenti del CREA e i 200 pasti pronti.

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

Gli utenti si gestiscono da riga di comando; le password sono salvate come hash in `utenti.db`, separato da `alimenti.db` ed escluso da git. Nello stesso database c'è il profilo personale di ogni utente (le condizioni scelte in `/profilo`, colonna `condizioni`), che si elimina con l'utente e non entra nei backup.

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
- **Pasti pronti**: dalla pagina *Pasti pronti* o dalla scheda del piatto, «Al pasto» aggiunge gli ingredienti crudi della ricetta per 1-12 porzioni; un alimento già nel pasto somma i grammi.
- **Piano settimanale**: ogni pasto ha le sue portate (di base a pranzo primo e contorno, a cena secondo e contorno), una porzione a testa, senza ripetere i piatti. Tra due piani si preferisce, nell'ordine: con un profilo, meno piatti Alto per te e poi meno piatti non classificati per te; meno volte lo stesso rischio Alto in due piatti dello stesso giorno; la somma più bassa dei quadrati delle medie settimanali dei rischi, pesate sulle Kcal come per il pasto (i rischi del profilo contano il doppio, differenze fino a 0,05 sono pari). Il piano si riempie un posto alla volta scegliendo a caso tra i piatti pari, poi si migliora un piatto alla volta; un piatto cambiato o scelto resta fisso e gli altri si ribilanciano con meno cambi possibile (`piano.py`). Il piano resta nella sessione del browser, come il pasto.
- **Lista della spesa**: un alimento è verde se ha i cinque rischi classificati, nessuno oltre Basso e il punteggio verde (da 84). Si propongono solo prodotti da comprare: niente alimenti cotti («…, cotti, bolliti»), piatti, erbe aromatiche e condimenti (porzione sotto i 30 g), e un alimento per tipo (prima parola del nome). Mai alimenti con un rischio alto o non classificato; con un profilo, prima il semaforo per te più basso. La lista (fino a 40 voci) resta nella sessione del browser, come il pasto; le spunte nel `localStorage` del dispositivo e ripartono da zero con una lista nuova.
- Il diario sta in `diario.db`, separato dagli altri database ed escluso da git e dai backup.

## 🌐 Lingue

L'interfaccia è in italiano e in inglese. Al primo accesso la lingua segue le preferenze del browser; il link 🌐 nel menu la cambia e la scelta resta in un cookie per un anno. Si traducono pagine, messaggi, errori dei form, livelli, categorie e guida; i nomi degli alimenti restano quelli del database. Anche gli export seguono la lingua: intestazioni, categorie, livelli e testi di Excel e PDF; il CSV in inglese usa la virgola come separatore e il punto decimale (in italiano punto e virgola e virgola decimale). L'import riconosce le intestazioni e le categorie in entrambe le lingue, quindi qualunque export si reimporta. L'API risponde con i messaggi (errori, descrizione dei parametri) nella lingua di `Accept-Language` o del cookie, mentre chiavi e valori dei dati restano in italiano. I comandi da riga di comando restano in italiano.

I testi sono scritti in italiano nel codice e nei template (con `_()` e `{% trans %}`); la traduzione è in `translations/en/LC_MESSAGES/messages.po`. Dopo aver aggiunto o cambiato dei testi:

```bash
pybabel extract -F babel.cfg -o messages.pot --no-location --sort-output .
pybabel update -i messages.pot -d translations --no-fuzzy-matching --ignore-obsolete
# tradurre le voci nuove in messages.po, poi:
pybabel compile -d translations
```

`pytest` segnala i testi senza traduzione, le voci non più usate e un `messages.mo` non ricompilato.

## 📱 App installabile e offline

Il sito si installa come app (Chrome, Edge, Safari su iPhone con «Aggiungi alla schermata Home»). Il service worker conserva sul dispositivo i file statici, la tabella completa (la versione con tutte le righe: online la tabella è divisa in pagine; la copia si riscarica in background al massimo una volta all'ora) e la guida; le schede degli alimenti, il piano settimanale e la lista della spesa restano disponibili dopo averli aperti una volta. Senza connessione la tabella usa l'ultima copia salvata: ricerca, filtri (anche per valori e «solo sicuri») e ordinamento funzionano sul dispositivo (`static/js/tabella.js`), con le stesse regole del server (la ricerca è la stessa di `ricerca.py`, un test le confronta); grafici, classifiche ed export tornano con la rete. Le pagine che richiedono la rete (pasto, diario, confronto, amministrazione) lasciano il posto a una pagina offline con l'elenco delle schede salvate.

All'uscita dall'account le pagine salvate vengono cancellate, perché possono contenere il nome dell'utente e i pulsanti di amministrazione. A ogni deploy che cambia CSS, JavaScript, icone o traduzioni il service worker si aggiorna da solo. L'app installabile richiede HTTPS (in locale va bene `http://localhost`).

## 🥦 Fonti dei dati

- **CREA** – [Tabelle di composizione degli alimenti](https://www.alimentinutrizione.it/tabelle-nutrizionali), aggiornamento 2019: nomi, categorie, porzione tipica e valori nutrizionali dei 900 alimenti. Il sito non ha API né file da scaricare: si leggono le schede, una al secondo. I dati si riproducono citando la fonte, come chiede il CREA (ogni alimento ha fonte, codice e link alla scheda).
- **USDA FoodData Central** (dominio pubblico) – i valori che il CREA non pubblica, soprattutto fruttosio e glucosio, dall'alimento corrispondente: gli abbinamenti, scelti alimento per alimento, sono in `dati/crea_usda.csv` (441 alimenti). Fruttosio, glucosio e lattosio mantengono la proporzione sugli zuccheri dell'alimento USDA, applicata agli zuccheri del CREA. Negli alimenti di origine animale il fruttosio è 0; nel latte e nei latticini non zuccherati gli zuccheri sono lattosio.
- **Open Food Facts** (licenza ODbL) – prodotti confezionati per codice a barre, dal form.
- **CoFID 2021** – [McCance and Widdowson's Composition of Foods Integrated Dataset](https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid) (Public Health England, Open Government Licence v3.0), prima di USDA: profilo degli zuccheri di prodotti europei (senza lo sciroppo di mais dei prodotti USA), applicato agli zuccheri totali del CREA o, se il CREA non li pubblica, a quelli USDA o CoFID; grassi saturi come percentuale degli acidi grassi, convertiti con i grassi totali del CREA e lo stesso fattore FAO, o, dove CoFID non dà la percentuale, con la quota dei saturi sui grassi. Un alimento solo simile si abbina quando il livello di rischio non dipende dalla scelta. Abbinamenti in `dati/crea_cofid.csv` (una riga per gruppo di campi, con una nota sulla scelta); in `dati/cofid.csv` solo gli alimenti CoFID usati, rigenerabili dal file Excel ufficiale con `flask cofid-estrai`.
- **Ciqual 2025** – [Table de composition nutritionnelle des aliments](https://ciqual.anses.fr/) dell'Anses ([doi:10.57745/RDMHWY](https://doi.org/10.57745/RDMHWY), [Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/)), dopo CoFID e prima di USDA, dove CoFID non ha un alimento comparabile o non ne ha i dati: frattaglie, piccione, capretto, panettone, babà, pappa reale, riso alla cantonese e altri. Stesse regole di CoFID: profilo degli zuccheri applicato agli zuccheri del CREA, grassi saturi con la quota dei saturi sui grassi. Per i valori sotto il limite di quantificazione («< 0,2») il fruttosio vale il limite, ma non più degli zuccheri non spiegati dagli altri zuccheri misurati, glucosio e lattosio valgono 0, i saturi il limite. Un gruppo di campi viene da una tabella sola. Abbinamenti in `dati/crea_ciqual.csv`, con la nota sulla scelta; in `dati/ciqual.csv` solo gli alimenti usati, rigenerabili dal file Excel ufficiale con `flask ciqual-estrai`.
- **Ricette CREA** – per i 53 piatti con la lista degli ingredienti, fruttosio, glucosio, lattosio e saturi che il CREA non pubblica si calcolano dagli ingredienti (abbinati agli alimenti CREA in `dati/ingredienti_crea.csv`): la composizione degli ingredienti si applica a zuccheri e grassi del piatto. Carne e pesce, senza fruttosio, hanno pochi zuccheri che vengono dal glicogeno: dove manca il glucosio contano come glucosio, nelle ricette e nei pasti pronti. Si ricalcolano dopo ogni import, modifica o sincronizzazione.
- **Pasti pronti** – ricette dal [Libro di cucina di Wikibooks](https://it.wikibooks.org/wiki/Libro_di_cucina) (licenza [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.it)) e da [Buttalapasta](https://www.buttalapasta.it/) (riuso consentito citando la fonte). Si riprendono solo nome, porzioni e ingredienti con le quantità, con il link alla pagina; il procedimento resta lì. GialloZafferano e altri siti che vietano la lettura automatica o l'estrazione di dati (robots.txt, riserva TDM) non sono stati usati. In `dati/pasti_pronti.csv` le ricette, in `dati/pasti_pronti_ingredienti.csv` gli ingredienti con il codice CREA dell'alimento, i grammi crudi dell'intera ricetta, la resa in cottura e una nota sulle stime; i due file, derivati in parte da Wikibooks, sono distribuiti con la stessa licenza CC BY-SA 4.0. `flask pasti-importa` li carica e calcola i piatti: nutrienti degli ingredienti divisi per il peso cotto, alcol del vino al 35% (tabelle USDA dei fattori di ritenzione), sale aggiunto non conteggiato. I piatti si ricalcolano con le ricette CREA.
- **Indice glicemico** – Atkinson et al., *Diabetes Care* 2008: tabella 1 (medie di più studi) e, dove manca, tabella A1 dell'appendice online (singoli studi, preferiti quelli italiani ed europei, media delle voci che corrispondono); 190 alimenti in `dati/indice_glicemico.csv`, con la voce e i numeri delle voci usate.
- **NOVA, FODMAP, rischi** – regole documentate in `classificazioni.py` e `rischi.py`, spiegate nella pagina Guida con i riferimenti.

```bash
flask --app app crea-importa 007000 007120          # importa o aggiorna alcuni alimenti CREA
flask --app app crea-importa --tutti --cache instance/crea   # tutto l'indice (circa 15 minuti)
flask --app app crea-importa --tutti --sostituisci   # elimina prima gli alimenti senza codice CREA
flask --app app usda-sincronizza                    # aggiorna subito i valori USDA (serve USDA_API_KEY)
flask --app app ricalcola-rischi                    # ricalcola i livelli dopo aver cambiato le regole
flask --app app ricalcola-ricette                   # ricalcola i valori delle ricette dagli ingredienti
flask --app app cofid-estrai CoFID_2021.xlsx        # rigenera dati/cofid.csv dal file Excel ufficiale
flask --app app ciqual-estrai Table_Ciqual_2025.xlsx  # rigenera dati/ciqual.csv dal file Excel ufficiale
flask --app app pasti-importa                       # carica i pasti pronti da dati/ e ricalcola i piatti
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

Parametri di `/api/alimenti`: `q` (ricerca nel nome, tollerante come nella tabella), `categoria`, `rischio_diabete` … `rischio_tumorale` (livello), `sicuri=1`, intervalli `<campo>_min` / `<campo>_max` per `kcal`, `zuccheri`, `fruttosio`, `fibre`, `grassi_saturi`, `sodio`, `rapporto`, `punteggio`, `sort` e `dir` (come la tabella, fino a tre criteri separati da virgole: `sort=categoria,kcal&dir=asc,desc`), `limit` (1–500, default 100), `offset`.

```bash
curl "http://127.0.0.1:5000/api/alimenti?q=mele&rischio_diabete=Basso&kcal_max=60&sort=kcal&dir=desc&limit=5"
```

Gli errori sono JSON: `{"errore": "...", "stato": 404}`, con il messaggio nella lingua di `Accept-Language` (italiano o inglese); chiavi e valori dei dati restano in italiano. `GET /salute` risponde `200` se il database è leggibile (controllo per Docker e Render).

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
- **Semaforo per te**: per ogni condizione del profilo conta un rischio (diabete → rischio diabete, ipercolesterolemia → rischio colesterolo, malassorbimento del fruttosio → rischio malassorbimento) e vale il più alto, senza soglie nuove. Un rischio Alto basta per dare Alto; altrimenti, se un rischio del profilo non è classificato, il semaforo per te resta non classificato. «Solo sicuri per il mio profilo» tiene gli alimenti con il semaforo per te al massimo Basso. Le alternative mettono prima quelle con il semaforo per te più basso, poi il punteggio più alto. Per pasti e giornate la stessa regola si applica ai livelli medi. Gli export applicano il filtro ma non hanno la colonna; l'API non usa il profilo.
- **Punteggio complessivo** = 100 × (1 − media dei punti ÷ 3), con Trascurabile = 0, Basso = 1, Medio = 2, Alto = 3 punti, calcolato sui rischi disponibili. Il colore del punteggio corrisponde al livello medio: oltre 83 Trascurabile, 51–83 Basso, 17–50 Medio, fino a 16 Alto.
- **Medaglie**: primi 10 dell'intero database per punteggio (a parità, più fibre), per rapporto fruttosio/fibre (solo alimenti con almeno 1 g di fruttosio) e per Kcal (esclusi i valori a 0, che indicano dati mancanti).
- **Origine dei dati**: vedi *Fonti dei dati*. Dove una fonte non dà un valore il campo resta vuoto e il rischio che ne dipende «Non classificato»: oggi il colesterolo di 16 alimenti (soprattutto biscotti, cracker e merendine industriali di cui non si conosce il tipo di grasso) e il malassorbimento di 39 (soprattutto verdure ed erbe, cereali, legumi e olive senza un equivalente con il dettaglio degli zuccheri). Le regole sono descritte, con domande aperte, in `docs/revisione_regole.md`, il dossier per la revisione di un nutrizionista.
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
| Dati | CREA (Tabelle di composizione degli alimenti), CoFID 2021, Ciqual 2025, USDA FoodData Central, Open Food Facts (requests) |
| Qualità | pytest, ruff, mypy, GitHub Actions |
| Deploy | Docker, Render |

## 👨‍💻 Sviluppatore

**Paolo Pierno**

## 📄 Licenza

Questo progetto include [Bootstrap Italia](https://italia.github.io/bootstrap-italia/), distribuito con la propria licenza (vedi `static/bootstrap-italia/LICENSE`).
