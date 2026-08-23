# 多场玩家画像

单场 Demo 只能说明当场发生了什么。玩家画像使用 SteamID 关联同一玩家，并可按地图筛选多场比赛，
用于判断一个信号是单场波动、正在形成的模式，还是跨场重复习惯。

## 画像内容

- 聚合交火数、回合数和比赛数；
- 先造成伤害/被先造成伤害的转化率与置信区间；
- 附近队友补枪代理就绪/未就绪的转化率；
- 同一阵营、地图区域是否在多场比赛中重复成为低转化热点。

每场比赛必须先满足最小样本条件，才能进入“支持该发现”的计数。画像状态分为：

- `single_match_signal`：只有单场证据；
- `emerging`：至少两场可评估，但重复性或总样本仍不足；
- `recurring`：至少三场且大部分比赛重复出现；
- 高置信度需要至少五场、较高一致性和足够的聚合交火样本。

## API

```text
GET /api/player-profiles/{steamid}?map_name=de_dust2
```

不提供 `map_name` 时聚合该 SteamID 当前进程内的所有地图。当前比赛仓库仍保存在内存中，Render 重启后
画像会丢失；生产版本应把 `MatchRepository` 替换为 PostgreSQL，同时继续使用相同画像函数。

## 本地批量模式

本地模式可以一次解析目录中的多份 Demo，不需要上传 Render：

```powershell
python -m chapter07_cs2_coach.profile_cli `
  --demo-dir "D:\CS2\demos" `
  --player-steamid "7656..." `
  --map-name de_dust2 `
  --output ".agent_data\profiles\dust2.json"
```

默认最多读取 20 个文件，可用 `--max-files` 调整到 1—100。重复路径会被去重，解析完成后还会按
Demo 内容生成的 `match_id` 再次去重，避免同一比赛被复制或重复传入后放大画像证据。
