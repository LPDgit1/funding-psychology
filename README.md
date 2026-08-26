# Funding Intelligence for Psychology v0.3.0

Motore locale-first di ricerca per finanziamenti destinati a progetti psicologici, con snapshot verificabile e fonti ufficiali in evidenza.

## Stato reale

- UI Sites responsive con ricerca senza LLM, sinonimi OR/AND deterministici, otto aree di interesse user-facing, filtri primari di tema/territorio/scadenza/partecipazione, dettaglio, Nuovi e Preferiti locali.
- Lo snapshot corrente `public/data/opportunities-current.json` separa le opportunità operative dall'archivio CLOSED; conteggi e distribuzione degli stati sono generati automaticamente a ogni sync (`reports/dataset-audit.json`).
- Ogni record conserva `firstSeen`, `lastSeen`, `lastChanged`, `contentHash`, fonte dati e URL ufficiale; un fetch fallito o anomalo conserva il precedente valido e marca la fonte `STALE`/`ERROR`.
- Core Python senza dipendenze esterne per normalizzazione, classificazione multi-label pesata, deduplicazione, paginazione EU, audit e anomaly warning.
- Funding & Tenders usa la query server-side OPEN/UPCOMING, il contratto multipart del portale e paginazione fino al totale dichiarato; i CLOSED sono esclusi dal feed operativo e lo stato ufficiale prevale sulle deadline locali.
- Incentivi.gov.it conserva Regioni/Ambito territoriale e preferisce `Link_istituzionale`; il link al catalogo resta come fonte aggregata.
- Le liste HTML prioritarie tentano un enrichment best-effort delle pagine dettaglio (deadline, stato, apertura, budget, destinatari) senza cancellare la scheda se il dettaglio non risponde.
- AIG filtra eventi, webinar, consultazioni, corsi e news prive di segnali di call/candidatura/finanziamento progettuale; le fonti live restano quelle già presenti in v0.1.
- Parser fixture-verificato per il calendario FSE+ Veneto; la verifica live resta bloccata dalla catena TLS locale.
- Parser fixture-verificato per il calendario FESR+ Veneto; la pubblicazione live resta bloccata finché il contratto ufficiale non è stabile.
- v0.3 aggiunge 14 adapter dedicati per fonti istituzionali e fondazioni, con filtri source-specific per bandi, avvisi, calendari EARLY e standing opportunity.
- Ogni nuova fonte conserva status `UNKNOWN`/`UPCOMING` e campi mancanti quando il sito ufficiale non espone una data o un territorio verificabile; non vengono trasformati news, esiti o progetti finanziati in candidature.
- La validazione live v0.3 e il rendimento `raw/current/unique/duplicates` sono registrati nei report sotto `reports/`.
- L'adapter Regione Veneto usa l'elenco ufficiale `Public/Elenco?Tipo=1` e non il blocco homepage limitato alle dieci card; il dettaglio viene consultato solo quando serve.
- Nessuna API AI, autenticazione, coda, cache complessa o servizio aggiuntivo.

## Verifica

```powershell
python -m unittest discover -s tests -p "test_*.py"
pnpm test
```

Validazione manuale degli adapter e rigenerazione dello snapshot current/archive:

```powershell
python -m funding_core.cli validate-source eu-funding-tenders
python -m funding_core.cli sync eu-funding-tenders
python -m funding_core.cli validate-source incentivi-gov
python -m funding_core.cli sync incentivi-gov
python -m funding_core.cli validate-source erasmus-indire
python -m funding_core.cli sync erasmus-indire
python -m funding_core.cli validate-source aig-opportunities
python -m funding_core.cli sync aig-opportunities
python -m funding_core.cli validate-source interreg-italy-croatia
python -m funding_core.cli sync interreg-italy-croatia
python -m funding_core.cli validate-source veneto-bandi
python -m funding_core.cli sync veneto-bandi
python -m funding_core.cli validate-source dipartimento-famiglia
python -m funding_core.cli sync dipartimento-famiglia
python -m funding_core.cli validate-source dipartimento-disabilita
python -m funding_core.cli sync dipartimento-disabilita
python -m funding_core.cli validate-source fondazione-cariparo
python -m funding_core.cli sync fondazione-cariparo
python -m funding_core.cli validate-source fondazione-cariverona
python -m funding_core.cli sync fondazione-cariverona
python -m funding_core.cli validate-source con-i-bambini
python -m funding_core.cli sync con-i-bambini
python -m funding_core.cli validate-source fondo-repubblica-digitale
python -m funding_core.cli sync fondo-repubblica-digitale
python -m funding_core.cli validate-source veneto-fse-calendar
python -m funding_core.cli validate-source veneto-fesr-calendar
python -m funding_core.cli populate-snapshot `
  --output public/data/opportunities-current.json `
  --archive-output public/data/opportunities-archive.json `
  --audit-dir reports
```

Il comando usa automaticamente lo snapshot precedente come fallback. Produce anche `reports/precision-audit.csv`, `reports/precision-audit.md`, `reports/adapter-status.csv`, `reports/known-relevant-opportunities.json`, `reports/dataset-audit.json`, `reports/search-quality.md` e `reports/final-report.md`.

Per la release v0.3, il report canonico dell’espansione selettiva è `reports/v0.3-source-report.md`, con la validazione live in `reports/v0.3-live-validation.txt` e il dettaglio incrementale in `reports/v0.3-incremental-coverage.json`.

La classificazione espone `Alta/Media/Bassa` e resta euristica: non decide l'ammissibilità. Date, importi e destinatari mancanti restano esplicitamente non indicati.

Vedi `docs/SOURCES.md` per lo stato puntuale delle fonti e `docs/ADDING_SOURCE.md` per il contratto minimo di un adapter.
