export type OpportunityStatus = "OPEN" | "UPCOMING" | "CLOSED" | "UNKNOWN";
export type Relevance = "Alta" | "Media" | "Bassa";
export type ApplicantCategory = "public" | "ets" | "research" | "business" | "professional" | "school" | "other";

export type Opportunity = {
  id: string;
  title: string;
  funder: string;
  programme: string;
  status: OpportunityStatus;
  territory: string;
  regions?: string[];
  deadline?: string;
  openingDate?: string;
  amount?: string;
  eligibleEntities: string[];
  macroAreas: string[];
  summary: string;
  relevance: Relevance;
  relevanceScore?: number;
  positiveSignals?: string[];
  negativeSignals?: string[];
  relevanceWhy: string;
  officialUrl: string;
  aggregatorUrl?: string | null;
  sourceLabel?: string;
  lastVerified: string;
  firstSeen?: string;
  lastSeen?: string;
  lastChanged?: string;
  contentHash?: string;
  demo: boolean;
  sourceId?: string;
};

const SYNONYMS: Record<string, string[]> = {
  anziani: ["anziani", "ageing", "elderly", "older people", "caregiver"],
  adolescenti: ["adolescenti", "adolescent", "minori", "youth", "children", "young people", "giovani"],
  scuola: ["scuola", "scolastico", "school", "studenti", "student", "formazione"],
  burnout: ["burnout", "stress lavoro", "benessere organizzativo", "workplace stress"],
  caregiver: ["caregiver", "anziani", "ageing", "elderly", "older people"],
  violenza: ["violenza", "trauma", "abuso", "violenza di genere", "gender-based violence"],
  dipendenze: ["dipendenze", "addiction", "substance use"],
  "salute mentale": ["salute mentale", "mental health", "benessere psicologico", "supporto psicologico", "psychological support"],
  "inclusione sociale": ["inclusione sociale", "inclusione", "vulnerabilità", "fragilità", "social exclusion"],
  demenza: ["demenza", "dementia", "alzheimer", "caregiver"],
  disabilita: ["disabilità", "disabilita", "neurodiversità", "autismo", "autism"],
  "intelligenza artificiale": ["intelligenza artificiale", "artificial intelligence", "ai", "digitale", "digital"],
};

function normalized(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("it-IT").replace(/\s+/g, " ").trim();
}

const normalizedSynonyms = Object.fromEntries(
  Object.entries(SYNONYMS).map(([key, values]) => [normalized(key), [...new Set(values.map(normalized))]]),
);

/** OR inside each concept, AND between concepts typed by the user. */
export function expandedTermGroups(query: string): string[][] {
  const tokens = normalized(query).split(/\s+/).filter(Boolean);
  const groups: string[][] = [];
  let index = 0;
  while (index < tokens.length) {
    const pair = tokens.slice(index, index + 2).join(" ");
    const key = normalizedSynonyms[pair] ? pair : tokens[index];
    groups.push(normalizedSynonyms[key] ? [...normalizedSynonyms[key]] : [tokens[index]]);
    index += key === pair ? 2 : 1;
  }
  return groups;
}

export function expandedTerms(query: string): string[] {
  return [...new Set(expandedTermGroups(query).flat())];
}

export function territoryBucket(value: string) {
  const territory = normalized(value);
  if (territory === "veneto") return "Veneto";
  if (territory === "unione europea" || territory === "ue" || territory === "europa") return "Europa";
  if (territory === "italia" || territory === "italia / nazionale" || territory === "nazionale") return "Italia";
  return "Altre regioni";
}

export function applicantCategory(item: Opportunity): ApplicantCategory {
  const text = normalized(item.eligibleEntities.join(" "));
  if (!text) return "other";
  if (/(comune|regione|minister|ente pubblico|amministraz|universita pubblica)/.test(text)) return "public";
  if (/(ets|terzo settore|non profit|non-profit|associazion|fondazion|cooperativ)/.test(text)) return "ets";
  if (/(universit|ricerca|ateneo|ente scientific)/.test(text)) return "research";
  if (/(impresa|pmi|azienda|startup|societa)/.test(text)) return "business";
  if (/(professionist|psicolog|liber[io] profession)/.test(text)) return "professional";
  if (/(scuola|istituto scolast|ente formativ|student)/.test(text)) return "school";
  return "other";
}

export function isNewOpportunity(item: Opportunity, now = new Date(), days = 7) {
  if (!item.firstSeen) return false;
  const timestamp = new Date(item.firstSeen).getTime();
  if (!Number.isFinite(timestamp)) return false;
  const age = (now.getTime() - timestamp) / 86_400_000;
  return age >= -1 && age <= days;
}

export function filterOpportunities(
  items: Opportunity[],
  filters: {
    query: string;
    macroAreas: string[];
    territory: string;
    status: string;
    deadline: string;
    applicant?: string;
    favoriteIds?: string[];
    favoritesOnly?: boolean;
    newOnly?: boolean;
    includeLowRelevance?: boolean;
  },
  now = new Date(),
) {
  const groups = expandedTermGroups(filters.query);
  return items.filter((item) => {
    const haystack = normalized([
      item.title, item.funder, item.programme, item.territory, item.summary,
      ...(item.regions ?? []), ...item.macroAreas, ...item.eligibleEntities,
    ].join(" "));
    const matchesText = groups.length === 0 || groups.every((group) => group.some((term) => haystack.includes(term)));
    const matchesMacro = filters.macroAreas.length === 0 || filters.macroAreas.some((area) => item.macroAreas.includes(area));
    const matchesTerritory = filters.territory === "all" || territoryBucket(item.territory) === filters.territory || item.territory === filters.territory;
    const matchesStatus = filters.status === "all"
      || (filters.status === "current" && (item.status === "OPEN" || item.status === "UPCOMING"))
      || item.status === filters.status;
    const matchesApplicant = !filters.applicant || filters.applicant === "all" || applicantCategory(item) === filters.applicant;
    const matchesFavorites = !filters.favoritesOnly || (filters.favoriteIds ?? []).includes(item.id);
    const matchesNew = !filters.newOnly || isNewOpportunity(item, now);
    const days = item.deadline ? Math.ceil((new Date(item.deadline).getTime() - now.getTime()) / 86_400_000) : undefined;
    const matchesDeadline = filters.deadline === "all" || (days !== undefined && days >= 0 && days <= Number(filters.deadline));
    const matchesRelevance = filters.includeLowRelevance !== false || item.relevance !== "Bassa";
    return matchesText && matchesMacro && matchesTerritory && matchesStatus && matchesApplicant && matchesFavorites && matchesNew && matchesDeadline && matchesRelevance;
  });
}
