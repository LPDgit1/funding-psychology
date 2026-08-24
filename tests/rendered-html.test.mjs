import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("home explains the task and discloses prototype data", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Trova finanziamenti per progetti psicologici/);
  assert.match(html, /Che progetto hai in mente/);
  assert.match(html, /Prototipo UX verificabile/);
  assert.match(html, /Le schede sono scenari dimostrativi, non bandi reali/);
  assert.match(html, /L’adapter UE è stato verificato live/);
  assert.match(html, /Minori e adolescenti/);
  assert.match(html, /In arrivo/);
  assert.match(html, /fonte ufficiale/i);
});
