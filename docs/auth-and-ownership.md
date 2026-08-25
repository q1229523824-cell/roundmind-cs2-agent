# 登录与数据归属

## 两种运行模式

- `ROUNDMIND_AUTH_REQUIRED=false`：默认作品展示模式，现有网页可匿名使用；
- `ROUNDMIND_AUTH_REQUIRED=true`：生产模式，比赛、Demo 任务、画像、分析和教练对话都要求 Bearer JWT。

生产模式还必须设置 PostgreSQL `DATABASE_URL` 和至少 32 字符的随机 `ROUNDMIND_JWT_SECRET`。JWT Secret
只放 Render Secret，不写入代码或 Git。密码使用 Argon2 哈希，数据库不保存明文密码；邮箱会规范为小写。

## API

```text
POST /api/auth/register  {"email":"user@example.com","password":"至少10个字符"}
POST /api/auth/login     {"email":"user@example.com","password":"..."}
GET  /api/auth/me        Authorization: Bearer <access_token>
```

登录和注册返回 7 天有效的 HS256 access token。业务接口从 token 的 `sub` 读取不可猜测用户 UUID，写入
`matches.owner_id` 和 Demo 任务的私有状态。查询时同时过滤资源 ID 与 owner ID，对其他用户统一返回 404，
避免泄露资源是否存在。

## 数据流

```text
密码 -> Argon2 verify -> JWT(sub=user_id)
                         |
Authorization Header -> FastAPI dependency -> owner_id
                         |                    |
                         |                    +-> PostgreSQL matches.owner_id
                         +-> Redis Demo job owner_id -> Celery Worker
```

当前提交完成的是后端鉴权与所有权边界。公开网页默认不显示登录框；真正开启生产模式前，应在前端增加登录、
安全保存 token、401 回登录页和退出清理。浏览器场景更成熟的后续方案是短期 access token + HttpOnly refresh
cookie，并配合 CSRF 防护。
