/* Food-stoplight — tema chiaro/scuro e tooltip dei grafici */
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
        var etichetta = scuro ? "Passa alla modalità chiara" : "Passa alla modalità scura";
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
// Conferma prima di inviare i form con data-conferma="messaggio"
// (es. ripristino di un backup dall'elenco)
// ---------------------------------------------------------------
(function () {
    "use strict";

    document.addEventListener("submit", function (evento) {
        var form = evento.target;
        var messaggio = form.getAttribute && form.getAttribute("data-conferma");

        if (messaggio && !window.confirm(messaggio)) {
            evento.preventDefault();
        }
    });
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

    function formatta(valore, decimali) {
        return valore.toLocaleString("it-IT", {
            maximumFractionDigits: decimali,
            useGrouping: false
        });
    }

    function livelloCarico(carico) {
        if (carico <= 10) {
            return ["good", "Basso"];
        }
        return carico < 20 ? ["warning", "Medio"] : ["critical", "Alto"];
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
