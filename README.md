# Funding Intelligence for Psychology

Prima iterazione separata e prudente di un motore di ricerca per finanziamenti destinati a progetti psicologici.

## Stato reale

- UI Sites responsive con ricerca, macroaree multi-select, filtri, dettaglio, opportunità in arrivo e preferiti locali.
- I record visibili sono **scenari dimostrativi** e sono dichiarati tali nell'interfaccia.
- Core Python senza dipendenze esterne per normalizzazione, classificazione multi-label, deduplicazione e anomaly warning.
- Adapter EU Funding & Tenders con chiamata live verificata, parser e fixture; il risultato non è ancora persistito nello snapshot pubblico.
- Parser fixture-verificato per il calendario FSE+ Veneto; la verifica live resta bloccata dalla catena TLS locale.
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
```

Vedi `docs/SOURCES.md` per lo stato puntuale delle fonti.
