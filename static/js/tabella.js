/* Food-stoplight — tabella della home senza rete
 *
 * Offline il service worker mostra la copia completa della tabella salvata
 * (tutte le righe, senza filtri) per qualunque indirizzo della home. Se i
 * parametri dell'indirizzo non sono quelli con cui il server ha preparato
 * la pagina (data-vista della tabella), questo script applica sul
 * dispositivo ricerca, filtri e ordinamento, con le stesse regole del
 * server (archivio.py, ricerca.py).
 *
 * Ricerca e semaforo per te sono anche un modulo per Node:
 * tests/test_tabella_offline.py confronta i risultati con quelli di
 * ricerca.py e di profilo.py.
 */
(function (radice) {
    "use strict";

    // -----------------------------------------------------------------
    // Ricerca per nome: stessa logica di ricerca.py
    // -----------------------------------------------------------------
    var LUNGHEZZA_MASSIMA = 100;
    var DESINENZE = [
        ["cia", ["ce", "cie"]], ["gia", ["ge", "gie"]], ["ca", ["che"]], ["ga", ["ghe"]],
        ["co", ["chi", "ci"]], ["go", ["ghi", "gi"]], ["che", ["ca"]], ["ghe", ["ga"]],
        ["chi", ["co"]], ["ghi", ["go"]], ["a", ["e"]], ["o", ["i", "a"]], ["e", ["i", "a"]],
        ["i", ["o", "e"]]
    ];
    var UGUALE = 1.0, VARIANTE = 0.95, INIZIO = 0.6, DENTRO = 0.5, SIMILE = 0.45, SIMILE_INIZIO = 0.3;
    var ESATTA = 1, SIMILE_PAROLA = 2, SIMILE_INIZIO_PAROLA = 3;

    function normalizza(testo) {
        var ascii = String(testo || "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "");
        return ascii.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ");
    }

    function parole(testo) {
        return testo ? testo.split(" ") : [];
    }

    function varianti(parola) {
        if (parola.length < 4) {
            return [];
        }
        for (var i = 0; i < DESINENZE.length; i++) {
            var desinenza = DESINENZE[i][0];
            if (parola.slice(-desinenza.length) === desinenza) {
                var radiceParola = parola.slice(0, parola.length - desinenza.length);
                return DESINENZE[i][1]
                    .map(function (alternativa) { return radiceParola + alternativa; })
                    .filter(function (forma) { return forma !== parola; });
            }
        }
        return [];
    }

    function distanza(a, b, massimo) {
        if (Math.abs(a.length - b.length) > massimo) {
            return massimo + 1;
        }
        var precedente2 = [];
        var precedente = [];
        var j;
        for (j = 0; j <= b.length; j++) {
            precedente.push(j);
        }
        for (var i = 1; i <= a.length; i++) {
            var corrente = [i];
            var minimo = i;
            for (j = 1; j <= b.length; j++) {
                var costo = a[i - 1] === b[j - 1] ? 0 : 1;
                var valore = Math.min(precedente[j] + 1, corrente[j - 1] + 1, precedente[j - 1] + costo);
                if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
                    valore = Math.min(valore, precedente2[j - 2] + 1);
                }
                corrente.push(valore);
                minimo = Math.min(minimo, valore);
            }
            if (minimo > massimo) {
                return massimo + 1;
            }
            precedente2 = precedente;
            precedente = corrente;
        }
        return precedente[b.length];
    }

    function tolleranza(parola) {
        return parola.length < 4 ? 0 : parola.length < 7 ? 1 : 2;
    }

    function tolleranzaInizio(parola) {
        return parola.length < 5 ? 0 : parola.length < 8 ? 1 : 2;
    }

    function corrispondenza(cercata, parola, variantiCercata, modo) {
        if (parola === cercata) {
            return UGUALE;
        }
        if (variantiCercata.indexOf(parola) !== -1) {
            return VARIANTE;
        }
        if (parola.indexOf(cercata) === 0) {
            return INIZIO + 0.3 * cercata.length / parola.length;
        }
        if (cercata.length >= 3 && parola.indexOf(cercata) !== -1) {
            return DENTRO;
        }
        var t;
        if (modo >= SIMILE_PAROLA) {
            t = tolleranza(cercata);
            if (t) {
                var d = distanza(cercata, parola, t);
                if (d <= t) {
                    return SIMILE - 0.05 * (d - 1);
                }
            }
        }
        if (modo >= SIMILE_INIZIO_PAROLA) {
            t = tolleranzaInizio(cercata);
            if (t && parola.length > cercata.length) {
                for (var lunghezza = cercata.length - 1; lunghezza <= cercata.length + 1; lunghezza++) {
                    if (distanza(cercata, parola.slice(0, lunghezza), t) <= t) {
                        return SIMILE_INIZIO;
                    }
                }
            }
        }
        return 0;
    }

    function migliore(cercata, paroleNome, modo, prima) {
        var variantiCercata = varianti(cercata);
        var risultato = 0;
        for (var j = 0; j < paroleNome.length; j++) {
            var valore = corrispondenza(cercata, paroleNome[j], variantiCercata, modo);
            if (valore && prima && j === 0) {
                valore += 0.2;
            }
            risultato = Math.max(risultato, valore);
        }
        return risultato;
    }

    function punteggio(normale, paroleNome, cercato, modi) {
        var cercate = parole(cercato);
        if (!cercate.length) {
            return null;
        }
        var somma = 0;
        for (var i = 0; i < cercate.length; i++) {
            var valore = migliore(cercate[i], paroleNome, modi ? modi[i] : ESATTA, i === 0);
            if (!valore) {
                return null;
            }
            somma += valore;
        }
        var risultato = somma / cercate.length;
        if (normale === cercato) {
            risultato += 2;
        } else if (normale.indexOf(cercato + " ") === 0) {
            risultato += 1;
        } else if (cercate.length > 1 && (" " + normale + " ").indexOf(" " + cercato + " ") !== -1) {
            risultato += 0.5;
        }
        return risultato - 0.001 * normale.length;
    }

    /* Indici e punteggi dei nomi che corrispondono al testo, nell'ordine dato:
       [[indice, punteggio], ...] */
    function cerca(nomi, testo) {
        var cercato = normalizza(String(testo || "").slice(0, LUNGHEZZA_MASSIMA));
        var normali = nomi.map(normalizza);
        var elenchi = normali.map(parole);
        var i;
        if (!cercato) {
            return nomi.map(function (_nome, indice) { return [indice, 0]; });
        }
        var modi = [];
        var cercate = parole(cercato);
        for (i = 0; i < cercate.length; i++) {
            var modo = null;
            for (var m = ESATTA; m <= SIMILE_INIZIO_PAROLA && modo === null; m++) {
                for (var k = 0; k < elenchi.length; k++) {
                    if (migliore(cercate[i], elenchi[k], m, false)) {
                        modo = m;
                        break;
                    }
                }
            }
            if (modo === null) {
                return [];
            }
            modi.push(modo);
        }
        var trovati = [];
        for (i = 0; i < nomi.length; i++) {
            var valore = punteggio(normali[i], elenchi[i], cercato, modi);
            if (valore !== null) {
                trovati.push([i, valore]);
            }
        }
        return trovati;
    }

    var Ricerca = { normalizza: normalizza, varianti: varianti, distanza: distanza, cerca: cerca };

    // -----------------------------------------------------------------
    // Semaforo per te: stessa logica di profilo.punti_per_te. livelli:
    // punti (0-3) dei rischi del profilo, null se non classificato
    // -----------------------------------------------------------------
    var PUNTI_MAX = 3;

    function puntiPerTe(livelli) {
        if (!livelli.length) {
            return null;
        }
        if (livelli.indexOf(PUNTI_MAX) !== -1) {
            return PUNTI_MAX;
        }
        if (livelli.indexOf(null) !== -1) {
            return null;
        }
        return Math.max.apply(null, livelli);
    }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = {
            normalizza: normalizza, varianti: varianti, distanza: distanza, cerca: cerca, puntiPerTe: puntiPerTe
        };
    }
    radice.Ricerca = Ricerca;

    if (typeof document === "undefined") {
        return;
    }

    // -----------------------------------------------------------------
    // Tabella offline
    // -----------------------------------------------------------------
    var tabella = document.querySelector("table.tabella-alimenti[data-vista]");
    if (!tabella) {
        return;
    }

    var vista;
    try {
        vista = JSON.parse(tabella.getAttribute("data-vista"));
    } catch (errore) {
        return;
    }

    var LIVELLI = ["trascurabile", "basso", "medio", "alto"];
    var RISCHI = vista.rischi;            // campi dei rischi, nell'ordine di data-r
    var VALORI = vista.valori;            // campi numerici, nell'ordine di data-v
    var INTERVALLI = vista.intervalli;    // campi dei filtri a intervallo
    var ORDINABILI = vista.ordinabili;    // campi ordinabili
    var ORDINAMENTI_MAX = vista.ordinamenti_max;
    var PER_TE = vista.per_te || [];      // rischi del profilo (semaforo per te), vuoto senza profilo
    var PER_TE_ADATTI = vista.per_te_adatti;
    var PERTINENZA = "pertinenza";

    function attivo(testo) {
        return ["1", "on", "true", "si", "sì"].indexOf(String(testo || "").trim().toLowerCase()) !== -1;
    }

    function valori(parametri, nome) {
        var tutti = parametri.getAll(nome);
        if (tutti.length === 1) {
            return tutti[0].split(",").map(function (v) { return v.trim(); });
        }
        return tutti.map(function (v) { return v.trim(); });
    }

    function numeroFiltro(testo) {
        testo = String(testo || "").trim().replace(",", ".");
        if (!testo || !/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(testo)) {
            return null;
        }
        var valore = parseFloat(testo);
        return isFinite(valore) && valore >= 0 ? valore : null;
    }

    function ordinamenti(campi, direzioni, ricerca) {
        var scelti = [];
        campi.forEach(function (campo, i) {
            var direzione = (direzioni[i] || "").toLowerCase();
            var valido;
            if (campo === PERTINENZA) {
                valido = ricerca && !scelti.length;
                direzione = "desc";
            } else {
                valido = ORDINABILI.indexOf(campo) !== -1;
            }
            var presente = scelti.some(function (c) { return c[0] === campo; });
            if (valido && !presente) {
                scelti.push([campo, direzione === "asc" || direzione === "desc" ? direzione : "asc"]);
            }
        });
        if (!scelti.length) {
            scelti = ricerca ? [[PERTINENZA, "desc"]] : [["alimento", "asc"]];
        }
        return scelti.slice(0, ORDINAMENTI_MAX);
    }

    /* Stato della tabella dai parametri, come archivio.leggi_filtri */
    function leggiStato(parametri) {
        var stato = { filtri: {}, criteri: [] };
        var q = (parametri.get("q") || "").split(/\s+/).filter(Boolean).join(" ").slice(0, LUNGHEZZA_MASSIMA);
        stato.filtri.q = q;
        ["categoria"].concat(RISCHI).forEach(function (campo) {
            stato.filtri[campo] = (parametri.get(campo) || "").trim();
        });
        stato.filtri.sicuri = attivo(parametri.get("sicuri")) ? "1" : "";
        stato.filtri.per_te = PER_TE.length && attivo(parametri.get("per_te")) ? "1" : "";
        INTERVALLI.forEach(function (campo) {
            ["min", "max"].forEach(function (limite) {
                var valore = numeroFiltro(parametri.get(campo + "_" + limite));
                stato.filtri[campo + "_" + limite] = valore === null ? "" : String(valore);
            });
        });
        stato.criteri = ordinamenti(valori(parametri, "sort"), valori(parametri, "dir"), Boolean(q));
        return stato;
    }

    function chiave(stato) {
        var filtri = Object.keys(stato.filtri).sort().map(function (k) { return k + "=" + stato.filtri[k]; });
        return filtri.join("&") + "#" + stato.criteri.map(function (c) { return c.join(":"); }).join(",");
    }

    var richiesto = leggiStato(new URLSearchParams(window.location.search));
    var server = leggiStato(new URLSearchParams(vista.parametri));

    if (chiave(richiesto) === chiave(server)) {
        return;   // la pagina è già quella giusta (online)
    }

    // --- righe della tabella --------------------------------------------
    var corpo = tabella.tBodies[0];
    var righe = Array.prototype.filter.call(corpo.rows, function (riga) { return riga.hasAttribute("data-id"); });

    function minuscoloAscii(testo) {
        return String(testo || "").replace(/[A-Z]+/g, function (s) { return s.toLowerCase(); });
    }

    var dati = righe.map(function (riga) {
        var nome = riga.querySelector(".nome-alimento").textContent.trim();
        var numeri = {};
        (riga.getAttribute("data-v") || "").split("|").forEach(function (testo, i) {
            numeri[VALORI[i]] = testo === "" ? null : parseFloat(testo);
        });
        var rischi = {};
        (riga.getAttribute("data-r") || "").split("|").forEach(function (testo, i) {
            rischi[RISCHI[i]] = testo;
        });
        return {
            riga: riga,
            id: parseInt(riga.getAttribute("data-id"), 10),
            nome: nome,
            categoria: riga.getAttribute("data-c") || "",
            rischi: rischi,
            numeri: numeri
        };
    });

    function livello(valore) {
        var indice = LIVELLI.indexOf(String(valore || "").trim().toLowerCase());
        return indice === -1 ? null : indice;
    }

    function perTe(dato) {
        return puntiPerTe(PER_TE.map(function (campo) { return livello(dato.rischi[campo]); }));
    }

    function espressione(dato, campo) {
        if (campo === "alimento") {
            return minuscoloAscii(dato.nome);
        }
        if (campo === "categoria") {
            var categoria = minuscoloAscii(dato.categoria.trim());
            return categoria || null;
        }
        if (RISCHI.indexOf(campo) !== -1) {
            return livello(dato.rischi[campo]);
        }
        if (campo === "per_te") {
            return perTe(dato);
        }
        var valore = dato.numeri[campo];
        return valore === undefined ? null : valore;
    }

    function confronta(a, b) {
        return a < b ? -1 : a > b ? 1 : 0;
    }

    // --- filtri -------------------------------------------------------------
    var filtri = richiesto.filtri;
    var risultato = dati.filter(function (dato) {
        if (filtri.categoria && dato.categoria.toLowerCase() !== filtri.categoria.toLowerCase()) {
            return false;
        }
        for (var i = 0; i < RISCHI.length; i++) {
            var atteso = filtri[RISCHI[i]];
            if (atteso && String(dato.rischi[RISCHI[i]] || "").toLowerCase() !== atteso.toLowerCase()) {
                return false;
            }
        }
        if (filtri.sicuri) {
            var sicuro = RISCHI.every(function (campo) {
                var l = livello(dato.rischi[campo]);
                return l === 0 || l === 1;
            });
            if (!sicuro) {
                return false;
            }
        }
        if (filtri.per_te) {
            var punti = perTe(dato);
            if (punti === null || punti > PER_TE_ADATTI) {
                return false;
            }
        }
        return INTERVALLI.every(function (campo) {
            var valore = espressione(dato, campo);
            var minimo = filtri[campo + "_min"];
            var massimo = filtri[campo + "_max"];
            if ((minimo || massimo) && valore === null) {
                return false;
            }
            return (!minimo || valore >= parseFloat(minimo)) && (!massimo || valore <= parseFloat(massimo));
        });
    });

    // --- ordinamento: criteri con i NULL in fondo, poi nome e id ---------------
    var criteri = richiesto.criteri;
    risultato.sort(function (a, b) {
        for (var i = 0; i < criteri.length; i++) {
            var campo = criteri[i][0];
            if (campo === PERTINENZA) {
                continue;
            }
            var va = espressione(a, campo);
            var vb = espressione(b, campo);
            if ((va === null) !== (vb === null)) {
                return va === null ? 1 : -1;
            }
            if (va !== null) {
                var esito = confronta(va, vb);
                if (esito) {
                    return criteri[i][1] === "desc" ? -esito : esito;
                }
            }
        }
        return confronta(minuscoloAscii(a.nome), minuscoloAscii(b.nome)) || confronta(a.id, b.id);
    });

    if (filtri.q) {
        var trovati = Ricerca.cerca(risultato.map(function (d) { return d.nome; }), filtri.q);
        var ordinati = trovati.map(function (coppia) { return { dato: risultato[coppia[0]], punti: coppia[1] }; });
        if (criteri[0][0] === PERTINENZA) {
            // ordinamento stabile per punteggio decrescente
            ordinati = ordinati
                .map(function (voce, posizione) { voce.posizione = posizione; return voce; })
                .sort(function (a, b) { return (b.punti - a.punti) || (a.posizione - b.posizione); });
        }
        risultato = ordinati.map(function (voce) { return voce.dato; });
    }

    // --- pagina ---------------------------------------------------------------
    var visibili = new Set(risultato.map(function (d) { return d.riga; }));
    righe.forEach(function (riga) { riga.hidden = !visibili.has(riga); });
    risultato.forEach(function (d) { corpo.appendChild(d.riga); });

    document.documentElement.classList.add("tabella-sul-dispositivo");

    var testi = radice.TESTI || {};
    var avviso = document.getElementById("avviso-offline-tabella");
    if (avviso) {
        avviso.hidden = false;
    }

    var conteggio = document.querySelector("#titolo-tabella .text-muted");
    if (conteggio) {
        var modello = risultato.length === 1 ? testi.tabellaUno : testi.tabellaMolti;
        conteggio.textContent = "· " + String(modello || "{n}").replace("{n}", risultato.length);
    }

    var vuota = document.getElementById("tabella-vuota-offline");
    if (vuota) {
        vuota.hidden = risultato.length > 0;
    }

    // --- moduli: mostrano lo stato richiesto e lo conservano all'invio ---------
    var moduloFiltri = document.querySelector("form.filtri");
    var moduloVista = document.querySelector("form.vista-form");

    function impostaCampo(modulo, nome, valore) {
        var campo = modulo && modulo.elements.namedItem(nome);
        // più campi con lo stesso nome (RadioNodeList) o nascosti: non si toccano
        if (!campo || !campo.tagName || campo.type === "hidden") {
            return;
        }
        if (campo.type === "checkbox") {
            campo.checked = Boolean(valore);
        } else {
            campo.value = valore;
        }
    }

    function nascosti(modulo, coppie) {
        if (!modulo) {
            return;
        }
        Array.prototype.forEach.call(modulo.querySelectorAll("input[type=hidden]"), function (campo) {
            campo.remove();
        });
        coppie.forEach(function (coppia) {
            var campo = document.createElement("input");
            campo.type = "hidden";
            campo.name = coppia[0];
            campo.value = coppia[1];
            modulo.appendChild(campo);
        });
    }

    var predefiniti = ordinamenti([], [], Boolean(filtri.q));
    var ordinePredefinito = JSON.stringify(predefiniti) === JSON.stringify(criteri);
    var ordine = ordinePredefinito ? [] : [
        ["sort", criteri.map(function (c) { return c[0]; }).join(",")],
        ["dir", criteri.map(function (c) { return c[1]; }).join(",")]
    ];

    Object.keys(filtri).forEach(function (nome) { impostaCampo(moduloFiltri, nome, filtri[nome]); });
    nascosti(moduloFiltri, ordine);

    if (moduloFiltri && INTERVALLI.some(function (c) { return filtri[c + "_min"] || filtri[c + "_max"]; })) {
        var riquadro = moduloFiltri.querySelector("details.filtri-valori");
        if (riquadro) {
            riquadro.open = true;
        }
    }

    var coppieFiltri = Object.keys(filtri)
        .filter(function (nome) { return filtri[nome]; })
        .map(function (nome) { return [nome, filtri[nome]]; });
    nascosti(moduloVista, coppieFiltri);

    if (moduloVista) {
        var menuOrdine = moduloVista.querySelectorAll("select[name=sort]");
        var menuVerso = moduloVista.querySelectorAll("select[name=dir]");
        Array.prototype.forEach.call(menuOrdine, function (menu, i) {
            var criterio = criteri[i];
            menu.value = criterio ? criterio[0] : "";
            if (menuVerso[i]) {
                menuVerso[i].value = criterio ? criterio[1] : "asc";
            }
        });
    }

    // --- intestazioni: frecce dell'ordinamento richiesto --------------------------
    Array.prototype.forEach.call(tabella.querySelectorAll("thead a.sort-link"), function (link) {
        var campo = new URLSearchParams(link.search).get("sort");
        var posizione = -1;
        criteri.forEach(function (c, i) { if (c[0] === campo) { posizione = i; } });
        var cella = link.closest("th");
        var segno = link.querySelector("span:last-child");
        link.classList.toggle("sort-active", posizione !== -1);
        if (cella) {
            if (posizione === 0) {
                cella.setAttribute("aria-sort", criteri[0][1] === "asc" ? "ascending" : "descending");
            } else {
                cella.removeAttribute("aria-sort");
            }
        }
        if (!segno) {
            return;
        }
        segno.className = posizione === -1 ? "sort-idle" : "";
        segno.textContent = posizione === -1 ? "↕" : (criteri[posizione][1] === "asc" ? "▲" : "▼");
        if (posizione !== -1 && criteri.length > 1) {
            var numero = document.createElement("sup");
            numero.className = "sort-ordine";
            numero.textContent = String(posizione + 1);
            segno.appendChild(numero);
        }
    });

    // --- intestazioni: clic e Maiusc+clic con lo stato richiesto -----------------
    function vai(nuovi) {
        var parametri = new URLSearchParams();
        coppieFiltri.forEach(function (coppia) { parametri.set(coppia[0], coppia[1]); });
        parametri.set("sort", nuovi.map(function (c) { return c[0]; }).join(","));
        parametri.set("dir", nuovi.map(function (c) { return c[1]; }).join(","));
        window.location.search = parametri.toString();
    }

    tabella.addEventListener("click", function (evento) {
        var link = evento.target.closest("a.sort-link");
        if (!link) {
            return;
        }
        var campo = new URLSearchParams(link.search).get("sort");
        if (!campo || ORDINABILI.indexOf(campo) === -1) {
            return;
        }
        evento.preventDefault();
        evento.stopPropagation();
        var posizione = -1;
        criteri.forEach(function (c, i) { if (c[0] === campo) { posizione = i; } });
        var altri = criteri.filter(function (c) { return c[0] !== PERTINENZA; });
        if (evento.shiftKey) {
            if (posizione === -1) {
                altri = altri.slice(0, ORDINAMENTI_MAX - 1).concat([[campo, "asc"]]);
            } else {
                altri = altri.map(function (c) {
                    return c[0] === campo ? [campo, c[1] === "asc" ? "desc" : "asc"] : c;
                });
            }
            vai(altri);
        } else {
            vai([[campo, posizione === 0 && criteri[0][1] === "asc" ? "desc" : "asc"]]);
        }
    }, true);
})(this);
