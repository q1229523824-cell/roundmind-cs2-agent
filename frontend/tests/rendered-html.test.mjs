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
  assert.match(visibleHtml, /围绕这名玩家继续追问/);
  assert.match(visibleHtml, /个人训练中心/);
  assert.match(visibleHtml, /先完成一次 Demo 解析/);
  assert.match(visibleHtml, /<strong>6<\/strong><span>分析工具<\/span>/);
  assert.match(visibleHtml, /<strong>8<\/strong><span>决策评测场景<\/span>/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("keeps demo uploads bounded and connected to the backend", async () => {
  const [page, configRoute, coachRoute, coachStore, annotationRoute, annotationStore, schema, migration, hosting] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/config/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/coach/chat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/coach-sessions.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/decision-annotations/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/decision-annotations.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
    readFile(new URL("../drizzle/0001_pretty_skullbuster.sql", import.meta.url), "utf8"),
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /const MAX_DEMO_MB = 500/);
  assert.match(page, /file\.size > MAX_DEMO_BYTES/);
  assert.match(page, /\/api\/demo-jobs/);
  assert.match(page, /\/player/);
  assert.match(page, /available_players/);
  assert.match(page, /player_options/);
  assert.match(page, /player_steamid/);
  assert.match(page, /request\.upload\.onprogress/);
  assert.match(page, /decision_cards/);
  assert.match(page, /contact_decision_cards/);
  assert.match(page, /当时还有哪些选择/);
  assert.match(page, /人工校准样本/);
  assert.match(page, /decision-annotations/);
  assert.match(page, /死亡前接战复盘卡/);
  assert.match(page, /knowledge_references/);
  assert.match(page, /accept="\.dem,\.json,application\/json"/);
  assert.match(configRoute, /process\.env\.ROUNDMIND_API_URL/);
  assert.match(page, /\/api\/coach\/chat/);
  assert.match(page, /\/api\/system\/job-metrics/);
  assert.match(page, /\/api\/match-history/);
  assert.match(page, /roundmind_access_token/);
  assert.match(page, /api\/auth\/\$\{authMode\}/);
  assert.match(page, /历史比赛/);
  assert.match(page, /玩家画像/);
  assert.match(page, /DATA QUALITY GATE/);
  assert.match(page, /CONTINUOUS COACH/);
  assert.match(page, /remembered_turns/);
  assert.match(page, /停止/);
  assert.match(page, /复制回答/);
  assert.match(page, /重试上一问/);
  assert.match(page, /重新上传刚才的 Demo/);
  assert.match(page, /Shift \+ Enter 换行/);
  assert.match(coachRoute, /export async function GET/);
  assert.match(coachRoute, /loadCoachHistory/);
  assert.match(coachRoute, /conversation_history: history/);
  assert.match(coachRoute, /HttpOnly; SameSite=Lax/);
  assert.match(coachStore, /MAX_HISTORY_MESSAGES = 12/);
  assert.match(coachStore, /MAX_HISTORY_CHARS = 18_000/);
  assert.match(coachStore, /DELETE FROM coach_messages/);
  assert.match(schema, /coach_messages/);
  assert.match(schema, /decision_annotations/);
  assert.match(annotationRoute, /export async function PUT/);
  assert.match(annotationRoute, /export async function POST/);
  assert.match(annotationRoute, /scenario_/);
  assert.match(annotationStore, /ON CONFLICT\(player_ref, scenario_ref\) DO UPDATE/);
  assert.match(annotationStore, /agent_action = human_action/);
  assert.match(migration, /CREATE TABLE `decision_annotations`/);
  assert.doesNotMatch(annotationStore, /steamid/i);
  assert.equal(JSON.parse(hosting).d1, "DB");
});
