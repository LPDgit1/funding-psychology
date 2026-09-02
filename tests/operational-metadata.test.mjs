import assert from "node:assert/strict";
import test from "node:test";

const { freshnessWarning, sourceSummary, updatedLabel } = await import("../app/operational-metadata.ts");

const now = new Date("2026-09-01T06:00:00Z");

test("updated label uses Europe/Rome time and human-readable wording", () => {
  assert.equal(updatedLabel({ generatedAt: "2026-09-01T04:17:00Z" }, now), "Aggiornato oggi alle 06:17");
  assert.equal(updatedLabel({ generatedAt: "2026-08-30T04:17:00Z" }, now), "Aggiornato il 30 agosto alle 06:17");
});

test("freshness warning has 36h and 72h thresholds", () => {
  assert.equal(freshnessWarning({ generatedAt: "2026-08-31T00:00:00Z" }, now), null);
  assert.equal(freshnessWarning({ generatedAt: "2026-08-30T12:00:00Z" }, now), "I dati non risultano aggiornati nelle ultime 24 ore.");
  assert.equal(freshnessWarning({ generatedAt: "2026-08-27T05:00:00Z" }, now), "Ultimo aggiornamento disponibile: 5 giorni fa. Alcune opportunità potrebbero essere cambiate.");
});

test("source summary uses consulted live-source count", () => {
  assert.equal(sourceSummary({
    sourceHealth: {
      totalSourceCount: 42,
      liveConfiguredSourceCount: 40,
      successfulSourceCount: 39,
      staleSourceCount: 1,
      errorSourceCount: 0,
      fixtureOnlySourceCount: 2,
    },
  }), "40 fonti consultate");
});

test("source summary falls back to live rows and handles the singular", () => {
  assert.equal(sourceSummary({
    sources: [{ kind: "live" }],
    sourceHealth: { successfulSourceCount: 0 },
  }), "1 fonte consultata");
});
