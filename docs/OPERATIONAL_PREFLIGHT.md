# Percorso operativo di aggiornamento

1. Il workflow GitHub Actions [`daily-funding-sync.yml`](../.github/workflows/daily-funding-sync.yml) parte una volta al giorno alle 04:00 UTC (circa 05:00 in inverno / 06:00 in estate in Europe/Rome) e supporta `workflow_dispatch`.
2. `python -m funding_core.cli daily-sync` usa lo stesso percorso di `populate-snapshot`: fetch, parse/normalize, fallback per fonte, deduplica, classificazione, current/archive e source-health.
3. Il comando valida entrambi gli envelope JSON e applica la guardia globale last-known-good prima di sostituire gli asset pubblicati.
4. Gli snapshot current/archive, l'alias di compatibilità e `reports/daily-sync-latest.json` vengono committati sul branch `github-ready`; il job termina con successo quando sync, validazione e pubblicazione GitHub sono riuscite.
5. Il Site non viene ridistribuito dalla daily sync: all'apertura usa il base URL GitHub Raw configurato in `app/data-config.ts`, con `daily-sync-latest.json` come health/freshness e query `version=<generatedAt>` per evitare cache vecchie.
6. Se il remoto non risponde o il JSON non supera la guardia minima, il frontend usa i file bundled `public/data/*.json`; l'archivio resta lazy-loaded.
7. Il deploy Sites del codice resta manuale e richiede il percorso nativo documentato dal skill Sites; dopo un deploy del codice, gli aggiornamenti giornalieri dei JSON non richiedono ulteriori deploy.

Esecuzione manuale locale: `python -m funding_core.cli populate-snapshot` (oppure `python -m funding_core.cli daily-sync`). Lo stato dell'ultima esecuzione è in [`reports/daily-sync-latest.json`](../reports/daily-sync-latest.json); la sezione `sourceHealth` è presente in entrambi gli snapshot.
