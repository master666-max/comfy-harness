# -*- coding: utf-8 -*-
"""test_reverse_flywheel.py — 反向飞轮三态开关红绿（维护者令 20261008）

维护者令：「反向飞轮要做成开关，可以从影子、关闭、开启 3 种形态切换」。
本件锁四组：
  A. 三态解析（CLI > env > 默认 on，20261009 全开全接线；非法值响亮拒绝）；
  B. 三态行为差异（off 零动作零写盘 / shadow 写日志但不注入 / on 注入）；
  C. 判据（形态闸流程词 / 标本同形 cosine；DI 离线）；
  D. **红线**：雷达全程不改受治库（零 add/零 retract/零事件）、不改候选集。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import embed_cache as ec          # noqa: E402
import reverse_flywheel as rf     # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402


def _spec_entry(eid="S-sp-aa11"):
    return {"id": eid, "gov": "draft", "task": "t2i", "kind": "governance",
            "level": "specialized", "type": "procedural", "importance": 3,
            "content": {"c": eid, "a": "", "d": ""}, "keywords": ["判官", "异族"],
            "evidence": {"artifact": "generation:t.png"},
            "facts": {"specimen": True, "specimen_note": "自食标本", "shadow_weight": 3}}


def _cache_with(vecs: dict, dim=4):
    items = {}
    for i, v in vecs.items():
        a = np.zeros(dim, dtype=np.float32)
        a[v] = 1.0
        items[i] = {"hash": "x", "vec": ec._b64(a)}
    return {"dim": dim, "items": items}


class TestModeSwitch(unittest.TestCase):
    def test_resolution_order(self):
        self.assertEqual(rf.resolve_mode("on", env="off"), "on")        # CLI 优先
        self.assertEqual(rf.resolve_mode(None, env="off"), "off")       # 其次 env
        self.assertEqual(rf.resolve_mode(None, env=""), "on")            # 缺省 on（20261009 全开全接线）
        self.assertEqual(rf.resolve_mode(" SHADOW ", env=""), "shadow")  # 容忍大小写空格

    def test_bad_mode_loud(self):
        with self.assertRaises(SystemExit) as cm:
            rf.resolve_mode("yes", env="")
        self.assertIn("DENY:BAD_MODE", str(cm.exception))

    def test_off_is_zero_action(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "anti.jsonl")
            r = rf.run([{"name": "x", "members": ["a"]}], PrecedentStore([_spec_entry()]),
                       "off", path)
            self.assertEqual(r["mode"], "off")
            self.assertEqual(r["checked"], 0)
            self.assertFalse(os.path.isfile(path))                  # 连日志都不碰

    def test_shadow_writes_log_but_not_injected(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "anti.jsonl")
            r = rf.run([{"name": "机器学习 提案 候选边界", "members": ["挖掘签名", "候选边界"]}],
                       PrecedentStore([_spec_entry()]), "shadow", path)
            self.assertEqual(r["mode"], "shadow")
            self.assertFalse(r["injected"])                         # 影子不注入
            self.assertTrue(os.path.isfile(path))
            lines = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
            self.assertEqual(lines[0]["kind"], "scan")

    def test_on_injects(self):
        with tempfile.TemporaryDirectory() as td:
            r = rf.run([{"name": "提案 候选", "members": ["挖掘签名", "候选边界"]}],
                       PrecedentStore([_spec_entry()]), "on", os.path.join(td, "a.jsonl"))
            self.assertTrue(r["injected"])


class TestJudge(unittest.TestCase):
    def test_process_gate_hit(self):
        r = rf.judge("提案流程簇", ["挖掘签名", "候选边界"], [])
        self.assertEqual(r["verdict"], "hit")
        self.assertTrue(any("形态闸" in b for b in r["by"]))

    def test_specimen_similarity_hit(self):
        spec = [{"id": "S-sp-aa11", "vec": np.zeros(4, dtype=np.float32)}]
        spec[0]["vec"][0] = 1.0
        fn = lambda texts, **kw: np.array([[1.0, 0, 0, 0]], dtype=np.float32)
        r = rf.judge("干净风格簇", ["tag one", "tag two"], spec, embed_fn=fn)
        self.assertEqual(r["verdict"], "hit")
        self.assertTrue(any("标本同形" in b for b in r["by"]))
        self.assertEqual(r["nearest"]["id"], "S-sp-aa11")

    def test_clear_when_far(self):
        spec = [{"id": "S-sp-aa11", "vec": np.array([1.0, 0, 0, 0], dtype=np.float32)}]
        fn = lambda texts, **kw: np.array([[0.0, 1.0, 0, 0]], dtype=np.float32)
        r = rf.judge("完全不同的簇", ["sunset", "rooftop"], spec, embed_fn=fn)
        self.assertEqual(r["verdict"], "clear")

    def test_embed_failure_loud_not_silent(self):
        spec = [{"id": "S-sp-aa11", "vec": np.array([1.0, 0, 0, 0], dtype=np.float32)}]

        def boom(texts, **kw):
            raise RuntimeError("端点离线（测试）")
        r = rf.judge("某簇", ["a"], spec, embed_fn=boom)
        self.assertTrue(any("标本对照跳过" in b for b in r["by"]))   # 降级现形不静默


class TestRedLine(unittest.TestCase):
    def test_radar_never_mutates_store(self):
        """红线：雷达只读——零 add/retract/事件，候选集原样。"""
        store = PrecedentStore([_spec_entry()])
        n0, e0 = len(store.entries), len(store.gov_events)
        cands = [{"name": "提案 候选", "members": ["挖掘签名", "候选边界"]},
                 {"name": "干净簇", "members": ["sunset"]}]
        with tempfile.TemporaryDirectory() as td:
            rf.run(cands, store, "on", os.path.join(td, "a.jsonl"))
        self.assertEqual(len(store.entries), n0)
        self.assertEqual(len(store.gov_events), e0)
        self.assertEqual(len(cands), 2)                             # 候选集未被改

    def test_stats_aggregation(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "a.jsonl")
            store = PrecedentStore([_spec_entry()])
            rf.run([{"name": "提案 候选", "members": ["挖掘签名", "候选边界"]}],
                   store, "shadow", path)
            rf.run([{"name": "干净簇", "members": ["sunset"]}], store, "shadow", path)
            s = rf.stats(path)
            self.assertEqual(s["scans"], 2)
            self.assertEqual(s["hits"], 1)
            self.assertEqual(s["hit_rate"], 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
