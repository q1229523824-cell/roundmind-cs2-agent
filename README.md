# RoundMind · CS2 智能复盘 Agent

RoundMind 是一个可解释的 CS2 比赛复盘项目：用户上传 Source 2 `.dem`，后端把原始录像转换为
结构化回合事实，再由受控 Agent 动态选择分析工具，输出带关键回合证据的训练建议。

## 技术架构

```text
React / vinext 公共网页
        │  .dem → 自动读取玩家名单 → 下拉选择
        ▼
FastAPI 异步上传 API
        │  文件校验、排队、进度、自动清理
        ▼
demoparser2（Rust 核心）
        │  回合、击杀、伤害、道具、经济事实
        ▼
LangGraph
prepare → planner → tools → reviewer → knowledge_retriever → reporter
                                      │
                                      └── Dust2 本地战术知识库
        │
        ▼
可追溯的中文复盘报告
```

## 目录

```text
chapter07_cs2_coach/  Python、FastAPI、Demo 解析器、LangGraph 和 Dockerfile
frontend/             React 19、TypeScript、vinext 和 Sites 配置
tests/                后端模型、API、工具、工作流与 Demo 管线测试
render.yaml           Render Blueprint
```

## 后端能力

- `.dem` 最大 500 MB，按 1 MB 分块接收；
- 校验文件扩展名和 `PBDEMS2` Source 2 文件头；
- 最多同时保留两个等待或解析中的任务；
- 自动提取本场玩家名单与 SteamID，由用户下拉选择复盘对象；
- 提取击杀、助攻、死亡、伤害、首轮交火、补枪、道具和装备价值；
- 识别正式比赛开始事件并过滤热身回合、热身击杀与无赢家回合；
- 无论解析成功或失败都会删除临时文件；
- 默认使用确定性 Planner，不产生模型调用费用；
- Dust2 报告会用地图、阵营、点位、问题和比赛证据检索本地战术知识，并返回来源；
- 为每次死亡前接战生成 0—100 风险评分卡，列出判断因素、更优动作与知识依据；
- 基于完整交火生成武器分布、步枪/主狙/混合角色画像，并按武器、阵营、点位和距离拆解被先手伤害后的转化差距；
- 可选 DeepSeek Planner，但只有显式启用时才会发送必要统计和问题。

## 本地启动

```powershell
python -m pip install -r chapter07_cs2_coach/requirements.txt
python -m chapter07_cs2_coach.local_server
```

访问：

- 网页：`http://127.0.0.1:8765`
- Swagger：`http://127.0.0.1:8765/docs`
- 健康检查：`http://127.0.0.1:8765/health`

本地模式只监听 `127.0.0.1`。大文件经过本机回环地址传给 Python，不会上传到 Render。

运行后端测试：

```powershell
python -m unittest discover -s tests -v
```

## 前端

```powershell
cd frontend
npm install
npm run dev
npm run build
```

前端通过运行时变量 `ROUNDMIND_API_URL` 获取后端地址。后端的
`ROUNDMIND_CORS_ORIGINS` 必须包含网页的公网来源。

## 部署

### Render 后端

仓库根目录已经提供 `render.yaml`。在 Render 中使用 Blueprint 连接该仓库即可创建
`roundmind-cs2-api`，健康检查路径为 `/health`。

### Sites 前端

`frontend/.openai/hosting.json` 关联现有 Sites 项目。后端上线后设置：

```text
ROUNDMIND_API_URL=https://你的后端地址
```

然后重新构建并发布网页。

## Agent 设计

RoundMind 不让模型计算比分、K/D 或 ADR。事实由程序计算，Agent 只负责选择受限的只读工具、
审查证据并组织报告。这样既保留 Agent 的动态决策能力，也避免模型编造比赛数据。

六类工具包括：首轮交火、补枪、道具效率、经济决策、残局转化和接战决策。每轮最多运行六个工具，报告中的
结论必须附带指标或相关回合。

### Dust2 战术知识库

第一版知识库位于 `chapter07_cs2_coach/knowledge/dust2_tactics.json`，包含 10 条项目自编的战术原则。
检索器先按地图过滤，再综合阵营、Demo 还原出的点位、问题关键词和分析证据计分，返回最相关的 3 条，
因此完全离线且没有 Embedding 费用。API 的 `knowledge_references` 字段会返回知识 ID、标题、原则、来源、
匹配主题和分数，报告正文也会使用 `[knowledge_id]` 引用。

这是一版可评测的 RAG MVP，而不是模型训练：Demo 事实仍由解析器和确定性工具计算，知识库只为训练建议
提供战术依据。后续可以保持相同返回模型，将关键词检索替换为 Embedding + FAISS/pgvector。

新增知识时请保持一条记录只表达一个原则，并填写稳定的 `id`、适用 `map/sides/locations/topics`、
检索 `keywords`、原则、可执行动作和来源。若使用外部资料，应确认授权并记录具体出处，不能直接复制整篇内容。

接战决策工具会在玩家死亡前重建局势快照，包括地图区域、双方存活人数、最近队友距离、
五秒移动距离、近期有效闪光、实际补枪结果、回合时间、炸弹状态与活跃烟雾。
第一版将 `1000` 地图单位作为明显孤立阈值，
`750` 单位以内作为近距离支持代理；它不会把空间接近直接等同于具备视线或一定能补枪。
烟雾判断只检查烟雾中心是否靠近玩家与最近队友的二维连线，是可解释的遮挡代理，不是地图墙体级真实视线。
系统还会关联击杀者的 Tick 位置与伤害事件，并用队友朝向、距离和烟雾共同估计“补枪准备度”；
该指标仍是显式代理，报告不会把它描述成已经验证的真实视线。

为避免只分析死亡样本，解析器还会把枪械伤害按回合、对手与时间间隔聚合成完整交火片段，
同时保留击杀、死亡和成功脱离。报告只在两组都有足够样本时比较先手转化与补枪准备度，
并把结果表述为本场相关性而不是因果关系。详见 `docs/contact-episodes.md`。

连续上传同一 SteamID 的多场 Demo 后，可以通过 `/api/player-profiles/{steamid}` 聚合玩家画像。
画像会区分单场信号、正在形成的模式和跨场重复习惯，并可用 `map_name` 限定地图。
生成画像前会自动执行数据质量门禁：失败比赛不参与聚合，需复核比赛会降低画像置信度，响应会明确返回
来源、采用、复核与拒绝的场次数，避免把解析缺失误判成长期习惯。
设计与置信度门槛见 `docs/player-profile.md`。
武器分类、角色阈值和被先手伤害切片见 `docs/weapon-role-profile.md`。
本地多 Demo 可使用 `python -m chapter07_cs2_coach.profile_cli` 批量生成画像，重复比赛会按 `match_id` 去重。

在把新 Demo 纳入画像前，建议先运行 `python -m chapter07_cs2_coach.quality_cli`。质量门禁会检查击杀/死亡
交火覆盖率、死亡快照覆盖率、重复事件、未知点位、关键上下文缺失和 SteamID，并输出 `pass/review/fail`。
`fail` 的比赛不应更新长期画像，避免把解析器缺失误判为玩家习惯。详见 `docs/data-quality-gate.md`。

`/health` 会返回 Render 当前部署的 Git 提交前 12 位，便于区分“代码已推送”和“新容器已上线”。

单场分析还会为失败交火检索同阵营、同点位的个人成功样本，把“通用建议”补充为玩家自己已经做到过的
成功基线；结构化结果位于 `personal_contact_contrasts`，设计边界见 `docs/personal-baseline.md`。

`python -m chapter07_cs2_coach.context_cli` 可以把多场质量摘要、武器角色画像、被先手弱点、个人案例、
Dust2 知识和训练优先级组合成不超过 32 KB 的匿名教练上下文。它不会调用模型，也不会包含昵称、SteamID、
Demo 文件名或本地路径；设计见 `docs/coach-context.md`。

可选 DeepSeek 教练通过 `POST /api/coach/chat` 或 `python -m chapter07_cs2_coach.coach_cli` 使用该上下文。
CLI 支持人类可读报告、`--json` 调试输出、`--interactive` 连续追问，以及按匿名玩家和地图隔离的有界
本地会话记忆；原始 Demo、SteamID 和 API Key 不进入会话文件。

公开网页也提供连续教练面板。网页历史由 Sites D1 保存最近 12 条消息，通过匿名 HttpOnly 会话隔离；
重新打开同一玩家与地图时会恢复可见历史，并支持停止生成、重试上一问、复制回答和主动清空。浏览器不能
伪造系统角色，回答仍须通过回合证据与知识 ID 白名单校验。CLI 本地记忆与网页记忆相互独立。
默认返回离线答案；显式启用后，模型 JSON 还必须通过回合证据和知识 ID 白名单校验，否则自动回退。
公网鉴权和限流完成前不要开启付费调用。配置与边界见 `docs/llm-coach.md`。

### 决策评分与评测集

`decision_scoring.py` 根据接战类型、队友距离、五秒移动、有效闪光、人数关系和实际补枪生成风险分。
风险表示“当时接战条件有多危险”，不是根据最终死亡结果倒推玩家一定做错；获得闪光、队友近且完成补枪
会降低分数。评分前还会重建回合阶段、人数、支援、炸弹目标与节奏状态。多场画像会输出带基线、目标、
最近值和趋势的训练目标。网页按风险从高到低展示最多 6 张逐回合决策卡。

`evaluation/dust2_decisions.json` 是第一版 14 场景人工设计的边界回归集，覆盖孤立前压、附近支援、
成功补枪、数据缺失与最后存活者。运行 `python -m chapter07_cs2_coach.evaluation` 可查看准确率。
它目前是工程回归基线，不代表真实教练标注的泛化效果；下一步应加入来自真实 Demo 的盲测样本。

真实评测通过 `annotation_cli` 单独进行，不依赖网页。导出器会分层选择高风险、阈值边界、低风险对照和
低置信度场景，并删除昵称、SteamID、比赛 ID 与 Demo 路径：

```powershell
python -m chapter07_cs2_coach.annotation_cli export `
  --demo "D:\path\match.dem" `
  --player-name "Player" `
  --player-steamid "7656..." `
  --output ".agent_data\annotations\match-v1.json" `
  --limit 8

python -m chapter07_cs2_coach.annotation_cli evaluate `
  --input ".agent_data\annotations\match-v1.json"
```

标注尚未完成时，指标会返回 `null`，不会把系统预测冒充人工真值。`.agent_data` 已被 Git 忽略，
真实标注包不会随代码提交或部署。

## 当前边界

- 玩家昵称与 SteamID 由 Demo 自动提取，同名玩家也能稳定区分；
- 部分新版本 CS2 Demo 可能暂时不兼容，系统会返回受控错误而不是生成空报告；
- 任务和比赛保存在进程内，服务重启后会消失；
- 免费云实例适合学习与作品展示，不适合大规模生产流量。
