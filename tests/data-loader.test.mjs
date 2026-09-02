import assert from "node:assert/strict";
import test from "node:test";

const {
  loadArchiveSnapshot,
  loadCurrentSnapshot,
  versionedUrl,
} = await import("../app/data-loader.ts");

function snapshot(generatedAt, title = "Remote opportunity") {
  return {
    schemaVersion: 2,
    dataset: "current",
    generatedAt,
    recordCount: 1,
    liveSourceCount: 1,
    sourceCount: 1,
    sources: [],
    opportunities: [{
      id: "remote:1",
      title,
      status: "OPEN",
      relevance: "Media",
      officialUrl: "https://example.test/remote",
    }],
  };
}

function response(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("remote current is preferred and versioned from the daily health file", async () => {
  const calls = [];
  const health = { snapshotGeneratedAt: "2026-09-02T06:15:12Z", LIVE: ["source"] };
  const loaded = await loadCurrentSnapshot(async (url, options) => {
    calls.push({ url: String(url), options });
    if (String(url).includes("daily-sync-latest")) return response(health);
    return response(snapshot(health.snapshotGeneratedAt, "Remote current"));
  });

  assert.equal(loaded.origin, "remote");
  assert.equal(loaded.snapshot.opportunities[0].title, "Remote current");
  assert.equal(loaded.remoteVersion, health.snapshotGeneratedAt);
  assert.equal(calls.length, 2);
  assert.match(calls[1].url, /opportunities-current\.json\?version=2026-09-02T06%3A15%3A12Z/);
  assert.equal(calls[0].options.cache, "no-store");
});

test("remote failure falls back silently to the bundled current snapshot", async () => {
  const calls = [];
  const loaded = await loadCurrentSnapshot(async (url) => {
    const value = String(url);
    calls.push(value);
    if (value.includes("raw.githubusercontent.com")) return response({ error: "temporarily unavailable" }, 503);
    return response(snapshot("2026-09-01T04:00:00Z", "Bundled current"));
  });

  assert.equal(loaded.origin, "bundled");
  assert.equal(loaded.snapshot.opportunities[0].title, "Bundled current");
  assert.ok(calls.some((url) => url === "/data/opportunities-current.json"));
});

test("invalid or unexpectedly empty remote JSON falls back to bundled data", async () => {
  const loaded = await loadCurrentSnapshot(async (url) => {
    const value = String(url);
    if (value.includes("daily-sync-latest")) return response({ snapshotGeneratedAt: "2026-09-02T06:15:12Z" });
    if (value.includes("raw.githubusercontent.com")) return response({ generatedAt: "2026-09-02T06:15:12Z", opportunities: [] });
    return response(snapshot("2026-09-01T04:00:00Z", "Bundled after invalid remote"));
  });

  assert.equal(loaded.origin, "bundled");
  assert.equal(loaded.snapshot.opportunities[0].title, "Bundled after invalid remote");
});

test("archive loader is independently remote-first and remains lazy to its caller", async () => {
  const calls = [];
  const loaded = await loadArchiveSnapshot("2026-09-02T06:15:12Z", async (url) => {
    calls.push(String(url));
    if (String(url).includes("opportunities-archive")) return response({
      ...snapshot("2026-09-02T06:15:12Z", "Remote archive"),
      dataset: "archive",
      opportunities: [{ id: "remote:closed", title: "Remote archive", status: "CLOSED", officialUrl: "https://example.test/archive" }],
    });
    throw new Error("unexpected request");
  });

  assert.equal(loaded.origin, "remote");
  assert.equal(loaded.snapshot.dataset, "archive");
  assert.equal(calls.length, 1);
  assert.match(calls[0], /opportunities-archive\.json\?version=2026-09-02T06%3A15%3A12Z/);
});

test("versioned URLs do not use random cache busting", () => {
  assert.equal(versionedUrl("https://example.test/data.json", "2026-09-02T06:15:12Z"), "https://example.test/data.json?version=2026-09-02T06%3A15%3A12Z");
  assert.equal(versionedUrl("/data.json"), "/data.json");
});
