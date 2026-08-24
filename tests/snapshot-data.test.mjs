import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("public snapshot contains live adapter data and explicit fixture boundaries", async () => {
  const snapshot = JSON.parse(await readFile(new URL("../public/data/opportunities-current.json", import.meta.url), "utf8"));
  const archive = JSON.parse(await readFile(new URL("../public/data/opportunities-archive.json", import.meta.url), "utf8"));
  assert.equal(snapshot.schemaVersion, 2);
  assert.equal(snapshot.dataset, "current");
  assert.equal(snapshot.complete, true);
  assert.ok(snapshot.recordCount > 0);
  assert.ok(snapshot.recordCount < 2000);
  assert.equal(snapshot.liveSourceCount, 12);
  assert.equal(snapshot.sources.find((source) => source.sourceId === "veneto-fse-calendar").status, "FIXTURE_ONLY");
  assert.equal(snapshot.opportunities.every((item) => item.demo === false), true);
  assert.equal(snapshot.opportunities.every((item) => item.officialUrl.startsWith("https://")), true);
  assert.equal(snapshot.opportunities.some((item) => item.status === "CLOSED"), false);
  assert.equal(archive.dataset, "archive");
  assert.equal(archive.opportunities.every((item) => item.status === "CLOSED"), true);
});
