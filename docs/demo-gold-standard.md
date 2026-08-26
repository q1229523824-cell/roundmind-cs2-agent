# Demo 金标准与解析准确率回归

数据质量门禁回答“字段是否完整”，金标准回归回答“字段是否正确”。两者不能互相替代。

## 第一次导出

```powershell
python -m chapter07_cs2_coach.gold_cli export `
  --demo "D:\path\match.dem" `
  --player-steamid "7656..." `
  --output ".agent_data\gold\match-01.json"
```

输出不保存昵称、SteamID 或本地 Demo 路径，只包含匿名玩家引用、比赛指纹、解析器版本指纹和需要核对的关键事实。新文件默认是 `draft`，不能直接作为正式准确率依据。

## 人工核对

对照 CS2 结算页、可信 Demo 工具或人工观看结果，核对：

- 地图、比分和总回合数；
- 玩家总击杀、死亡和助攻；
- 每回合阵营、胜负、K/D/A；
- 每回合首杀、首死或未参与首轮交火。

修正 `expected` 后，把顶层 `status` 从 `draft` 改为 `verified`，并在 `verification_notes` 写明核对来源。不要把真实金标准提交到公开仓库；`.agent_data/` 已被 Git 忽略。

## 单场回归

```powershell
python -m chapter07_cs2_coach.gold_cli evaluate `
  --demo "D:\path\match.dem" `
  --player-steamid "7656..." `
  --gold ".agent_data\gold\match-01.json" `
  --output ".agent_data\reports\match-01.json"
```

门禁要求所有关键汇总字段正确，全部字段准确率不低于 98%。报告会列出每个不一致字段，并标记 demoparser2 或 RoundMind 解析器源码是否相对金标准基线发生变化。

调试阶段可传 `--allow-draft`，但这种结果不能作为发布准确率。

## 批量回归

在 `.agent_data/gold/manifest.json` 保存本地清单：

```json
{
  "schema_version": "roundmind.demo-regression-manifest.v1",
  "cases": [
    {
      "case_id": "dust2-standard-01",
      "demo_path": "../demos/match01.dem",
      "player_steamid": "7656...",
      "gold_path": "match-01.json"
    }
  ]
}
```

路径相对于 manifest 所在目录解析：

```powershell
python -m chapter07_cs2_coach.gold_cli batch `
  --manifest ".agent_data\gold\manifest.json" `
  --output ".agent_data\reports\batch.json"
```

批量报告只保留 `case_id`、准确率、版本变化和受控错误，不把本地路径复制到报告中。任何无法解析、草稿未核对或准确率未达标的案例都会失败。

## 游戏版本更新流程

1. 记录新 Demo 对应的 CS2 版本和地图；
2. 先运行现有 verified 金标准，确认旧能力没有回退；
3. 对新 Demo 导出草稿并人工核对；
4. 将新版特有事件加入解析器与测试；
5. 批量报告通过后才发布解析器更新；
6. 不兼容 Demo 必须返回明确错误，不能生成空建议。

## 当前指标含义

- `critical.accuracy`：地图、比分、回合数、K/D/A 和首杀/首死汇总准确率；
- `round_level.accuracy`：每回合阵营、胜负、击杀、助攻、死亡和首轮交火准确率；
- `overall.accuracy`：上述全部字段的总体准确率；
- `parser_version_changed`：解析库版本或 RoundMind 解析器源码相对基线是否变化。

这些指标衡量解析器，不衡量玩家水平或教练建议质量。决策建议仍需使用独立的人工动作标注集评测。
