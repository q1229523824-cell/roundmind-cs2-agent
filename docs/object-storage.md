# Demo 对象存储

## 为什么需要它

HTTP 上传可能发生在 API 容器，而 Demo 解析将来会由另一个 Celery Worker 执行。容器本地临时文件不能
跨机器共享，因此任务不能只保存 `C:\Temp\xxx.dem` 一类路径。RoundMind 现在先把 Demo 存为私有对象，
任务仅保存随机对象键；Worker 解析时临时下载，完成、失败或玩家选择超时后都会删除对象。

## 本地模式

默认无需任何云账号：

```text
ROUNDMIND_OBJECT_STORAGE=local
ROUNDMIND_LOCAL_DEMO_DIR=
```

留空目录时使用操作系统临时目录。该模式适合单进程开发，不适合多个容器共享。

## Cloudflare R2 / AWS S3

R2 提供 S3 兼容 API，在 Render 环境变量中设置：

```text
ROUNDMIND_OBJECT_STORAGE=r2
S3_BUCKET=你的私有 bucket
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

使用 AWS S3 时将模式设为 `s3`，endpoint 可留空，region 填实际区域。密钥只能放在部署平台的 Secret
环境变量中，不能写入 `.env.example` 的值、更不能提交到 Git。

对象名由服务端 UUID 生成，不使用用户文件名；对象不会公开读取。当前删除语义是 best effort，生产环境
仍建议为 `incoming/` 配置较短的生命周期规则，兜底清理进程崩溃留下的对象。

## 执行流

```text
浏览器 -> FastAPI 分块接收并校验 -> ObjectStore.put -> 随机 object_key
                                            |
                                      DemoJobManager
                                            |
                            materialize -> demoparser2 -> delete
```

`LocalDemoObjectStore` 与 `S3DemoObjectStore` 实现相同协议，因此下一阶段接入 Celery 时不需要改解析器。
