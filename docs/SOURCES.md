# Fonti e contratti v0.2

Lo snapshot corrente separa le opportunità operative dall'archivio CLOSED. I numeri sotto sono quelli dell'ultima generazione locale del 24/08/2026; una nuova sync può variare i conteggi.

| Source | Adapter | Method | Role | Status | Notes |
|---|---|---|---|---|---|
| EU Funding & Tenders | `EuFundingTendersAdapter` | API ufficiale POST/JSON | Canonica UE | LIVE / SNAPSHOT ACTIVE | Query server-side OPEN/UPCOMING, paginazione reale e URL canonico; 518 correnti e 490 archiviate nell'ultimo run |
| Incentivi.gov.it | `IncentiviGovAdapter` | Open data Solr ufficiali | Nazionale/regionale | LIVE / SNAPSHOT ACTIVE | 802 correnti e 4.971 archiviate; conserva `Regioni`, `Ambito_territoriale`, `Link_istituzionale` e URL aggregatore |
| Erasmus+ INDIRE | `ErasmusIndireAdapter` | HTML strutturato della tabella scadenze | Tier A | LIVE / SNAPSHOT ACTIVE | 1 opportunità corrente; le scadenze 2026 già trascorse sono archiviate |
| Agenzia Italiana per la Gioventù | `AigOpportunitiesAdapter` | REST API WordPress ufficiale, categoria Opportunità AIG | Tier A | LIVE / SNAPSHOT ACTIVE | 15 correnti e 15 archiviate; eventi/news senza segnali di call o finanziamento sono esclusi |
| Interreg Italy–Croatia | `InterregItalyCroatiaAdapter` | HTML strutturato della pagina 4th Call | Tier A | LIVE / SNAPSHOT ACTIVE | 1 call con schedule e budget parseabili |
| Veneto FSE+ calendario | `VenetoFseCalendarAdapter` | CSV ufficiale | EARLY | FIXTURE VERIFIED / LIVE BLOCKED | Parser, deduplica e test presenti; il download live è bloccato dalla catena TLS locale e non viene pubblicato nello snapshot |
| Veneto FESR calendario | `VenetoFesrCalendarAdapter` | Parser CSV condiviso con FSE+ | EARLY | FIXTURE VERIFIED / SOURCE LINK PENDING | Il parser e la fixture sono presenti; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone un CSV stabile da sincronizzare |
| Regione Veneto bandi | `VenetoBandiAdapter` | HTML statico della sezione `IN SCADENZA` | Tier A regionale | LIVE / SNAPSHOT ACTIVE | 10 card correnti; il contratto acquisito è la sezione pubblica `IN SCADENZA`, non un archivio completo |
| Dipartimento Politiche della Famiglia | `DipartimentoFamigliaAdapter` | HTML lista + detail best-effort | Tier A nazionale | LIVE / SNAPSHOT ACTIVE | 15 correnti e 7 archiviate; il dettaglio viene consultato entro un limite e può valorizzare deadline/budget/destinatari |
| Dipartimento Disabilità | `DipartimentoDisabilitaAdapter` | HTML lista + detail best-effort | Tier A nazionale | LIVE / SNAPSHOT ACTIVE | 8 correnti e 1 archiviata |
| Fondazione Cariparo | `FondazioneCariparoAdapter` | HTML lista + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | 8 correnti e 1 archiviata |
| Fondazione Cariverona | `FondazioneCariveronaAdapter` | HTML lista + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | 5 correnti e 1 archiviata |
| Con i Bambini | `ConIBambiniAdapter` | JSON embedded `var bandi` + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | 3 correnti e 30 archiviate; stati In corso/Scaduti mantenuti |
| Fondo per la Repubblica Digitale | `FondoRepubblicaDigitaleAdapter` | HTML lista + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | 1 corrente e 6 archiviate |
| Pari Opportunità / Dipendenze / FAMI | `NOT IMPLEMENTED` | Per fonte | OPEN | NOT IMPLEMENTED | Da implementare con contratti separati, senza forzare una lista universale |

`FIXTURE VERIFIED` non equivale a sorgente live completata. Lo snapshot espone solo fonti live riuscite; i calendari FSE+/FESR+ restano disponibili per test fixture finché i contratti ufficiali non sono stabili. In caso di errore o calo anomalo, la pipeline conserva i record precedenti e marca la fonte come `STALE`.
