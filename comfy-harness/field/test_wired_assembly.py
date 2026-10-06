# -*- coding: utf-8 -*-
"""test_wired_assembly.py — 批一-2 传动轴消费者红绿锁（工单 §二-1-2）

守 wired_assembly 的三个契约：
  ① facts 提取：recall_tier 命中带 facts 条目 → 按 class 抽机器事实，facts_source="recall"；
  ② 无 facts 跳过并计数：散文教训条目被跳过进 skipped_no_facts 计数（禁静默）；
  ③ 零召回回退：空供血 → naive_prior 原样返回，facts_source="naive_fallback" + 计数披露。
红灯先行：本文件先于 wired_assembly.py 存在。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wired_assembly import extract_wiring, NAIVE_PRIOR  # noqa: E402


class _Hit:
    def __init__(self, eid, facts=None):
        self.id = eid
        self.facts = facts


class ExtractWiringTests(unittest.TestCase):
    """假件用 dict 形态——与 evocore 条目真实形状一致（recall_tier 出的是 entry dict）。"""

    @staticmethod
    def _hit(eid, facts=None):
        return {"id": eid, "facts": facts}

    def test_recall_hit_injects_facts(self):
        hits = [(0.9, self._hit("P-1", facts={"Flux2Scheduler": ["steps", "width", "height"]}))]
        w = extract_wiring("flux2 布线", hits)
        self.assertEqual(w["facts_source"], "recall")
        self.assertEqual(w["facts"]["Flux2Scheduler"], ["steps", "width", "height"])
        self.assertEqual(w["skipped_no_facts"], 0)

    def test_no_facts_entry_skipped_and_counted(self):
        hits = [(0.8, self._hit("P-2", facts=None))]
        w = extract_wiring("flux2 布线", hits)
        self.assertEqual(w["facts_source"], "naive_fallback")
        self.assertEqual(w["skipped_no_facts"], 1)
        self.assertEqual(w["facts"], {})

    def test_mixed_hits_skip_counted_recall_wins(self):
        hits = [(0.9, self._hit("P-3", facts=None)),
                (0.7, self._hit("P-4", facts={"K": ["v"]}))]
        w = extract_wiring("q", hits)
        self.assertEqual(w["facts_source"], "recall")
        self.assertEqual(w["skipped_no_facts"], 1)
        self.assertEqual(w["facts"], {"K": ["v"]})

    def test_empty_supply_falls_back_naive(self):
        w = extract_wiring("flux2 布线", [])
        self.assertEqual(w["facts_source"], "naive_fallback")
        self.assertEqual(w["naive_prior"], NAIVE_PRIOR)
        self.assertIn("model", NAIVE_PRIOR["suspect_keys"])   # 可疑键=活体 schema 必拒的两个


if __name__ == "__main__":
    unittest.main(verbosity=2)
