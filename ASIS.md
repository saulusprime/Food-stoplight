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
