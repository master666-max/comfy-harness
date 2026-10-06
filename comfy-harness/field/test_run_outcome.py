# -*- coding: utf-8 -*-
"""test_run_outcome.py — 批二埋点常开红绿锁（工单 §三 · 三态→油量的诚实映射）

守 run_outcome.record_run_outcome 的契约：
  ① 咬合→success / 不咬合→failure 落账；
  ② 登记盲区→跳过不落（盲区既不证实也不证伪，记哪边都是撒谎）+ 返回披露；
  ③ 判例不在库→容错跳过（点题件/库缺席不炸）；
  ④ 真库落账与 save 往返。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gov"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from precedent_gov import PrecedentStore  # noqa: E402
from run_outcome import record_run_outcome  # noqa: E402


def mk(eid):
    return {"id": eid, "type": "semantic", "importance": 2,
            "keywords": ["k"], "content": {"c": "x", "a": "y", "d": "z"},
            "evidence": {"artifact": "t", "quote": "q", "recalc": "r"}, "owner": ""}


class RunOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ro-")
        self.seed = os.path.join(self.tmp, "s.json")
        store = PrecedentStore()
        store.add(mk("R-1"), actor="ai:x")
        store.save(self.seed)

    def test_bite_maps_to_success(self):
        rec = record_run_outcome("R-1", "咬合", "EXP-A", store_path=self.seed)
        self.assertEqual(rec["result"], "success")
        self.assertEqual(rec["context"], "EXP-A")

    def test_no_bite_maps_to_failure(self):
        rec = record_run_outcome("R-1", "不咬合", "EXP-B", store_path=self.seed)
        self.assertEqual(rec["result"], "failure")

    def test_blind_zone_skips_with_disclosure(self):
        rec = record_run_outcome("R-1", "登记盲区", "EXP-C", store_path=self.seed)
        self.assertIsNone(rec)
        store = PrecedentStore.load(self.seed)
        self.assertNotIn("outcomes", store._get("R-1"))  # 盲区零落账

    def test_absent_eid_tolerated(self):
        rec = record_run_outcome("不存在", "咬合", "EXP-D", store_path=self.seed)
        self.assertIsNone(rec)

    def test_accumulates_across_runs(self):
        record_run_outcome("R-1", "咬合", "EXP-E", store_path=self.seed)
        record_run_outcome("R-1", "不咬合", "EXP-F", store_path=self.seed)
        store = PrecedentStore.load(self.seed)
        self.assertEqual([o["result"] for o in store._get("R-1")["outcomes"]],
                         ["success", "failure"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
