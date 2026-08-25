# Fonti e contratti v0.2.1

Il dataset corrente separa le opportunità operative dall'elenco dei bandi scaduti. Conteggi, stati e avvisi sono generati a ogni sync nei report sotto `reports/` e non sono duplicati nella documentazione statica.

| Source | Adapter | Method | Role | Status | Notes |
|---|---|---|---|---|---|
| EU Funding & Tenders | `EuFundingTendersAdapter` | API ufficiale POST/JSON | Canonica UE | LIVE / SNAPSHOT ACTIVE | Query server-side OPEN/UPCOMING, paginazione reale, stato ufficiale prioritario e tutte le deadline valide; conteggi nel report generato |
| Incentivi.gov.it | `IncentiviGovAdapter` | Open data Solr ufficiali | Nazionale/regionale | LIVE / SNAPSHOT ACTIVE | Conserva `Regioni`, `Ambito_territoriale`, `Link_istituzionale` e URL aggregatore; conteggi nel report generato |
| Erasmus+ INDIRE | `ErasmusIndireAdapter` | HTML strutturato della tabella scadenze | Tier A | LIVE / SNAPSHOT ACTIVE | Le scadenze già trascorse sono archiviate; conteggi nel report generato |
| Agenzia Italiana per la Gioventù | `AigOpportunitiesAdapter` | REST API WordPress ufficiale, categoria Opportunità AIG | Tier A | LIVE / SNAPSHOT ACTIVE | Eventi/news senza segnali chiari di call, progetto o finanziamento sono esclusi; conteggi nel report generato |
| Interreg Italy–Croatia | `InterregItalyCroatiaAdapter` | HTML strutturato della pagina 4th Call | Tier A | LIVE / SNAPSHOT ACTIVE | Call con schedule e budget parseabili; conteggi nel report generato |
| Veneto FSE+ calendario | `VenetoFseCalendarAdapter` | CSV ufficiale | EARLY | FIXTURE VERIFIED / LIVE BLOCKED | Parser, deduplica e test presenti; il download live è bloccato dalla catena TLS locale e non viene pubblicato nello snapshot |
| Veneto FESR calendario | `VenetoFesrCalendarAdapter` | Parser CSV condiviso con FSE+ | EARLY | FIXTURE VERIFIED / SOURCE LINK PENDING | Il parser e la fixture sono presenti; la pagina corrente rimanda al cronoprogramma regionale HTML e non espone un CSV stabile da sincronizzare |
| Regione Veneto bandi | `VenetoBandiAdapter` | Endpoint JSON ufficiale `Public/GetListaAttiJson` dalla lista `Public/Elenco?Tipo=1` | Tier A regionale | LIVE / SNAPSHOT ACTIVE | Paginazione dell'elenco ufficiale di bandi/avvisi/concorsi senza il limite artificiale delle 10 card homepage; campi di riga e dettaglio best-effort |
| Dipartimento Politiche della Famiglia | `DipartimentoFamigliaAdapter` | HTML lista + detail best-effort | Tier A nazionale | LIVE / SNAPSHOT ACTIVE | Il dettaglio viene consultato entro un limite e può valorizzare deadline/budget/destinatari; conteggi nel report generato |
| Dipartimento Disabilità | `DipartimentoDisabilitaAdapter` | HTML lista + detail best-effort | Tier A nazionale | LIVE / SNAPSHOT ACTIVE | Conteggi nel report generato |
| Fondazione Cariparo | `FondazioneCariparoAdapter` | HTML lista + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | Conteggi nel report generato |
| Fondazione Cariverona | `FondazioneCariveronaAdapter` | HTML lista + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | Deadline lasciata nulla quando il dettaglio non la identifica con sufficiente affidabilità; conteggi nel report generato |
| Con i Bambini | `ConIBambiniAdapter` | JSON embedded `var bandi` + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | Stati In corso/Scaduti mantenuti; conteggi nel report generato |
| Fondo per la Repubblica Digitale | `FondoRepubblicaDigitaleAdapter` | HTML lista + detail best-effort | Tier A fondazioni | LIVE / SNAPSHOT ACTIVE | Conteggi nel report generato |
| Pari Opportunità / Dipendenze / FAMI | `NOT IMPLEMENTED` | Per fonte | OPEN | NOT IMPLEMENTED | Da implementare con contratti separati, senza forzare una lista universale |

`FIXTURE VERIFIED` non equivale a sorgente live completata. Lo snapshot espone solo fonti live riuscite; i calendari FSE+/FESR+ restano disponibili per test fixture finché i contratti ufficiali non sono stabili. In caso di errore o calo anomalo, la pipeline conserva i record precedenti e marca la fonte come `STALE`.
