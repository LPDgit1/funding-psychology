# Funding Intelligence for Psychology v0.2.2 — report finale

## CHANGES MADE

Consolidamento mirato: filtro del tipo di opportunità nei feed HTML/AIG, pulizia di tre stringhe di navigazione, correzione della tutela contestuale, ricerca inversa dei sinonimi e otto temi user-facing. Nessuna nuova fonte o architettura.

## OPPORTUNITY-TYPE FILTERING

Decreti di nomina/commissione, graduatorie, riparti, accordi di collaborazione e contenuti editoriali sono esclusi quando non presentano un avviso o un finanziamento progettuale. Gli avvisi e le call con segnali di candidatura restano eleggibili.

## SEMANTIC FIXES

La parola inglese `protection` da sola non attiva la violenza; contano solo formule contestuali come child protection from violence, victim protection o protection against abuse.

## SEARCH

Ogni termine di un gruppo sinonimico attiva lo stesso gruppo: giovani/adolescenti/youth/young people e AI/artificial intelligence sono verificati in entrambe le direzioni.

## UX

La UI mostra Aree di interesse, Tema, Territorio, Scadenza e Chi può partecipare; i filtri secondari sono raccolti sotto Altri filtri. I bandi scaduti sono consultabili con un'azione esplicita e senza esporre il lessico tecnico del dataset.

## GOLD SET

Campione manuale: **30** record (15 positivi, 15 hard negative). Precisione Alta/Media: **100.0%** (15 TP, 0 FP, 0 FN). Discoverability: **100.0%** (15/15); correttezza tipo **100.0%**, tema **100.0%**.

Esito gate gold set: **PASS** — tutte le soglie sono rispettate. Se non superato, la correzione minima è intervenire solo sui casi elencati in `reports/known-relevant-opportunities.json`, senza ampliare la raccolta.

## TESTS

La suite Python e TypeScript è eseguita dopo le modifiche; il test HTML controlla l'assenza del vocabolario tecnico e i test mirati coprono tipo opportunità, tutela contestuale, sinonimi inversi e mapping dei temi.

## KNOWN LIMITATIONS

Il feed corrente contiene **1935** record e l'elenco scaduti **5807**; una fonte può restare stale se il trasporto ufficiale è temporaneamente indisponibile. La classificazione è euristica e non decide l'ammissibilità.

## STOPPING RULE

**PASSED** — arresto dopo test, gold set e smoke test richiesti; nessuna nuova feature viene introdotta.
