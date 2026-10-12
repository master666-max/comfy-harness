# -*- coding: utf-8 -*-
"""test_health.py — P9 健康度读数红绿（占比记账/回声双口径/T-a/T-b）"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import embed_cache as ec          # noqa: E402
import health as H                # noqa: E402


def _e(eid, gov, **kw):
    d = {"id": eid, "gov": gov, "content": {"c": eid, "a": "", "d": ""}}
    d.update(kw)
    return d


def _cache(vecs: dict, dim=4):
    items = {}
    for i, v in vecs.items():
        arr = np.zeros(dim, dtype=np.float32)
        arr[v] = 1.0
        items[i] = {"hash": "x", "vec": ec._b64(arr)}
    return {"dim": dim, "items": items}


class TestHealth(unittest.TestCase):
    def test_entry_health(self):
        ents = ([_e(f"A{i}", "approved") for i in range(3)]
                + [_e("V1", "verified")] + [_e(f"D{i}", "draft") for i in range(6)])
        h = H.entry_health(ents, gen_docs=26)
        self.assertEqual(h["ratio"], "26:4:6")
        self.assertAlmostEqual(h["approved_rate"], 0.75, places=4)
        self.assertAlmostEqual(h["ratified_rate"], 0.4, places=4)

    def test_probe_health_offline(self):
        p = H.probe_health()                    # 固化夹具：离线确定性
        self.assertEqual(p["probes"], 7)
        # 20261010 重固化：19 条签发后 i3/i4 增补手部知识族、i6 颗粒盲区自愈
        # （no-grain-CA 颗粒权威条 + hires 条转正入池）→ 7/7 全命中，零命中集合清空
        self.assertEqual(p["hits"], 7)
        self.assertAlmostEqual(p["zero_hit_rate"], 0.0, places=4)
        self.assertFalse(p["over_threshold"])   # 0% < 30%
        self.assertEqual(p["misses"], [])

    def test_echo_dual_basis(self):
        ents = [_e("A1", "approved"), _e("D1", "draft"), _e("D2", "draft")]
        cache = _cache({"A1": 0, "D1": 1, "D2": 2})
        cands = [{"name": "c-san", "members": ["a", "b"]},
                 {"name": "c-self", "members": ["a", "c"]},
                 {"name": "c-new", "members": ["z", "y"]}]
        # embed_fn 按序给向量：c-san→e0（贴已签）、c-self→e1（贴草案）、c-new→e3（新）
        seq = [0, 1, 3]

        def fn(texts, **kw):
            out = []
            for v in seq:
                arr = np.zeros(4, dtype=np.float32)
                arr[v] = 1.0
                out.append(arr)
            return np.asarray(out, dtype=np.float32)

        r = H.echo_health(ents, cands, cache=cache, embed_fn=fn)
        self.assertEqual(r["candidates"], 3)
        self.assertEqual(r["echoes"], 1)            # 对已签：只有 c-san
        self.assertEqual(r["echoes_all"], 2)        # 对全库：c-san + c-self
        self.assertAlmostEqual(r["rate"], 1 / 3, places=4)
        self.assertAlmostEqual(r["rate_all"], 2 / 3, places=4)

    def test_reforge_health(self):
        ents = [_e("S-x-aaaa", "draft"), _e("S-x-bbbb", "draft"),
                _e("S-y-cccc", "draft"), _e("S-y-dddd", "draft"),
                _e("D-solo", "draft"), _e("A1", "approved")]
        r = H.reforge_health(ents)
        self.assertEqual(r["drafts"], 5)
        self.assertEqual(r["twin_groups"], 2)
        self.assertAlmostEqual(r["rate"], 2 / 5, places=4)
        self.assertTrue(r["over_threshold"])        # 40% > 5%

    def test_format_readings_contains_all(self):
        ents = [_e("A1", "approved"), _e("D1", "draft")]
        r = {"entry": H.entry_health(ents, 5),
             "probe": {"probes": 7, "hits": 7, "misses": [], "zero_hit_rate": 0.0,
                       "over_threshold": False},
             "echo": {"candidates": 2, "echoes": 1, "rate": 0.5, "echoes_all": 2,
                      "rate_all": 1.0, "cos_cut": 0.9, "samples": []},
             "reforge": {"drafts": 1, "twin_groups": 0, "rate": 0.0,
                         "over_threshold": False},
             "thresholds": {"T_A": 0.3, "T_B": 0.05, "ECHO_COS": 0.9}}
        s = H.format_readings(r)
        for token in ("raw:ratified:draft", "approved 率", "回声簇率", "对全库", "T-a", "T-b"):
            self.assertIn(token, s)

    def test_mine_trigger_health_lines(self):
        import mine_trigger as mt
        lines = mt.health_lines()               # 端点/读数失败也须返回提示行（不抛）
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("（健康度"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
