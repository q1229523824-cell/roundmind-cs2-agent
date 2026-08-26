# 本地 Demo 自动整理

`demo_catalog_cli` 用于先盘点大量 `.dem`，再决定哪些文件值得做完整逐回合解析。它只读取 Demo 头、玩家表并计算文件指纹，不会调用大模型，也不会移动或删除原文件。

如果使用 RoundMind 本地解析器，公开网页现在也提供相同能力：切换到“本地模式”，进入“Demo 资料库”，点击“选择并扫描文件夹”。Windows 会弹出原生文件夹选择框；授权后网页可按地图和游戏补丁筛选、查看重复文件、选择 Demo 与玩家并直接开始解析。绝对路径只保留在本地解析器的一小时内存会话中，不返回网页。

## 使用

在项目根目录执行：

```powershell
python -m chapter07_cs2_coach.demo_catalog_cli `
  --demo-dir "D:\CS2-Demos" `
  --output-dir ".agent_data\catalog"
```

默认递归扫描子目录，最多读取 1000 个文件。只扫描第一层时添加 `--no-recursive`；可用 `--max-files 2000` 调整数量。输出包含：

- `demo-catalog.json`：适合后续程序、Agent 和数据管线读取；
- `demo-catalog.csv`：带 UTF-8 BOM，可直接用 Excel 打开；
- SHA-256 内容指纹与重复文件位置；
- 地图、服务器名、Demo 类型、格式、CS2 `patch_version`；
- 玩家昵称、SteamID 和解析状态。

## 字段边界

| 字段 | 可靠性与含义 |
| --- | --- |
| `map_name`、`players`、`patch_version` | 直接来自 Demo，读取成功时可作为后续解析输入 |
| `demo_id` | 整个文件的 SHA-256；内容相同才判为重复 |
| `source` | 只在服务器名或文件名出现 FACEIT、HLTV、PGL 等明确文本时提示来源，并附置信度 |
| `file_modified_at` | 文件系统修改时间，不等于比赛开赛时间 |
| `match_date` | Demo 头没有可信时间时保持 `null`，不根据文件名猜测 |
| `status` | `metadata_ready`、`duplicate` 或 `failed`；失败不会伪造空比赛 |

JSON/CSV 含昵称和 SteamID，只应保存在本地；对外分享前应删除玩家身份列。快速目录扫描也不等于解析准确率验证：纳入画像前仍需运行质量门禁，发布解析器更新前仍需用人工金标准回归。

## 推荐数据流

1. 将不同来源的 Demo 放入一个本地总目录，可保留原有子目录。
2. 运行目录整理器，先移除或忽略 `duplicate`。
3. 按地图、补丁版本和来源挑选覆盖面更广的样本。
4. 对目标 SteamID 运行 `profile_cli` 和 `quality_cli`。
5. 从每个补丁版本挑少量 Demo 建立人工金标准，避免游戏更新后静默解析错误。

网页资料库适合交互挑选；命令行输出的 JSON/CSV 适合长期数据治理和后续程序处理。两者复用同一套扫描、指纹和元数据模型。
