# Food-stoplight: regole dei rischi da rivedere

Documento per la revisione da parte di un nutrizionista o di un medico.
Dati e regole aggiornati al 10 novembre 2026 (900 alimenti delle Tabelle di composizione CREA).

## 1. Cosa Le chiediamo

Food-stoplight è un'applicazione web che mostra, per ogni alimento delle Tabelle di composizione del CREA, cinque livelli di attenzione ("rischi") a semaforo. I livelli non sono scritti a mano: li calcolano regole automatiche a partire dai valori nutrizionali, con soglie prese da norme e linee guida.

Le chiediamo di dirci se queste regole sono ragionevoli per un pubblico generale, e dove vanno cambiate. In particolare:

- se le soglie e i criteri di ogni rischio (sezione 4) sono corretti e ben scelti;
- se i casi della sezione 6, che a noi sembrano discutibili, lo sono davvero;
- le risposte alle domande della sezione 7.

Può rispondere come preferisce: commenti a margine di questo documento, oppure una riga per domanda con «va bene», «da cambiare» o «non so» e un commento. In allegato può ricevere l'export Excel di tutti i 900 alimenti con valori e livelli, per controllare i casi che Le interessano.

L'app non dà consigli personalizzati e non sostituisce il parere di un professionista: i livelli descrivono un alimento alla volta, non una dieta.

## 2. Come funzionano i livelli

Per ogni alimento si calcolano cinque rischi: **diabete**, **colesterolo**, **malassorbimento** (del fruttosio), **metabolico**, **tumorale**. Ciascuno ha quattro livelli:

| Livello | Significato nell'app |
|---|---|
| Trascurabile | nessun fattore rilevante |
| Basso | un fattore lieve |
| Medio | con moderazione |
| Alto | da limitare |

Un rischio senza dati sufficienti resta **Non classificato** (grigio): l'app non indovina.

Ogni scheda dell'alimento mostra il livello, il motivo in una frase (per esempio «Carico glicemico della porzione (200 g): 30, con indice glicemico 49») e le fonti.

Alcuni criteri valgono **per 100 g** (bevande per 100 ml), altri **per la porzione tipica** indicata dal CREA (per esempio pasta secca 80 g, pasta cotta 200 g, pane 50 g, olio 10 g, frutta 150 g). Quando una regola ha più criteri, vale il livello più alto.

Il **punteggio complessivo** (0–100) è 100 × (1 − media dei punti ÷ 3), con Trascurabile = 0, Basso = 1, Medio = 2, Alto = 3, sui rischi classificati.

Il filtro **«Solo alimenti sicuri»** mostra gli alimenti con tutti e cinque i rischi classificati e al massimo Bassi: oggi sono 171 su 900.

## 3. Da dove vengono i dati

| Dato | Fonte |
|---|---|
| Valori nutrizionali, porzione tipica | CREA, Tabelle di composizione degli alimenti (aggiornamento 2019) |
| Fruttosio, glucosio, lattosio dove il CREA non li pubblica | profilo degli zuccheri di un alimento simile della tabella britannica CoFID 2021 o di USDA FoodData Central, riportato agli zuccheri totali del CREA (se il CREA non li pubblica, a quelli di USDA o, in mancanza, di CoFID) |
| Grassi saturi dove il CREA non pubblica la composizione in acidi grassi | percentuale di acidi grassi saturi di un alimento simile di CoFID 2021 (o, se CoFID non la dà, la sua quota di saturi sui grassi), applicata ai grassi del CREA |
| Ricette CREA senza dettaglio di zuccheri o saturi | composizione calcolata dagli ingredienti della ricetta, applicata a zuccheri e grassi del piatto |
| Indice glicemico | Atkinson et al. 2008: tabella 1 (medie di più studi) e tabella A1 dell'appendice (singoli studi); 190 alimenti |
| Gruppo NOVA, FODMAP | regole sul nome e sulla categoria (Monteiro 2019) e soglie FODMAP (Varney 2017, Sultan 2022) |

Gli abbinamenti con gli alimenti simili sono scelti uno per uno. Dove non c'è un alimento davvero comparabile il dato resta mancante. Un alimento solo simile (per esempio la coscia di pollo per la faraona) si usa quando il livello di rischio non cambierebbe con nessuna composizione plausibile; se il risultato finirebbe a cavallo di una soglia, il dato resta mancante.

Restano non classificati, per dati mancanti:
- **colesterolo:** 29 alimenti: carni rare e frattaglie (9), biscotti, grissini e dolci industriali di cui non si conosce il tipo di grasso (10), ricette (6) e altri 4;
- **malassorbimento:** 55 alimenti: verdure ed erbe senza un equivalente con il dettaglio degli zuccheri (13), ricette e piatti pronti (10), cereali e derivati (9), legumi e frutta secca (6), olive (4) e altri 13.

## 4. Le regole

### Scala comune per i nutrienti da limitare (per 100 g; bevande per 100 ml)

| | Trascurabile | Basso | Medio | Alto | Fonte |
|---|---|---|---|---|---|
| Zuccheri liberi | ≤ 0,5 g | ≤ 5 g | ≤ 22,5 g | > 22,5 g | Reg. CE 1924/2006 («senza», «a basso contenuto»), semaforo FSA |
| Zuccheri liberi, bevande | ≤ 0,5 g | ≤ 2,5 g | ≤ 11,25 g | > 11,25 g | idem |
| Grassi saturi | ≤ 0,1 g | ≤ 1,5 g | ≤ 5 g | > 5 g | idem |
| Grassi saturi, bevande | ≤ 0,1 g | ≤ 0,75 g | ≤ 2,5 g | > 2,5 g | idem |

Gli **zuccheri liberi** seguono la definizione dell'OMS (2015) con una stima prudente:
- per succhi, miele, sciroppi e alimenti trasformati contano tutti gli zuccheri;
- per frutta, verdura, legumi, carne e pesce non trasformati (NOVA 1) nessuno;
- per latte e latticini non dolcificati sono esclusi gli zuccheri del latte.

### Diabete

1. **Carico glicemico della porzione** = indice glicemico × carboidrati disponibili della porzione ÷ 100.
   - Soglie: fino a 5 Trascurabile, fino a 10 Basso, da 11 a 19 Medio, da 20 Alto (Glycemic Index Foundation; il 5 è una convenzione dell'app, metà della soglia «basso»).
2. **Senza indice glicemico** si usa una stima prudente: il carico massimo possibile, pari ai carboidrati disponibili della porzione (indice 100).
3. **Zuccheri liberi:** scala comune.
4. **Fibre** ≥ 6 g/100 g («ad alto contenuto di fibre», Reg. CE 1924/2006): un livello in meno (Reynolds 2019).

Distribuzione:

| Livello | Alimenti | Esempi |
|---|---|---|
| Trascurabile | 458 | latte intero, Parmigiano, olio extravergine, uova, petto di pollo, lombata di bovino |
| Basso | 157 | mele, arance, yogurt intero, carote, pomodori |
| Medio | 120 | ceci bolliti, cioccolato fondente, pizza margherita, lasagna, uva |
| Alto | 165 | pane bianco, pasta cotta, riso, patate bollite, miele, zucchero |

### Colesterolo

1. **Grassi saturi** per 100 g: scala comune (EFSA 2010, Reg. CE 1924/2006, FSA). Se i saturi mancano ma i grassi totali sono al massimo 1,5 g, si usano i grassi totali (i saturi non possono superarli).
2. **Colesterolo della porzione** ≥ 300 mg (limite giornaliero dei LARN 2014): almeno Medio.

| Livello | Alimenti | Esempi |
|---|---|---|
| Trascurabile | 239 | riso, mele, merluzzo, patate, carote, pomodori |
| Basso | 271 | pane, pasta, arance, petto di pollo, ceci, lenticchie |
| Medio | 175 | latte intero, yogurt intero, uova, lombata di bovino, salmone, mandorle |
| Alto | 186 | Parmigiano, burro, olio extravergine, salame, noci, cioccolato fondente |
| Non classificato | 29 | |

### Malassorbimento del fruttosio

Si guarda il **fruttosio in eccesso sul glucosio nella porzione**: il fruttosio accompagnato da altrettanto glucosio viene assorbito insieme. La soglia è 0,15 g per porzione (Varney et al. 2017, criteri Monash).

| Condizione | Livello |
|---|---|
| fruttosio della porzione ≤ 0,15 g | Trascurabile |
| fruttosio bilanciato dal glucosio, o eccesso ≤ 0,15 g | Basso |
| eccesso tra 0,15 e 0,30 g (con mezza porzione si resta sotto soglia) | Medio |
| eccesso oltre 0,30 g | Alto |
| fruttosio sconosciuto, alimento ricco di fruttosio in eccesso secondo la letteratura (Sultan 2022) | Alto |

Fruttani, GOS e polioli sono classificati a parte (sezione FODMAP della scheda) e **non** entrano in questo livello.

| Livello | Alimenti | Esempi |
|---|---|---|
| Trascurabile | 534 | pane, pasta, riso, latte, yogurt, Parmigiano |
| Basso | 179 | patate, carote, zucchine, pizza margherita, lasagna, pasta al pomodoro |
| Medio | 29 | |
| Alto | 103 | mele, arance, pomodori, miele, uva |
| Non classificato | 55 | |

### Metabolico

1. **Densità energetica** per 100 g, secondo WCRF/AICR 2007: fino a 125 kcal Trascurabile, fino a 225 Basso, fino a 275 Medio, oltre Alto.
2. **Zuccheri liberi** > 22,5 g/100 g: Alto.
3. **Bevande:** la densità energetica non si applica (WCRF). Si usa la scala degli zuccheri liberi delle bevande.

| Livello | Alimenti | Esempi |
|---|---|---|
| Trascurabile | 396 | mele, arance, latte, yogurt, petto di pollo, merluzzo |
| Basso | 172 | pasta cotta, uova, lombata, salmone, ceci, lasagna |
| Medio | 60 | pane bianco, pizza margherita |
| Alto | 271 | riso (crudo), Parmigiano, burro, olio extravergine, salame, noci |

### Tumorale

| Criterio | Livello | Fonte |
|---|---|---|
| alcol ≥ 1 g/100 g | Alto | IARC vol. 100E, gruppo 1 |
| carne lavorata (salumi, insaccati, carne in scatola) | Alto | IARC 2015, gruppo 1 |
| carne rossa (bovino, suino, ovino, caprino, equino, coniglio e selvaggina; frattaglie escluse) | Medio | IARC 2015, gruppo 2A |
| sale > 1,5 g/100 g | Medio | WCRF 2018, rosso FSA |
| ultra-trasformato (NOVA 4) | Medio | Fiolet 2018, Monteiro 2019 |
| bevanda zuccherata (zuccheri liberi > 2,5 g/100 ml) | Medio | WCRF 2018 |
| nessuno dei precedenti, fibre ≥ 3 g/100 g | Trascurabile | WCRF 2018 |
| nessuno dei precedenti | Basso | |

| Livello | Alimenti | Esempi |
|---|---|---|
| Trascurabile | 161 | pane bianco, ceci, lenticchie, carote, noci, mandorle |
| Basso | 517 | pasta, riso, mele, arance, latte, yogurt |
| Medio | 152 | lombata di bovino, cioccolato fondente, pizza margherita |
| Alto | 70 | salame, vino |

## 5. Classificazioni di supporto

- **NOVA:** regole sul nome e sulla categoria (Monteiro 2019).
  - Gruppo 1: 554 alimenti; gruppo 2: 22; gruppo 3: 168; gruppo 4: 74.
  - Nessun gruppo per 82 alimenti, quasi tutti ricette (68).
  - Per i prodotti confezionati da codice a barre si usa il gruppo di Open Food Facts.
- **FODMAP:**
  - lattosio e fruttosio in eccesso dai valori misurati, con le soglie di Varney 2017 (lattosio > 1 g, fruttosio in eccesso > 0,15 g, FOS/raffinosio > 0,3 g per porzione);
  - fruttani, GOS e polioli dagli elenchi pubblicati in Sultan 2022.
- **Indice glicemico:** si assegna solo se una voce di Atkinson 2008 corrisponde all'alimento e alla preparazione. Le versioni crude ricevono il valore delle cotte (per esempio le patate crude quello delle bollite).

## 6. Casi che ci sembrano discutibili

1. **Olio extravergine di oliva:** colesterolo Alto e metabolico Alto. I saturi sono 14,6 g e l'energia 899 kcal per 100 g, ma la porzione è di 10 g. Lo stesso vale per frutta secca (noci) e Parmigiano.
2. **Riso e pasta secchi** si valutano come venduti, cioè crudi: riso brillato metabolico Alto (334 kcal/100 g). La pasta cotta risulta Basso.
3. **Pasta cotta:** diabete Alto. La porzione CREA di 200 g dà un carico glicemico di circa 30, con indice glicemico 49.
4. **Pane bianco:** tumorale Trascurabile perché ha 3,8 g di fibre per 100 g («fonte di fibre»). La pasta cotta, con meno fibre, risulta Basso.
5. **Mele, arance, pomodori:** malassorbimento Alto. È coerente con le liste FODMAP, ma l'utente generico potrebbe leggerlo come un giudizio negativo sull'alimento.
6. **Uova:** colesterolo Medio per i grassi saturi. Il criterio dei 300 mg di colesterolo al giorno (LARN 2014) non è più presente in alcune linee guida recenti.

## 7. Domande

1. **Per 100 g o per porzione?** Saturi, densità energetica e sale si valutano per 100 g, come nelle indicazioni nutrizionali europee e nel semaforo FSA. Preferisce che, almeno per gli alimenti consumati in piccole quantità (oli, frutta secca, formaggi stagionati, spezie), si usi la porzione tipica?
2. **Alimenti crudi:** per riso, pasta, legumi secchi e farine conviene valutare la densità energetica sul prodotto cotto, oppure togliere il rischio metabolico ai prodotti che non si mangiano crudi?
3. **Grassi:** il rischio colesterolo dovrebbe considerare anche i grassi insaturi (per esempio un livello in meno per oli vegetali e frutta secca ricchi di monoinsaturi e polinsaturi)?
4. **Colesterolo alimentare:** il criterio «colesterolo della porzione ≥ 300 mg» va tenuto, cambiato o tolto?
5. **Diabete:**
   - Il carico glicemico per porzione tipica, con le soglie 10 e 20, è adatto?
   - È accettabile la stima prudente quando manca l'indice glicemico (carico = carboidrati della porzione)?
   - È accettabile la riduzione di un livello per le fibre ≥ 6 g/100 g?
6. **Malassorbimento:**
   - La soglia di 0,15 g di fruttosio in eccesso per porzione e la scala a quattro livelli sono adatte?
   - Fruttani, GOS e polioli dovrebbero entrare nel livello, oppure il rischio va rinominato «fruttosio»?
7. **Zuccheri liberi:** va bene la stima prudente (tutti gli zuccheri degli alimenti trasformati), anche per prodotti con zuccheri della frutta o del latte?
8. **Tumorale:**
   - Le fibre ≥ 3 g/100 g come fattore protettivo sono adatte?
   - Va bene Medio per carne rossa, NOVA 4, sale > 1,5 g/100 g e bevande zuccherate?
   - Va bene Alto per carni lavorate e alcol, indipendentemente dalla quantità?
9. **Metabolico:** le soglie di densità energetica del WCRF (125, 225, 275 kcal/100 g) sono un buon criterio?
10. **«Solo alimenti sicuri»:** la definizione (tutti i rischi classificati e al massimo Bassi) e il nome sono appropriati, oppure il nome rischia di essere frainteso? Possibili alternative: «semaforo verde», «poco impegnativi».
11. **Punteggio complessivo:** i cinque rischi pesano allo stesso modo. Andrebbero pesati diversamente, oppure il punteggio va tolto?
12. **Dati stimati:** sono accettabili i valori presi da alimenti simili (CoFID, USDA) e quelli calcolati dagli ingredienti delle ricette? La scheda indica sempre quali sono.
13. **Linguaggio:** la parola «rischio» riferita a un singolo alimento può spaventare o essere fraintesa. Preferisce un'altra etichetta (per esempio «attenzione per…»)? Ci sono avvertenze da aggiungere?

## 8. Riferimenti

1. Regolamento (CE) n. 1924/2006 relativo alle indicazioni nutrizionali e sulla salute fornite sui prodotti alimentari, allegato.
2. Department of Health, Food Standards Agency. Guide to creating a front of pack (FoP) nutrition label for pre-packed products sold through retail outlets. 2016.
3. Atkinson FS, Foster-Powell K, Brand-Miller JC. International tables of glycemic index and glycemic load values: 2008. Diabetes Care 2008;31(12):2281-2283 (con l'appendice online, tabella A1).
4. Glycemic Index Foundation (University of Sydney): soglie del carico glicemico per porzione.
5. World Health Organization. Guideline: sugars intake for adults and children. Geneva, 2015.
6. Reynolds A, Mann J, Cummings J, et al. Carbohydrate quality and human health. Lancet 2019;393:434-445.
7. EFSA Panel on Dietetic Products, Nutrition, and Allergies. Scientific Opinion on Dietary Reference Values for fats. EFSA Journal 2010;8(3):1461.
8. SINU. LARN – Livelli di assunzione di riferimento di nutrienti ed energia per la popolazione italiana, IV revisione, 2014.
9. Varney J, Barrett J, Scarlata K, et al. FODMAPs: food composition, defining cutoff values and international application. J Gastroenterol Hepatol 2017;32 Suppl 1:53-61.
10. Sultan N, Varney JE, Halmos EP, et al. How to implement the 3-phase FODMAP diet into gastroenterological practice. J Neurogastroenterol Motil 2022;28(3):343-356.
11. World Cancer Research Fund / American Institute for Cancer Research. Food, Nutrition, Physical Activity, and the Prevention of Cancer: a Global Perspective. 2007.
12. World Cancer Research Fund / American Institute for Cancer Research. Diet, Nutrition, Physical Activity and Cancer: a Global Perspective. Continuous Update Project Expert Report 2018.
13. Bouvard V, Loomis D, Guyton KZ, et al. Carcinogenicity of consumption of red and processed meat. Lancet Oncol 2015;16(16):1599-1600.
14. IARC Monographs vol. 100E (2012): consumption of alcoholic beverages.
15. Fiolet T, Srour B, Sellem L, et al. Consumption of ultra-processed foods and cancer risk: results from NutriNet-Santé prospective cohort. BMJ 2018;360:k322.
16. Monteiro CA, Cannon G, Levy RB, et al. Ultra-processed foods: what they are and how to identify them. Public Health Nutr 2019;22(5):936-941.
17. CREA – Centro di ricerca Alimenti e Nutrizione. Tabelle di composizione degli alimenti, aggiornamento 2019.
18. Public Health England. McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID) 2021, Open Government Licence v3.0.
19. U.S. Department of Agriculture. FoodData Central (SR Legacy, Foundation Foods).
