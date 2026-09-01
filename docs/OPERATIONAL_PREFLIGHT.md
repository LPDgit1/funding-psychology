# Percorso operativo di aggiornamento

1. Il workflow GitHub Actions [`daily-funding-sync.yml`](../.github/workflows/daily-funding-sync.yml) parte una volta al giorno alle 04:00 UTC (circa 05:00 in inverno / 06:00 in estate in Europe/Rome) e supporta `workflow_dispatch`.
2. `python -m funding_core.cli daily-sync` usa lo stesso percorso di `populate-snapshot`: fetch, parse/normalize, fallback per fonte, deduplica, classificazione, current/archive e source-health.
3. Il comando valida entrambi gli envelope JSON e applica la guardia globale last-known-good prima di sostituire gli asset pubblici.
4. Il workflow esegue `python -m funding_core.cli validate-snapshot` e `npm run build`, verificando `dist/server/index.js` e `dist/.openai/hosting.json`.
5. Gli asset current/archive, l'alias di compatibilità e `reports/daily-sync-latest.json` vengono committati sul branch `github-ready`.
6. Se è configurato il secret `SITES_DEPLOY_HOOK_URL`, il workflow invia a quel deploy hook il commit appena pubblicato e registra `DEPLOY_TRIGGERED`; in assenza del secret registra `NOT_CONFIGURED` e fa fallire il job (la sync dati resta conservata), mentre un errore del hook registra `DEPLOY_FAILED` e fa fallire il job.
7. Nel progetto Sites attuale non è configurata una credenziale repository/hook CI: la pubblicazione pubblica verificata richiede quindi il percorso nativo Sites sul commit esatto: `bash C:/Users/lucap/.codex/plugins/cache/openai-bundled/sites/0.1.52/scripts/package-site.sh <project-dir> <archive.zip>`, poi `sites_save_site_version(project_id="appgprj_6a8c7c07886881918e42afbd0caa853e", commit_sha=<HEAD-pushato>, archive=<archive.zip>)`, `sites_deploy_site_version(project_id=..., version_id=<id-salvato>)` e polling `sites_get_deployment_status`.

Esecuzione manuale locale: `python -m funding_core.cli populate-snapshot` (oppure `python -m funding_core.cli daily-sync`). Lo stato dell'ultima esecuzione è in [`reports/daily-sync-latest.json`](../reports/daily-sync-latest.json); la sezione `sourceHealth` è presente in entrambi gli snapshot.
