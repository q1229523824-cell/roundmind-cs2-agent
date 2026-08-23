import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the RoundMind demo upload experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  const visibleHtml = html.replaceAll("<!-- -->", "");
  assert.match(visibleHtml, /<title>RoundMind · CS2 智能复盘教练<\/title>/i);
  assert.match(visibleHtml, /上传 CS2 Demo 或 JSON/);
  assert.match(visibleHtml, /\.dem 最大 500 MB/);
  assert.match(visibleHtml, /accept="\.dem,\.json,application\/json"/);
  assert.match(visibleHtml, /选择要复盘的玩家/);
  assert.match(visibleHtml, /上传 Demo 后自动读取玩家名单/);
  assert.match(visibleHtml, /接战决策/);
  assert.match(visibleHtml, /<strong>6<\/strong><span>分析工具<\/span>/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("keeps demo uploads bounded and connected to the backend", async () => {
  const [page, configRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/config/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /const MAX_DEMO_MB = 500/);
  assert.match(page, /file\.size > MAX_DEMO_BYTES/);
  assert.match(page, /\/api\/demo-jobs/);
  assert.match(page, /\/player/);
  assert.match(page, /available_players/);
  assert.match(page, /player_options/);
  assert.match(page, /player_steamid/);
  assert.match(page, /request\.upload\.onprogress/);
  assert.match(page, /accept="\.dem,\.json,application\/json"/);
  assert.match(configRoute, /process\.env\.ROUNDMIND_API_URL/);
});
