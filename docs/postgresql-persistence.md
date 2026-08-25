# PostgreSQL 比赛持久化

## 为什么先做这一层

原来的 `MatchRepository` 使用进程内字典。它适合本地学习和测试，但 Render 重启或横向扩容后，上传比赛
无法在新进程中恢复。第一阶段引入 SQLAlchemy Repository，在不改变 Agent、API 和领域模型的前提下，
让比赛数据能够持久化。

## 运行模式

- 未设置 `DATABASE_URL`：使用线程安全的内存仓库；
- 设置 `DATABASE_URL`：使用 `SqlAlchemyMatchRepository`；
- Docker 启动时只有检测到 `DATABASE_URL` 才运行 Alembic；
- `/health` 的 `storage` 字段会返回 `memory`、`sqlite` 或 `postgresql`；
- `/ready` 会执行 `SELECT 1`，数据库不可达时返回 503，避免平台继续向故障实例分流。

生产配置示例只写变量名，不要把真实账号密码提交到 Git：

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/roundmind
```

迁移命令：

```powershell
python -m alembic -c chapter07_cs2_coach/alembic.ini upgrade head
```

## 数据设计

`matches` 表包含：

- `match_id`：领域主键；
- `player_steamid`、`map_name`：常用过滤列和联合索引；
- `payload`：完整、经过 Pydantic 验证的 `MatchRecord` JSON；
- `created_at`、`updated_at`：创建和更新时间。

这一版选择“聚合根 JSON + 常用查询列”，原因是现有分析工具一次读取完整比赛，先替换存储不会迫使全部
算法改写为 ORM 查询。后续只有在需要跨大量比赛执行 SQL 聚合时，再把 `rounds`、`contact_episodes`、
`training_goals` 拆成独立表。这样是分阶段演进，不应在简历中描述成已经完成全量关系模型规范化。

## Repository 边界

`CS2CoachRuntime` 依赖 `MatchRepositoryProtocol`，Agent 不知道数据来自内存还是 PostgreSQL：

```text
FastAPI / Agent
       ↓
MatchRepositoryProtocol
       ├── MatchRepository（内存、本地和测试）
       └── SqlAlchemyMatchRepository（生产数据库）
```

这种结构便于使用 SQLite 做仓库测试，同时在生产使用 PostgreSQL，也为后续给任务、用户和分析报告增加
独立 Repository 留出边界。

## 当前边界

- Demo 临时文件仍在 API 机器本地；
- Demo 任务状态仍在内存；
- 数据库故障会让配置了数据库的服务启动失败，不会静默回退到内存；
- 尚未加入用户归属字段和行级权限；
- 尚未把交火数据拆成独立关系表。

下一阶段是对象存储：先让 API 和未来 Parser Worker 能读取同一份 Demo，再引入 Redis 和 Celery。
