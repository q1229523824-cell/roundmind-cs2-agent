# 最低成本生产部署

## 第一阶段架构

```text
Sites 前端
    -> Render Free：FastAPI + 同进程 Demo 解析
        -> Neon Free：PostgreSQL + pgvector
```

第一阶段只增加持久化数据库与零 API 费用的本地哈希向量检索。保持以下开关关闭：

- `ROUNDMIND_JOB_BACKEND=local`：不部署 Redis 和 Celery Worker；
- `ROUNDMIND_OBJECT_STORAGE=local`：Demo 解析完成后删除临时对象；
- `ROUNDMIND_AUTH_REQUIRED=false`：前端登录界面完成前不强制登录；
- `ROUNDMIND_ENABLE_LLM_COACH=false`：不产生 DeepSeek 调用费用。

这套组合适合学习、作品集和少量体验用户。Render Free 休眠后的首次请求会较慢，大 Demo 仍需要经过公网
上传到 Render；这属于成本优先方案，不等于高并发生产方案。

## 1. 创建 Neon 数据库

1. 在 Neon 创建名为 `roundmind-cs2` 的免费项目，区域尽量靠近 Render 当前服务区域。
2. 在 **Connect** 中选择 **Direct connection**，复制完整连接串。
3. 不要选择带 `-pooler` 的连接串：Docker 启动时会执行 Alembic 迁移，迁移应使用 direct 连接。
4. 不需要手工建表。容器启动时会执行 `alembic upgrade head`，迁移会创建 `vector` 扩展、业务表和索引。

连接串包含数据库用户名和密码，只能填写到 Render Secret，不能粘贴到聊天、截图、README 或 Git。

## 2. 设置 Render 环境变量

打开现有 `roundmind-cs2-agent` 服务的 **Environment**，设置：

```text
DATABASE_URL=<Neon Direct connection string>
ROUNDMIND_CORS_ORIGINS=https://roundmind-cs2-coach.kclespark.chatgpt.site
ROUNDMIND_KNOWLEDGE_BACKEND=pgvector
ROUNDMIND_JOB_BACKEND=local
ROUNDMIND_MAX_PENDING_JOBS=2
ROUNDMIND_DEMO_WORKERS=1
ROUNDMIND_OBJECT_STORAGE=local
ROUNDMIND_AUTH_REQUIRED=false
ROUNDMIND_ENABLE_LLM_COACH=false
```

保存后让 Render 重新部署。不要创建新的 Web Service；继续使用已有服务，避免产生两个后端和错误的前端地址。

## 3. 验收

访问：

```text
https://roundmind-cs2-agent.onrender.com/ready
```

成功响应至少应包含：

```json
{
  "status": "ready",
  "storage": "postgresql"
}
```

再访问 `/health`，确认 `demo_storage=local`、`job_backend=memory`、`auth=disabled`，以及
`pending_jobs` 没有超过 `max_pending_jobs`。

然后在网页上传一份小 Demo 并完成一次解析。再次刷新网页或等待后端重启后，数据库中的比赛记录仍应存在。
第一次触发知识检索时会把版本化知识同步进 pgvector；向量由本地确定性算法生成，不调用外部 Embedding API。

如果部署失败，先查看 Render 日志中 Alembic 的第一条错误。常见原因是误用了 pooled 连接串、连接串被截断，
或 Neon 项目区域暂时不可达。

## 4. 第二阶段再启用 R2

R2 适合未来把 API 与 Celery Worker 分开，但当前同进程解析不依赖它。Cloudflare 当前要求先启用 R2 才能生成
S3 API 凭据，因此第一阶段先不创建凭据，也不要求绑定付款方式。

确定需要跨容器共享 Demo 后，再创建私有 bucket，并只授予该 bucket 的 Object Read & Write 权限：

```text
ROUNDMIND_OBJECT_STORAGE=r2
S3_BUCKET=<private bucket>
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY_ID=<Render Secret>
S3_SECRET_ACCESS_KEY=<Render Secret>
```

R2 密钥只能直接录入 Render，不进入本地 `.env`、聊天记录或 Git。最后再为 `incoming/` 配置短生命周期规则，
兜底清理进程异常退出后残留的 Demo。

## 面试解释

- 通过 Repository 协议把内存存储替换为 SQLAlchemy/PostgreSQL，没有侵入 Agent 与领域模型；
- 用 Alembic 在容器启动时管理数据库版本，部署失败时显式失败而不是静默退回内存；
- PostgreSQL 同时承载业务数据与 pgvector，减少一套向量数据库的运维成本；
- 通过环境变量切换本地/云端组件，低流量阶段保持单体部署，达到流量阈值后再启用 R2、Redis 和 Celery。
