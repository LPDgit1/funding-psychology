import assert from "node:assert/strict";
import test from "node:test";
import { expandedTermGroups, filterOpportunities } from "../app/funding-domain.ts";

const base = {
  funder: "Fonte", programme: "Programma", territory: "Italia", eligibleEntities: ["ETS"],
  macroAreas: [], summary: "", relevance: "Alta", relevanceWhy: "", officialUrl: "https://example.test/a",
  lastVerified: "24 agosto 2026", demo: false,
};

const items = [
  { ...base, id: "elder", title: "Servizi per caregiver e anziani", macroAreas: ["Anziani, ageing e caregiver"] },
  { ...base, id: "youth-school", title: "Supporto psicologico a scuola per adolescenti", macroAreas: ["Minori e adolescenti", "Scuola, università e formazione"] },
  { ...base, id: "burnout", title: "Benessere organizzativo e burnout", macroAreas: ["Lavoro, organizzazioni e occupazione"] },
  { ...base, id: "violence", title: "Contrasto alla violenza di genere", macroAreas: ["Violenza, trauma e tutela"] },
  { ...base, id: "addiction", title: "Prevenzione delle dipendenze giovanili", macroAreas: ["Dipendenze"] },
  { ...base, id: "mental", title: "Salute mentale e inclusione sociale", macroAreas: ["Salute mentale e benessere", "Inclusione sociale e vulnerabilità"] },
];

test("synonyms are OR within a concept and AND between concepts", () => {
  const groups = expandedTermGroups("anziani demenza");
  assert.equal(groups.length, 2);
  assert.ok(groups[0].includes("caregiver"));
  assert.ok(groups[1].includes("dementia"));
  assert.deepEqual(filterOpportunities(items, {
    query: "anziani caregiver", macroAreas: [], territory: "all", status: "all", deadline: "all", includeLowRelevance: true,
  }).map((item) => item.id), ["elder"]);
});

test("required psychology search terms return relevant records", () => {
  for (const query of ["anziani", "adolescenti", "scuola", "burnout", "caregiver", "violenza", "dipendenze", "salute mentale", "inclusione sociale"]) {
    const result = filterOpportunities(items, { query, macroAreas: [], territory: "all", status: "all", deadline: "all", includeLowRelevance: true });
    assert.ok(result.length > 0, query);
  }
});
