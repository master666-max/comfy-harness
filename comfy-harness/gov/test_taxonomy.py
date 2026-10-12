# -*- coding: utf-8 -*-
"""test_taxonomy.py — v2 分类分面红绿锁（20261007 · 维护者三问后铺齐）

七条契约：
  ① 词表校验：task/kind/level 值域外构造即拒；kind 允许列表（混体双面）
  ② 存量回溯：真库 13 条全部带合法三字段（不落下任何一件）
  ③ task 分面：过滤 t2i 不得放 i2v 件入池；task=general 件跨类服务
  ④ kind 分面：混体件（kind 列表）在 prompt 过滤下可见（提示词经验可检出）
  ⑤ level 分面
  ⑥ 无字段件在带过滤时被排除且计数披露（禁静默）
  ⑦ 不带过滤=老行为零变（向后兼容）
红灯先行。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from precedent_gov import PrecedentStore, TASKS, KINDS, LEVELS  # noqa: E402


def mk(eid, **extra):
    e = {"id": eid, "type": "semantic", "importance": 2, "keywords": ["k", "测试"],
         "content": {"c": f"x-{eid}", "a": "y", "d": "z"},   # 内容注入 id 防 L2 去重误撞
         "evidence": {"artifact": "t", "quote": "q", "recalc": "r"}, "owner": ""}
    e.update(extra)
    return e


class VocabTests(unittest.TestCase):
    def test_bad_task_rejected(self):
        s = PrecedentStore()
        with self.assertRaises(ValueError):
            s.add(mk("A", task="文生图"), actor="ai:x")   # 值域外（中文名不是码）

    def test_bad_kind_rejected(self):
        s = PrecedentStore()
        with self.assertRaises(ValueError):
            s.add(mk("A", kind="prompteng"), actor="ai:x")

    def test_kind_list_allowed_for_hybrids(self):
        s = PrecedentStore()
        s.add(mk("A", task="t2i", kind=["prompt", "pipeline"], level="specialized"), actor="ai:x")
        self.assertEqual(s._get("A")["kind"], ["prompt", "pipeline"])

    def test_bad_level_rejected(self):
        s = PrecedentStore()
        with self.assertRaises(ValueError):
            s.add(mk("A", level="universal"), actor="ai:x")


class FacetRetrievalTests(unittest.TestCase):
    def _store(self):
        s = PrecedentStore()
        s.add(mk("T2I-PIPE", task="t2i", kind="pipeline", level="specialized"), actor="ai:x")
        s.add(mk("I2V-PIPE", task="i2v", kind="pipeline", level="specialized"), actor="ai:x")
        s.add(mk("HYBRID", task="t2i", kind=["prompt", "pipeline"], level="specialized"), actor="ai:x")
        s.add(mk("GENERAL", task="general", kind="governance", level="general"), actor="ai:x")
        s.add(mk("UNLABELED"), actor="ai:x")
        for eid in ("T2I-PIPE", "I2V-PIPE", "HYBRID", "GENERAL", "UNLABELED"):
            s.promote(eid, actor="human:维护者")
        return s

    def test_task_facet_excludes_other_tasks(self):
        hits = self._store().recall_tier("k 测试", k=9, task="t2i")
        ids = [e["id"] for _, e in hits]
        self.assertIn("T2I-PIPE", ids)
        self.assertNotIn("I2V-PIPE", ids, "i2v 件不得混入 t2i 检索")
        self.assertIn("GENERAL", ids, "task=general 跨类服务")

    def test_kind_facet_sees_hybrid_under_prompt(self):
        hits = self._store().recall_tier("k 测试", k=9, kind="prompt")
        ids = [e["id"] for _, e in hits]
        self.assertIn("HYBRID", ids, "混体件的 prompt 面必须可检出")

    def test_level_facet(self):
        hits = self._store().recall_tier("k 测试", k=9, level="general")
        ids = [e["id"] for _, e in hits]
        self.assertEqual(ids, ["GENERAL"])

    def test_unlabeled_excluded_and_counted(self):
        s = self._store()
        hits = s.recall_tier("k 测试", k=9, task="t2i")
        self.assertNotIn("UNLABELED", [e["id"] for _, e in hits])
        self.assertGreaterEqual(s.last_filtered["excluded_unlabeled"], 1)

    def test_no_filter_backward_compatible(self):
        s = self._store()
        hits = s.recall_tier("k 测试", k=9)
        ids = [e["id"] for _, e in hits]
        self.assertIn("UNLABELED", ids)          # 无过滤：老行为零变


class RealLibraryBackfillTests(unittest.TestCase):
    def test_all_seed_entries_carry_valid_taxonomy(self):
        seed = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "precedents_e2_seed.json")
        if not os.path.exists(seed):
            self.skipTest("seed 不在位")
        import json as _j
        d = _j.load(open(seed, encoding="utf-8"))
        for e in d["entries"]:
            tt = e.get("task")
            ts = tt if isinstance(tt, list) else [tt]
            self.assertTrue(ts and all(t in TASKS for t in ts), f"{e['id']} task 缺席/非法")
            kk = e.get("kind")
            ks = kk if isinstance(kk, list) else [kk]
            self.assertTrue(all(k in KINDS for k in ks), f"{e['id']} kind 非法")
            self.assertIn(e.get("level"), LEVELS, f"{e['id']} level 缺席/非法")

    def test_prompt_cluster_exists(self):
        """提示词面主场比赛：库里必须有 ≥1 条 kind 含 prompt 的件。"""
        seed = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "precedents_e2_seed.json")
        if not os.path.exists(seed):
            self.skipTest("seed 不在位")
        import json as _j
        d = _j.load(open(seed, encoding="utf-8"))
        got = False
        for e in d["entries"]:
            kk = e.get("kind")
            ks = kk if isinstance(kk, list) else [kk]
            got = got or "prompt" in ks
        self.assertTrue(got, "全库零 prompt 件=提示词面空白（三问痛点）")


class PoolCoverageTests(unittest.TestCase):
    """严查（20261007）：全池分类覆盖——E-1 游离池孤儿教训必须迁入受治池且带全分类。"""

    def test_orphan_lessons_migrated_with_taxonomy(self):
        seed = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "precedents_e2_seed.json")
        import json as _j
        d = _j.load(open(seed, encoding="utf-8"))
        ids = {e["id"]: e for e in d["entries"]}
        for oid in ("P-uv-venv-trampoline", "P-objectinfo-cache"):
            self.assertIn(oid, ids, f"孤儿教训 {oid} 未迁入受治池")
            e = ids[oid]
            self.assertTrue(e.get("task") and e.get("kind") and e.get("level"),
                            f"{oid} 迁入件缺分类")

    def test_e1_pool_declares_frozen(self):
        lib = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "e1", "draft_library.json")
        import json as _j
        d = _j.load(open(lib, encoding="utf-8"))
        self.assertIn("frozen", str(d.get("_meta", {})).lower(),
                      "E-1 游离池未立冻结声明（迁移去向须在案）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
