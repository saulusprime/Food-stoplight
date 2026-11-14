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

Commit `a8f0ea9` — 8 novembre 2026 — nuova fonte CoFID 2021 (tabella britannica, Open Government Licence v3.0), ricette calcolate dagli ingredienti, appendice di Atkinson 2008. Non classificati: colesterolo da 195 a 52 alimenti, malassorbimento da 217 a 79

- [x] Grassi saturi per carni e pesci che il CREA pubblica senza percentuale degli acidi grassi: percentuale di saturi da un alimento CoFID simile (alimenti senza saturi da 281 a 134)
- [x] Fruttosio per ricette, biscotti e prodotti da forno: profilo degli zuccheri da CoFID (anche al posto di 15 abbinamenti USDA con sciroppo di mais, come la cola) e ricette CREA calcolate dagli ingredienti (alimenti senza fruttosio da 229 a 82)
- [x] Indice glicemico oltre le 62 voci della tabella di Atkinson 2008: appendice A1 (singoli studi), da 83 a 190 alimenti; le tabelle 2021 restano non accessibili (vedi TODO)
- [x] Materiale per la revisione delle regole da parte di un nutrizionista: `docs/revisione_regole.md` (la revisione resta nel TODO)
- [x] Corretta la sincronizzazione USDA: gli alimenti CREA abbinati a USDA senza campi presi da lì (3) non vengono più sovrascritti

## 📱 Esperienza utente: export in inglese e tabella offline

Commit `d1a74c3` — 9 novembre 2026 — export e messaggi dell'API seguono la lingua; senza rete ricerca, filtri e ordinamento funzionano sulla copia salvata della tabella

- [x] Export (CSV, Excel, PDF) e messaggi dell'API anche in inglese: intestazioni, categorie, livelli e testi nella lingua dell'interfaccia (CSV inglese con virgola e punto decimale); l'import riconosce intestazioni, categorie e livelli in entrambe le lingue; nell'API i messaggi seguono `Accept-Language`, chiavi e valori dei dati restano in italiano
- [x] Filtri e ricerca anche offline: ricerca tollerante, filtri (anche per valori e «solo sicuri») e ordinamento multiplo applicati sul dispositivo alla copia salvata (`static/js/tabella.js`), con le stesse regole del server; un test confronta la ricerca JavaScript con quella Python

## 🏗️ Architettura: blueprint

Commit `6b46f86` — 9 novembre 2026 — `app.py` da 2.500 a circa 320 righe; gli indirizzi delle pagine non cambiano (41 regole, verificate prima e dopo)

- [x] Dividere `app.py` in blueprint Flask nel pacchetto `web/`: pagine (tabella, scheda, confronto, guida), alimenti (nuovo, modifica, elimina), import/export, backup, pasto e diario, accesso (login, lingua, ruoli), comandi da riga di comando e funzioni comuni; in `app.py` restano configurazione, template, errori e avvio

## 🌐 Integrazione dati: rischi non classificati

Commit `6289fec` — 10 novembre 2026 — non classificati: colesterolo da 52 a 29 alimenti, malassorbimento da 79 a 55; un alimento solo simile si abbina quando il livello di rischio non dipende dalla scelta

- [x] Grassi saturi da CoFID anche senza la percentuale sugli acidi grassi: quota dei saturi sui grassi dell'alimento CoFID (colonna «Satd FA /100g fd»), applicata ai grassi del CREA (alimenti senza saturi da 134 a 111)
- [x] Profilo degli zuccheri CoFID applicato anche agli zuccheri totali USDA quando il CREA non li pubblica (carciofi e topinambur avevano l'abbinamento ma restavano senza fruttosio); se mancano anche in USDA, zuccheri totali CoFID, al massimo i carboidrati del CREA (alimenti senza fruttosio da 82 a 58)
- [x] 40 nuovi abbinamenti in `dati/crea_cofid.csv`, ognuno con la nota sulla scelta: frattaglie, selvaggina, patè, mortadella, cheeseburger, caviale, minestre in scatola, gelati, piatti etnici, pizza, dolci, castagne, anona, germe di grano, grano saraceno, riso cotto e gnocchi (con le tre ricette di gnocchi)

## 🛠️ Ritocchi: legenda e import CREA

Commit `880ebc2` — 12 novembre 2026 — legenda e pulsante delle colonne non occupano più una riga a sé; un import CREA con USDA non disponibile non cancella più i valori USDA

- [x] Legenda della tabella sulla riga dell'ordinamento, accanto a «Righe per pagina» e con l'aspetto delle select; aperta si sovrappone alla tabella senza spostarla e si chiude con Esc o con un clic fuori
- [x] «Mostra tutte le colonne» sulla riga del titolo, accanto all'export; offline, quando l'export è nascosto, il pulsante resta
- [x] `crea-importa` scarica i valori USDA prima delle pagine CREA e, se USDA rifiuta le richieste, si ferma senza scrivere nulla: prima riscriveva gli alimenti abbinati senza fruttosio, FDC ID e gli altri campi presi da USDA

## 🍝 Pasti pronti

Commit `5e1b3f9` — 12 novembre 2026 — 100 ricette della cucina italiana (20 antipasti, 30 primi, 30 secondi, 20 contorni) convertite negli alimenti dell'app: si aggiungono al pasto e sono anche piatti della tabella

- [x] Ricette dal Libro di cucina di Wikibooks (48, licenza CC BY-SA 4.0) e da Buttalapasta (52, riuso consentito citando la fonte): solo nome, porzioni e ingredienti con le quantità, con il link alla pagina. GialloZafferano non è stato usato: il suo robots.txt vieta la lettura agli agenti di Anthropic; esclusi anche i siti che riservano l'estrazione dei dati (Fatto in casa da Benedetta, Sale&Pepe)
- [x] Ogni ingrediente abbinato a un alimento CREA con i grammi crudi dell'intera ricetta, la resa in cottura e una nota sulle stime (pesi standard per pezzi, cucchiai e «q.b.», parte edibile, olio di frittura assorbito): `dati/pasti_pronti.csv` e `dati/pasti_pronti_ingredienti.csv`
- [x] Migrazione 5 di `alimenti.db`: tabelle `pasti_pronti` e `pasti_pronti_ingredienti`; comando `flask pasti-importa` (con backup e `--prova`)
- [x] Piatto calcolato dagli ingredienti (metodo delle ricette): nutrienti divisi per il peso cotto, resa di pasta, riso, cereali e legumi dalle coppie crudo/cotto del CREA, alcol del vino al 35% (tabelle USDA dei fattori di ritenzione), indice glicemico pesato sui carboidrati; si ricalcola con le ricette CREA dopo ogni import, modifica o sincronizzazione
- [x] Pagina «Pasti pronti» per portata, ordinabile per nome, punteggio o Kcal per porzione, con punteggio e rischi medi o alti di ogni piatto; «Al pasto» aggiunge gli ingredienti per 1-12 porzioni
- [x] Nella scheda del piatto: ingredienti per una porzione con il link a ogni alimento, fonte e licenza della ricetta, aggiunta al pasto; sezione «Pasti pronti» nella guida

## 🍝 Altri 100 pasti pronti

Commit `6a71f07` — 13 novembre 2026 — i pasti pronti passano da 100 a 200 (40 antipasti, 60 primi, 60 secondi, 40 contorni), senza doppioni

- [x] 100 ricette nuove, 83 da Buttalapasta e 17 dal Libro di cucina di Wikibooks (in tutto 137 e 63), con le stesse regole di conversione e il caricamento con `flask pasti-importa`
- [x] Doppioni esclusi confrontando i candidati con i 100 pasti già presenti e con tutti gli alimenti del database, non solo per nome: fuori i piatti che hanno già un alimento CREA (patatine fritte, minestrone, pollo arrosto) e quelli troppo simili a un pasto esistente (zuppa di cozze e cozze alla tarantina, tiella di polpo e polpo con patate, peperoni in padella e peperonata; il baccalà mantecato di Wikibooks è in realtà un baccalà alla vicentina). Nessun nome nuovo coincide con un alimento: non serve il suffisso «(pasto pronto)»
- [x] Scartate le ricette senza quantità per l'ingrediente principale o senza elenco degli ingredienti, e la bagna càuda: è la sola salsa, senza le verdure da intingere
- [x] Regole di conversione precisate: capperi non conteggiati; olio, burro e brodo usati solo nel procedimento in una riga «(nel procedimento)»; impasti fatti in casa (farina 1,8 nella pasta bollita, acqua dell'impasto 0,6 in forno); parte edibile di pesci interi e asparagi; porzioni ricalcolate, con una nota, quando la fonte ne indica di inverosimili
- [x] La guida descrive i pasti pronti senza numeri fissi, così non va aggiornata a ogni aggiunta
- [x] Calcolo di pasti pronti e ricette CREA identico su ogni versione di Python (commit `9067c3b`): le somme dei nutrienti usano `math.fsum`, perché dalla 3.12 `sum` somma i float in modo diverso e gli zuccheri delle sogliole alla mugnaia (1,145) si arrotondavano a 1,14 su Python 3.11 e a 1,15 dalla 3.12. I valori salvati non cambiano

## 👤 Profili utente e semaforo per te

14 novembre 2026 — ogni utente sceglie le sue condizioni e l'app mostra il semaforo «Per te» accanto al punteggio, senza soglie nuove

- [x] Pagina «Profilo» (`/profilo`) con tre condizioni: diabete, ipercolesterolemia, malassorbimento del fruttosio. Con l'accesso il profilo si salva nell'account (migrazione 2 di `utenti.db`, colonna `condizioni`), senza nella sessione del browser, come il pasto: gli utenti si creano solo da riga di comando, quindi il pubblico è quasi tutto anonimo. All'accesso e all'uscita il profilo della sessione si cancella
- [x] Semaforo per te (`profilo.py`): il livello più alto tra i rischi delle condizioni scelte. Un rischio Alto basta per dare Alto; altrimenti un rischio del profilo non classificato lascia il semaforo per te non classificato
- [x] Tabella: colonna «Per te», ordinamento e filtro «Solo sicuri per il mio profilo» (funzione SQL `per_te`), anche offline in `static/js/tabella.js`; gli export applicano filtro e ordinamento senza aggiungere la colonna, l'API non usa il profilo
- [x] Scheda: riquadro «Per te» con il livello di ogni condizione, rischi del profilo segnati nei motivi, alternative ordinate prima per semaforo per te e poi per punteggio
- [x] Confronto, pasti pronti (anche ordinati «Per te»), pasto e diario (stessa regola sui livelli medi) mostrano il semaforo per te; sezione nella guida
- [x] Salvando il profilo, all'accesso e all'uscita la pagina successiva chiede al service worker di riscaricare le pagine salvate, che contengono il semaforo per te

## 🌐 Integrazione dati: Ciqual e ricette

14 novembre 2026 — nuova fonte Ciqual 2025 (tabella francese dell'Anses, Licence Ouverte 2.0); non classificati: colesterolo da 29 a 16 alimenti, malassorbimento da 55 a 39; nei pasti pronti malassorbimento da 63 a 34

- [x] Ciqual 2025 come terza tabella, dopo CoFID e prima di USDA, con le stesse regole: profilo degli zuccheri sugli zuccheri del CREA, quota dei saturi sui grassi (`ciqual.py`, migrazione 6 di `alimenti.db` con `codice_ciqual` e `campi_ciqual`, comando `flask ciqual-estrai`); valori sotto il limite di quantificazione con una stima prudente per il fruttosio
- [x] 23 abbinamenti in `dati/crea_ciqual.csv`, ognuno con la nota: cuori di pollo, tacchino e cavallo, capretto, piccione, panettone, babà, crostata industriale al cacao, pappa reale, yogurt di soia, pane di segale, riso alla cantonese, spaghetti fritti, salvia, gomme da masticare, gelato confezionato, borlotti cotti, cracker e biscotti integrali alla soia, gnocchi di patate; un alimento solo simile, o un prodotto industriale, solo se il livello non dipende dalla scelta. Restano fuori, a cavallo della soglia o con fonti in disaccordo: cheeseburger, biscotti alla soia, merendine, cicoria, borlotti crudi, fegato di cavallo, milza
- [x] Ricette CREA: abbinati salsa tahina (olio di sesamo, per i grassi) e brodo vegetale (senza grassi né zuccheri rilevanti), quindi hummus e risotto alla parmigiana classificati; con i saturi degli gnocchi e gli zuccheri della salvia anche gnocchi al sugo e ravioli burro e salvia
- [x] Carne e pesce, senza fruttosio, senza il glucosio: nelle ricette e nei pasti pronti i loro zuccheri (dal glicogeno) contano come glucosio. Classificati alici marinate, spigola al cartoccio e 29 pasti pronti di pesce o carne
- [x] Il gelato confezionato con biscotto prende gli zuccheri totali da Ciqual e passa da Medio ad Alto nel rischio metabolico, come gli altri gelati confezionati

## 🛒 Lista della spesa a semaforo verde

14 novembre 2026 — pagina «Spesa» (`/spesa`): una lista per reparti generata dai semafori, da modificare, stampare, scaricare e usare offline al supermercato

- [x] Semaforo verde della lista (`spesa.py`): i cinque rischi classificati, nessuno oltre Basso e punteggio verde (da 84). Nei reparti senza verdi (con le regole attuali cereali, oli e grassi) le scelte migliori senza rischi alti, segnate come non verdi; mai alimenti con un rischio alto o non classificato
- [x] Solo prodotti da comprare: niente alimenti cotti, piatti, erbe aromatiche e condimenti (porzione sotto i 30 g); un alimento per tipo; reparti nell'ordine del supermercato; con un profilo prima il semaforo per te più basso
- [x] Generazione con reparti e alimenti per reparto a scelta, ogni volta diversa tra i verdi del reparto; avviso per i reparti senza niente da proporre
- [x] Voci da cambiare (verde successivo dello stesso reparto, o il successivo non verde dove non ci sono verdi), togliere o aggiungere dalla ricerca; per un alimento non verde l'alternativa verde del reparto
- [x] Spunte salvate sul dispositivo, che ripartono da zero con una lista nuova; stampa senza menu e comandi, download come testo, copia offline nel service worker; voce «Spesa» nel menu con il numero di alimenti e sezione nella guida

## 🗓️ Piano settimanale bilanciato

14 novembre 2026 — pagina «Piano» (`/piano`): pranzi e cene della settimana con i pasti pronti, bilanciati sui rischi; sui dati attuali, rispetto a piatti presi a caso, il punteggio della settimana sale in media da 54 a 68, il rischio medio peggiore scende da 2,3 a 1,5 e le volte in cui lo stesso rischio è Alto due volte in un giorno da 6 a 0

- [x] Bilanciamento (`piano.py`): con un profilo prima meno piatti Alto per te (con il diabete da 12 a 4, il minimo: solo 3 primi su 60 non sono Alto per te) e meno piatti non classificati per te; poi meno volte lo stesso rischio Alto in due piatti dello stesso giorno; poi la somma più bassa dei quadrati delle medie settimanali dei cinque rischi, pesate sulle Kcal come nel pasto, con i rischi del profilo che contano il doppio e una tolleranza di 0,05 sotto cui due piani sono pari
- [x] Costruzione un posto alla volta (prima le portate con più Kcal), a caso tra i piatti pari, così ogni piano è diverso; poi miglioramento un piatto alla volta. Un piano da 28 piatti si calcola in circa 30 ms
- [x] Da 1 a 7 giorni dalla data scelta, portate a scelta per pranzo e cena (di base primo e contorno a pranzo, secondo e contorno a cena), una porzione a testa, nessun piatto ripetuto finché la portata ne ha abbastanza
- [x] ↻ cambia un piatto con il successivo nell'ordine del bilanciamento; «Scegli un altro piatto» mette quello che si vuole, cercandolo per nome. Il piatto resta fisso (📌, si può liberare) e gli altri si ribilanciano partendo dal piano com'è, con meno cambi possibile e un messaggio che dice quali sono cambiati
- [x] Per ogni giorno Kcal, punteggio e semaforo per te; tabella dei rischi giorno per giorno; nutrienti e profilo di rischio della settimana; avviso se con il profilo alcuni piatti restano Alto per te
- [x] Ingredienti della settimana sommati per reparto, per 1-8 persone; «Al pasto» per ogni piatto; stampa, download come testo, copia offline nel service worker; voce «Piano» nel menu e sezione nella guida
