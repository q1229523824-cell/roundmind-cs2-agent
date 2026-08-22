# RoundMind 公开网页

RoundMind 是 CS2 智能复盘教练的公开前端，使用 vinext 构建并部署到 Sites。

## 功能

- 无后端时仍可体验内置 Mirage 比赛或在浏览器读取结构化 JSON；
- 配置 Python 后端后可以上传最大 500 MB 的 `.dem`；
- 展示上传和解析进度、Agent 证据、训练建议与执行轨迹；
- Demo 在后端解析结束后自动删除，网页不保存原始文件。
- Demo 上传后自动提取昵称与 SteamID，可从下拉框选择复盘对象，并能区分同名玩家。

## 后端连接

网页通过同源 `/api/config` 在运行时读取 `ROUNDMIND_API_URL`，因此后端地址不会硬编码进
客户端源码。部署后应把该变量设置为 FastAPI 服务的 HTTPS 根地址，例如：

```text
ROUNDMIND_API_URL=https://roundmind-cs2-api.onrender.com
```

同时后端的 `ROUNDMIND_CORS_ORIGINS` 必须包含当前 Sites 公网地址。

## 本地命令

```text
npm run dev
npm run build
```
