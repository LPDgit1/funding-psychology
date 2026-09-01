import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("public snapshot contains live adapter data and explicit fixture boundaries", async () => {
  const snapshot = JSON.parse(await readFile(new URL("../public/data/opportunities-current.json", import.meta.url), "utf8"));
  const archive = JSON.parse(await readFile(new URL("../public/data/opportunities-archive.json", import.meta.url), "utf8"));
  assert.equal(snapshot.schemaVersion, 2);
  assert.equal(snapshot.dataset, "current");
  // A temporary upstream outage may leave one source STALE/ERROR while the
  // previously verified records remain published; that state is explicit in
  // the envelope and is not a malformed snapshot.
  assert.equal(snapshot.complete, !snapshot.sources.some((source) => ["ERROR", "STALE"].includes(source.status)));
  assert.ok(snapshot.recordCount > 0);
  // The official feeds grow over time; keep a broad guard against accidental
  // explosions while allowing the current live set to exceed the v0.2 bound.
  assert.ok(snapshot.recordCount < 2500);
  assert.equal(new Set(snapshot.opportunities.map((item) => item.id)).size, snapshot.recordCount);
  assert.ok(snapshot.liveSourceCount >= 10);
  assert.equal(snapshot.sourceHealth.totalSourceCount, snapshot.sourceCount);
  assert.equal(snapshot.sourceHealth.successfulSourceCount, snapshot.liveSourceCount);
  assert.equal(snapshot.sourceHealth.staleSourceCount, snapshot.sources.filter((source) => source.status === "STALE").length);
  assert.equal(snapshot.sourceHealth.errorSourceCount, snapshot.sources.filter((source) => source.status === "ERROR").length);
  assert.equal(snapshot.sourceHealth.fixtureOnlySourceCount, snapshot.sources.filter((source) => source.status === "FIXTURE_ONLY").length);
  assert.equal(snapshot.sources.find((source) => source.sourceId === "veneto-fse-calendar").status, "FIXTURE_ONLY");
  assert.equal(snapshot.opportunities.every((item) => item.demo === false), true);
  assert.equal(snapshot.opportunities.every((item) => item.officialUrl.startsWith("https://")), true);
  assert.equal(snapshot.opportunities.some((item) => item.status === "CLOSED"), false);
  assert.equal(archive.dataset, "archive");
  assert.equal(archive.opportunities.every((item) => item.status === "CLOSED"), true);
});
