"""可以直接在网页体验的离线样例比赛。"""

from __future__ import annotations

from chapter07_cs2_coach.models import MatchRecord


SAMPLE_MATCH = MatchRecord.model_validate(
    {
        "match_id": "demo-mirage-001",
        "player_name": "Learner",
        "map_name": "de_mirage",
        "team_name": "Blue Five",
        "opponent_name": "Red Five",
        "team_score": 10,
        "opponent_score": 12,
        "rounds": [
            {"number": 1, "side": "T", "won": True, "kills": 2, "damage": 168, "opening_duel": "won", "equipment_value": 800, "note": "A1 首杀后顺利下包。"},
            {"number": 2, "side": "T", "won": True, "kills": 1, "assists": 1, "damage": 103, "utility_damage": 18, "enemies_flashed": 1, "equipment_value": 3600},
            {"number": 3, "side": "T", "won": False, "died": True, "damage": 31, "opening_duel": "lost", "equipment_value": 4200, "note": "中路单摸，队友相距过远无法补枪。"},
            {"number": 4, "side": "T", "won": False, "kills": 1, "died": True, "damage": 94, "was_traded": True, "equipment_value": 4700},
            {"number": 5, "side": "T", "won": True, "kills": 2, "damage": 157, "utility_damage": 22, "enemies_flashed": 2, "equipment_value": 4650},
            {"number": 6, "side": "T", "won": False, "died": True, "damage": 18, "opening_duel": "lost", "equipment_value": 3900, "note": "A 坡无闪干拉。"},
            {"number": 7, "side": "T", "won": False, "kills": 1, "died": True, "damage": 112, "equipment_value": 2000, "note": "半起局购买不统一。"},
            {"number": 8, "side": "T", "won": True, "kills": 1, "assists": 1, "damage": 89, "was_traded": False, "utility_damage": 35, "enemies_flashed": 2, "equipment_value": 4800},
            {"number": 9, "side": "T", "won": False, "kills": 2, "died": True, "damage": 173, "clutch_attempted": True, "equipment_value": 4900, "note": "1v3 残局击杀两人后失败。"},
            {"number": 10, "side": "T", "won": False, "died": True, "damage": 26, "opening_duel": "lost", "equipment_value": 4450, "note": "B 二楼第一身位无道具进入。"},
            {"number": 11, "side": "T", "won": True, "kills": 2, "damage": 149, "opening_duel": "won", "utility_damage": 12, "enemies_flashed": 1, "equipment_value": 5050},
            {"number": 12, "side": "CT", "won": True, "kills": 1, "damage": 101, "equipment_value": 1000},
            {"number": 13, "side": "CT", "won": False, "died": True, "damage": 42, "equipment_value": 3350, "note": "强起局单人前压中路。"},
            {"number": 14, "side": "CT", "won": False, "kills": 2, "died": True, "damage": 181, "clutch_attempted": True, "equipment_value": 5100, "note": "1v3 回防击杀两人，时间不足。"},
            {"number": 15, "side": "CT", "won": True, "kills": 2, "damage": 154, "utility_damage": 41, "enemies_flashed": 2, "equipment_value": 4950},
            {"number": 16, "side": "CT", "won": False, "died": True, "damage": 23, "opening_duel": "lost", "equipment_value": 5200, "note": "短箱重复 peek，死亡后未被补枪。"},
            {"number": 17, "side": "CT", "won": True, "kills": 1, "assists": 1, "damage": 97, "utility_damage": 28, "enemies_flashed": 1, "equipment_value": 5300},
            {"number": 18, "side": "CT", "won": False, "kills": 1, "died": True, "damage": 105, "was_traded": True, "equipment_value": 4900},
            {"number": 19, "side": "CT", "won": False, "kills": 2, "died": True, "damage": 165, "clutch_attempted": True, "equipment_value": 5250, "note": "1v2 回防没有拆包时间。"},
            {"number": 20, "side": "CT", "won": True, "kills": 2, "damage": 142, "opening_duel": "won", "utility_damage": 16, "equipment_value": 5050},
            {"number": 21, "side": "CT", "won": False, "died": True, "damage": 37, "opening_duel": "lost", "equipment_value": 2400, "note": "半起局在 A1 单独接触。"},
            {"number": 22, "side": "CT", "won": True, "kills": 1, "assists": 1, "damage": 91, "utility_damage": 32, "enemies_flashed": 2, "equipment_value": 5100},
        ],
    }
)
