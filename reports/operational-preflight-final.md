# Operational preflight — report finale

## PRE-FLIGHT FIXES

CRT: **PASS** — le parser conserva la precedenza dei badge ufficiali: `Risultati` → CLOSED, `In arrivo` → UPCOMING, `In corso` con finestra futura → OPEN; le regression case CRT restano coperte dai test.

MLPS: **PASS** — l'adapter usa i due entry point ufficiali per il Fondo assistenza bambini oncologici e il Fondo ex artt. 72–73 CTS; FAQ, commissioni, graduatorie, beneficiari e rendicontazione restano associati alla call originaria.

AICS: **PASS** — decodifica UTF-8 corretta e regression test per `Organizzazioni della Società Civile` e `Università pubbliche`; non compaiono caratteri corrotti.

## DAILY AUTOMATION

- scheduler: GitHub Actions, workflow `.github/workflows/daily-funding-sync.yml`
- schedule: `0 4 * * *` UTC, circa 05:00 CET / 06:00 CEST in Europe/Rome
- timezone: Europe/Rome (variazione stagionale documentata; la precisione al minuto non è requisito)
- sync command: `python -m funding_core.cli daily-sync`, stesso percorso di `populate-snapshot`
- sequence: fetch → parse/normalize → fallback per fonte → dedup/classification → current/archive → source-health → validate/anomaly guard → build
- deployment mechanism: commit degli asset sul branch `github-ready` e POST opzionale a `SITES_DEPLOY_HOOK_URL`
- manual trigger: `workflow_dispatch`; localmente `python -m funding_core.cli populate-snapshot`

Il percorso concreto build/publish è descritto in `docs/OPERATIONAL_PREFLIGHT.md`.

## SOURCE HEALTH

- registered / monitored: **42**
- live configured / attempted: **40**
- LIVE: **37**
- STALE: **2** — `incentivi-gov` (timeout di lettura, record precedenti preservati), `european_youth_foundation` (HTTP 403, record precedenti preservati)
- ERROR: **1** — `dipendenze` (HTTP 503, nessun record precedente riutilizzabile)
- fixture-only: **2** — `veneto-fse-calendar`, `veneto-fesr-calendar`

Il risultato supera la guardia globale: **PASS**, nessun collasso del current e nessuna maggioranza di fonti live indisponibile. Current: **2.081**; archive: **6.212**.

## FRESHNESS

- generatedAt della sync finale: **2026-09-01T21:05:06.979323Z** (mostrato in Europe/Rome come 1 settembre alle 23:05)
- UI: data/ora e riepilogo fonti derivano dal JSON corrente; nessun contatore o data hardcoded
- soglie: nessun avviso fino a 36 ore; avviso discreto oltre 36 ore; avviso evidente oltre 72 ore, senza bloccare la consultazione

## DEPLOYMENT VERIFICATION

- snapshot generated: **PASS** — current/archive e `reports/daily-sync-latest.json` scritti atomically
- snapshot validation: **PASS** — `validate-snapshot` ha verificato envelope, URL HTTPS, ID univoci, source-health e separazione current/archive
- build: **PASS** — `dist/server/index.js` e `dist/.openai/hosting.json` presenti dopo `vinext build`
- deploy triggered: **NOT CONFIGURED** — il workflow può chiamare `SITES_DEPLOY_HOOK_URL`, ma il secret non è configurato; in questo run non è stato invocato il deploy Sites nativo e la job schedulata sarebbe marcata fallita, senza mascherare la sync dati riuscita
- deploy verified: **NOT VERIFIED** — il sito pubblico resta alla versione Sites osservata 13 (commit sorgente `05872e9a…`); non viene dichiarato aggiornato sulla sola base della generazione locale

## TESTS

- targeted: **PASS** — 6 test Python operational/preflight e 3 test frontend metadati/freschezza; regression CRT/MLPS/AICS incluse nella suite
- full Python: **PASS** — 99 test
- frontend: **PASS** — 12 test Node/Vinext
- build: **PASS** — production `vinext build`
- full sync: **PASS** — 40 fonti live tentate; report latest aggiornato

## KNOWN LIMITATIONS

- Due fonti live sono temporaneamente STALE e una ERROR per risposte upstream; il fallback per fonte conserva i dati validi senza bloccare le altre.
- Il progetto Sites corrente non espone una credenziale repository/hook CI (`source_repository_credential: null`); per completare la pubblicazione pubblica automatica occorre configurare `SITES_DEPLOY_HOOK_URL` oppure eseguire il percorso nativo Sites sul commit esatto.
- Il cron GitHub diventa attivo dopo il commit/push del workflow sul repository; il working tree locale è pronto per la revisione in GitHub Desktop.
- La sync finale ha richiesto circa 28 minuti per i timeout/retry e gli enrichment bounded già presenti; non sono stati aumentati timeout o retry.

## STOPPING RULE

**NOT PASSED** — sync schedulata, validazione, snapshot, metadati dinamici, freshness, fallback, guardia anti-collasso, fix CRT/MLPS/AICS, suite completa e build sono operative. Resta intenzionalmente non verificato il passaggio finale `publish/deploy` sul sito pubblico finché non viene configurato il deploy hook o autorizzato/eseguito il salvataggio e deploy nativo Sites.
