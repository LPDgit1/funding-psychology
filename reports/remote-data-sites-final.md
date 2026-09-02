# Remote data delivery to Sites — report finale

## DAILY ACTION

- sync: **PASS** — GitHub Actions run #2 (`workflow_dispatch`) ha completato `daily-sync` e `validate-snapshot`.
- publication: **PASS** — gli snapshot e `reports/daily-sync-latest.json` sono stati pubblicati sul branch `github-ready` nel commit `ad7f55cc6fe292d7d657d64f55daa3da89de3adf`.
- Sites deploy hook removed: **PASS** — `SITES_DEPLOY_HOOK_URL` e lo step di hook non sono più requisiti né passaggi del workflow.
- workflow result: **SUCCESS** — [run #2](https://github.com/LPDgit1/funding-psychology/actions/runs/33679122911), conclusa il 2 settembre 2026.

## REMOTE DATA ENDPOINT

- method: file JSON pubblico GitHub Raw, sole richieste GET; GitHub Pages è stato provato ma l’endpoint restituisce HTTP 404 e non viene usato.
- base URL: `https://raw.githubusercontent.com/LPDgit1/funding-psychology/github-ready`
- current URL: `https://raw.githubusercontent.com/LPDgit1/funding-psychology/github-ready/public/data/opportunities-current.json`
- archive URL: `https://raw.githubusercontent.com/LPDgit1/funding-psychology/github-ready/public/data/opportunities-archive.json`
- health URL: `https://raw.githubusercontent.com/LPDgit1/funding-psychology/github-ready/reports/daily-sync-latest.json`
- browser fetch verified: **PASS** — il Site pubblico v15 ha caricato dal remoto `generatedAt=2026-09-02T20:25:02.375015Z` (visualizzato come 2 settembre alle 22:25 in Europe/Rome), 2.250 record current, riepilogo 42 fonti / 35 aggiornate / 5 temporaneamente non disponibili / 2 non ancora automatizzate; l’archivio lazy ha restituito 6.209 record. Gli endpoint GET hanno risposto HTTP 200 con JSON valido e `Access-Control-Allow-Origin: *`.

## FRONTEND

- remote-first: **PASS** — health remoto, poi snapshot current remoto.
- bundled fallback: **PASS** — i JSON bundled restano nel build e vengono usati se il remoto è irraggiungibile, malformato o vuoto.
- archive lazy: **PASS** — `opportunities-archive.json` viene richiesto solo aprendo “Scaduti”, con fallback bundled.
- freshness: **PASS** — data/ora deriva dal `generatedAt` dello snapshot effettivamente caricato; viene usato `fetch(..., { cache: "no-store" })` e il parametro `version=<generatedAt>`.
- source counts: **PASS** — il riepilogo UI proviene dallo stesso snapshot remoto attivo; `sourceHealth` riporta 42 totali, 40 live configurate, 35 riuscite, 4 stale, 1 error e 2 fixture-only.

## TESTS

- targeted: **PASS** — 5 test mirati per remote success, fallback HTTP, JSON invalido/vuoto, archive remote-first/lazy e version query.
- full Python: **PASS** — 99 test.
- frontend: **PASS** — 17 test Node/Vinext.
- build: **PASS** — `vinext build`; presenti `dist/server/index.js` e `dist/.openai/hosting.json`.

## MANUAL SITE UPDATE REQUIRED

**YES**

Instructions: deploy this code version once in ChatGPT Sites. **Eseguito**: versione Sites 15, commit sorgente `6507267677a1a60f0d6429be274f2bdce23ca132`, deploy pubblico riuscito; gli aggiornamenti giornalieri dei JSON non richiedono altri deploy.

## KNOWN LIMITATIONS

- GitHub Pages non è immediatamente utilizzabile per questo repository (404); Raw GitHub è il solo endpoint configurato.
- La CDN Raw espone `max-age=300`: il parametro versione e `no-store` evitano cache prolungate, ma una propagazione può richiedere alcuni minuti.
- Nell’ultima sync 4 fonti live sono `STALE`, 1 è `ERROR` e 2 sono fixture-only; il pipeline conserva i dati precedenti validi e lo segnala senza bloccare il current.
- La validazione browser è volutamente minima (struttura JSON e record utilizzabili); classificazione, deduplica e source health restano responsabilità della pipeline Python.

## STOPPING RULE

**PASSED** — daily workflow SUCCESS senza hook, pubblicazione JSON pubblica stabile, fetch runtime verificato dal Site, percorso `remote → bundled fallback`, metadati coerenti, archivio lazy, test/build verdi e un solo deploy manuale del codice completato.
