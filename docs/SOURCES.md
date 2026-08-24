# Fonti

| Source | Adapter | Method | Role | Status | Notes |
|---|---|---|---|---|---|
| EU Funding & Tenders | `EuFundingTendersAdapter` | API ufficiale POST/JSON | Canonica UE | LIVE VERIFIED / SNAPSHOT ACTIVE | HTTP 200 verificato il 24/08/2026; 100 schede parseabili pubblicate nel primo snapshot (endpoint paginato) |
| Incentivi.gov.it | `IncentiviGovAdapter` | Open data Solr ufficiali | Nazionale | LIVE VERIFIED / SNAPSHOT ACTIVE | Query ufficiale `index_id:incentivi`, HTTP 200 e 5.773 record parseabili e pubblicati nello snapshot iniziale |
| Erasmus+ INDIRE | `ErasmusIndireAdapter` | HTML strutturato della tabella scadenze | Tier A | LIVE VERIFIED / SNAPSHOT ACTIVE | Pagina ufficiale HTTP 200; 10 righe INDIRE parseabili e pubblicate nello snapshot |
| Agenzia Italiana per la Gioventù | `AigOpportunitiesAdapter` | REST API WordPress ufficiale, categoria Opportunità AIG | Tier A | LIVE VERIFIED / SNAPSHOT ACTIVE | Endpoint pubblico HTTP 200; 32 post parseabili e pubblicati nello snapshot. Deadline valorizzata solo quando esplicita nel testo |
| Interreg Italy–Croatia | `InterregItalyCroatiaAdapter` | HTML strutturato della pagina 4th Call | Tier A | LIVE VERIFIED / SNAPSHOT ACTIVE | Pagina ufficiale HTTP 200; 1 call con schedule e budget parseabili e pubblicati nello snapshot |
| Veneto FSE+ calendario | `VenetoFseCalendarAdapter` | CSV ufficiale | EARLY | FIXTURE VERIFIED / LIVE BLOCKED | Parser, deduplica e test presenti; il download live è bloccato dalla catena TLS locale e non viene pubblicato nello snapshot |
| Veneto FESR calendario | `VenetoFesrCalendarAdapter` | Parser CSV condiviso con FSE+ | EARLY | FIXTURE VERIFIED / SOURCE LINK PENDING | Il parser e la fixture sono presenti; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone un CSV stabile da sincronizzare |
| Regione Veneto bandi | `VenetoBandiAdapter` | HTML statico della sezione `IN SCADENZA` | Tier A regionale | LIVE VERIFIED / SNAPSHOT ACTIVE | Homepage ufficiale: 10 card correnti parseabili e pubblicate nello snapshot |
| Dipartimento Politiche della Famiglia | `DipartimentoFamigliaAdapter` | HTML strutturato della lista avvisi e bandi | Tier A nazionale | LIVE VERIFIED / SNAPSHOT ACTIVE | 22 link di dettaglio correnti pubblicati nello snapshot; il campo deadline viene valorizzato solo quando la lista ufficiale lo espone |
| Dipartimento Disabilità | `DipartimentoDisabilitaAdapter` | HTML strutturato della sezione Avvisi e Bandi | Tier A nazionale | LIVE VERIFIED / SNAPSHOT ACTIVE | 9 voci pubblicate nello snapshot; date/importi non presenti nell’elenco e quindi lasciati null |
| Fondazione Cariparo | `FondazioneCariparoAdapter` | HTML lista Bandi | Tier A fondazioni | LIVE VERIFIED / SNAPSHOT ACTIVE | 9 link correnti pubblicati nello snapshot; la pagina elenco non espone in modo uniforme deadline/importi |
| Fondazione Cariverona | `FondazioneCariveronaAdapter` | HTML lista Bandi e Contributi | Tier A fondazioni | LIVE VERIFIED / SNAPSHOT ACTIVE | 6 link di iniziativa pubblicati nello snapshot |
| Con i Bambini | `ConIBambiniAdapter` | JSON embedded `var bandi` nella pagina ufficiale | Tier A fondazioni | LIVE VERIFIED / SNAPSHOT ACTIVE | 33 voci (stati In corso/Scaduti) pubblicate nello snapshot |
| Fondo per la Repubblica Digitale | `FondoRepubblicaDigitaleAdapter` | HTML lista Bandi | Tier A fondazioni | LIVE VERIFIED / SNAPSHOT ACTIVE | 7 link di dettaglio pubblicati nello snapshot |
| Pari Opportunità / Dipendenze / FAMI | `NOT IMPLEMENTED` | Per fonte | OPEN | NOT IMPLEMENTED | Da implementare con contratti separati, senza forzare una lista universale |

`FIXTURE VERIFIED` non equivale a sorgente live completata. Lo snapshot espone solo fonti live riuscite; i calendari FSE+/FESR+ restano disponibili per test fixture finché i contratti ufficiali non sono stabili.
