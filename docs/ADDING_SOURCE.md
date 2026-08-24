# Aggiungere una fonte

1. Crea un adapter piccolo con `fetch` e `parse`; usa solo HTTPS, timeout, retry e limite di byte.
2. Normalizza, quando disponibili, `external_id`, titolo, URL ufficiale, status, apertura, deadline, budget, destinatari e territorio.
3. Per una lista HTML, mantieni il link di dettaglio e aggiungi solo un enrichment best-effort bounded; un errore del dettaglio non deve cancellare la scheda della lista.
4. Salva una fixture locale minima e rappresentativa.
5. Testa parsing, campi mancanti, date, idempotenza e filtro di eventuali news/eventi non finanziabili.
6. Registra la fonte in `docs/SOURCES.md` come `FIXTURE VERIFIED` finché il contratto live non è verificato.
7. Esegui `validate-source` e una validazione live manuale con timeout e limite dimensione.
8. Abilita la fonte nello snapshot e dichiarala `LIVE` solo dopo una seconda sincronizzazione senza duplicati.

Se il run corrente è anomalo, conserva i dati precedenti e registra un warning (`STALE`/`ERROR`). Non inventare valori mancanti: usa `NULL`, `UNKNOWN` o `Da verificare`.
