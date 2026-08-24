# Fonti

| Source | Adapter | Method | Role | Status | Notes |
|---|---|---|---|---|---|
| EU Funding & Tenders | `EuFundingTendersAdapter` | API ufficiale POST/JSON | Canonica UE | LIVE VERIFIED / NOT PERSISTED | Chiamata reale verificata il 24/08/2026: HTTP 200, 1.219 risultati; parser e fixture presenti. Non ancora collegato a database o scheduler |
| Incentivi.gov.it | `IncentiviGovAdapter` | Open data Solr ufficiali | Nazionale | LIVE VERIFIED / NOT PERSISTED | Query ufficiale `index_id:incentivi`, HTTP 200 e 5.773 record parseabili verificati il 24/08/2026; il risultato non è ancora nello snapshot pubblico |
| Veneto FSE+ calendario | `VenetoFseCalendarAdapter` | CSV ufficiale | EARLY | FIXTURE VERIFIED / LIVE BLOCKED | Parser, deduplica e test presenti; il download live è bloccato dalla catena TLS locale e non viene dichiarato completo |
| Veneto FESR calendario | `VenetoFesrCalendarAdapter` | Parser CSV condiviso con FSE+ | EARLY | FIXTURE VERIFIED / SOURCE LINK PENDING | Il parser e la fixture sono presenti; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone un CSV stabile da sincronizzare |
| Regione Veneto bandi | `NOT IMPLEMENTED` | HTML strutturato | OPEN | NOT IMPLEMENTED | Portale ufficiale individuato; parsing non implementato |
| Erasmus+ INDIRE | `NOT IMPLEMENTED` | Da verificare | OPEN | NOT IMPLEMENTED | Tier A successivo |
| AIG | `NOT IMPLEMENTED` | Da verificare | OPEN | NOT IMPLEMENTED | Tier A successivo |
| Interreg Italy–Croatia | `NOT IMPLEMENTED` | Da verificare | OPEN | NOT IMPLEMENTED | Tier A successivo |
| Famiglia / Disabilità / Fondazioni | `NOT IMPLEMENTED` | Per fonte | OPEN | NOT IMPLEMENTED | Nessun adapter universale anticipato |

`FIXTURE VERIFIED` non equivale a sorgente live completata. L'adapter diventa `COMPLETE` solo dopo una prova reale riuscita e ripetibile.
