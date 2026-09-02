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

test("home presents the simplified public vocabulary", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Trova finanziamenti per progetti psicologici/);
  assert.match(html, /Che progetto hai in mente/);
  assert.doesNotMatch(html, /snapshot|macroarea|Archivio CLOSED|\bOPEN\b|\bUPCOMING\b|\bCLOSED\b/);
  assert.doesNotMatch(html, /Prototipo UX verificabile|scenari dimostrativi|non bandi reali/i);
  assert.match(html, /Aree di interesse|Scegli un.area di interesse/);
  assert.match(html, /Minori, giovani e famiglie/);
  assert.match(html, /Inclusione, disabilità e fragilità/);
  assert.match(html, /Scaduti/);
  assert.match(html, /Tutti i temi/);
  assert.match(html, /Altri filtri/);
  assert.doesNotMatch(html, /Consulta anche i bandi scaduti/);
  assert.doesNotMatch(html, /temporaneamente non disponibili|non ancora automatizzate|Alcune fonti non sono state aggiornate oggi/);
  assert.match(html, /In arrivo/);
  assert.match(html, /fonte ufficiale/i);
});
