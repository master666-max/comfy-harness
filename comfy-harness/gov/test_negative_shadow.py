# -*- coding: utf-8 -*-
"""test_negative_shadow.py — 反例面与影子权重红绿（维护者令 20261008）

维护者令："① 标本、反例 …… ② 给那几条真正重复的，后面表一个影子权重"。
本件锁三面：
  A. facts 面注册（shadow_weight 全六面 / specimen 属 style+governance）；
  B. 影子权重口径（=同代重复数 + 跨轮被拦重铸数；**只标注不升信任级**）；
  C. 标本守卫（promote-drafts 不得批量转正标本件——反例面须显式处置）。
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # 仓根（evocore）

import style_registry as sr               # noqa: E402
from precedent_gov import FACTS_PLANES, PrecedentStore   # noqa: E402
import draft_consolidate as dc            # noqa: E402


def _e(eid, kind="style", **kw):
    d = {"id": eid, "gov": "draft", "task": "t2i", "kind": kind, "level": "specialized",
         "type": "procedural", "importance": 3,
         "content": {"c": eid, "a": "", "d": ""}, "keywords": [eid.lower()],
         "evidence": {"artifact": "generation:test.png"},
         "_mine_gen": 1, "_mine_sig": eid[-6:]}
    d.update(kw)
    return d


class TestFactsRegistry(unittest.TestCase):
    def test_cross_plane_key_classes(self):
        """三类键分立：度量/标记入跨面表；知识面表不被污染（面单一不变量保住）。"""
        from precedent_gov import FACTS_METRIC_KEYS, FACTS_MARKER_KEYS
        self.assertIn("shadow_weight", FACTS_METRIC_KEYS)
        self.assertEqual({"specimen", "specimen_note"} <= FACTS_MARKER_KEYS, True)
        for plane, keys in FACTS_PLANES.items():
            self.assertNotIn("shadow_weight", keys, f"{plane} 知识面被度量键污染")

    def test_style_facts_with_metric_and_marker_pass(self):
        """style 知识键 + 影重 + 标本标记同束 → 合规（跨面键豁免面单一）。"""
        from precedent_gov import facts_plane_problems
        self.assertEqual(facts_plane_problems(
            {"tags": ["a"], "sig": "x", "shadow_weight": 3,
             "specimen": True, "specimen_note": "反例"}), [])

    def test_store_accepts_specimen_facts(self):
        s = PrecedentStore([])
        s.add(_e("S-spec-1", kind="governance"), actor="machine:test",
              facts={"specimen": True, "specimen_note": "自食标本", "shadow_weight": 2})
        self.assertTrue(s._get("S-spec-1")["facts"]["specimen"])

    def test_unknown_facts_key_still_rejected(self):
        s = PrecedentStore([])
        with self.assertRaises(ValueError):
            s.add(_e("S-bad-1"), actor="machine:test", facts={"no_such_key": 1})


class TestShadowWeight(unittest.TestCase):
    def _store_with_two(self):
        return PrecedentStore([_e("S-dup-aaaa11", keywords=["hires", "redraw"]),
                               _e("S-dup-bbbb22", keywords=["hires", "redraw"])])

    def test_merge_records_shadow_weight_with_recurrence(self):
        s = self._store_with_two()
        rec = {"S-dup-aaaa11": {"count": 3}, "S-dup-bbbb22": {"count": 1}}
        r = dc.merge(s, ["S-dup-aaaa11", "S-dup-bbbb22"], recurrence=rec)
        self.assertEqual(r["shadow_weight"], 1 + 4)          # (2-1) + (3+1)
        merged = s._get(r["new"])
        self.assertEqual(merged["facts"]["shadow_weight"], 5)
        self.assertEqual(merged["gov"], "draft")             # 非放大：仍是草案
        self.assertEqual(int(merged.get("_mine_gen") or 1), 1)   # 代数不升

    def test_merge_shadow_weight_without_ledger(self):
        s = self._store_with_two()
        r = dc.merge(s, ["S-dup-aaaa11", "S-dup-bbbb22"])
        self.assertEqual(r["shadow_weight"], 1)              # 缺账本只计同代重复

    def test_registry_and_group_expose_weight(self):
        rep = sr.build([_e("S-k-aa11"), _e("S-k-bb22")], recurrence={"S-k-aa11": {"count": 2}})
        self.assertEqual(rep["concepts"]["s-k"]["shadow_weight"], 1 + 2)


class TestSpecimenGuard(unittest.TestCase):
    def test_promote_drafts_skips_specimen(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "precedent_cli",
            os.path.join(os.path.dirname(os.path.dirname(_HERE)), "tools", "precedent_cli.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            s = PrecedentStore([_e("S-ok-aaaa11"),
                                _e("S-spec-bbbb22", kind="governance",
                                   facts={"specimen": True, "specimen_note": "反例"})])
            path = os.path.join(td, "seed.json")
            s.save(path)

            class A:
                seed, actor, prereg = path, "human:test", None
            rc = cli.cmd_promote_drafts(A())
            self.assertEqual(rc, 0)
            s2 = PrecedentStore.load(path)
            self.assertEqual(s2._get("S-ok-aaaa11")["gov"], "approved")
            self.assertEqual(s2._get("S-spec-bbbb22")["gov"], "draft")   # 标本未被动


class TestMergeIdConvention(unittest.TestCase):
    def test_no_double_s_prefix(self):
        """canonical 名自带 S- → 合并条 id 剥前缀后套一次（S-S- 会让基底比对失配）。"""
        s = PrecedentStore([_e("S-hires-aaaa11", keywords=["hires", "redraw"]),
                            _e("S-hires-bbbb22", keywords=["hires", "redraw"])])
        r = dc.merge(s, ["S-hires-aaaa11", "S-hires-bbbb22"],
                     name="S-hires-aaaa11", recurrence={})
        self.assertFalse(r["new"].startswith("S-S-"), r["new"])
        self.assertTrue(r["new"].startswith("S-hires-aaaa11-"), r["new"])


class TestReviewSpecimenAnnotation(unittest.TestCase):
    def test_specimen_group_marked_not_merge(self):
        """标本组在组视图里须标"勿并"（防以后误执行合并）。"""
        import draft_review as dr
        ents = [_e("S-sp-aa11", kind="governance",
                   facts={"specimen": True, "specimen_note": "自食标本"}),
                _e("S-sp-bb22", kind="governance",
                   facts={"specimen": True, "specimen_note": "自食标本"})]
        rep = dr.group_drafts(ents, None)
        g = rep["groups"][0]
        self.assertTrue(g["specimen"])
        self.assertIn("标本组", g["hint"])
        self.assertIn("勿并", g["hint"])

    def test_normal_group_still_gets_merge_hint(self):
        import draft_review as dr
        ents = [_e("S-nm-aa11", keywords=["x", "y"]), _e("S-nm-bb22", keywords=["x", "y"])]
        rep = dr.group_drafts(ents, None)
        self.assertFalse(rep["groups"][0]["specimen"])
        self.assertIn("合并提示", rep["groups"][0]["hint"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
