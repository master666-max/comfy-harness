# -*- coding: utf-8 -*-
"""test_style_registry.py — P11 注册表/族谱/变体红绿（N3/N6/N7）"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import style_registry as sr        # noqa: E402


def _e(eid, gen=1, ev=None, gov="draft", created="2026-01-01T00:00:00", **kw):
    d = {"id": eid, "gov": gov, "created_at": created, "_mine_gen": gen,
         "content": {"c": eid, "a": "", "d": ""}}
    if ev is not None:
        d["evidence"] = [f"generation:p{i}.png" for i in range(ev)]
    d.update(kw)
    return d


class TestStyleRegistry(unittest.TestCase):
    def test_concepts_and_canonical(self):
        ents = [_e("S-a-aaaa", gen=2, ev=5), _e("S-a-bbbb", gen=1, ev=0),
                _e("S-a-cccc", gen=1, ev=9)]
        rep = sr.build(ents)
        c = rep["concepts"]["s-a"]
        self.assertEqual(c["state"], "family")                 # 3 件 = 族
        self.assertEqual(c["canonical"], "S-a-cccc")           # gen 平 → 证据多者
        self.assertEqual(c["variants"], ["S-a-aaaa", "S-a-bbbb"])
        self.assertEqual(c["generations"], [1, 2])

    def test_twins_vs_single(self):
        rep = sr.build([_e("S-b-x-1"), _e("S-b-x-2"), _e("S-c-y-1")])
        self.assertEqual(rep["concepts"]["s-b-x"]["state"], "twins")
        self.assertEqual(rep["concepts"]["s-c-y"]["state"], "single")
        self.assertEqual(rep["counts"]["twins"], 1)
        self.assertEqual(rep["counts"]["single"], 1)

    def test_retracted_and_tombstoned_excluded(self):
        ents = [_e("S-a-aaaa"), _e("S-a-bbbb", machine_retracted=True),
                _e("S-a-cccc", tombstone=True)]
        rep = sr.build(ents)
        self.assertEqual(rep["concepts"]["s-a"]["members"], ["S-a-aaaa"])
        self.assertEqual(rep["concepts"]["s-a"]["state"], "single")

    def test_non_mined_excluded(self):
        rep = sr.build([_e("P-plain-1"), {"id": "D-x", "gov": "draft"}])
        self.assertEqual(rep["counts"]["concepts"], 0)

    def test_alias_extension_and_render(self):
        rep = sr.build([_e("S-a-1", gen=1), _e("S-a-2", gen=2), _e("S-a-3", gen=3),
                        _e("S-b-1"), _e("S-b-2")])
        ext = sr.alias_extension(rep)
        self.assertEqual(ext["S-a-1"], ["S-a-2", "S-a-3"])
        self.assertEqual(ext["S-b-1"], ["S-b-2"])
        txt = sr.render(rep)
        self.assertIn("family 候选", txt)
        self.assertIn("twins", txt)

    def test_deterministic(self):
        ents = [_e("S-a-zzz", ev=2), _e("S-a-aaa", ev=2)]
        r1, r2 = sr.build(ents), sr.build(ents)
        self.assertEqual(r1["concepts"]["s-a"]["canonical"],
                         r2["concepts"]["s-a"]["canonical"])
        self.assertEqual(r1["concepts"]["s-a"]["canonical"], "S-a-aaa")   # 时间/id 序兜底

    def test_min_family_override(self):
        ents = [_e("S-a-1"), _e("S-a-2")]
        self.assertEqual(sr.build(ents, min_family=2)["concepts"]["s-a"]["state"], "family")
        self.assertEqual(sr.build(ents, min_family=3)["concepts"]["s-a"]["state"], "twins")


class TestFeedFamilyRule(unittest.TestCase):
    """N6 feed 侧：候选撞上 ≥2 件同基 → 族谱候选入报告（只提案不铸）。"""

    def test_family_candidate_in_feed_report(self):
        import style_feed as sf
        import tempfile
        from precedent_gov import PrecedentStore

        def _se(eid, gen):
            return {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
                    "gov": "draft", "content": {"c": f"{eid} 正文", "a": "", "d": ""},
                    "keywords": ["风格"], "evidence": ["generation:p.png"],
                    "_mine_gen": gen}

        with tempfile.TemporaryDirectory() as td:
            store = PrecedentStore([_se("S-fam-aa11", 1), _se("S-fam-bb22", 2)])
            cands = [{"name": "fam", "members": ["tag one", "tag two", "tag three"],
                      "evidence": ["generation:p.png"]}]
            # 测试卫生：recurrence 落盘路径必传临时件（曾漏传→污染生产 recurrence.json 实录）
            res = sf.feed(cands, store, corpus_docs=[], min_size=1, dry=True,
                          recurrence_path=os.path.join(td, "rec.json"))
        fams = res.get("family_candidates") or []
        self.assertEqual(len(fams), 1)
        self.assertEqual(fams[0]["base"], "s-fam")
        self.assertIn("族谱候选", fams[0]["hint"])
        self.assertEqual(res["minted"], [])              # 只提案，不铸


if __name__ == "__main__":
    unittest.main(verbosity=2)
