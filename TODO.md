# 📋 TO-DO — Food-stoplight

Idee, funzionalità e implementazioni future per l'applicazione.
Le attività completate sono in [ASIS.md](ASIS.md).

## 🔐 Sicurezza e configurazione

- [ ] Limitare i tentativi di login falliti (es. Flask-Limiter) contro gli attacchi a forza bruta

## 🌐 Integrazione dati

- [ ] Grassi saturi per le 91 carni e pesci che il CREA pubblica senza percentuale degli acidi grassi (abbinamento USDA come per il fruttosio)
- [ ] Fruttosio per ricette, biscotti e prodotti da forno (oggi «non disponibile»: malassorbimento non classificato)
- [ ] Indice glicemico oltre le 62 voci della tabella di Atkinson 2008 (tabelle complete 2021, previo accesso ai dati)
- [ ] Revisione delle regole dei rischi da parte di un nutrizionista o di un medico

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
