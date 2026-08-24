# 可选大模型教练层

大模型教练位于 `coach_llm.py`，默认关闭。它只接收匿名教练上下文和当前问题，不接收 `.dem`、昵称、
SteamID、原始比赛 ID 或本地路径。当前适配 DeepSeek 的 OpenAI 兼容聊天接口。

## 安全执行流

```text
多场比赛事实 → 质量门禁 → 匿名上下文（最大 32 KB）
                            ↓
                      DeepSeek JSON 草稿
                            ↓
              格式校验 + 回合引用白名单 + 知识 ID 白名单
                   ↓通过                     ↓失败
              返回 LLM 回答              返回离线报告
```

模型输出必须提供 `answer`、`evidence_refs`、`knowledge_ids` 和 `follow_up_questions`。代表回合只能引用
上下文中的 `match_XX:R数字`，知识只能引用上下文中已有的 `knowledge_id`。引用越界、非 JSON、网络异常
或模型异常都会被丢弃，用户仍能获得确定性离线结果。

## 本地离线验证

不开启模型时，命令仍会生成离线教练答案：

```powershell
python -m chapter07_cs2_coach.coach_cli `
  --demo-dir ".agent_data\demos" `
  --player-steamid "7656..." `
  --map-name de_dust2 `
  --question "我下一步最应该练什么？" `
  --output ".agent_data\coach\answer.json"
```

## 显式启用 DeepSeek

只有用户确认将“匿名上下文 JSON + 当前问题”发送到 DeepSeek 后，才设置：

```text
ROUNDMIND_ENABLE_LLM_COACH=true
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

密钥只能设置在本机环境或 Render Secret 中，不得进入 Git、前端变量或日志。公网服务在实现用户鉴权、
调用频率限制和费用上限前，应保持 `ROUNDMIND_ENABLE_LLM_COACH=false`。

API 入口为 `POST /api/coach/chat`。不开启模型时同一接口返回 `mode=offline`；启用且回答通过校验时返回
`mode=llm` 和模型名。
