# Funding Intelligence for Psychology v0.2.2a — report finale

## CHANGES

Correzioni locali ai falsi positivi osservati nei risultati Alta/Media; Tema user-facing reso single-select; pannello Filtri realmente apribile/chiudibile; aggiornamento reso secondario; Scaduti accessibili dal solo filtro Stato. Nessuna nuova fonte o architettura.

## PRECISION AUDIT

Tutti i record Alta/Media correnti sono stati revisionati: **17 Relevant, 6 Borderline, 0 Not relevant**. Precisione ponderata: **87.0%** (PASS; Relevant=1, Borderline=0.5, Not relevant=0).

I 28 record iniziali Alta/Media sono stati revisionati tutti: **17 Relevant, 6 Borderline, 5 Not relevant**. I cinque falsi positivi ricorrenti riguardavano housing sociale, incentivi occupazionali generici, tutoraggio amministrativo e upskilling digitale; dopo la correzione locale restano 23 record Alta/Media.

## DISCOVERABILITY

Default UI (solo OPEN/UPCOMING e rilevanza Alta/Media): **12/15 = 80.0%**. Dopo cambio esplicito di stato/filtro: **15/15**.

## UX

Le Aree di interesse restano shortcut in home; il filtro mostra un solo selettore Tema, insieme a Territorio, Scadenza, Chi può partecipare e Altri filtri. Lo stato normale non ha una riga autonoma di aggiornamento; Scaduti è una sola scelta nel filtro Stato e usa il lazy load esistente.

## FUNDING & TENDERS

STALE / UNVERIFIED: la validazione live dell'adapter continua a restituire HTTP 404 in modo riproducibile su pagine successive, mentre l'endpoint e il contratto multipart risultano ancora quelli documentati ufficialmente. Nessuna modifica speculativa applicata; i 1.049 record precedenti restano conservati.

## GOLD SET

Campione manuale: **30** record (15 positivi, 15 hard negative). Correttezza tipo **100.0%**, tema **90.0%**; gate gold set: **PASS** (tutte le soglie sono rispettate).

## TESTS

Targeted: classifier guard, discoverability default-status, Tema single-select, Filtri show/hide, update status e Scaduti. Full suite: **35 test Python e 9 test JavaScript**, eseguita una volta dopo le modifiche; smoke UX: ricerca diretta, Tema, Tema+Veneto, Scaduti.

## KNOWN LIMITATION

Il feed corrente contiene **1935** record e l'elenco scaduti **5807**. Funding & Tenders resta stale/unverified finché il 404 dell'API non viene chiarito dal gestore del servizio.

## STOPPING RULE

**PASSED** — precisione manuale e discoverability default hanno raggiunto le soglie; nessun ampliamento dello scope.
