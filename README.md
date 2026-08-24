# Funding Intelligence for Psychology

Prima iterazione separata e prudente di un motore di ricerca per finanziamenti destinati a progetti psicologici.

## Stato reale

- UI Sites responsive con ricerca, macroaree multi-select, filtri, dettaglio, opportunità in arrivo e preferiti locali.
- I record visibili sono **scenari dimostrativi** e sono dichiarati tali nell'interfaccia.
- Core Python senza dipendenze esterne per normalizzazione, classificazione multi-label, deduplicazione e anomaly warning.
- Un parser fixture-verificato per il calendario FSE+ Veneto; nessun adapter è ancora dichiarato live completo.
- Nessuna API AI, autenticazione, coda, cache complessa o servizio aggiuntivo.

## Verifica

```powershell
python -m unittest discover -s tests -p "test_*.py"
pnpm test
```

Vedi `docs/SOURCES.md` per lo stato puntuale delle fonti.
