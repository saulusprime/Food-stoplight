/* Food-stoplight — service worker (generato da pwa.py, versione {{ versione }})
 *
 * - File statici: dalla cache, scaricati all'installazione. La versione
 *   cambia quando cambia un file, e le copie vecchie vengono scartate.
 * - Tabella, guida, schede degli alimenti e lista della spesa: dalla rete;
 *   senza connessione l'ultima copia salvata. Le altre pagine senza rete
 *   mostrano la pagina offline.
 * - La tabella è divisa in pagine: la copia offline è quella con tutte le
 *   righe (TABELLA_COMPLETA), salvata come pagina iniziale e riscaricata
 *   in background, al massimo una volta all'ora, quando si apre la tabella.
 */
"use strict";

const VERSIONE = {{ versione|tojson }};
const PREFISSO = "food-stoplight-statici-";
const CACHE_STATICI = PREFISSO + VERSIONE;
const CACHE_PAGINE = {{ cache_pagine|tojson }};
const STATICI = {{ statici|tojson }};
const PREFISSO_STATICI = {{ prefisso_statici|tojson }};
const BASE = {{ base|tojson }};
// [indirizzo da scaricare, chiave con cui salvarlo]
const PAGINE = {{ pagine|tojson }};
const TABELLA_COMPLETA = {{ tabella_completa|tojson }};
const AGGIORNA_TABELLA_MS = 60 * 60 * 1000;
const OFFLINE = {{ offline|tojson }};
const INTESTAZIONE = {{ intestazione|tojson }};

// Percorsi (relativi a BASE) delle pagine di consultazione
const CONSULTABILI = [/^$/, /^guida$/, /^alimento\/\d+$/, /^spesa$/];

function relativo(url) {
    return url.pathname.startsWith(BASE) ? url.pathname.slice(BASE.length) : null;
}

function consultabile(url) {
    const percorso = relativo(url);
    return percorso !== null && CONSULTABILI.some((regola) => regola.test(percorso));
}

// Chiave della copia salvata: la tabella solo nella versione completa (tutte
// le righe, senza filtri), salvata come pagina iniziale; le schede senza
// parametri (es. ?grammi=150)
function chiave(url) {
    if (relativo(url) === "") {
        const completa = new URL(TABELLA_COMPLETA, self.location.href);
        return url.search === completa.search ? url.origin + url.pathname : null;
    }
    return url.origin + url.pathname;
}

// Salva una pagina in anticipo; l'intestazione evita che consumi i messaggi
function precarica(cache, url, chiaveCopia) {
    const richiesta = new Request(url, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { [INTESTAZIONE]: "1" }
    });
    return fetch(richiesta).then((risposta) => {
        if (!risposta.ok || risposta.redirected) {
            throw new Error("Pagina non salvata: " + url);
        }
        return cache.put(new URL(chiaveCopia || url, self.location.href).href, risposta);
    });
}

function precaricaPagine() {
    return caches.open(CACHE_PAGINE).then((cache) => Promise.all([
        precarica(cache, OFFLINE),
        ...PAGINE.map(([url, chiaveCopia]) => precarica(cache, url, chiaveCopia).catch(() => undefined))
    ]));
}

// Riscarica la tabella completa se la copia salvata ha più di un'ora (o manca)
async function aggiornaTabella() {
    const cache = await caches.open(CACHE_PAGINE);
    const salvata = await cache.match(new URL(BASE, self.location.href).href);
    const data = salvata ? Date.parse(salvata.headers.get("date") || "") : NaN;

    if (!Number.isNaN(data) && Date.now() - data < AGGIORNA_TABELLA_MS) {
        return;
    }
    await precarica(cache, TABELLA_COMPLETA, BASE).catch(() => undefined);
}

self.addEventListener("install", (evento) => {
    evento.waitUntil(
        caches.open(CACHE_STATICI)
            .then((cache) => cache.addAll(STATICI.map((url) => new Request(url, { cache: "reload" }))))
            .then(precaricaPagine)
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (evento) => {
    evento.waitUntil(
        caches.keys()
            .then((nomi) => Promise.all(
                nomi
                    .filter((nome) => nome.startsWith(PREFISSO) && nome !== CACHE_STATICI)
                    .map((nome) => caches.delete(nome))
            ))
            .then(() => self.clients.claim())
    );
});

// Dopo l'uscita dall'account la pagina chiede di cancellare le copie salvate
self.addEventListener("message", (evento) => {
    if (evento.data === "svuota-pagine") {
        evento.waitUntil(caches.delete(CACHE_PAGINE).then(precaricaPagine).catch(() => undefined));
    }
});

async function statico(richiesta) {
    const cache = await caches.open(CACHE_STATICI);
    const salvata = await cache.match(richiesta, { ignoreSearch: true });

    if (salvata) {
        return salvata;
    }

    const risposta = await fetch(richiesta);

    if (risposta.ok) {
        cache.put(richiesta, risposta.clone());
    }
    return risposta;
}

async function navigazione(evento, url) {
    const salvabile = consultabile(url);

    try {
        const risposta = await fetch(evento.request);
        const chiaveCopia = salvabile ? chiave(url) : null;

        if (chiaveCopia && risposta.ok && !risposta.redirected) {
            const copia = risposta.clone();
            evento.waitUntil(caches.open(CACHE_PAGINE).then((cache) => cache.put(chiaveCopia, copia)));
        } else if (relativo(url) === "" && risposta.ok) {
            evento.waitUntil(aggiornaTabella().catch(() => undefined));
        }
        return risposta;
    } catch (errore) {
        const cache = await caches.open(CACHE_PAGINE);

        if (salvabile) {
            const salvata = await cache.match(url.origin + url.pathname);

            if (salvata) {
                return salvata;
            }
        }
        return (await cache.match(new URL(OFFLINE, self.location.href).href)) || Response.error();
    }
}

self.addEventListener("fetch", (evento) => {
    const richiesta = evento.request;

    if (richiesta.method !== "GET") {
        return;
    }

    const url = new URL(richiesta.url);

    if (url.origin !== self.location.origin) {
        return;
    }

    if (url.pathname.startsWith(PREFISSO_STATICI)) {
        evento.respondWith(statico(richiesta));
    } else if (richiesta.mode === "navigate") {
        evento.respondWith(navigazione(evento, url));
    }
});
