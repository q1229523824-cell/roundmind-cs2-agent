# RoundMind 公开网页

RoundMind 是 CS2 智能复盘教练的公开前端，使用 vinext 构建并部署到 Sites。

## 功能

- 无后端时仍可体验内置 Mirage 比赛或在浏览器读取结构化 JSON；
- 配置 Python 后端后可以上传最大 500 MB 的 `.dem`；
- 展示上传和解析进度、Agent 证据、训练建议与执行轨迹；
- Demo 在后端解析结束后自动删除，网页不保存原始文件。
- Demo 上传后自动提取昵称与 SteamID，可从下拉框选择复盘对象，并能区分同名玩家。
- 接战决策报告展示死亡前人数、地图区域、队友距离、移动距离和补枪结果。
- Demo 解析完成后可在同一页面连续追问，回答展示回合证据、知识 ID、模型模式和校验警告。
- 匿名网页会话由 HttpOnly Cookie 隔离，最近 12 条消息保存在 Sites D1；不保存原始 Demo、昵称、
  SteamID 或 API Key，并可由用户主动清空。

## 后端连接

网页通过同源 `/api/config` 在运行时读取 `ROUNDMIND_API_URL`，因此后端地址不会硬编码进
客户端源码。部署后应把该变量设置为 FastAPI 服务的 HTTPS 根地址，例如：

```text
ROUNDMIND_API_URL=https://roundmind-cs2-api.onrender.com
```

同时后端的 `ROUNDMIND_CORS_ORIGINS` 必须包含当前 Sites 公网地址。

网页的 `/api/coach/chat` 在服务端读取 D1 历史，再把“最近 12 条匿名问答 + 当前问题”发送给 Python
后端。`.openai/hosting.json` 中的 `d1` 必须保持为 `DB`，部署时 Sites 会创建并应用 `drizzle/` 中的
迁移。DeepSeek Key 只配置在 Python 后端；前端与 D1 均不接触密钥。公网开放模型前仍需增加正式登录、
调用限流和费用上限，未完成前建议后端保持离线教练模式。

## 本地命令

```text
npm run dev
npm run build
```
