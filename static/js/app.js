/* Food-stoplight — comportamento delle pagine
 * Tema chiaro/scuro, tooltip dei grafici, notifiche, conferme, calcolatore
 * della porzione, colonne e ordinamento della tabella, selezione per il
 * confronto e app installabile (service worker).
 * I testi arrivano tradotti dal blocco <script id="testi-js"> di base.html.
 */
var TESTI = (function () {
    "use strict";

    try {
        return JSON.parse(document.getElementById("testi-js").textContent);
    } catch (errore) {
        return {};
    }
})();

function testo(chiave, alternativa) {
    "use strict";
    return TESTI[chiave] || alternativa;
}

(function () {
    "use strict";

    var root = document.documentElement;

    // -----------------------------------------------------------------
    // Tema: segue il sistema operativo finché l'utente non sceglie;
    // la scelta resta in localStorage (applicata nel <head> da base.html).
    // -----------------------------------------------------------------
    var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

    function temaCorrente() {
        var t = root.getAttribute("data-theme");
        if (t === "light" || t === "dark") {
            return t;
        }
        return mq && mq.matches ? "dark" : "light";
    }

    function aggiornaPulsante() {
        var btn = document.getElementById("tema-toggle");
        if (!btn) {
            return;
        }
        var scuro = temaCorrente() === "dark";
        var etichetta = scuro
            ? testo("temaChiaro", "Passa alla modalità chiara")
            : testo("temaScuro", "Passa alla modalità scura");
        btn.querySelector(".tema-icona").textContent = scuro ? "☀️" : "🌙";
        btn.setAttribute("aria-label", etichetta);
        btn.setAttribute("title", etichetta);
        btn.setAttribute("aria-pressed", scuro ? "true" : "false");
    }

    document.addEventListener("click", function (evento) {
        var btn = evento.target.closest("#tema-toggle");
        if (!btn) {
            return;
        }
        var nuovo = temaCorrente() === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", nuovo);
        try {
            localStorage.setItem("tema", nuovo);
        } catch (errore) {
            /* storage non disponibile: il tema vale solo per questa pagina */
        }
        aggiornaPulsante();
    });

    if (mq && mq.addEventListener) {
        mq.addEventListener("change", aggiornaPulsante);
    }

    aggiornaPulsante();

    // -----------------------------------------------------------------
    // Tooltip: ogni elemento con data-tooltip (etichetta) e
    // data-tooltip-valore (valore) mostra un riquadro su hover e focus.
    // I valori sono sempre leggibili anche nella vista tabella.
    // -----------------------------------------------------------------
    var tip = document.createElement("div");
    tip.className = "grafico-tooltip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);

    var attivo = null;

    function mostra(el) {
        if (el === attivo) {
            return;
        }
        attivo = el;

        tip.textContent = "";

        var valore = document.createElement("strong");
        valore.textContent = el.getAttribute("data-tooltip-valore") || "";

        var etichetta = document.createElement("span");
        etichetta.className = "tooltip-etichetta";
        etichetta.textContent = el.getAttribute("data-tooltip") || "";

        var stato = el.getAttribute("data-tooltip-stato");
        if (stato) {
            etichetta.classList.add("stato-" + stato);
        }

        tip.appendChild(valore);
        tip.appendChild(etichetta);
        tip.hidden = false;
    }

    function posiziona(x, y) {
        var r = tip.getBoundingClientRect();
        var left = Math.min(window.innerWidth - r.width - 8, Math.max(8, x + 14));
        var top = y - r.height - 12;
        if (top < 8) {
            top = y + 18;
        }
        tip.style.left = left + "px";
        tip.style.top = top + "px";
    }

    function nascondi() {
        attivo = null;
        tip.hidden = true;
    }

    document.addEventListener("pointermove", function (evento) {
        var el = evento.target.closest ? evento.target.closest("[data-tooltip]") : null;
        if (!el) {
            if (attivo && document.activeElement !== attivo) {
                nascondi();
            }
            return;
        }
        mostra(el);
        posiziona(evento.clientX, evento.clientY);
    });

    document.addEventListener("focusin", function (evento) {
        var el = evento.target.closest ? evento.target.closest("[data-tooltip]") : null;
        if (!el) {
            return;
        }
        mostra(el);
        var r = el.getBoundingClientRect();
        posiziona(r.left + r.width / 2, r.top);
    });

    document.addEventListener("focusout", nascondi);
    window.addEventListener("scroll", nascondi, { passive: true });
    document.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape") {
            nascondi();
        }
    });
})();

// ---------------------------------------------------------------
// Notifiche (toast): i messaggi del server arrivano nella pagina come
// avvisi; qui diventano toast in un angolo. Conferme e informazioni
// si chiudono da sole dopo qualche secondo (non mentre il puntatore o
// il focus sono sopra), errori e avvisi restano finché non si chiudono.
// ---------------------------------------------------------------
var Notifiche = (function () {
    "use strict";

    var DURATA = 6000;
    var contenitore = document.getElementById("notifiche");

    if (!contenitore) {
        return { mostra: function () {} };
    }

    contenitore.classList.add("notifiche-toast");

    // Regioni live vuote all'avvio: i lettori di schermo annunciano i
    // messaggi quando vengono inseriti, non quelli già presenti
    var cortese = document.createElement("div");
    cortese.setAttribute("role", "status");
    cortese.setAttribute("aria-live", "polite");

    var urgente = document.createElement("div");
    urgente.setAttribute("role", "alert");

    contenitore.appendChild(cortese);
    contenitore.appendChild(urgente);

    function chiudi(notifica) {
        if (!notifica.isConnected || notifica.classList.contains("in-uscita")) {
            return;
        }
        notifica.classList.add("in-uscita");
        window.setTimeout(function () {
            notifica.remove();
        }, 200);
    }

    function attiva(notifica) {
        var tipo = notifica.getAttribute("data-tipo") || "info";
        var pulsante = notifica.querySelector(".notifica-chiudi");
        var timer = null;

        if (pulsante) {
            pulsante.hidden = false;
            pulsante.addEventListener("click", function () {
                chiudi(notifica);
            });
        }

        if (tipo === "success" || tipo === "info") {
            var avvia = function () {
                window.clearTimeout(timer);
                timer = window.setTimeout(function () {
                    chiudi(notifica);
                }, DURATA);
            };
            var ferma = function () {
                window.clearTimeout(timer);
            };

            notifica.addEventListener("pointerenter", ferma);
            notifica.addEventListener("pointerleave", avvia);
            notifica.addEventListener("focusin", ferma);
            notifica.addEventListener("focusout", avvia);
            avvia();
        }

        (tipo === "danger" || tipo === "warning" ? urgente : cortese).appendChild(notifica);
    }

    var iniziali = Array.prototype.slice.call(contenitore.querySelectorAll(":scope > .notifica"));

    // Un attimo dopo il caricamento, così le regioni live sono già registrate,
    // i messaggi del server si spostano nelle regioni (restando visibili)
    window.setTimeout(function () {
        iniziali.forEach(attiva);
    }, 150);

    function mostra(messaggio, tipo) {
        var modello = document.createElement("div");
        modello.className = "notifica notifica-" + tipo;
        modello.setAttribute("data-tipo", tipo);

        var icona = document.createElement("span");
        icona.className = "notifica-icona";
        icona.setAttribute("aria-hidden", "true");
        icona.textContent = tipo === "success" ? "✓" : (tipo === "info" ? "i" : "!");

        var corpo = document.createElement("p");
        corpo.className = "notifica-testo";
        corpo.textContent = messaggio;

        var pulsante = document.createElement("button");
        pulsante.type = "button";
        pulsante.className = "notifica-chiudi";
        pulsante.setAttribute("aria-label", testo("chiudiNotifica", "Chiudi la notifica"));
        pulsante.innerHTML = "<span aria-hidden=\"true\">×</span>";

        modello.appendChild(icona);
        modello.appendChild(corpo);
        modello.appendChild(pulsante);
        attiva(modello);
    }

    return { mostra: mostra };
})();

// ---------------------------------------------------------------
// Conferma con finestra modale prima di inviare i form (o i pulsanti)
// con data-conferma="messaggio"; facoltativi data-conferma-titolo e
// data-conferma-pulsante. Senza <dialog> si usa confirm().
// ---------------------------------------------------------------
(function () {
    "use strict";

    var dialogo = document.getElementById("dialogo-conferma");
    var supportato = dialogo && typeof dialogo.showModal === "function";

    function attributo(nome, submitter, form) {
        return (submitter && submitter.getAttribute(nome)) || form.getAttribute(nome) || "";
    }

    document.addEventListener("submit", function (evento) {
        var form = evento.target;
        var submitter = evento.submitter || null;
        var messaggio = attributo("data-conferma", submitter, form);

        if (!messaggio) {
            return;
        }

        if (form.getAttribute("data-confermato") === "1") {
            form.removeAttribute("data-confermato");
            return;
        }

        evento.preventDefault();

        if (!supportato) {
            if (window.confirm(messaggio)) {
                form.setAttribute("data-confermato", "1");
                if (form.requestSubmit) {
                    form.requestSubmit(submitter || undefined);
                } else {
                    form.submit();
                }
            }
            return;
        }

        var titolo = attributo("data-conferma-titolo", submitter, form) || testo("conferma", "Conferma");
        var pulsante = attributo("data-conferma-pulsante", submitter, form) || testo("conferma", "Conferma");

        document.getElementById("dialogo-titolo").textContent = titolo;
        document.getElementById("dialogo-testo").textContent = messaggio;
        document.getElementById("dialogo-conferma-pulsante").textContent = pulsante;

        dialogo.returnValue = "";
        dialogo.showModal();
        // Il focus parte da «Annulla»: Invio per sbaglio non elimina nulla
        document.getElementById("dialogo-annulla").focus();

        dialogo.addEventListener("close", function chiusura() {
            dialogo.removeEventListener("close", chiusura);

            if (dialogo.returnValue !== "conferma") {
                if (submitter) {
                    submitter.focus();
                }
                return;
            }

            form.setAttribute("data-confermato", "1");

            if (form.requestSubmit) {
                form.requestSubmit(submitter || undefined);
            } else {
                form.submit();
            }
        });
    });

    // Clic sullo sfondo: come Annulla
    if (supportato) {
        dialogo.addEventListener("click", function (evento) {
            if (evento.target === dialogo) {
                dialogo.close("annulla");
            }
        });
    }
})();

// ---------------------------------------------------------------
// Calcolatore della porzione nella scheda alimento: ricalcola i valori
// con data-per100 senza ricaricare la pagina (senza JS: pulsante Ricalcola)
// ---------------------------------------------------------------
(function () {
    "use strict";

    var campo = document.getElementById("porzione-grammi");

    if (!campo) {
        return;
    }

    var MIN = parseFloat(campo.min) || 1;
    var MAX = parseFloat(campo.max) || 2000;
    var LINGUA = document.documentElement.lang || "it";
    var LIVELLI = TESTI.livelli || { Basso: "Basso", Medio: "Medio", Alto: "Alto" };

    function formatta(valore, decimali) {
        return valore.toLocaleString(LINGUA, {
            maximumFractionDigits: decimali,
            useGrouping: false
        });
    }

    function livelloCarico(carico) {
        if (carico <= 10) {
            return ["good", LIVELLI.Basso];
        }
        return carico < 20 ? ["warning", LIVELLI.Medio] : ["critical", LIVELLI.Alto];
    }

    function aggiorna(grammi) {
        if (!(grammi >= MIN && grammi <= MAX)) {
            return;
        }

        var fattore = grammi / 100;

        document.querySelectorAll("[data-per100]").forEach(function (el) {
            var decimali = parseInt(el.getAttribute("data-decimali"), 10) || 0;
            el.textContent = formatta(parseFloat(el.getAttribute("data-per100")) * fattore, decimali);
        });

        document.querySelectorAll("[data-grammi-testo]").forEach(function (el) {
            el.textContent = formatta(grammi, 1);
        });

        document.querySelectorAll("[data-grammi-campo]").forEach(function (el) {
            el.value = grammi;
        });

        document.querySelectorAll("[data-cg100]").forEach(function (el) {
            var carico = Math.round(parseFloat(el.getAttribute("data-cg100")) * fattore * 10) / 10;
            var livello = livelloCarico(carico);
            el.className = "badge-risk stato-" + livello[0];
            el.querySelector("[data-cg-valore]").textContent = formatta(carico, 1);
            el.querySelector("[data-cg-livello]").textContent = livello[1];
        });

        document.querySelectorAll(".porzione-rapide [data-grammi]").forEach(function (el) {
            if (parseFloat(el.getAttribute("data-grammi")) === grammi) {
                el.setAttribute("aria-current", "true");
            } else {
                el.removeAttribute("aria-current");
            }
        });

        try {
            var url = new URL(window.location.href);
            url.searchParams.set("grammi", grammi);
            window.history.replaceState(null, "", url);

            // Dopo "Aggiungi al pasto" si torna alla scheda con la stessa porzione
            document.querySelectorAll("[data-ritorno]").forEach(function (el) {
                el.value = url.pathname + url.search;
            });
        } catch (e) {
            // URL non modificabile (es. anteprima): il ricalcolo resta valido
        }
    }

    campo.addEventListener("input", function () {
        aggiorna(parseFloat(String(campo.value).replace(",", ".")));
    });

    document.querySelectorAll(".porzione-rapide [data-grammi]").forEach(function (link) {
        link.addEventListener("click", function (evento) {
            evento.preventDefault();
            campo.value = link.getAttribute("data-grammi");
            aggiorna(parseFloat(campo.value));
        });
    });
})();

// ---------------------------------------------------------------
// Tabella da tablet in su: le colonne secondarie (TEF, fruttosio, fibre,
// rapporto F/F) sono nascoste; il pulsante le mostra tutte e la scelta
// resta memorizzata.
// ---------------------------------------------------------------
(function () {
    "use strict";

    var pulsante = document.getElementById("mostra-colonne");

    if (!pulsante) {
        return;
    }

    var root = document.documentElement;

    function aggiorna() {
        var tutte = root.classList.contains("tutte-colonne");
        pulsante.setAttribute("aria-pressed", tutte ? "true" : "false");
        pulsante.textContent = tutte
            ? testo("colonnePrincipali", "Solo le colonne principali")
            : testo("tutteLeColonne", "Mostra tutte le colonne");
    }

    pulsante.hidden = false;
    aggiorna();

    pulsante.addEventListener("click", function () {
        var tutte = root.classList.toggle("tutte-colonne");
        try {
            localStorage.setItem("tutte-colonne", tutte ? "1" : "0");
        } catch (errore) {
            /* la scelta vale solo per questa pagina */
        }
        aggiorna();
    });
})();

// ---------------------------------------------------------------
// Tabella: Maiusc+clic su un'intestazione aggiunge la colonna come
// criterio di ordinamento successivo (indirizzo in data-url-aggiungi).
// ---------------------------------------------------------------
document.addEventListener("click", function (evento) {
    "use strict";

    var link = evento.target.closest ? evento.target.closest("a[data-url-aggiungi]") : null;

    if (!link || !evento.shiftKey || evento.ctrlKey || evento.metaKey || evento.altKey) {
        return;
    }

    evento.preventDefault();
    window.location.href = link.getAttribute("data-url-aggiungi");
});

// ---------------------------------------------------------------
// Confronto: la selezione resta in sessionStorage anche cambiando pagina,
// filtri o ricerca; la barra in fondo mostra gli scelti e apre il
// confronto con tutti. Senza JavaScript il form invia le caselle della pagina.
// ---------------------------------------------------------------
(function () {
    "use strict";

    var form = document.getElementById("form-confronto");

    if (!form) {
        return;
    }

    var CHIAVE = "confronto";
    var massimo = parseInt(form.getAttribute("data-massimo"), 10) || 4;
    var stato = form.querySelector("[data-confronto-stato]");
    var elenco = form.querySelector("[data-confronto-scelti]");
    var annulla = form.querySelector("[data-confronto-annulla]");
    var invia = form.querySelector("button[type=submit]");
    var caselle = document.querySelectorAll(".seleziona-confronto");

    function leggi() {
        try {
            var dati = JSON.parse(sessionStorage.getItem(CHIAVE) || "[]");
            return Array.isArray(dati) ? dati.filter(function (voce) {
                return voce && /^\d+$/.test(String(voce.id));
            }) : [];
        } catch (errore) {
            return [];
        }
    }

    var scelti = leggi();

    function salva() {
        try {
            sessionStorage.setItem(CHIAVE, JSON.stringify(scelti));
        } catch (errore) {
            /* la selezione vale solo per questa pagina */
        }
    }

    function indice(id) {
        for (var i = 0; i < scelti.length; i++) {
            if (String(scelti[i].id) === String(id)) {
                return i;
            }
        }
        return -1;
    }

    function aggiorna() {
        var n = scelti.length;

        form.classList.toggle("attiva", n > 0);
        invia.disabled = n < 2;
        annulla.hidden = n === 0;
        elenco.hidden = n === 0;
        stato.textContent = n < 2
            ? testo("confrontoPochi", "Seleziona almeno un altro alimento.")
            : testo("confrontoPronti", "Pronti per il confronto.");

        elenco.textContent = "";
        scelti.forEach(function (voce) {
            var li = document.createElement("li");
            var togli = document.createElement("button");
            togli.type = "button";
            togli.className = "filtro-attivo";
            togli.textContent = voce.nome + " ✕";
            togli.setAttribute("aria-label", testo("confrontoTogli", "Togli dal confronto:") + " " + voce.nome);
            togli.addEventListener("click", function () {
                scelti.splice(indice(voce.id), 1);
                salva();
                sincronizza();
            });
            li.appendChild(togli);
            elenco.appendChild(li);
        });
    }

    function sincronizza() {
        caselle.forEach(function (casella) {
            casella.checked = indice(casella.value) !== -1;
        });
        aggiorna();
    }

    caselle.forEach(function (casella) {
        casella.addEventListener("change", function () {
            var posizione = indice(casella.value);

            if (casella.checked && posizione === -1) {
                if (scelti.length >= massimo) {
                    casella.checked = false;
                    Notifiche.mostra(testo("confrontoMassimo", "Puoi confrontare al massimo " + massimo + " alimenti."), "warning");
                    return;
                }
                var link = casella.closest("tr") && casella.closest("tr").querySelector(".nome-alimento");
                scelti.push({ id: casella.value, nome: link ? link.textContent.trim() : casella.value });
            } else if (!casella.checked && posizione !== -1) {
                scelti.splice(posizione, 1);
            }

            salva();
            aggiorna();
        });
    });

    annulla.addEventListener("click", function () {
        scelti = [];
        salva();
        sincronizza();
    });

    form.addEventListener("submit", function (evento) {
        evento.preventDefault();

        if (scelti.length < 2) {
            return;
        }

        var parametri = scelti.map(function (voce) {
            return "id=" + encodeURIComponent(voce.id);
        }).join("&");

        scelti = [];
        salva();
        window.location.href = form.action + "?" + parametri;
    });

    sincronizza();
})();

// ---------------------------------------------------------------
// App installabile: registrazione del service worker, pagine salvate
// cancellate all'uscita dall'account, avvisi di connessione persa e
// ritrovata, elenco delle schede salvate nella pagina offline.
// ---------------------------------------------------------------
(function () {
    "use strict";

    var corpo = document.body;
    var supportato = "serviceWorker" in navigator && window.isSecureContext;

    if (supportato && corpo.getAttribute("data-sw")) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register(corpo.getAttribute("data-sw")).catch(function () {
                /* senza service worker l'app funziona lo stesso, solo online */
            });
        });

        if (corpo.hasAttribute("data-svuota-cache")) {
            navigator.serviceWorker.ready.then(function (registrazione) {
                if (registrazione.active) {
                    registrazione.active.postMessage("svuota-pagine");
                }
            });
        }
    }

    window.addEventListener("offline", function () {
        Notifiche.mostra(testo("offline", "Sei offline: le pagine già aperte restano consultabili."), "warning");
    });

    window.addEventListener("online", function () {
        Notifiche.mostra(testo("online", "Di nuovo online."), "success");
    });

    var pagina = document.querySelector("[data-cache-pagine]");
    var elenco = document.getElementById("schede-salvate");

    if (!pagina || !elenco || !window.caches) {
        return;
    }

    var vuoto = document.getElementById("schede-salvate-vuoto");

    caches.open(pagina.getAttribute("data-cache-pagine"))
        .then(function (cache) {
            return cache.keys().then(function (richieste) {
                var schede = richieste.filter(function (richiesta) {
                    return /\/alimento\/\d+$/.test(new URL(richiesta.url).pathname);
                });

                return Promise.all(schede.map(function (richiesta) {
                    return cache.match(richiesta)
                        .then(function (risposta) { return risposta.text(); })
                        .then(function (html) {
                            var documento = new DOMParser().parseFromString(html, "text/html");
                            var titolo = documento.querySelector("h1");
                            return { url: richiesta.url, nome: titolo ? titolo.textContent.trim() : richiesta.url };
                        });
                }));
            });
        })
        .then(function (schede) {
            if (!schede.length) {
                return;
            }

            schede.sort(function (a, b) {
                return a.nome.localeCompare(b.nome, document.documentElement.lang || "it");
            });

            schede.forEach(function (scheda) {
                var voce = document.createElement("li");
                var link = document.createElement("a");
                link.href = scheda.url;
                link.textContent = scheda.nome;
                voce.appendChild(link);
                elenco.appendChild(voce);
            });

            elenco.hidden = false;
            vuoto.hidden = true;
        })
        .catch(function () {
            /* cache non leggibile: resta il messaggio "nessuna scheda" */
        });
})();
