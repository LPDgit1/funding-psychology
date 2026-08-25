import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  applicantCategories,
  expandedTermGroups,
  filterOpportunities,
  territoryMatches,
  USER_FACING_THEMES,
  userFacingThemes,
} from "../app/funding-domain.ts";

const base = {
  funder: "Fonte", programme: "Programma", territory: "Italia", eligibleEntities: ["ETS"],
  macroAreas: [], summary: "", relevance: "Alta", relevanceWhy: "", officialUrl: "https://example.test/a",
  lastVerified: "24 agosto 2026", demo: false,
};

const items = [
  { ...base, id: "elder", title: "Servizi per caregiver e anziani", macroAreas: ["Anziani, ageing e caregiver"] },
  { ...base, id: "caregiver-dementia", title: "Servizi per caregiver e demenza", macroAreas: [] },
  { ...base, id: "caregiver-only", title: "Supporto per caregiver", macroAreas: [] },
  { ...base, id: "dementia-only", title: "Ricerca sulla demenza", macroAreas: [] },
  { ...base, id: "youth-school", title: "Supporto psicologico a scuola per adolescenti", macroAreas: ["Minori e adolescenti", "Scuola, università e formazione"] },
  { ...base, id: "burnout", title: "Benessere organizzativo e burnout", macroAreas: ["Lavoro, organizzazioni e occupazione"] },
  { ...base, id: "violence", title: "Contrasto alla violenza di genere", macroAreas: ["Violenza, trauma e tutela"] },
  { ...base, id: "addiction", title: "Prevenzione delle dipendenze giovanili", macroAreas: ["Dipendenze"] },
  { ...base, id: "mental", title: "Salute mentale e inclusione sociale", macroAreas: ["Salute mentale e benessere", "Inclusione sociale e vulnerabilità"] },
];

const commonCases = JSON.parse(readFileSync(new URL("./fixtures/search-cases.json", import.meta.url), "utf8"));
const fixtureItems = [
  ["fixture-dementia-caregiver", "Programma caregiver e demenza"],
  ["fixture-youth-mental-health", "Salute mentale degli adolescenti"],
  ["fixture-school-bullying", "Prevenzione bullismo a scuola"],
  ["fixture-gender-violence", "Violenza di genere"],
  ["fixture-youth-addictions", "Dipendenze e giovani"],
  ["fixture-worker-burnout", "Burnout dei lavoratori"],
  ["fixture-older-psychology", "Psicologia per anziani"],
  ["fixture-migration-trauma", "Migrazione e trauma"],
  ["fixture-disability-inclusion", "Inclusione sociale e disabilità"],
  ["fixture-ai-mental-health", "AI e salute mentale"],
].map(([id, title]) => ({ ...base, id, title }));

const filters = (query) => ({ query, themes: [], territory: "all", status: "all", deadline: "all", includeLowRelevance: true });

test("synonyms are OR within a concept and AND between concepts", () => {
  const groups = expandedTermGroups("anziani demenza");
  assert.equal(groups.length, 2);
  assert.ok(!groups[0].includes("caregiver"));
  assert.ok(groups[1].includes("dementia"));
  assert.deepEqual(filterOpportunities(items, filters("caregiver demenza")).map((item) => item.id), ["caregiver-dementia"]);
  assert.deepEqual(filterOpportunities(items, filters("anziani caregiver")).map((item) => item.id), ["elder"]);
});

test("common search fixture uses the same concept semantics in the frontend", () => {
  for (const { query, expected } of commonCases) {
    const result = filterOpportunities(fixtureItems, filters(query)).map((item) => item.id);
    assert.deepEqual(result, expected, query);
  }
});

test("required psychology search terms return relevant records", () => {
  for (const query of ["anziani", "adolescenti", "scuola", "burnout", "caregiver", "violenza", "dipendenze", "salute mentale", "inclusione sociale"]) {
    assert.ok(filterOpportunities(items, filters(query)).length > 0, query);
  }
});

test("reverse synonym lookup works from any term in the group", () => {
  assert.ok(expandedTermGroups("giovani")[0].includes("adolescenti"));
  assert.ok(expandedTermGroups("adolescenti")[0].includes("giovani"));
  assert.ok(expandedTermGroups("AI")[0].includes("artificial intelligence"));
});

test("user-facing themes map internal areas and share filter semantics", () => {
  assert.equal(USER_FACING_THEMES.length, 8);
  const item = { ...base, id: "theme-item", macroAreas: ["Disabilità e neurodiversità", "Inclusione sociale e vulnerabilità"] };
  assert.deepEqual(userFacingThemes(item), ["Inclusione, disabilità e fragilità"]);
  assert.equal(filterOpportunities([item], { ...filters(""), themes: ["Inclusione, disabilità e fragilità"] }).length, 1);
  assert.equal(filterOpportunities([item], { ...filters(""), themes: ["Digitale, AI e ricerca"] }).length, 0);
});

test("applicant categories are multilabel and ETS includes public plus ETS", () => {
  const item = { ...base, eligibleEntities: ["Comuni e ETS"] };
  assert.deepEqual(applicantCategories(item).sort(), ["ets", "public"]);
  assert.equal(filterOpportunities([item], { ...filters(""), applicant: "ets" }).length, 1);
});

test("territory filter recognizes Veneto in a multi-region record", () => {
  const multi = { ...base, id: "multi", territory: "Multi-regione", regions: ["Veneto", "Friuli-Venezia Giulia"] };
  const other = { ...base, id: "other-region", territory: "Multi-regione", regions: ["Lombardia", "Emilia-Romagna"] };
  assert.equal(territoryMatches(multi, "Veneto"), true);
  assert.equal(territoryMatches(other, "Veneto"), false);
  assert.equal(territoryMatches({ ...base, territory: "Unione Europea" }, "Europa"), true);
});
