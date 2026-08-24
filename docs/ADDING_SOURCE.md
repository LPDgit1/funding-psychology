# Aggiungere una fonte

1. Crea un adapter piccolo con `fetch` e `parse`.
2. Salva una fixture locale minima e rappresentativa.
3. Testa parsing, campi mancanti, date e idempotenza.
4. Registra la fonte in `docs/SOURCES.md` come `FIXTURE VERIFIED`.
5. Esegui una validazione live manuale con timeout e limite dimensione.
6. Abilita la fonte e dichiarala `COMPLETE` solo dopo una seconda sincronizzazione senza duplicati.

Se il run corrente è anomalo, conserva i dati precedenti e registra un warning. Non inventare valori mancanti.
