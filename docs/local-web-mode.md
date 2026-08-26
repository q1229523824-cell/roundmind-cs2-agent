# 网页本地解析模式

## 解决的问题

云端模式必须先把 `.dem` 上传到美国节点。300–500 MB 文件的等待时间主要来自用户上行带宽，
并且免费实例只能单任务解析。本地模式让公开 React 网页继续负责交互，但把 Demo 解析交给用户电脑。

```text
公开网页
  → 检测 http://127.0.0.1:8765/api/system/local-bridge
  → Demo 仅通过回环地址传给本机 FastAPI
  → demoparser2 在本机生成 MatchRecord
  → 本机 LangGraph 工作流生成证据化报告
```

原始 Demo 不进入 Render，也不会交给大模型。只有用户显式启用本机 DeepSeek 配置时，匿名上下文才会
按现有教练服务规则发送给模型。

## 启动

### 普通用户：Windows 压缩包

从 GitHub Actions 构建产物或 Releases 下载 `RoundMind-Local-Parser-win-x64.zip`，完整解压后双击
`RoundMind-Local-Parser.exe`。压缩包已经包含 Python 解释器和运行依赖。

当前测试版没有商业代码签名证书，Windows SmartScreen 可能显示“未知发布者”。正式公开推广前应
增加签名、安装器哈希与发布来源验证。

### 开发者：Python 启动

在项目根目录运行：

```powershell
python -m pip install -r chapter07_cs2_coach/requirements.txt
python -m chapter07_cs2_coach.local_server
```

启动器只监听 `127.0.0.1:8765`，随后打开：

```text
https://roundmind-cs2-agent.yangmiaomiao37.chatgpt.site/?processing=local#workspace
```

网页显示“本地解析器已连接”后再选择 Demo。关闭终端或按 `Ctrl+C` 即停止本地服务。

## 安全边界

- 本地桥接必须由 `local_server` 显式开启，普通 Render API 会返回 `enabled: false`；
- 服务不监听 `0.0.0.0`，局域网其他设备不能访问；
- 私有网络预检只允许代码中配置的 RoundMind 第一方来源；
- 文件名不参与磁盘路径，临时对象使用随机键；
- 成功、失败、取消和玩家选择超时都会删除临时 Demo；
- 网页切换解析模式前必须先结束当前任务，避免失去取消句柄。

## 当前限制

- 源码启动需要 Python；普通用户可改用 Windows x64 免 Python 压缩包；
- 本地服务关闭后，内存中的比赛与任务状态不会保留；
- 浏览器或企业安全策略可能阻止网页访问回环地址，此时可使用 `--local-ui`；
- 当前 PyInstaller 版本是免安装 ZIP，不包含自动更新器；升级时需要重新下载新版本。
