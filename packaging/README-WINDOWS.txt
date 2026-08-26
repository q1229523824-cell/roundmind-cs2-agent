RoundMind CS2 本地解析器（Windows x64）
========================================

使用方法：

1. 解压整个 ZIP，不要只把 EXE 单独拖出来。
2. 双击 RoundMind-Local-Parser.exe。
3. 保持黑色窗口打开，浏览器会自动进入 RoundMind“本地模式”。
4. 网页显示“本地解析器已连接”后，可逐个选择 .dem，也可在“Demo 资料库”选择整个文件夹。
5. 资料库会显示地图、补丁版本、重复文件和玩家；选择一场后再开始完整解析。
6. 使用结束后关闭黑色窗口，或在窗口中按 Ctrl+C。

使用自己的 DeepSeek API（可选）：

1. 双击 Start-RoundMind-With-DeepSeek.cmd，而不是普通 EXE。
2. 阅读将要发送的数据说明，输入 YES 表示同意。
3. 输入你自己的 DeepSeek API Key；输入内容不会显示。
4. 密钥只在本次程序运行中保留，关闭窗口后失效，不会写入网页、仓库或配置文件。
5. 原始 Demo 不会交给大模型；大模型只接收匿名化教练上下文、当前问题和最近对话。

隐私说明：

- 本地模式只监听 127.0.0.1，Demo 不会上传到 Render。
- 资料库不会把磁盘绝对路径返回公开网页，也不会删除原文件。
- 原始 Demo 解析结束后会删除临时副本。
- 默认不调用大模型；只有用户另行显式配置并启用时才会调用。
- 不要把自己的 API Key 发给项目作者或其他人；产生的模型费用由密钥所有者承担。

常见问题：

- Windows SmartScreen 可能提示“未知发布者”，因为当前测试版尚未购买代码签名证书。
- 如果浏览器禁止公开网页连接本机，请关闭程序后使用命令：
  RoundMind-Local-Parser.exe --local-ui
- 端口 8765 被占用时，可使用：
  RoundMind-Local-Parser.exe --port 8766 --local-ui
- 只检查某个 Demo 是否兼容：
  RoundMind-Local-Parser.exe --check-demo "D:\path\match.dem"
