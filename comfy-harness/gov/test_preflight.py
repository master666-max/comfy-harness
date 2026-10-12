# -*- coding: utf-8 -*-
"""test_preflight.py — 生图前预检红绿（飞轮复用腿）

锁：① 召回只给已签（approved/verified，draft 不供血）；② 负例条件告警会命中（strong/mention）；
③ off 模式零动作零写盘；④ 每轮落日志（preflight.jsonl）。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import preflight as pf          # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402


def _mk(eid, content, evidence=None, facts=None):
    d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
         "type": "procedural", "importance": 3,
         "content": {"c": content, "a": "", "d": ""}, "keywords": [],
         "evidence": {"artifact": evidence or "generation:x.png"}}
    if facts:
        d["facts"] = facts
    return d


class TestPreflight(unittest.TestCase):
    def _store(self, tmp):
        s = PrecedentStore([])
        s.add(_mk("P-recipe-aa11", "NoobAI 配方：质控组 masterpiece/best quality + hires 二段", ), actor="ai:t")
        s.promote("P-recipe-aa11", actor="human:t")            # 已签（可召回）
        s.add(_mk("S-draft-bb22", "未签草案：也谈 hires 配方"), actor="ai:t")   # draft（不得供血）
        s.add(_mk("N-spec-cc33", "负例：M_dz@1.0 在 hand 构图下糊指（糊指 DNA）",
                  facts={"specimen": True, "specimen_note": "M_dz@1.0 + hand 构图 → 糊指"}), actor="ai:t")
        for i in range(10):
            s.add(_mk(f"S-fill-{i:02d}", f"独立记录 {i}：无关术语集 {i}"), actor="ai:t")
        p = os.path.join(tmp, "seed.json")
        s.save(p)
        return p

    def test_recall_only_sanctioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._store(tmp)
            r = pf.preflight(text="hires 二段 配方 质控组", store_path=seed,
                             log_path=os.path.join(tmp, "pf.jsonl"))
            ids = [eid for _sc, eid, _h in r["recall"]]
            self.assertIn("P-recipe-aa11", ids)             # 已签可召回
            self.assertNotIn("S-draft-bb22", ids)           # draft 不供血

    def test_negative_warning_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._store(tmp)
            r = pf.preflight(text="lora M_dz_x.safetensors 权重 1.0，hand 类构图下糊指，手部特写",
                             store_path=seed, log_path=os.path.join(tmp, "pf.jsonl"))
            self.assertTrue(r["neg_warnings"], "应命中糊指负例")
            self.assertIn(r["neg_warnings"][0]["tier"], ("strong", "mention"))

    def test_off_mode_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._store(tmp)
            lg = os.path.join(tmp, "pf.jsonl")
            r = pf.preflight(text="任意", store_path=seed, log_path=lg, mode="off")
            self.assertEqual(r["mode"], "off")
            self.assertFalse(os.path.isfile(lg))            # off 零写盘
            pf.preflight(text="hires 二段", store_path=seed, log_path=lg)
            lines = [json.loads(x) for x in open(lg, encoding="utf-8") if x.strip()]
            self.assertEqual(lines[0]["kind"], "preflight")


if __name__ == "__main__":
    unittest.main(verbosity=2)
