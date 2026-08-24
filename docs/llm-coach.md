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

## 本地单次问答

不开启模型时，命令仍会生成离线教练答案。默认输出适合人阅读的分段报告；需要检查接口原始字段时追加
`--json`。默认会话名为 `default`，同一匿名玩家和地图的最近 12 条消息保存在被 Git 忽略的
`.agent_data/coach_sessions/`：

```powershell
python -m chapter07_cs2_coach.coach_cli `
  --demo-dir ".agent_data\demos" `
  --player-steamid "7656..." `
  --map-name de_dust2 `
  --question "我下一步最应该练什么？" `
  --output ".agent_data\coach\answer.json"
```

如果不希望本次问答读取或保存记忆，追加 `--no-memory`。可以通过 `--session-id aim-training` 创建独立
主题会话；会话名只能使用字母、数字、下划线和连字符。

## 连续交互问答

交互模式只解析一次 Demo，随后可以直接输入问题：

```powershell
python -m chapter07_cs2_coach.coach_cli `
  --demo-dir ".agent_data\demos" `
  --player-steamid "7656..." `
  --map-name de_dust2 `
  --interactive
```

交互命令：

- `/exit`：保存会话并退出。
- `/new`：删除当前会话记忆，开始新对话。

会话文件只包含匿名 `player_ref`、地图、用户问题和教练回答，不包含 SteamID、昵称、Demo、本地路径或
API Key。历史按最近 12 条消息和 18,000 字符双重裁剪，再与匿名教练上下文一同发送给模型。历史仅用于
理解“第三点”“接着刚才”等指代，不能覆盖 Demo 事实或充当回合证据。

如果传统 PowerShell 中文显示异常，先执行：

```powershell
chcp 65001
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

## 网页连续会话

公开前端通过自己的 `/api/coach/chat` 服务端路由调用 Python 后端。网页不会信任浏览器提供的历史，
而是使用匿名 HttpOnly Cookie 从 Sites D1 读取最近 12 条消息，再交给后端的 Pydantic 模型验证角色、
数量和长度。后端只允许 `user` 与 `assistant`，拒绝浏览器注入 `system` 历史。

每轮通过校验的回答才会与问题一起写入 D1；用户可点击“清空对话”删除当前匿名玩家与地图的会话。
CLI 的 `.agent_data/coach_sessions/` 与网页 D1 是两套独立记忆，当前不会互相同步。
