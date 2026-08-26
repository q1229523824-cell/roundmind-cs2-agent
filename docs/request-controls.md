# 请求保护、追踪与任务取消

## 为什么现在做

RoundMind 允许匿名上传最大 500 MB 的 Demo，解析又是 CPU 和内存密集操作。即使队列容量有限，如果没有
HTTP 准入控制，公开服务仍可能先接收大量请求才拒绝。低成本阶段不引入 Redis，先用单实例固定窗口限流
保护最昂贵的接口。

## 默认策略

Render Blueprint 开启以下配置：

```text
ROUNDMIND_RATE_LIMIT_ENABLED=true
ROUNDMIND_TRUST_PROXY_HEADERS=true
ROUNDMIND_UPLOADS_PER_HOUR=6
ROUNDMIND_HEAVY_REQUESTS_PER_MINUTE=30
ROUNDMIND_AUTH_ATTEMPTS_PER_15M=10
```

- Demo 上传：每个客户端地址每小时 6 次；
- `/api/analyze` 与 `/api/coach/chat`：共享每分钟 30 次额度；
- 注册与登录：共享每 15 分钟 10 次额度；
- 超限返回 `429` 和 `Retry-After`，不会进入 multipart 解析或 Agent 工作流。

本地默认关闭限流，避免影响学习和批量测试。`ROUNDMIND_TRUST_PROXY_HEADERS` 只能在明确位于可信反向代理
之后时开启；否则使用 socket 客户端地址，避免客户端伪造转发头。

这是单实例保护，不是分布式强一致配额：服务重启会清空计数，多个 API 实例各自计数。真正扩容后应把
计数器替换为 Redis Lua/原子操作，并按登录用户 ID 优先、IP 兜底生成限流键。

## 请求追踪

每个 HTTP 响应包含随机 `X-Request-ID`。后端同时输出一行 JSON 日志：

```json
{
  "event": "http_request",
  "request_id": "匿名随机编号",
  "method": "POST",
  "path": "/api/demo-jobs",
  "status": 202,
  "duration_ms": 42.1
}
```

日志不记录 Demo 文件名、SteamID、问题正文、Token 或客户端 IP。用户报告问题时只需提供请求编号，即可在
Render 日志中定位同一次调用。

跨域响应会显式暴露 `X-Request-ID`。前端在后端返回错误时把它显示为“请求编号”，便于用户直接复制给维护
者；若 Demo 上传或解析失败，当前页面还会保留浏览器中的文件引用，允许一键重新上传。文件不会写入浏览器
持久存储，刷新页面后引用即消失，后端失败任务的临时对象仍按原有策略删除。

## Demo 取消语义

`DELETE /api/demo-jobs/{job_id}` 取消任务：

- `queued`、`awaiting_player`：立即标记 `cancelled` 并删除对象；
- `discovering`、`parsing`：设置取消标志，当前解析函数释放文件后清理，不保存分析结果；
- `finalizing`、`completed`、`failed`：拒绝取消，避免向用户声称已取消但比赛已经入库；
- 重复取消返回相同 `cancelled` 状态，便于前端安全重试。

Python 线程无法安全强制终止，因此正在执行的底层 demoparser2 调用可能继续占用 CPU 到当前解析步骤结束。
分布式阶段可用 Celery revoke 配合软超时，但仍应保留当前的协作式检查和对象幂等删除。

## 面试解释

- 中间件在框架解析 multipart 前完成资源准入，区别于“接口函数里才检查文件大小”；
- 限流、队列容量和 Worker 并发分别保护请求频率、磁盘占用与 CPU/内存，是三层不同的背压；
- 请求编号建立用户报错、HTTP 响应和后端日志的关联，同时避免记录敏感业务正文；
- 取消采用状态机和协作式取消，明确承认 Python 线程不能安全强杀，而不是把 UI 状态变化冒充计算已停止。
