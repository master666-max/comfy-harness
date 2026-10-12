# -*- coding: utf-8 -*-
"""test_draft_review.py — N5 评审组视图红绿（工单 P8）

**核心红绿锁**：判据反转教训——cos 不可判别（不同概念 0.972 / 同概念重铸 0.874），
标签 Jaccard 可判别。测试用"全同向量"（cos 恒 1.0）配"标签不同"证明：判决与 cos
无关；再用"标签连通但完全链接 min<阈值"证明不链式崩塌（单链会并三为一）。
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import draft_review as dr          # noqa: E402
import embed_cache as ec           # noqa: E402


def _entry(eid, tags=None, sig=None, gen=None, ev=None, created="2026-01-01T00:00:00"):
    e = {"id": eid, "gov": "draft", "created_at": created,
         "content": {"c": f"{eid} 正文", "a": "", "d": ""}}
    if tags is not None:
        e["facts"] = {"tags": tags}
    if sig:
        e["_mine_sig"] = sig
    if gen is not None:
        e["_mine_gen"] = gen
    if ev is not None:
        e["evidence"] = [f"generation:p{i}.png" for i in range(ev)]
    return e


def _cache_with(vec_ids, dim=4, same_vec=False):
    items = {}
    for k, i in enumerate(vec_ids):
        v = np.ones(dim, dtype=np.float32) if same_vec else np.zeros(dim, dtype=np.float32)
        if not same_vec:
            v[k % dim] = 1.0
        items[i] = {"hash": "x", "vec": ec._b64(v)}
    return {"dim": dim, "items": items}


class TestDraftReview(unittest.TestCase):
    def test_groups_by_tags_not_cos(self):
        """cos 恒 1.0 但标签不同 → 不得同组；cos 相同但标签同 → 同组。"""
        ents = [_entry("D-a", tags=["x", "y", "z"]),
                _entry("D-b", tags=["x", "y", "z"]),
                _entry("D-c", tags=["p", "q", "r"]),
                _entry("D-d", tags=["m", "n", "o"])]
        cache = _cache_with([e["id"] for e in ents], same_vec=True)   # 全同向量
        rep = dr.group_drafts(ents, cache)
        groups = [set(m["id"] for m in g["members"]) for g in rep["groups"]]
        self.assertIn({"D-a", "D-b"}, groups)
        self.assertNotIn({"D-c"}, groups)
        for g in groups:                                              # 不同概念的 C/D 不得并
            self.assertFalse({"D-c", "D-d"} <= g)

    def test_complete_linkage_blocks_chain(self):
        """A~B、B~C 均过阈但 A~C 不过 → 不得三并（单链会）。"""
        A = _entry("D-A", tags=["1", "2", "3", "4", "5", "6", "7"])
        B = _entry("D-B", tags=["1", "2", "3", "4", "5", "6", "8", "9", "10", "11", "12"])
        C = _entry("D-C", tags=["1", "2", "3", "4", "5", "6", "8", "9", "10", "11", "12",
                                "13", "14"])
        rep = dr.group_drafts([A, B, C], None)               # cache=None：分组不依赖向量
        groups = [set(m["id"] for m in g["members"]) for g in rep["groups"]]
        self.assertIn({"D-B", "D-C"}, groups)
        self.assertNotIn({"D-A", "D-B", "D-C"}, groups)
        self.assertIn("D-A", rep["singles"])

    def test_base_and_sig_forced(self):
        ents = [_entry("S-x-aaaa1111"), _entry("S-x-bbbb2222"),      # 同基底
                _entry("D-p", sig="sig1"), _entry("D-q", sig="sig1")]  # 同签名
        rep = dr.group_drafts(ents, None)
        groups = [set(m["id"] for m in g["members"]) for g in rep["groups"]]
        self.assertIn({"S-x-aaaa1111", "S-x-bbbb2222"}, groups)
        self.assertIn({"D-p", "D-q"}, groups)

    def test_canonical_priority(self):
        # 代际低者优先
        g1 = dr.group_drafts([_entry("S-x-a", gen=2), _entry("S-x-b", gen=1)], None)
        self.assertEqual(g1["groups"][0]["canonical"], "S-x-b")
        # 代际平 → 证据多者
        g2 = dr.group_drafts([_entry("S-y-a", ev=0), _entry("S-y-b", ev=3)], None)
        self.assertEqual(g2["groups"][0]["canonical"], "S-y-b")
        # 都对 → 时间早者
        g3 = dr.group_drafts([_entry("S-z-a", created="2026-02-01T00:00:00"),
                              _entry("S-z-b", created="2026-01-01T00:00:00")], None)
        self.assertEqual(g3["groups"][0]["canonical"], "S-z-b")
        # 提示文含动作口径
        self.assertIn("merged", g3["groups"][0]["hint"])
        self.assertIn("retract 其余 1 条", g3["groups"][0]["hint"])

    def test_missing_vec_and_attention(self):
        ents = [_entry("D-a", tags=["x", "y"]), _entry("D-b", tags=["x", "y"]),
                _entry("D-w", tags=["k", "l", "m"]), _entry("D-z", tags=["q", "r"])]
        cache = _cache_with(["D-a", "D-b", "D-w"], same_vec=True)   # D-z 无向量
        rep = dr.group_drafts(ents, cache, cos_attention=0.9)
        self.assertEqual(rep["missing_vec"], ["D-z"])          # 缺件现形（禁静默丢件）
        groups = [set(m["id"] for m in g["members"]) for g in rep["groups"]]
        self.assertIn({"D-a", "D-b"}, groups)                  # 缺向量不影响分组
        pairs = {(p["a"], p["b"]) for p in rep["cos_attention"]}
        self.assertIn(("D-a", "D-w"), pairs)                   # 跨组高 cos 入注意力清单
        self.assertNotIn(("D-a", "D-b"), pairs)                # 已同组不入清单

    def test_deterministic(self):
        ents = [_entry("S-k-a", gen=1), _entry("S-k-b", gen=2),
                _entry("D-m", tags=["u", "v"]), _entry("D-n", tags=["u", "v"])]
        r1 = dr.group_drafts(copy.deepcopy(ents), None)
        r2 = dr.group_drafts(copy.deepcopy(ents), None)
        self.assertEqual(json.dumps(r1, ensure_ascii=False, sort_keys=True),
                         json.dumps(r2, ensure_ascii=False, sort_keys=True))

    def test_review_loud_on_missing_or_stale_cache(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            seed = os.path.join(tmp.name, "seed.json")
            shutil.copy(os.path.join(_HERE, "precedents_e2_seed.json"), seed)
            with self.assertRaises(RuntimeError) as cm:
                dr.review(seed, os.path.join(tmp.name, "nope.json"))
            self.assertIn("组视图不降级", str(cm.exception))
            stale = os.path.join(tmp.name, "stale.json")
            json.dump({"model": "nomic-embed", "dim": 768, "prefix_scheme": "OLD",
                       "items": {"x": {"hash": "h", "vec": "AA=="}}},
                      open(stale, "w", encoding="utf-8"))
            with self.assertRaises(RuntimeError) as cm2:
                dr.review(seed, stale)
            self.assertIn("前缀方案", str(cm2.exception))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
