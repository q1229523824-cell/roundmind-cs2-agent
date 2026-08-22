# RoundMind CS2 Demo 后端

RoundMind 使用 FastAPI 接收 CS2 Source 2 `.dem`，用 `demoparser2` 提取回合结束、击杀、
伤害和闪光事件，再转换成受 Pydantic 约束的 `MatchRecord`。LangGraph Agent 只读取这份
结构化事实，不直接访问原始文件。

## 执行流程

1. API 按 1 MB 分块接收文件，校验 `.dem` 扩展名、`PBDEMS2` 文件头和 500 MB 上限；
2. 临时文件使用服务器生成的随机名称，用户文件名不会参与磁盘路径；
3. 有界线程池异步解析，最多同时保留两个等待或执行中的任务；
4. 提取昵称与 SteamID 供网页选择，按 SteamID 计算击杀、助攻、死亡、伤害、首轮交火、补枪、道具和装备价值；
5. 比赛记录进入现有 LangGraph 工作流，返回证据、工具轨迹与训练建议；
6. 无论成功或失败，`finally` 都会删除临时 Demo。

## 本地启动

```powershell
& "C:\Users\19194\.conda\envs\langchain1.2\python.exe" -m pip install -r chapter07_cs2_coach/requirements.txt
& "C:\Users\19194\.conda\envs\langchain1.2\python.exe" -m chapter07_cs2_coach.local_server
```

命令会打开 `http://127.0.0.1:8765`。浏览器仍会把文件传给 Python，但流量只经过本机
`127.0.0.1`，不会进入 Render 或互联网，因此 300–500 MB Demo 也能快速开始解析。

统计口径：回合使用击杀事件的当前回合编号；装备价值取冻结时间结束时的
`current_equip_value`；有效闪白只统计持续至少 1 秒的敌方玩家，并按 tick 与 SteamID 去重。

## Render 部署

根目录 `render.yaml` 使用 Docker 构建 `roundmind-cs2-api`，健康检查地址为 `/health`。
连接 GitHub 仓库后可直接创建 Blueprint。免费实例磁盘是临时的，本项目不会依赖其持久化。

后端成功部署后，把 Sites 运行时变量 `ROUNDMIND_API_URL` 设置为后端 HTTPS 地址并重新发布
网页即可。不要把 API 密钥写入 Git 或前端环境变量。

## 当前边界

- 玩家名单由 Demo 自动提取，并使用 SteamID 区分同名玩家；
- 残局识别仍保留为后续增强项，当前不会根据不完整事件猜测残局；
- CS2 更新可能改变 Demo 格式，解析失败会返回受控错误而不是生成空比赛；
- 进程内比赛与任务状态会在服务重启后消失，适合作品演示而不是长期数据仓库。

## 面试表达

可以把该模块概括为“异步文件处理管线 + 确定性事实层 + 受控 Agent 决策层”。解析器负责事实，
LangGraph 负责选择分析工具与组织报告；这种分层避免让大模型猜测 K/D、比分或关键回合。
