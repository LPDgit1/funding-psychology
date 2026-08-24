# Funding Intelligence for Psychology

Prima iterazione separata e prudente di un motore di ricerca per finanziamenti destinati a progetti psicologici.

## Stato reale

- UI Sites responsive con ricerca, macroaree multi-select, filtri, dettaglio, opportunità in arrivo e preferiti locali.
- Lo snapshot pubblico `public/data/opportunities.json` contiene il primo popolamento reale: 6.012 opportunità normalizzate da 12 adapter live, con date/importi mancanti lasciati nulli e fallback dimostrativo se il file non è raggiungibile.
- Core Python senza dipendenze esterne per normalizzazione, classificazione multi-label, deduplicazione e anomaly warning.
- Adapter EU Funding & Tenders con chiamata live verificata e 100 schede pubblicate nello snapshot iniziale.
- Adapter Incentivi.gov.it sull'export Solr ufficiale: chiamata live verificata con 5.773 record pubblicati nello snapshot iniziale.
- Adapter Erasmus+ INDIRE (10 righe), AIG (32 post), Interreg Italy–Croatia (1 call) e Regione Veneto bandi (10 card): trasporto/parsing live verificati e record pubblicati nello snapshot.
- Adapter Dipartimento Famiglia (22), Dipartimento Disabilità (9), Fondazione Cariparo (9), Fondazione Cariverona (6), Con i Bambini (33) e Fondo per la Repubblica Digitale (7): liste ufficiali live verificate e pubblicate nello snapshot; deadline/importi restano nulli quando l'elenco non li espone.
- Parser fixture-verificato per il calendario FSE+ Veneto; la verifica live resta bloccata dalla catena TLS locale.
- Parser fixture-verificato per il calendario FESR+ Veneto; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone ancora un CSV stabile.
- Nessuna API AI, autenticazione, coda, cache complessa o servizio aggiuntivo.

## Verifica

```powershell
python -m unittest discover -s tests -p "test_*.py"
pnpm test
```

Validazione manuale degli adapter e rigenerazione dello snapshot:

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
python -m funding_core.cli populate-snapshot --output public/data/opportunities.json
```

Vedi `docs/SOURCES.md` per lo stato puntuale delle fonti.
