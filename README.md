# RoundMind · CS2 智能复盘 Agent

RoundMind 是一个可解释的 CS2 比赛复盘项目：用户上传 Source 2 `.dem`，后端把原始录像转换为
结构化回合事实，再由受控 Agent 动态选择分析工具，输出带关键回合证据的训练建议。

项目目标、目标架构、量化指标与后续六个迭代版本见 [`cs2agent.md`](cs2agent.md)。

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
- 对击杀、死亡和主动脱离使用同一套事前条件评分，并比较继续接触、脱离重置、等待支援和创造道具条件；
- 网页展示候选动作风险与成立前提，并允许匿名人工选择更合理动作，累计推荐一致率；
- 可选 PostgreSQL 持久化：通过 SQLAlchemy Repository 保存完整比赛对象，Alembic 管理表结构迁移；
- Demo 存储可在本地目录与 S3/Cloudflare R2 间切换，任务只传递随机对象键，解析后自动删除；
- 可选 Redis + Celery 分布式任务：API 只投递 job_id，独立 Worker 解析大 Demo 并共享任务进度；
- 单实例低成本限流在 multipart 解析前保护上传与 Agent 重接口；每个响应携带请求编号并输出结构化访问日志；
- 用户可取消排队、读取名单或解析中的 Demo 任务，任务状态和临时对象均按幂等语义收敛；
- 提供任务成功率、失败数和平均处理耗时，并在网页展示最近任务运行状态；
- 前端错误会附带可检索的请求编号，失败的 Demo 可在当前页面一键重新上传；
- 可选邮箱登录与 JWT 鉴权：Argon2 保存密码，比赛、任务、画像和对话按用户 UUID 隔离；
- 网页提供个人训练中心：登录/注册、历史比赛、跨场玩家画像和单场数据质量门禁；
- 可选 pgvector 混合 RAG：地图过滤 + 向量召回 + 阵营/点位/主题重排，默认仍可完全离线；
- 基于完整交火生成武器分布、步枪/主狙/混合角色画像，并按武器、阵营、点位和距离拆解被先手伤害后的转化差距；
- 可选 DeepSeek Planner，但只有显式启用时才会发送必要统计和问题。
- 受控双 Agent：确定性管道负责解析、质量门禁、指标、评分、证据校验和知识检索；Coach Agent
  只负责理解问题、选择工具并组织建议，Critic 仅在低质量、低置信或高风险判断出现时独立复核；
  网页会列出本次触发复核的具体原因。

## 本地启动

```powershell
python -m pip install -r chapter07_cs2_coach/requirements.txt
python -m chapter07_cs2_coach.local_server
```

启动后会自动打开公开网页并切换到“本地模式”。网页先验证本机
`http://127.0.0.1:8765/api/system/local-bridge`，验证成功后才允许选择 Demo。
大文件只从浏览器传到本机 Python，不经过 Render。需要使用后端自带的简易页面时运行：

```powershell
python -m chapter07_cs2_coach.local_server --local-ui
```

未配置 `DATABASE_URL` 时使用内存仓库；配置 PostgreSQL 后，容器启动时会先执行 Alembic 迁移，再启动
FastAPI。数据库配置、迁移和回退方式见 `docs/postgresql-persistence.md`。
对象存储配置与安全边界见 `docs/object-storage.md`；未配置时保持本地临时存储。
Redis/Celery 的进程职责、配置和 Worker 命令见 `docs/distributed-jobs.md`。
登录开关、API 与所有权边界见 `docs/auth-and-ownership.md`。
玩家运营中心、质量观测与正式启用登录的步骤见 `docs/player-operations-center.md`。
向量生成边界、索引命令和评测方式见 `docs/pgvector-rag.md`。
公开服务的限流、请求追踪和任务取消边界见 `docs/request-controls.md`。

本地服务地址：

- 网页：`http://127.0.0.1:8765`
- Swagger：`http://127.0.0.1:8765/docs`
- 存活检查：`http://127.0.0.1:8765/health`
- 就绪检查：`http://127.0.0.1:8765/ready`

本地模式只监听 `127.0.0.1`。大文件经过本机回环地址传给 Python，不会上传到 Render。
本地桥接标记默认关闭，只有 `local_server` 启动器会显式开启；浏览器的私有网络预检也只允许
RoundMind 官方网页来源，其他网站不能借此调用本地解析接口。

### Windows 免 Python 版本

仓库提供 `Build Windows Local Parser` 工作流。手动运行工作流会生成可下载 ZIP；推送 `v*` 标签时
会同时发布到 GitHub Releases。用户解压后双击 `RoundMind-Local-Parser.exe` 即可，不需要安装
Python。当前程序尚未购买代码签名证书，因此 Windows SmartScreen 可能显示“未知发布者”。

给普通玩家转发时，可同时发送 [中文用户使用手册](docs/user-manual.md) 或
[排版版 PDF](output/pdf/RoundMind-CS2-Agent-用户使用手册-v0.2.0.pdf)。手册包含下载、解压、
本地复盘、结果解读、隐私说明和常见问题排查。

普通用户默认使用完全离线的规则教练。希望获得更自然的个性化对话时，可双击发布包里的
`Start-RoundMind-With-DeepSeek.cmd`，由用户自行输入并承担自己的 DeepSeek API Key。密钥只在
本次本地进程中生效，不进入公开网页、仓库或配置文件；调用前会明确显示数据边界并要求同意。

开发者也可以在 Windows 本地构建：

```powershell
python -m pip install -r chapter07_cs2_coach/requirements-local.txt
python -m pip install pyinstaller==6.22.2
.\scripts\build-windows-local-parser.ps1
```

产物位于 `release/RoundMind-Local-Parser-win-x64.zip`。构建脚本会运行打包后 EXE 的 `--help`
作为最小启动验证。

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
`roundmind-cs2-api`，依赖就绪检查路径为 `/ready`。

最低成本生产部署（Sites + Render Free + Neon Free，暂不启用 Redis/Celery 与 R2）的逐项配置和验收方式见
`docs/low-cost-production-deployment.md`。

### Sites 前端

`frontend/.openai/hosting.json` 关联现有 Sites 项目。后端上线后设置：

```text
ROUNDMIND_API_URL=https://你的后端地址
```

然后重新构建并发布网页。

## Agent 设计

RoundMind 不让模型计算比分、K/D 或 ADR。事实和可复现检查全部由程序完成。Coach Agent 负责选择
受限只读工具和组织报告；Critic 只在风险门槛命中时复核原始证据。普通分析不为固定工作流节点支付
额外模型调用，既保留动态决策能力，也避免模型编造比赛数据。

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

收集大量 Demo 后，可先运行 `python -m chapter07_cs2_coach.demo_catalog_cli` 生成 JSON/CSV 清单。整理器会递归
扫描、用 SHA-256 识别内容重复文件，并快速读取地图、玩家、SteamID、Demo 格式和 CS2 `patch_version`；
它不会把文件修改时间伪装成比赛日期，也不会移动或删除原文件。使用方法与字段边界见
`docs/demo-catalog.md`。
连接本地解析器后，网页“Demo 资料库”也能弹出系统文件夹选择框，按地图和补丁筛选，并从清单直接选择
Demo 与玩家开始解析；绝对路径不会返回公开网页，原文件也不会被任务清理。

在把新 Demo 纳入画像前，建议先运行 `python -m chapter07_cs2_coach.quality_cli`。质量门禁会检查击杀/死亡
交火覆盖率、死亡快照覆盖率、重复事件、未知点位、关键上下文缺失和 SteamID，并输出 `pass/review/fail`。
`fail` 的比赛不应更新长期画像，避免把解析器缺失误判为玩家习惯。详见 `docs/data-quality-gate.md`。

质量完整不代表解析一定正确。`python -m chapter07_cs2_coach.gold_cli` 可以导出匿名待核对摘要，并将
verified 人工金标准与新解析结果逐字段比较，输出关键字段、回合字段和总体准确率；批量 manifest 可用于
游戏版本更新后的解析回归。使用流程和指标定义见 `docs/demo-gold-standard.md`。

GitHub Actions 会自动运行后端、金标准契约和前端构建测试。配置匿名批量报告后，网页训练中心会展示
verified Demo 数量与关键字段准确率；未配置人工真值时只显示“等待真值”，不会展示伪造的准确率。

`/health` 会返回 Render 当前部署的 Git 提交前 12 位、当前队列占用和容量；`/ready` 会实际执行最小数据库
查询。这样既能区分“代码已推送”和“新容器已上线”，也不会在 PostgreSQL 断开时把实例误判为可接流量。

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

`contact_decision_scoring.py` 进一步覆盖全部枪械交火。它只读取交火开始时的先手关系、血量、支援和
准星朝向，不读取最终结果、最终伤害或持续时间。API 返回有结果多样性的代表卡，教练上下文只携带
有界候选动作及其风险，具体设计与防结果泄漏测试见 `docs/contact-decision-scoring.md`。

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
- Demo 任务状态仍保存在进程内，服务重启后会消失；比赛可选持久化到 PostgreSQL；
- 免费云实例适合学习与作品展示，不适合大规模生产流量。
