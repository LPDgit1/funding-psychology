# Fonti

| Source | Adapter | Method | Role | Status | Notes |
|---|---|---|---|---|---|
| EU Funding & Tenders | `EuFundingTendersAdapter` | API ufficiale POST/JSON | Canonica UE | LIVE VERIFIED / NOT PERSISTED | Chiamata reale verificata il 24/08/2026: HTTP 200, 1.219 risultati; parser e fixture presenti. Non ancora collegato a database o scheduler |
| Incentivi.gov.it | `IncentiviGovAdapter` | Open data Solr ufficiali | Nazionale | LIVE VERIFIED / NOT PERSISTED | Query ufficiale `index_id:incentivi`, HTTP 200 e 5.773 record parseabili verificati il 24/08/2026; il risultato non è ancora nello snapshot pubblico |
| Erasmus+ INDIRE | `ErasmusIndireAdapter` | HTML strutturato della tabella scadenze | Tier A | LIVE VERIFIED / NOT PERSISTED | Pagina ufficiale HTTP 200; 10 righe INDIRE parseabili verificate il 24/08/2026. Le schede restano fuori dallo snapshot pubblico |
| Agenzia Italiana per la Gioventù | `AigOpportunitiesAdapter` | REST API WordPress ufficiale, categoria Opportunità AIG | Tier A | LIVE VERIFIED / NOT PERSISTED | Endpoint pubblico HTTP 200; 32 post parseabili verificati il 24/08/2026. Deadline valorizzata solo quando esplicita nel testo |
| Interreg Italy–Croatia | `InterregItalyCroatiaAdapter` | HTML strutturato della pagina 4th Call | Tier A | LIVE VERIFIED / NOT PERSISTED | Pagina ufficiale HTTP 200; call schedule 15/06/2026–15/09/2026 e budget ERDF 5.859.000 estratti il 24/08/2026 |
| Veneto FSE+ calendario | `VenetoFseCalendarAdapter` | CSV ufficiale | EARLY | FIXTURE VERIFIED / LIVE BLOCKED | Parser, deduplica e test presenti; il download live è bloccato dalla catena TLS locale e non viene dichiarato completo |
| Veneto FESR calendario | `VenetoFesrCalendarAdapter` | Parser CSV condiviso con FSE+ | EARLY | FIXTURE VERIFIED / SOURCE LINK PENDING | Il parser e la fixture sono presenti; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone un CSV stabile da sincronizzare |
| Regione Veneto bandi | `VenetoBandiAdapter` | HTML statico della sezione `IN SCADENZA` | Tier A regionale | LIVE MARKUP VERIFIED / FETCH TLS BLOCKED | Homepage ufficiale: 10 card correnti parseabili verificate il 24/08/2026 con markup live; l’endpoint Python non viene dichiarato live-complete finché la TLS locale non consente una prova `urlopen` ripetibile |
| Dipartimento Politiche della Famiglia | `DipartimentoFamigliaAdapter` | HTML strutturato della lista avvisi e bandi | Tier A nazionale | LIVE MARKUP VERIFIED / NOT PERSISTED | 22 link di dettaglio correnti verificati il 24/08/2026; il campo deadline viene valorizzato solo quando la lista ufficiale lo espone |
| Dipartimento Disabilità | `DipartimentoDisabilitaAdapter` | HTML strutturato della sezione Avvisi e Bandi | Tier A nazionale | LIVE MARKUP VERIFIED / NOT PERSISTED | 9 voci di dettaglio verificabili live il 24/08/2026; date/importi non presenti nell’elenco e quindi lasciati null |
| Fondazione Cariparo | `FondazioneCariparoAdapter` | HTML lista Bandi | Tier A fondazioni | LIVE MARKUP VERIFIED / NOT PERSISTED | 9 link correnti verificati live il 24/08/2026; la pagina elenco non espone in modo uniforme deadline/importi |
| Fondazione Cariverona | `FondazioneCariveronaAdapter` | HTML lista Bandi e Contributi | Tier A fondazioni | LIVE MARKUP VERIFIED / NOT PERSISTED | 6 link di iniziativa verificati live il 24/08/2026 |
| Con i Bambini | `ConIBambiniAdapter` | JSON embedded `var bandi` nella pagina ufficiale | Tier A fondazioni | LIVE VERIFIED / NOT PERSISTED | 33 voci (stati In corso/Scaduti) parseabili live il 24/08/2026 |
| Fondo per la Repubblica Digitale | `FondoRepubblicaDigitaleAdapter` | HTML lista Bandi | Tier A fondazioni | LIVE MARKUP VERIFIED / NOT PERSISTED | 7 link di dettaglio verificati live il 24/08/2026 |
| Pari Opportunità / Dipendenze / FAMI | `NOT IMPLEMENTED` | Per fonte | OPEN | NOT IMPLEMENTED | Da implementare con contratti separati, senza forzare una lista universale |

`FIXTURE VERIFIED` non equivale a sorgente live completata. L'adapter diventa `COMPLETE` solo dopo una prova reale riuscita e ripetibile.
