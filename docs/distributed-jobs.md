# Redis + Celery Demo 任务

## 解决什么问题

本地模式的 `ThreadPoolExecutor` 与任务字典只存在于 FastAPI 进程：重启会丢状态，多个 API 实例也互相
看不到任务。分布式模式把职责拆成三部分：

```text
FastAPI：校验、存对象、写任务状态、投递 job_id
Redis：Celery broker + 任务状态 JSON（24 小时 TTL）
Celery Worker：读取对象、demoparser2 解析、写 PostgreSQL、更新 Redis
```

队列只传随机 `job_id`，不传 500 MB Demo，也不传 API Key。Demo 通过 R2/S3 在 API 与 Worker 间共享。

## 开启条件

生产环境需同时具备 PostgreSQL、Redis、私有 R2/S3 bucket，并让 API 与 Worker 使用相同环境变量：

```text
DATABASE_URL=...
REDIS_URL=redis://...
ROUNDMIND_OBJECT_STORAGE=r2
S3_BUCKET=...
S3_ENDPOINT_URL=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
ROUNDMIND_JOB_BACKEND=celery
```

Worker 启动命令：

```powershell
python -m celery -A chapter07_cs2_coach.celery_worker:celery_app worker --loglevel=INFO --concurrency=1
```

Demo 解析是 CPU 和内存密集任务，起步时每个 Worker 建议并发为 1。Celery 设置了 late ack、prefetch=1、
18 分钟软超时和 20 分钟硬超时。R2/S3 的 `incoming/` 仍应配置生命周期规则，以清理由断电或硬超时产生的
孤儿对象。

## 本地回退

不设置或设置 `ROUNDMIND_JOB_BACKEND=local` 时，仍使用原来的线程池，不需要 Redis 和 Celery，适合学习、
单机测试和本地大 Demo 解析。低成本实例默认 `ROUNDMIND_DEMO_WORKERS=1`、
`ROUNDMIND_MAX_PENDING_JOBS=2`；队列满时 API 会在接收大文件前返回 429 和 `Retry-After`，避免先写入
500 MB 临时文件才拒绝。也就是说，引入生产架构不会让开发环境变复杂。
