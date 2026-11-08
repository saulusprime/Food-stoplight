# ✅ AS-IS — Food-stoplight

Attività completate, spostate da [TODO.md](TODO.md). Per ogni sezione è indicato il commit che le ha introdotte.

## 🔐 Sicurezza e configurazione

Commit `7ef6aed` — 7 novembre 2026

- [x] Spostare la `secret_key` di Flask in una variabile d'ambiente (`FLASK_SECRET_KEY`) con file `.env` e `python-dotenv`
- [x] Aggiungere autenticazione utente (login) per proteggere le operazioni di scrittura (nuovo/modifica/elimina/import)
- [x] Ruoli utente: amministratore (CRUD completo) e visitatore (sola consultazione)
- [x] Protezione CSRF sui form (Flask-WTF)
- [x] Configurazione separata sviluppo/produzione (debug off, host/porta configurabili)

## 📊 Visualizzazione dati

Commit `c413e49` — 7 novembre 2026

- [x] Grafici riassuntivi in home page (distribuzione per categoria, per livello di rischio)
- [x] Grafico radar del profilo di rischio nella scheda alimento
- [x] Punteggio complessivo sintetico per alimento (indice 0–100 combinando i 5 rischi)
- [x] Badge/medaglie "top alimenti" (più protettivi, migliore rapporto F/F, meno calorici)
- [x] Modalità scura (dark mode)

## 📥 Import / Export

Commit `4d114f1` — 7 novembre 2026

- [x] **Export CSV/Excel** della tabella filtrata dall'interfaccia web
- [x] Export PDF della scheda alimento o della tabella
- [x] Import da file Excel (.xlsx) oltre che CSV
- [x] Anteprima dell'import con conferma prima della scrittura (mostrare le prime righe mappate)
- [x] Aggiornamento (upsert) da interfaccia web invece del solo inserimento — logica già presente in `update.py`
- [x] Backup/restore del database dall'interfaccia

## 🍽️ Funzionalità nutrizionali

Commit `01e743e` — 7 novembre 2026 — macro e micronutrienti reali per i 199 alimenti USDA; indice glicemico, FODMAP e NOVA hanno i campi ma ancora nessun valore (vedi TODO, Integrazione dati)

- [x] Aggiungere i **macronutrienti completi** (proteine, carboidrati, grassi, grassi saturi, zuccheri, colesterolo) anche nella web app — già supportati da `update.py`
- [x] Micronutrienti: vitamine e sali minerali principali
- [x] **Indice glicemico e carico glicemico** per alimento
- [x] Classificazione FODMAP completa (non solo fruttosio)
- [x] Grado di processazione (classificazione NOVA)
- [x] **Calcolatore porzioni**: ricalcolo dei valori per grammatura personalizzata (es. 150 g invece di 100 g)
- [x] **Composizione pasti**: sommare più alimenti e vedere totali e profilo di rischio del pasto
- [x] Diario alimentare giornaliero con totali di Kcal nette e TEF
- [x] Suggerimenti di alimenti alternativi con profilo di rischio migliore nella stessa categoria

## 🏗️ Architettura e qualità del codice

Commit `4008fd4` — 7 novembre 2026 — deploy preparato (Docker, `render.yaml`), il primo deploy su Render resta da fare

- [x] **API REST** (JSON) per l'accesso programmatico ai dati (`/api/alimenti`, `/api/alimenti/<id>`)
- [x] Unificare lo schema del database tra `app.py` e `update.py` (oggi differiscono: rischi diabete/colesterolo vs macronutrienti/fonti)
- [x] Estrarre la logica condivisa (to_float, mapping CSV, calcoli TEF) in un modulo comune riutilizzato da `app.py`, `update.py` e `autogen.py`
- [x] Migrazioni database strutturate (es. Alembic o script versionati)
- [x] **Test automatici** (pytest): utilities, calcoli TEF, import CSV, route Flask
- [x] Type hints completi e controllo mypy in CI
- [x] GitHub Actions: lint + test a ogni push
- [x] Dockerfile e docker-compose per il deploy
- [x] Deploy su piattaforma cloud: configurazione per Render (`render.yaml`, Dockerfile, docker-compose)

## 📱 Esperienza utente

Commit `7e7a61f` — 7 novembre 2026 — interfaccia tradotta in inglese (export, API e riga di comando restano in italiano); offline la tabella completa, la guida e le schede già aperte

- [x] Ottimizzazione mobile della tabella (colonne prioritarie, schede compatte)
- [x] PWA installabile con consultazione offline
- [x] Internazionalizzazione (italiano/inglese)
- [x] Legenda esplicativa dei livelli di rischio e della metodologia TEF nell'interfaccia
- [x] Conferma di eliminazione con modale (invece del solo submit)
- [x] Toast di notifica non invasivi al posto degli alert

## 🌐 Integrazione dati

Commit `0aef7ea` — 7 novembre 2026 — 900 alimenti reali del CREA al posto dei 1004 precedenti (805 sintetici e 199 USDA in inglese); fruttosio e altri valori mancanti da USDA per 441 alimenti; rischi calcolati con regole documentate. Restano non classificati, per dati mancanti nelle fonti, soprattutto il colesterolo di 91 carni e pesci e il malassorbimento di ricette, biscotti e prodotti da forno

- [x] Sincronizzazione periodica con **USDA FoodData Central** (chiave API configurabile, non demo)
- [x] Integrazione con database CREA (Tabelle di composizione degli alimenti italiane)
- [x] Integrazione con Open Food Facts (ricerca per codice a barre)
- [x] Campi fonte/URL visibili nella web app per la tracciabilità dei dati (già nello schema di `update.py`)
- [x] Sostituire gli 805 alimenti sintetici generati da `autogen.py` (valori casuali, omonimi) con dati reali USDA o CREA (`autogen.py` e i CSV sintetici in `docs/` sono stati poi eliminati)
- [x] Popolare indice glicemico, FODMAP e NOVA da una fonte documentata (tabelle internazionali IG, Monash, Open Food Facts per NOVA)
- [x] Revisione scientifica dei punteggi di rischio con riferimenti bibliografici espliciti

## 🔍 Ricerca e consultazione

Commit `2ad9b63` — 8 novembre 2026 — la home mostra 50 righe per pagina (circa 200 KB invece di 1,6 MB); la copia offline resta quella con tutte le righe

- [x] **Barra di ricerca testuale** per nome alimento: parziale, senza accenti, singolare/plurale, con errori di battitura (`ricerca.py`), ordinata per pertinenza; anche nell'API e nell'export
- [x] **Paginazione** della tabella: 25, 50, 100 righe o tutte; grafici e classifiche restano calcolati su tutti gli alimenti filtrati
- [x] Filtri numerici a intervallo (da / fino a) per Kcal, zuccheri, fruttosio, fibre, grassi saturi, sodio, rapporto F/F e punteggio
- [x] Vista scheda di dettaglio per singolo alimento con tutti i dati e le fonti (già presente dai commit `01e743e` e `0aef7ea`; ora porta anche al confronto)
- [x] **Confronto side-by-side** tra 2–4 alimenti (`/confronta`), dalla tabella, dalla scheda o con la ricerca
- [x] Ordinamento multiplo fino a tre criteri (menu «Ordina per / poi per» e Maiusc+clic sulle intestazioni); rischi in ordine di gravità, dati mancanti in fondo
- [x] Filtro rapido «Solo alimenti sicuri» (tutti e cinque i rischi classificati, al massimo Bassi)

## 🌐 Integrazione dati: fonti aggiuntive

8 novembre 2026 — nuova fonte CoFID 2021 (tabella britannica, Open Government Licence v3.0), ricette calcolate dagli ingredienti, appendice di Atkinson 2008. Non classificati: colesterolo da 195 a 52 alimenti, malassorbimento da 217 a 79

- [x] Grassi saturi per carni e pesci che il CREA pubblica senza percentuale degli acidi grassi: percentuale di saturi da un alimento CoFID simile (alimenti senza saturi da 281 a 134)
- [x] Fruttosio per ricette, biscotti e prodotti da forno: profilo degli zuccheri da CoFID (anche al posto di 15 abbinamenti USDA con sciroppo di mais, come la cola) e ricette CREA calcolate dagli ingredienti (alimenti senza fruttosio da 229 a 82)
- [x] Indice glicemico oltre le 62 voci della tabella di Atkinson 2008: appendice A1 (singoli studi), da 83 a 190 alimenti; le tabelle 2021 restano non accessibili (vedi TODO)
- [x] Materiale per la revisione delle regole da parte di un nutrizionista: `docs/revisione_regole.md` (la revisione resta nel TODO)
- [x] Corretta la sincronizzazione USDA: gli alimenti CREA abbinati a USDA senza campi presi da lì (3) non vengono più sovrascritti

