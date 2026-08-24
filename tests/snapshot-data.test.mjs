import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("public snapshot contains live adapter data and explicit fixture boundaries", async () => {
  const snapshot = JSON.parse(await readFile(new URL("../public/data/opportunities.json", import.meta.url), "utf8"));
  assert.equal(snapshot.schemaVersion, 1);
  assert.equal(snapshot.complete, true);
  assert.equal(snapshot.recordCount, 6012);
  assert.equal(snapshot.liveSourceCount, 12);
  assert.equal(snapshot.sources.find((source) => source.sourceId === "veneto-fse-calendar").status, "FIXTURE_ONLY");
  assert.equal(snapshot.opportunities.every((item) => item.demo === false), true);
  assert.equal(snapshot.opportunities.every((item) => item.officialUrl.startsWith("https://")), true);
});
