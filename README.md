# Funding Intelligence for Psychology

Prima iterazione separata e prudente di un motore di ricerca per finanziamenti destinati a progetti psicologici.

## Stato reale

- UI Sites responsive con ricerca, macroaree multi-select, filtri, dettaglio, opportunità in arrivo e preferiti locali.
- I record visibili sono **scenari dimostrativi** e sono dichiarati tali nell'interfaccia.
- Core Python senza dipendenze esterne per normalizzazione, classificazione multi-label, deduplicazione e anomaly warning.
- Adapter EU Funding & Tenders con chiamata live verificata, parser e fixture; il risultato non è ancora persistito nello snapshot pubblico.
- Adapter Incentivi.gov.it sull'export Solr ufficiale: chiamata live verificata con 5.773 record, parser e fixture; il risultato non è ancora persistito nello snapshot pubblico.
- Adapter Erasmus+ INDIRE sulla tabella ufficiale delle scadenze: 10 righe INDIRE parseabili verificate live, parser e fixture.
- Adapter AIG sulla REST API ufficiale delle opportunità: 32 post parseabili verificati live, parser e fixture.
- Adapter Interreg Italy–Croatia sulla pagina ufficiale della 4th Call: calendario e budget estratti live, parser e fixture.
- Adapter Regione Veneto bandi sulla sezione statica `IN SCADENZA` della homepage: 10 card correnti parseabili verificate sul markup live, parser e fixture; la fetch Python resta soggetta alla TLS policy locale.
- Adapter Dipartimento Famiglia: 22 avvisi/bandi correnti parseabili dalla lista ufficiale; adapter Dipartimento Disabilità: 9 voci parseabili dalla sezione ufficiale.
- Adapter Fondazione Cariparo (9 link), Fondazione Cariverona (6 link), Con i Bambini (33 voci dall'embedded JSON ufficiale) e Fondo per la Repubblica Digitale (7 link): markup/JSON live verificati, parser e fixture; deadline/importi restano nulli quando l'elenco non li espone.
- Parser fixture-verificato per il calendario FSE+ Veneto; la verifica live resta bloccata dalla catena TLS locale.
- Parser fixture-verificato per il calendario FESR+ Veneto; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone ancora un CSV stabile.
- Nessuna API AI, autenticazione, coda, cache complessa o servizio aggiuntivo.

## Verifica

```powershell
python -m unittest discover -s tests -p "test_*.py"
pnpm test
```

Validazione manuale live dell'adapter UE:

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
```

Vedi `docs/SOURCES.md` per lo stato puntuale delle fonti.
