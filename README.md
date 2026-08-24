# Funding Intelligence for Psychology v0.2

Motore locale-first di ricerca per finanziamenti destinati a progetti psicologici, con snapshot verificabile e fonti ufficiali in evidenza.

## Stato reale

- UI Sites responsive con ricerca senza LLM, sinonimi OR/AND deterministici, macroaree multi-select, filtri di territorio/partecipante, dettaglio, Nuovi e Preferiti locali.
- Lo snapshot corrente `public/data/opportunities-current.json` contiene 1.387 opportunità operative (871 OPEN, 280 UPCOMING, 236 UNKNOWN); i 5.483 CLOSED sono in `public/data/opportunities-archive.json` e non vengono caricati dalla home.
- Ogni record conserva `firstSeen`, `lastSeen`, `lastChanged`, `contentHash`, fonte dati e URL ufficiale; un fetch fallito o anomalo conserva il precedente valido e marca la fonte `STALE`/`ERROR`.
- Core Python senza dipendenze esterne per normalizzazione, classificazione multi-label pesata, deduplicazione, paginazione EU, audit e anomaly warning.
- Funding & Tenders usa la query server-side OPEN/UPCOMING e paginazione fino al totale dichiarato; i CLOSED sono esclusi dal feed operativo.
- Incentivi.gov.it conserva Regioni/Ambito territoriale e preferisce `Link_istituzionale`; il link al catalogo resta come fonte aggregata.
- Le liste HTML prioritarie tentano un enrichment best-effort delle pagine dettaglio (deadline, stato, apertura, budget, destinatari) senza cancellare la scheda se il dettaglio non risponde.
- AIG filtra eventi, webinar e news prive di segnali di call/candidatura/finanziamento; le fonti live restano quelle già presenti in v0.1.
- Parser fixture-verificato per il calendario FSE+ Veneto; la verifica live resta bloccata dalla catena TLS locale.
- Parser fixture-verificato per il calendario FESR+ Veneto; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone ancora un CSV stabile.
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

Il comando usa automaticamente lo snapshot precedente come fallback. Produce anche `reports/high-relevance-audit.csv`, `reports/dataset-audit.json` e `reports/search-quality.md`.

La classificazione espone `Alta/Media/Bassa` e resta euristica: non decide l'ammissibilità. Date, importi e destinatari mancanti restano esplicitamente non indicati.

Vedi `docs/SOURCES.md` per lo stato puntuale delle fonti e `docs/ADDING_SOURCE.md` per il contratto minimo di un adapter.
