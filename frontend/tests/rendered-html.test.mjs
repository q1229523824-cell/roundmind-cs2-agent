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
  assert.match(html, /<title>RoundMind · CS2 智能复盘教练<\/title>/i);
  assert.match(html, /上传 CS2 Demo 或 JSON/);
  assert.match(html, /\.dem 最大 200 MB/);
  assert.match(html, /accept="\.dem,\.json,application\/json"/);
  assert.match(html, /Demo 中的游戏昵称/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("keeps demo uploads bounded and connected to the backend", async () => {
  const [page, configRoute] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/config/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /file\.size > 200 \* 1024 \* 1024/);
  assert.match(page, /\/api\/demo-jobs/);
  assert.match(page, /request\.upload\.onprogress/);
  assert.match(page, /accept="\.dem,\.json,application\/json"/);
  assert.match(configRoute, /process\.env\.ROUNDMIND_API_URL/);
});

