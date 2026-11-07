# 📋 TO-DO — Food-stoplight

Idee, funzionalità e implementazioni future per l'applicazione.

## 🔐 Sicurezza e configurazione

- [x] Spostare la `secret_key` di Flask in una variabile d'ambiente (`FLASK_SECRET_KEY`) con file `.env` e `python-dotenv`
- [x] Aggiungere autenticazione utente (login) per proteggere le operazioni di scrittura (nuovo/modifica/elimina/import)
- [x] Ruoli utente: amministratore (CRUD completo) e visitatore (sola consultazione)
- [x] Protezione CSRF sui form (Flask-WTF)
- [x] Configurazione separata sviluppo/produzione (debug off, host/porta configurabili)
- [ ] Limitare i tentativi di login falliti (es. Flask-Limiter) contro gli attacchi a forza bruta

## 🔍 Ricerca e consultazione

- [ ] **Barra di ricerca testuale** per nome alimento (con ricerca parziale/fuzzy)
- [ ] **Paginazione** della tabella (attualmente carica tutti gli alimenti in una pagina)
- [ ] Filtri numerici a intervallo (es. Kcal min–max, fruttosio max)
- [ ] Vista scheda di dettaglio per singolo alimento con tutti i dati e le fonti
- [ ] **Confronto side-by-side** tra due o più alimenti
- [ ] Ordinamento multiplo (es. categoria + kcal)
- [ ] Filtro rapido "solo alimenti sicuri" (tutti i rischi bassi/trascurabili)

## 📊 Visualizzazione dati

- [x] Grafici riassuntivi in home page (distribuzione per categoria, per livello di rischio)
- [x] Grafico radar del profilo di rischio nella scheda alimento
- [x] Punteggio complessivo sintetico per alimento (indice 0–100 combinando i 5 rischi)
- [x] Badge/medaglie "top alimenti" (più protettivi, migliore rapporto F/F, meno calorici)
- [x] Modalità scura (dark mode)

## 🍽️ Funzionalità nutrizionali

- [ ] Aggiungere i **macronutrienti completi** (proteine, carboidrati, grassi, grassi saturi, zuccheri, colesterolo) anche nella web app — già supportati da `update.py`
- [ ] Micronutrienti: vitamine e sali minerali principali
- [ ] **Indice glicemico e carico glicemico** per alimento
- [ ] Classificazione FODMAP completa (non solo fruttosio)
- [ ] Grado di processazione (classificazione NOVA)
- [ ] **Calcolatore porzioni**: ricalcolo dei valori per grammatura personalizzata (es. 150 g invece di 100 g)
- [ ] **Composizione pasti**: sommare più alimenti e vedere totali e profilo di rischio del pasto
- [ ] Diario alimentare giornaliero con totali di Kcal nette e TEF
- [ ] Suggerimenti di alimenti alternativi con profilo di rischio migliore nella stessa categoria

## 📥 Import / Export

- [x] **Export CSV/Excel** della tabella filtrata dall'interfaccia web
- [x] Export PDF della scheda alimento o della tabella
- [x] Import da file Excel (.xlsx) oltre che CSV
- [x] Anteprima dell'import con conferma prima della scrittura (mostrare le prime righe mappate)
- [x] Aggiornamento (upsert) da interfaccia web invece del solo inserimento — logica già presente in `update.py`
- [x] Backup/restore del database dall'interfaccia

## 🌐 Integrazione dati

- [ ] Sincronizzazione periodica con **USDA FoodData Central** (chiave API configurabile, non demo)
- [ ] Integrazione con database CREA (Tabelle di composizione degli alimenti italiane)
- [ ] Integrazione con Open Food Facts (ricerca per codice a barre)
- [ ] Campi fonte/URL visibili nella web app per la tracciabilità dei dati (già nello schema di `update.py`)
- [ ] Revisione scientifica dei punteggi di rischio con riferimenti bibliografici espliciti

## 🏗️ Architettura e qualità del codice

- [ ] **API REST** (JSON) per l'accesso programmatico ai dati (`/api/alimenti`, `/api/alimenti/<id>`)
- [ ] Unificare lo schema del database tra `app.py` e `update.py` (oggi differiscono: rischi diabete/colesterolo vs macronutrienti/fonti)
- [ ] Estrarre la logica condivisa (to_float, mapping CSV, calcoli TEF) in un modulo comune riutilizzato da `app.py`, `update.py` e `autogen.py`
- [ ] Migrazioni database strutturate (es. Alembic o script versionati)
- [ ] **Test automatici** (pytest): utilities, calcoli TEF, import CSV, route Flask
- [ ] Type hints completi e controllo mypy in CI
- [ ] GitHub Actions: lint + test a ogni push
- [ ] Dockerfile e docker-compose per il deploy
- [ ] Deploy su piattaforma cloud (Render / Railway / PythonAnywhere)

## 📱 Esperienza utente

- [ ] Ottimizzazione mobile della tabella (colonne prioritarie, schede compatte)
- [ ] PWA installabile con consultazione offline
- [ ] Internazionalizzazione (italiano/inglese)
- [ ] Legenda esplicativa dei livelli di rischio e della metodologia TEF nell'interfaccia
- [ ] Conferma di eliminazione con modale (invece del solo submit)
- [ ] Toast di notifica non invasivi al posto degli alert

## 💡 Idee a lungo termine

- [ ] Profili utente con preferenze e restrizioni (diabete, ipercolesterolemia, malassorbimento del fruttosio) e semaforo personalizzato in base al profilo
- [ ] Generatore di liste della spesa "a semaforo verde"
- [ ] Pianificatore settimanale dei pasti con bilanciamento automatico dei rischi
- [ ] Assistente AI per domande in linguaggio naturale sui dati ("quali frutti hanno il miglior rapporto fruttosio/fibre?")
- [ ] App companion per la scansione dei codici a barre al supermercato
