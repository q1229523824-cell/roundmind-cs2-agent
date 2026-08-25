# RoundMind CS2 Demo 后端

RoundMind 使用 FastAPI 接收 CS2 Source 2 `.dem`，用 `demoparser2` 提取回合结束、击杀、
伤害和闪光事件，再转换成受 Pydantic 约束的 `MatchRecord`。LangGraph Agent 只读取这份
结构化事实，不直接访问原始文件。

## 执行流程

1. API 按 1 MB 分块接收文件，校验 `.dem` 扩展名、`PBDEMS2` 文件头和 500 MB 上限；
2. 临时文件使用服务器生成的随机名称，用户文件名不会参与磁盘路径；
3. 有界线程池异步解析，最多同时保留两个等待或执行中的任务；
4. 提取昵称与 SteamID 供网页选择，按 SteamID 计算回合统计，并重建每次死亡前五秒的接战局势；
5. 比赛记录进入现有 LangGraph 工作流，返回证据、工具轨迹与训练建议；
6. 无论成功或失败，`finally` 都会删除临时 Demo。

跨场画像还会按交火武器生成武器分布与角色倾向，并比较不同武器、阵营、点位和距离下被先造成伤害后的
转化差距。角色只表示可观测行为，不会把 Demo 无法确认的队内战术分工当成事实。

新 Demo 进入长期玩家画像前，可使用 `python -m chapter07_cs2_coach.quality_cli` 运行数据质量门禁。
它会区分解析失败与玩家表现，关键事件覆盖不足的比赛不会被建议用于画像更新。

画像验证后，可使用 `python -m chapter07_cs2_coach.context_cli` 生成匿名、最大 32 KB 的教练上下文包。
该步骤只组合事实、个人案例与本地知识，不调用外部大模型。

`POST /api/coach/chat` 和 `python -m chapter07_cs2_coach.coach_cli` 提供可选 DeepSeek 教练。CLI 默认输出
分段教练报告，`--interactive` 支持连续追问，并将有界匿名会话保存在 `.agent_data/coach_sessions/`；默认离线；
显式启用后的回答必须通过证据引用白名单，否则自动回退确定性报告。

## 本地启动

```powershell
& "C:\Users\19194\.conda\envs\langchain1.2\python.exe" -m pip install -r chapter07_cs2_coach/requirements.txt
& "C:\Users\19194\.conda\envs\langchain1.2\python.exe" -m chapter07_cs2_coach.local_server
```

命令会打开 `http://127.0.0.1:8765`。浏览器仍会把文件传给 Python，但流量只经过本机
`127.0.0.1`，不会进入 Render 或互联网，因此 300–500 MB Demo 也能快速开始解析。

统计口径：回合使用击杀事件的当前回合编号；装备价值取冻结时间结束时的
`current_equip_value`；有效闪白只统计持续至少 1 秒的敌方玩家，并按 tick 与 SteamID 去重。
部分平台 Demo 会在正式比赛前保留热身回合、热身击杀和无赢家的 `round_end`；解析器会根据
`round_announce_match_start` 过滤这些事件，避免热身数据被聚合到正式第一回合。

接战快照使用死亡前一 tick 的 `X/Y/Z`、`last_place_name`、血甲、武器和存活玩家，计算最近
队友距离；同时比较五秒前位置以识别孤立推进。距离只是可解释代理，第一版不声称已经还原墙体、
烟雾遮挡或真实视线，因此报告会区分“附近支持”和“最终是否补枪”。

## Render 部署

根目录 `render.yaml` 使用 Docker 构建 `roundmind-cs2-api`，依赖就绪检查地址为 `/ready`；`/health`
仍用于查看版本、存储后端和队列容量。
连接 GitHub 仓库后可直接创建 Blueprint。免费实例磁盘是临时的，本项目不会依赖其持久化。

后端成功部署后，把 Sites 运行时变量 `ROUNDMIND_API_URL` 设置为后端 HTTPS 地址并重新发布
网页即可。不要把 API 密钥写入 Git 或前端环境变量。

## 当前边界

- 玩家名单由 Demo 自动提取，并使用 SteamID 区分同名玩家；
- 残局识别仍保留为后续增强项，当前不会根据不完整事件猜测残局；
- 接战工具当前使用距离代理，尚未计算地图碰撞、视线和烟雾遮挡；
- CS2 更新可能改变 Demo 格式，解析失败会返回受控错误而不是生成空比赛；
- 进程内比赛与任务状态会在服务重启后消失，适合作品演示而不是长期数据仓库。

## 面试表达

可以把该模块概括为“异步文件处理管线 + 确定性事实层 + 受控 Agent 决策层”。解析器负责事实，
LangGraph 负责选择分析工具与组织报告；这种分层避免让大模型猜测 K/D、比分或关键回合。
