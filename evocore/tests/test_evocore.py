# -*- coding: utf-8 -*-
"""test_evocore.py — evocore 不变量测试（零依赖，标准库 unittest）
（S1 平移 · 源 memsys/tests/test_engine.py @ b19c9a4）
不变量：只增不改 / 打分确定性 / 墓碑退出 / 类型衰减 / 保守拒绝 / tunables 构造时校验。
"""
import sys, os, unittest, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # 仓根：含 evocore 包
from evocore import Tunables, DEFAULTS           # noqa: E402
from evocore import retrieval                      # noqa: E402
from evocore import lifecycle                      # noqa: E402
from evocore import decision                       # noqa: E402

NOW = datetime.datetime(2026, 9, 21, 12, 0, 0)

def entry(**kw):
    base = {"id": "e1", "content": "用户偏好深色主题", "keywords": ["偏好"],
            "importance": 5, "created_at": "2026-09-20T00:00:00", "type": "semantic",
            "state": "intermediate"}
    base.update(kw); return base

class TestTunables(unittest.TestCase):
    def test_negative_weight_rejected_at_construction(self):
        with self.assertRaises(ValueError): Tunables(w_kw=-1)
    def test_bad_filter_zero_rejected(self):
        with self.assertRaises(ValueError): Tunables(filter_zero=2)
    def test_bad_rate_rejected(self):
        with self.assertRaises(ValueError): Tunables(irreversible_error_rate_max=1.5)

class TestRetrieval(unittest.TestCase):
    def test_deterministic(self):
        a = retrieval.score(entry(), "偏好", DEFAULTS, NOW)
        b = retrieval.score(entry(), "偏好", DEFAULTS, NOW)
        self.assertEqual(a, b, "同输入必须同输出（确定性不变量）")
    def test_keyword_hit_scores_above_zero(self):
        self.assertGreater(retrieval.score(entry(), "偏好", DEFAULTS, NOW), 0)
    def test_filter_zero_miss_is_zero(self):
        self.assertEqual(retrieval.score(entry(), "完全不相关的查询词组", DEFAULTS, NOW), 0.0)
    def test_tombstone_exits_retrieval(self):
        self.assertEqual(retrieval.score(entry(tombstone=True), "偏好", DEFAULTS, NOW), 0.0)
    def test_procedural_zero_decay(self):
        e = entry(type="procedural", created_at="2025-01-01T00:00:00")
        self.assertEqual(retrieval.score(e, "偏好", DEFAULTS, NOW),
                         retrieval.score(entry(type="procedural", created_at="2026-09-21T00:00:00"),
                                         "偏好", DEFAULTS, NOW), "procedural 零衰减不变量")
    def test_retrieve_ranking_order(self):
        es = [entry(id="low", importance=1), entry(id="high", keywords=["偏好","深色","主题"], importance=9)]
        got = retrieval.retrieve(es, "偏好 深色", k=2, now=NOW)
        self.assertEqual(got[0][1]["id"], "high")

class TestLifecycle(unittest.TestCase):
    def test_route_threshold(self):
        self.assertEqual(lifecycle.route(entry(importance=9)), "longterm")
        self.assertEqual(lifecycle.route(entry(importance=3)), "intermediate")
    def test_attic_never_delete(self):
        e = entry(); ev = lifecycle.attic(e, "测试")
        self.assertEqual(e["state"], "attic"); self.assertEqual(ev["kind"], "attic_nomination")
    def test_tombstone_marks_not_deletes(self):
        e = entry(); lifecycle.tombstone(e)
        self.assertTrue(e["tombstone"]); self.assertIn("content", e)   # 原位保留
    def test_touch_refreshes_last_used(self):
        e = entry(); lifecycle.touch(e, "2026-09-21T00:00:00")
        self.assertEqual(e["last_used_at"], "2026-09-21T00:00:00")

class TestDecision(unittest.TestCase):
    def test_conflict_keeps_manual(self):
        m = entry(id="manual", source="manual", importance=1)
        a = entry(id="agent", source="agent", importance=9)
        tr, win, _ = decision.adjudicate_conflict([a, m])
        self.assertEqual(win["id"], "manual", "manual 来源信任最高")
        self.assertEqual(tr["severity_if_wrong"], "irreversible", "含 manual 条目的冲突错判=不可逆")
    def test_merge_conservative_defer(self):
        tr = decision.adjudicate_merge([entry(), entry()])
        self.assertEqual(tr["decision"], "defer", "v1 规则对合并保守拒绝（金标判据奖励）")
    def test_promote_threshold(self):
        tr, out = decision.adjudicate_promote([entry(id="hi", importance=9), entry(id="lo", importance=3)])
        d = dict((e["id"], ok) for e, ok in out)
        self.assertTrue(d["hi"]); self.assertFalse(d["lo"])
    def test_traces_have_kind_and_ts(self):
        tr = decision.adjudicate_conflict([entry(), entry(id="e2")])[0]
        self.assertEqual(tr["kind"], "memory_adjudicate"); self.assertTrue(tr["ts"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
