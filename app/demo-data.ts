import type { Opportunity } from "./funding-domain";

export const MACRO_AREAS = [
  "Salute mentale e benessere", "Minori e adolescenti", "Scuola, università e formazione",
  "Famiglia e genitorialità", "Inclusione sociale e vulnerabilità", "Disabilità e neurodiversità",
  "Anziani, ageing e caregiver", "Violenza, trauma e tutela", "Dipendenze",
  "Lavoro, organizzazioni e occupazione", "Comunità, welfare e sviluppo territoriale",
  "Salute pubblica e prevenzione", "Migrazione, integrazione e intercultura",
  "Diritti, pari opportunità e contrasto alle discriminazioni", "Digitale, innovazione e AI",
  "Ricerca e innovazione scientifica",
];

const common = { lastVerified: "24 agosto 2026", demo: true as const };

export const DEMO_OPPORTUNITIES: Opportunity[] = [
  {
    ...common, id: "demo-school", title: "Supporto psicologico e benessere degli adolescenti a scuola",
    funder: "Snapshot locale", programme: "Programma locale", status: "OPEN", territory: "Veneto",
    deadline: "2026-11-15", amount: "Fino a €150.000", eligibleEntities: ["ETS", "Scuole", "Enti locali"],
    macroAreas: ["Minori e adolescenti", "Scuola, università e formazione", "Salute mentale e benessere"],
    summary: "Interventi integrati di prevenzione del disagio, ascolto e supporto alle famiglie.", relevance: "Alta",
    relevanceWhy: "Il progetto riguarda direttamente adolescenti, benessere psicologico e contesto scolastico.",
    officialUrl: "https://programmazione-ue-2021-2027.regione.veneto.it/fse/fse-calendario-inviti-a-presentare-proposte",
  },
  {
    ...common, id: "demo-disability", title: "Percorsi di inclusione lavorativa per persone con disabilità",
    funder: "Snapshot locale", programme: "Programma locale", status: "UPCOMING", territory: "Veneto",
    openingDate: "2026-10-01", amount: "Budget da definire", eligibleEntities: ["Cooperative sociali", "ETS"],
    macroAreas: ["Disabilità e neurodiversità", "Inclusione sociale e vulnerabilità", "Lavoro, organizzazioni e occupazione"],
    summary: "Accompagnamento, sviluppo delle competenze e sostegno all'inserimento lavorativo.", relevance: "Alta",
    relevanceWhy: "Sono previsti interventi psicosociali, orientamento e inclusione.",
    officialUrl: "https://spazio-operatori.regione.veneto.it/bandi-servizi-sociali",
  },
  {
    ...common, id: "demo-violence", title: "Reti territoriali per prevenire e contrastare la violenza di genere",
    funder: "Snapshot locale", programme: "Programma locale", status: "OPEN", territory: "Italia",
    deadline: "2026-12-05", amount: "Da verificare", eligibleEntities: ["Enti locali", "Centri antiviolenza", "ETS"],
    macroAreas: ["Violenza, trauma e tutela", "Diritti, pari opportunità e contrasto alle discriminazioni", "Salute mentale e benessere"],
    summary: "Prevenzione, presa in carico e rafforzamento delle reti di protezione.", relevance: "Alta",
    relevanceWhy: "La dimensione trauma, tutela e supporto psicologico è centrale.",
    officialUrl: "https://www.regione.veneto.it/web/sociale/contributi-regionali",
  },
  {
    ...common, id: "demo-caregiver", title: "Servizi di prossimità per anziani e caregiver familiari",
    funder: "Snapshot locale", programme: "Programma locale", status: "OPEN", territory: "Italia",
    deadline: "2027-01-20", amount: "Fino a €300.000", eligibleEntities: ["ETS", "Comuni", "Aziende sanitarie"],
    macroAreas: ["Anziani, ageing e caregiver", "Comunità, welfare e sviluppo territoriale", "Salute mentale e benessere"],
    summary: "Servizi domiciliari, sollievo dei caregiver e prevenzione dell'isolamento.", relevance: "Alta",
    relevanceWhy: "Il bando può sostenere supporto ai caregiver e interventi contro isolamento e stress.",
    officialUrl: "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis",
  },
  {
    ...common, id: "demo-digital", title: "Innovazione digitale accessibile nei servizi sociali",
    funder: "Snapshot locale", programme: "Programma locale", status: "UPCOMING", territory: "Unione Europea",
    openingDate: "2026-11-01", amount: "Budget previsto €2 milioni", eligibleEntities: ["Università", "Enti pubblici", "Imprese sociali"],
    macroAreas: ["Digitale, innovazione e AI", "Inclusione sociale e vulnerabilità", "Ricerca e innovazione scientifica"],
    summary: "Strumenti digitali inclusivi per accesso, prevenzione e continuità dei servizi.", relevance: "Media",
    relevanceWhy: "Può includere soluzioni per servizi psicologici, ma l'ambito è più ampio.",
    officialUrl: "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
  },
  {
    ...common, id: "demo-migration", title: "Benessere e integrazione di giovani con background migratorio",
    funder: "Snapshot locale", programme: "Programma locale", status: "OPEN", territory: "Italia",
    deadline: "2026-10-30", amount: "Da verificare", eligibleEntities: ["ETS", "Scuole", "Comuni"],
    macroAreas: ["Migrazione, integrazione e intercultura", "Minori e adolescenti", "Inclusione sociale e vulnerabilità"],
    summary: "Azioni interculturali, sostegno psicosociale e partecipazione comunitaria.", relevance: "Alta",
    relevanceWhy: "Il sostegno psicosociale e l'integrazione dei giovani sono espliciti.",
    officialUrl: "https://bandi.regione.veneto.it/Public/Elenco?Tipo=1",
  },
];
