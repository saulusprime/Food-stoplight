# 📋 TO-DO — Food-stoplight

Idee, funzionalità e implementazioni future per l'applicazione.
Le attività completate sono in [ASIS.md](ASIS.md).

## 🔐 Sicurezza e configurazione

- [ ] Limitare i tentativi di login falliti (es. Flask-Limiter) contro gli attacchi a forza bruta

## 🌐 Integrazione dati

- [ ] Revisione delle regole dei rischi da parte di un nutrizionista o di un medico: il dossier da inviare è pronto in `docs/revisione_regole.md` (regole, soglie, esempi, 13 domande)
- [ ] Indice glicemico dalle tabelle internazionali 2021 (Atkinson et al., Am J Clin Nutr 2021): il sito dell'editore blocca lo scaricamento dei dati supplementari
- [ ] Rischi ancora non classificati per dati mancanti: colesterolo di 52 alimenti (frattaglie, carni rare, alcuni prodotti industriali) e malassorbimento di 79 (verdure, cereali e ricette senza un equivalente in CoFID o USDA)

## 🏗️ Architettura e qualità del codice

- [ ] Primo deploy su Render dal proprio account: configurazione pronta in `render.yaml` (vedi README, *Render*)
- [ ] Dividere `app.py` in blueprint Flask (pagine, import/export, backup, pasto e diario)

## 📱 Esperienza utente

- [ ] Export (CSV, Excel, PDF) e messaggi dell'API anche in inglese (oggi restano in italiano, come le intestazioni che l'import riconosce)
- [ ] Filtri e ricerca anche offline (senza rete oggi si vede la tabella completa salvata, senza filtri)

## 💡 Idee a lungo termine

- [ ] Profili utente con preferenze e restrizioni (diabete, ipercolesterolemia, malassorbimento del fruttosio) e semaforo personalizzato in base al profilo
- [ ] Generatore di liste della spesa "a semaforo verde"
- [ ] Pianificatore settimanale dei pasti con bilanciamento automatico dei rischi
- [ ] Assistente AI per domande in linguaggio naturale sui dati ("quali frutti hanno il miglior rapporto fruttosio/fibre?")
- [ ] App companion per la scansione dei codici a barre al supermercato
