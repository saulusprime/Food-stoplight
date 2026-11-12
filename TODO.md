# 📋 TO-DO — Food-stoplight

Idee, funzionalità e implementazioni future per l'applicazione.
Le attività completate sono in [ASIS.md](ASIS.md).

## 🔐 Sicurezza e configurazione

- [NON SERVE AL MOMENTO] Limitare i tentativi di login falliti (es. Flask-Limiter) contro gli attacchi a forza bruta

## 🌐 Integrazione dati

- [ ] Revisione delle regole dei rischi da parte di un nutrizionista o di un medico: il dossier da inviare è pronto in `docs/revisione_regole.md` (regole, soglie, esempi, 13 domande)
- [ ] Indice glicemico dalle tabelle internazionali 2021 (Atkinson et al., Am J Clin Nutr 2021): dal 2023 l'articolo è nell'archivio aperto di Elsevier (ScienceDirect, PII S0002916522004944), ma il sito blocca lo scaricamento automatico e dichiara riservata l'estrazione dei dati (`tdm-reservation`). Serve scaricare a mano dal browser la tabella supplementare e verificarne la licenza d'uso; poi si importa come l'appendice 2008
- [ ] Rischi ancora non classificati per dati mancanti: colesterolo di 29 alimenti (frattaglie e carni rare, biscotti e dolci industriali di cui non si conosce il tipo di grasso, alcune ricette) e malassorbimento di 55 (verdure ed erbe, ricette, cereali e legumi senza un equivalente con il dettaglio degli zuccheri in CoFID o USDA, o con un risultato a cavallo di una soglia)
- [ ] Reimportare tutti gli alimenti (`crea-importa --tutti`): l'API USDA ora restituisce anche vitamina D, vitamina B12 e folati, che oggi hanno solo gli 8 alimenti con abbinamento USDA reimportati il 10 novembre 2026. Serve una chiave USDA personale (gratuita, https://fdc.nal.usda.gov/api-key-signup) in `USDA_API_KEY`: con `DEMO_KEY` USDA ha bloccato le richieste dopo 200 dei 303 alimenti abbinati

## 🏗️ Architettura e qualità del codice

- [ ] Primo deploy su Render dal proprio account: configurazione pronta in `render.yaml` (vedi README, *Render*)

## 💡 Idee a lungo termine

- [ ] Profili utente con preferenze e restrizioni (diabete, ipercolesterolemia, malassorbimento del fruttosio) e semaforo personalizzato in base al profilo
- [ ] Generatore di liste della spesa "a semaforo verde"
- [ ] Pianificatore settimanale dei pasti con bilanciamento automatico dei rischi
- [ ] Assistente AI per domande in linguaggio naturale sui dati ("quali frutti hanno il miglior rapporto fruttosio/fibre?")
- [ ] App companion per la scansione dei codici a barre al supermercato
