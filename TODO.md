# 📋 TO-DO — Food-stoplight

Idee, funzionalità e implementazioni future per l'applicazione.
Le attività completate sono in [ASIS.md](ASIS.md).

## 🔐 Sicurezza e configurazione

- [NON SERVE AL MOMENTO] Limitare i tentativi di login falliti (es. Flask-Limiter) contro gli attacchi a forza bruta

## 🌐 Integrazione dati

- [ ] Revisione delle regole dei rischi da parte di un nutrizionista o di un medico: il dossier da inviare è pronto in `docs/revisione_regole.md` (regole, soglie, esempi, 14 domande, anche sui pasti pronti)
- [ ] Indice glicemico dalle tabelle internazionali 2021 (Atkinson et al., Am J Clin Nutr 2021): dal 2023 l'articolo è nell'archivio aperto di Elsevier (ScienceDirect, PII S0002916522004944). 
- [ ] Rischi ancora non classificati per dati mancanti, anche dopo Ciqual: colesterolo di 16 alimenti (biscotti, cracker, grissini e merendine industriali di cui non si conosce il tipo di grasso, tre piatti etnici del CREA, fegato di cavallo e milza di bovino a cavallo della soglia, minestrone liofilizzato, pappa reale, tè in foglie, bottarga) e malassorbimento di 39 (verdure ed erbe senza dati o con fonti in disaccordo, come la cicoria; cereali, legumi e olive con zuccheri in tracce nelle altre tabelle; cheeseburger e biscotti alla soia a cavallo della soglia). Per la bottarga servirebbe un'analisi degli acidi grassi delle uova di muggine; per menta, rosmarino e rucola un dato sul fruttosio
- [ ] Reimportare tutti gli alimenti (`crea-importa --tutti`): l'API USDA ora restituisce anche vitamina D, vitamina B12 e folati, che oggi hanno solo gli 8 alimenti con abbinamento USDA reimportati il 10 novembre 2026. Serve una chiave USDA personale (gratuita, https://fdc.nal.usda.gov/api-key-signup) in `USDA_API_KEY`: con `DEMO_KEY` USDA ha bloccato le richieste dopo 200 dei 303 alimenti abbinati
- [ ] Pasti pronti: far controllare le stime segnate nelle note degli ingredienti (porzioni stimate, sostituzioni come guanciale → pancetta tesa, cavolo nero → broccoletti di rapa, gallinella → scorfano, vodka → whisky, funghi secchi → porcini freschi equivalenti) e decidere se il rischio tumorale di un piatto debba tener conto della carne rossa o lavorata che contiene (oggi, come per le ricette CREA, conta solo nell'ingrediente). Entrambe le cose sono la domanda 14 del dossier

## 🏗️ Architettura e qualità del codice

- [ ] Primo deploy su Render dal proprio account: configurazione pronta in `render.yaml` (vedi README, *Render*)

## 💡 Idee a lungo termine

- [ ] Pianificatore settimanale dei pasti con bilanciamento automatico dei rischi
- [ ] Assistente AI per domande in linguaggio naturale sui dati ("quali frutti hanno il miglior rapporto fruttosio/fibre?")
- [ ] App companion per la scansione dei codici a barre al supermercato
