# 📋 TO-DO — Food-stoplight

Idee, funzionalità e implementazioni future per l'applicazione.
Le attività completate sono in [ASIS.md](ASIS.md).

## 🔐 Sicurezza e configurazione

- [ ] Limitare i tentativi di login falliti (es. Flask-Limiter) contro gli attacchi a forza bruta

## 🔍 Ricerca e consultazione

- [ ] **Barra di ricerca testuale** per nome alimento (con ricerca parziale/fuzzy)
- [ ] **Paginazione** della tabella (attualmente carica tutti gli alimenti in una pagina)
- [ ] Filtri numerici a intervallo (es. Kcal min–max, fruttosio max)
- [ ] Vista scheda di dettaglio per singolo alimento con tutti i dati e le fonti
- [ ] **Confronto side-by-side** tra due o più alimenti
- [ ] Ordinamento multiplo (es. categoria + kcal)
- [ ] Filtro rapido "solo alimenti sicuri" (tutti i rischi bassi/trascurabili)

## 🌐 Integrazione dati

- [ ] Sincronizzazione periodica con **USDA FoodData Central** (chiave API configurabile, non demo)
- [ ] Integrazione con database CREA (Tabelle di composizione degli alimenti italiane)
- [ ] Integrazione con Open Food Facts (ricerca per codice a barre)
- [ ] Campi fonte/URL visibili nella web app per la tracciabilità dei dati (già nello schema di `update.py`)
- [ ] Sostituire gli 805 alimenti sintetici generati da `autogen.py` (valori casuali, omonimi) con dati reali USDA o CREA
- [ ] Popolare indice glicemico, FODMAP e NOVA da una fonte documentata (tabelle internazionali IG, Monash, Open Food Facts per NOVA)
- [ ] Revisione scientifica dei punteggi di rischio con riferimenti bibliografici espliciti

## 🏗️ Architettura e qualità del codice

- [ ] Primo deploy su Render dal proprio account: configurazione pronta in `render.yaml` (vedi README, *Render*)
- [ ] Dividere `app.py` in blueprint Flask (pagine, import/export, backup, pasto e diario)

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
