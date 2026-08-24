export type OpportunityStatus = "OPEN" | "UPCOMING" | "CLOSED" | "UNKNOWN";
export type Relevance = "Alta" | "Media" | "Bassa";

export type Opportunity = {
  id: string;
  title: string;
  funder: string;
  programme: string;
  status: OpportunityStatus;
  territory: string;
  deadline?: string;
  openingDate?: string;
  amount?: string;
  eligibleEntities: string[];
  macroAreas: string[];
  summary: string;
  relevance: Relevance;
  relevanceWhy: string;
  officialUrl: string;
  lastVerified: string;
  demo: boolean;
  sourceId?: string;
};

const SYNONYMS: Record<string, string[]> = {
  anziani: ["ageing", "elderly", "older people", "caregiver"],
  adolescenti: ["minori", "youth", "children", "young people"],
  disabilita: ["disabilità", "neurodiversità", "inclusione"],
  burnout: ["stress lavoro", "benessere organizzativo"],
  scuola: ["scolastico", "formazione", "studenti"],
};

function normalized(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("it-IT");
}

export function expandedTerms(query: string): string[] {
  const base = normalized(query).split(/\s+/).filter(Boolean);
  const additions = base.flatMap((term) => SYNONYMS[term] ?? []);
  return [...new Set([...base, ...additions.map(normalized)])];
}

export function filterOpportunities(
  items: Opportunity[],
  filters: { query: string; macroAreas: string[]; territory: string; status: string; deadline: string },
  now = new Date(),
) {
  const terms = expandedTerms(filters.query);
  return items.filter((item) => {
    const haystack = normalized([
      item.title, item.funder, item.programme, item.territory, item.summary,
      ...item.macroAreas, ...item.eligibleEntities,
    ].join(" "));
    const matchesText = terms.length === 0 || terms.every((term) => haystack.includes(term));
    const matchesMacro = filters.macroAreas.length === 0 || filters.macroAreas.some((area) => item.macroAreas.includes(area));
    const matchesTerritory = filters.territory === "all" || item.territory === filters.territory;
    const matchesStatus = filters.status === "all" || item.status === filters.status;
    const days = item.deadline ? Math.ceil((new Date(item.deadline).getTime() - now.getTime()) / 86_400_000) : undefined;
    const matchesDeadline = filters.deadline === "all" || (days !== undefined && days >= 0 && days <= Number(filters.deadline));
    return matchesText && matchesMacro && matchesTerritory && matchesStatus && matchesDeadline;
  });
}
