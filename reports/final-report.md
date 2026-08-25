# Funding Intelligence for Psychology v0.2.1 — report finale

## PRE-FLIGHT

Repository e snapshot rigenerati; il report usa i dati del sync corrente e non conteggi statici nella documentazione.

## P0 FIXES

- Funding & Tenders: deadline multiple, paginazione e precedenza dello stato ufficiale.
- HTML: contenuto principale selezionato prima della classificazione, con esclusione del chrome di navigazione.
- Ricerca: sinonimi per concetto, OR interno e AND tra concetti; macroaree escluse dal testo.

## FUNDING & TENDERS RESULT

L'adapter conserva OPEN/UPCOMING ufficiali anche quando una deadline storica è presente; i test A/B/C sono nel suite Python.

## HTML CLEANUP RESULT

Fixture di dettaglio verificano titolo e contenuto reale senza menu, header, aside o footer.

## SEARCH FIXES

Il report `search-quality.md` è calcolato con la stessa semantica del frontend.

## AIG FILTER RESULT

Eventi, consultazioni, corsi, focus group e call for participants prive di finanziamento progettuale sono esclusi; avvisi e project/grant call restano eleggibili.

## REGIONE VENETO RESULT

L'elenco ufficiale JSON viene paginato senza il limite delle dieci card della homepage.

## DETAIL PARSER IMPROVEMENTS

Le date sono cercate vicino a etichette di scadenza/termine/deadline e restano nulle quando il contesto è ambiguo.

## FILTER FIXES

Categorie applicant multilabel e regioni multi-regione sono testate; ETS e Veneto non dipendono da una singola etichetta.

## UX BUG FIXES

La vista `current|archive` è separata dalla cache dell'archivio e il linguaggio residuo di prototipo è stato rimosso dall'interfaccia.

## DATASET BEFORE / AFTER

- After (sync corrente): **1949** record operativi, **5805** archiviati.
- Before: il baseline v0.2 è conservato nella storia Git; il generatore non inserisce un conteggio statico nella documentazione.

## PRECISION AUDIT

sample size: **28** risultati Alta/Media in ordine home (massimo 50).

result: **NON VERIFICATO** — il CSV è pronto per la revisione manuale titolo per titolo; nessun valore viene auto-promosso a precision pass.

Failure pattern da controllare: misure amministrative su inclusione/disabilità, giovani o formazione che non finanziano un intervento psicologico diretto.

## RECALL AUDIT

sample size: **25** opportunità selezionate dalle macroaree note.

result: **NON VERIFICATO** — discoverability meccanica query 5/25 e macroarea 25/25; manca la conferma manuale richiesta dal gate.

Failure pattern da controllare: termini pertinenti presenti solo nel dettaglio ufficiale o espressi con una combinazione linguistica diversa dalla query naturale.

## SEARCH QUALITY

Vedi `search-quality.md` per conteggi e primi cinque titoli delle dieci query obbligatorie.

## TESTS

Vedi la suite Python e TypeScript; i comandi di verifica sono nel README.

## KNOWN LIMITATIONS

Deadline assenti quando la fonte non identifica il contesto; due calendari Veneto restano fixture-only; la classificazione è euristica e non decide l'ammissibilità.

## DEFERRED

Nessuna nuova fonte o feature: FAMI, Pari Opportunità e Dipendenze restano fuori scope.

## STOPPING RULE STATUS

**NOT PASSED** — i gate tecnici A–G e i test sono predisposti, ma precisione e recall non sono dichiarabili superati senza revisione manuale verificata.
