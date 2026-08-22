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
prepare → planner → tools → reviewer → reporter
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
- 自动提取本场玩家名单，由用户下拉选择复盘对象；
- 提取击杀、助攻、死亡、伤害、首轮交火、补枪、道具和装备价值；
- 无论解析成功或失败都会删除临时文件；
- 默认使用确定性 Planner，不产生模型调用费用；
- 可选 DeepSeek Planner，但只有显式启用时才会发送必要统计和问题。

## 本地启动

```powershell
python -m pip install -r chapter07_cs2_coach/requirements.txt
python -m chapter07_cs2_coach.main
```

访问：

- 网页：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

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

五类工具包括：首轮交火、补枪、道具效率、经济决策和残局转化。每轮最多运行五个工具，报告中的
结论必须附带指标或相关回合。

## 当前边界

- 玩家昵称由 Demo 自动提取，同名玩家后续可升级为 SteamID 选择；
- 部分新版本 CS2 Demo 可能暂时不兼容，系统会返回受控错误而不是生成空报告；
- 任务和比赛保存在进程内，服务重启后会消失；
- 免费云实例适合学习与作品展示，不适合大规模生产流量。
