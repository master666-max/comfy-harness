# -*- coding: utf-8 -*-
"""test_propagation.py — 加权衰减传播 + 贝叶斯影子序数版 红绿（维护者令 20261008）

维护者令：「先上加权衰减传播，贝叶斯做影子」。
本件锁：
  A. 传播语义（跳衰减 / 边型权序 / raw 自证折 / 环上阻尼收敛 / 确定性 / 只读）；
  B. 贝叶斯影子四纪律（序数不输出概率 / 默认 shadow / off 零动作 / 只读不改库 / 无执行接口）。
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

import bayes_shadow as bs      # noqa: E402
import edge_graph as eg        # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402


def _e(eid, **kw):
    d = {"id": eid, "gov": "draft", "task": "t2i", "kind": "style", "level": "specialized",
         "content": {"c": eid, "a": "", "d": ""}, "keywords": [], "evidence": {}}
    d.update(kw)
    return d


class TestPropagate(unittest.TestCase):
    """夹具 id 用**不同基底**（S-a/S-c 同基会生成 base-mate 边污染断言——实测教训）。"""

    def _g(self):
        # P-root →(cites) S-alpha(raw 自证) / S-bravo(仅引用) ; S-bravo →(merged-from) S-charlie（2 跳）
        return eg.extract_graph([
            _e("P-root", evidence={"artifact": "generation:r.png"}),
            _e("S-alpha-aa11", content={"c": "见 P-root", "a": "", "d": ""},
               evidence={"artifact": "generation:mine.png"}),          # raw 自证
            _e("S-bravo-bb22", content={"c": "见 P-root", "a": "", "d": ""},
               evidence={"artifact": "见 P-root"}),                     # citation
            _e("S-charlie-cc33", evidence={"artifact": "见 S-bravo-bb22"},
               facts={"merged_from": ["S-bravo-bb22"]}),
        ])

    def test_raw_self_evidence_discounted(self):
        p = eg.propagate(self._g(), "P-root")
        self.assertAlmostEqual(p["S-alpha-aa11"]["score"], 0.8 * 0.6 * 0.3, places=3)
        self.assertAlmostEqual(p["S-bravo-bb22"]["score"], 0.8 * 0.6, places=3)
        self.assertLess(p["S-alpha-aa11"]["score"], p["S-bravo-bb22"]["score"])   # 引用≠同错

    def test_hop_decay(self):
        """每远一跳打一次折（λ=0.6，经父分数复利）：S-charlie = S-bravo × 1.0 × 0.6。"""
        p = eg.propagate(self._g(), "P-root")
        self.assertAlmostEqual(p["S-charlie-cc33"]["score"],
                               p["S-bravo-bb22"]["score"] * 0.6, places=3)
        self.assertEqual(p["S-charlie-cc33"]["hop"], 2)
        self.assertEqual(p["S-charlie-cc33"]["via"]["type"], "merged-from")

    def test_edge_weight_order(self):
        """同跳不同边型权重序：merged-from(1.0) > cites(0.8) > base-mate(0.5)。"""
        g = eg.extract_graph([
            _e("R-root"),
            _e("S-mike-mm44", facts={"merged_from": ["R-root"]}),         # 血缘
            _e("S-cite-nn55", content={"c": "见 R-root", "a": "", "d": ""}),  # 引用
        ])
        p = eg.propagate(g, "R-root")
        self.assertAlmostEqual(p["S-mike-mm44"]["score"], 1.0 * 0.6, places=3)
        self.assertAlmostEqual(p["S-cite-nn55"]["score"], 0.8 * 0.6, places=3)
        g2 = eg.extract_graph([_e("S-kilo-aa11"), _e("S-kilo-bb22")])     # 同基底对（对称边）
        p2 = eg.propagate(g2, "S-kilo-aa11")
        self.assertAlmostEqual(p2["S-kilo-bb22"]["score"], 0.5 * 0.6, places=3)

    def test_cycle_damping_converges(self):
        g = eg.extract_graph([_e("S-xray-aa11", content={"c": "见 S-yankee-bb22", "a": "", "d": ""}),
                              _e("S-yankee-bb22", content={"c": "见 S-xray-aa11", "a": "", "d": ""})])
        p = eg.propagate(g, "S-xray-aa11")
        v = p["S-yankee-bb22"]["score"]
        self.assertGreater(v, 0)
        self.assertLess(v, 2.0)                                          # 有环不爆炸

    def test_deterministic_and_readonly(self):
        ents = self._g()["nodes"]
        p1 = eg.propagate(self._g(), "P-root")
        p2 = eg.propagate(self._g(), "P-root")
        self.assertEqual(json.dumps(p1, sort_keys=True), json.dumps(p2, sort_keys=True))
        self.assertEqual(len(ents), 4)                                   # 图未被改


class TestBayesShadow(unittest.TestCase):
    def test_mode_defaults_and_off(self):
        self.assertEqual(bs.mode(cli=None, env=""), "act")              # 缺省 act（20261010 贝叶斯影子转正）
        self.assertEqual(bs.mode(cli="on", env="off"), "on")             # CLI 优先
        with self.assertRaises(SystemExit):
            bs.mode(cli="yes", env="")
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "b.jsonl")
            r = bs.run({"nodes": {}, "edges": []}, "X", "off", log)
            self.assertEqual(r["mode"], "off")
            self.assertFalse(os.path.isfile(log))                        # off 零写盘

    def test_ordinal_no_probabilities(self):
        g = eg.extract_graph([_e("P-root", evidence={"artifact": "generation:r.png"}),
                              _e("S-b", content={"c": "见 P-root", "a": "", "d": ""},
                                 evidence={"artifact": "见 P-root"})])
        rows = bs.posterior_ordinal(g, "P-root")
        self.assertTrue(rows)
        for x in rows:
            self.assertIn(x["band"], ("high", "mid", "low"))
            self.assertIsInstance(x["rank"], int)
            self.assertTrue(x["uncalibrated"])
            for k, v in x.items():                                       # 无概率形状的键
                self.assertNotIn(k, ("p", "prob", "probability", "posterior_pct"))
                self.assertNotIsInstance(v, float)                       # 输出不含浮点数字

    def test_shadow_writes_log_and_on_marks_injected(self):
        g = eg.extract_graph([_e("P-root"), _e("S-b", content={"c": "见 P-root", "a": "", "d": ""})])
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "b.jsonl")
            r1 = bs.run(g, "P-root", "shadow", log)
            self.assertTrue(os.path.isfile(log))
            self.assertFalse(r1["injected"])
            r2 = bs.run(g, "P-root", "on", log)
            self.assertTrue(r2["injected"])
            n = len([1 for ln in open(log, encoding="utf-8") if ln.strip()])
            self.assertEqual(n, 2)
            self.assertEqual(bs.stats(log)["runs"], 2)

    def test_no_execution_interface(self):
        """纪律④：不得接 auto_heal——本模块不该有任何执行/降权接口。"""
        for name in ("apply", "execute", "enforce", "derate", "wire"):
            self.assertFalse(hasattr(bs, name), name)

    def test_readonly_store(self):
        s = PrecedentStore([_e("P-root"), _e("S-b")])
        n0, e0 = len(s.entries), len(s.gov_events)
        g = eg.extract_graph(s.entries)
        with tempfile.TemporaryDirectory() as td:
            bs.run(g, "P-root", "on", os.path.join(td, "b.jsonl"))
        self.assertEqual((len(s.entries), len(s.gov_events)), (n0, e0))


class TestVectorCircuitBreaker(unittest.TestCase):
    """向量路熔断：一次失败后窗口内不再重试（仍词法兜底）；进入窗口只告警一次。"""

    def test_breaker_skips_retry_within_window(self):
        import recall_hybrid as rh
        calls = {"n": 0}

        def boom(texts, **kw):
            calls["n"] += 1
            raise RuntimeError("端点不可用（测试）")

        import embed_cache as _ec
        orig = _ec.embed_query
        _ec.embed_query = boom                    # 打 live 路径（熔断只对 live 生效）

        pool = [{"id": "S-a-aa11", "gov": "draft", "content": {"c": "hires redraw"},
                 "keywords": ["hires"], "evidence": {}},
                {"id": "S-b-bb22", "gov": "draft", "content": {"c": "sakura petals"},
                 "keywords": ["sakura"], "evidence": {}}]
        old = rh._VEC_DOWN_UNTIL
        rh._VEC_DOWN_UNTIL = 0.0
        try:
            r1 = rh.rank(pool, "hires", k=5)
            r2 = rh.rank(pool, "hires", k=5)
            self.assertEqual(calls["n"], 1, "熔断窗口内不应重试")
            self.assertTrue(r1 and r2)                       # 词法兜底仍有结果
            self.assertIn("hires", str(r2))
        finally:
            rh._VEC_DOWN_UNTIL = old
            _ec.embed_query = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
