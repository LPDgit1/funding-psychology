export type OpportunityStatus = "OPEN" | "UPCOMING" | "CLOSED" | "UNKNOWN";
export type Relevance = "Alta" | "Media" | "Bassa";
export type ApplicantCategory = "public" | "ets" | "research" | "business" | "professional" | "education" | "school" | "other" | "unknown";

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
  sourceTags?: string[];
  cleanSourceText?: string;
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

// Only genuine synonyms belong in a group.  Related concepts remain
// searchable as their own terms and do not silently widen a query.
const SYNONYMS: Record<string, string[]> = {
  anziani: ["anziani", "ageing", "elderly", "older people", "older persons", "senior"],
  adolescenti: ["adolescenti", "adolescent", "minori", "youth", "children", "young people", "giovani"],
  scuola: ["scuola", "scolastico", "school", "studenti", "student"],
  burnout: ["burnout", "stress lavoro", "benessere organizzativo", "workplace stress"],
  caregiver: ["caregiver", "caregivers", "caregiving", "carer", "carers", "informal caregiver", "informal caregivers", "informal carer", "informal carers"],
  violenza: ["violenza", "abuso", "violenza di genere", "gender-based violence"],
  dipendenze: ["dipendenze", "addiction", "substance use"],
  "salute mentale": ["salute mentale", "mental health", "benessere psicologico", "supporto psicologico", "psychological support"],
  "inclusione sociale": ["inclusione sociale", "inclusione", "vulnerabilità", "fragilità", "social exclusion"],
  demenza: ["demenza", "dementia", "alzheimer", "alzheimers"],
  disabilita: ["disabilità", "disabilita", "neurodiversità", "autismo", "autism"],
  "intelligenza artificiale": ["intelligenza artificiale", "artificial intelligence", "machine learning", "ai"],
  migrazione: ["migrazione", "migranti", "migration", "migrant", "rifugiati", "refugees"],
  lavoratori: ["lavoratori", "lavoro", "workers", "workplace", "occupazione", "employment"],
};

export function normalized(value: string) {
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

function containsTerm(haystack: string, term: string) {
  // A two-letter acronym must not match arbitrary substrings such as the
  // “ai” in “finanziamento”.
  if (term === "ai") return /(^|[^a-z0-9])ai([^a-z0-9]|$)/.test(haystack);
  return haystack.includes(term);
}

export function territoryBucket(value: string, regions: string[] = []) {
  const normalizedRegions = regions.map(normalized);
  const territory = normalized(value);
  if (normalizedRegions.includes("veneto") || territory === "veneto") return "Veneto";
  if (territory === "unione europea" || territory === "ue" || territory === "europa") return "Europa";
  if (territory === "italia" || territory === "italia / nazionale" || territory === "nazionale") return "Italia";
  return "Altre regioni";
}

export function territoryMatches(item: Opportunity, selected: string) {
  if (selected === "all") return true;
  const territory = normalized(item.territory);
  const regions = (item.regions ?? []).map(normalized);
  if (selected === "Veneto") return territory === "veneto" || regions.includes("veneto");
  if (selected === "Europa") return ["unione europea", "ue", "europa"].includes(territory);
  if (selected === "Italia") return ["italia", "italia / nazionale", "nazionale"].includes(territory);
  return territoryBucket(item.territory, item.regions) === "Altre regioni";
}

export function applicantCategories(item: Opportunity): ApplicantCategory[] {
  const text = normalized(item.eligibleEntities.join(" "));
  if (!text) return ["unknown"];
  const categories = new Set<ApplicantCategory>();
  if (/(comun\w*|region\w*|minister\w*|ente pubblico|amministraz\w*|ente locale|azienda sanitaria|asl\b)/.test(text)) categories.add("public");
  if (/(ets\b|terzo settore|non profit|non-profit|associazion\w*|fondazion\w*|cooperativ\w*)/.test(text)) categories.add("ets");
  if (/(universit\w*|ricerca|ateneo|ente scientific\w*)/.test(text)) categories.add("research");
  if (/(universit\w*|scuol\w*|istituto scolast|ente formativ\w*|student\w*)/.test(text)) categories.add("education");
  if (/(impres\w*|pmi\b|aziend\w*|startup|societ\w*)/.test(text)) categories.add("business");
  if (/(professionist\w*|psicolog\w*|liber[io] profession)/.test(text)) categories.add("professional");
  if (/(qualsiasi soggetto|persona fisica|altro soggetto|soggetti diversi)/.test(text)) categories.add("other");
  return categories.size ? [...categories] : ["unknown"];
}

/** Compatibility helper for callers that need one label; filters use the full set. */
export function applicantCategory(item: Opportunity): ApplicantCategory {
  return applicantCategories(item)[0];
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
      item.title, item.funder, item.programme, item.summary,
      ...(item.regions ?? []), ...(item.sourceTags ?? []), item.cleanSourceText ?? "",
      ...item.eligibleEntities,
    ].join(" "));
    const matchesText = groups.length === 0 || groups.every((group) => group.some((term) => containsTerm(haystack, term)));
    const matchesMacro = filters.macroAreas.length === 0 || filters.macroAreas.some((area) => item.macroAreas.includes(area));
    const matchesTerritory = territoryMatches(item, filters.territory);
    const matchesStatus = filters.status === "all"
      || (filters.status === "current" && (item.status === "OPEN" || item.status === "UPCOMING"))
      || item.status === filters.status;
    const matchesApplicant = !filters.applicant || filters.applicant === "all" || applicantCategories(item).includes(filters.applicant as ApplicantCategory);
    const matchesFavorites = !filters.favoritesOnly || (filters.favoriteIds ?? []).includes(item.id);
    const matchesNew = !filters.newOnly || isNewOpportunity(item, now);
    const days = item.deadline ? Math.ceil((new Date(item.deadline).getTime() - now.getTime()) / 86_400_000) : undefined;
    const matchesDeadline = filters.deadline === "all" || (days !== undefined && days >= 0 && days <= Number(filters.deadline));
    const matchesRelevance = filters.includeLowRelevance !== false || item.relevance !== "Bassa";
    return matchesText && matchesMacro && matchesTerritory && matchesStatus && matchesApplicant && matchesFavorites && matchesNew && matchesDeadline && matchesRelevance;
  });
}
