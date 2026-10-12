# -*- coding: utf-8 -*-
"""test_candidate_pool.py — N2 成熟度闸红绿（复现才铸；RecMem 语义）"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".."))
import style_feed as sf                 # noqa: E402
import candidate_pool as cp             # noqa: E402


def _cand():
    return {"name": "成熟度测试束", "members": ["azurea", "cerulea", "diantha", "eulalia"],
            "arms": ["det"], "cohesion": 0.9, "evidence": ["generation:m.png"]}


class TestMaturityGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "seed.json")
        shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "precedents_e2_seed.json"), self.store)
        self.pool = os.path.join(self.tmp.name, "pool.json")
        self.rec = os.path.join(self.tmp.name, "rec.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self):
        from precedent_gov import PrecedentStore
        return PrecedentStore.load(self.store)

    def _key(self):
        pl = cp.load_pool(self.pool)
        self.assertEqual(len(pl), 1)                       # 单概念单键
        return next(iter(pl))

    def test_first_sight_pools_second_round_mints(self):
        # 第一轮：首现 → 落池不铸（其他闸全过也拦）
        s = self._load()
        r1 = sf.feed([_cand()], s, [], min_size=4, pool_path=self.pool,
                     recurrence_path=self.rec)
        self.assertEqual(len(r1["minted"]), 0)
        self.assertTrue(any("成熟度闸" in sk["why"] for sk in r1["skipped"]), r1["skipped"])
        self.assertEqual(cp.load_pool(self.pool)[self._key()]["rounds_seen"], 1)
        # 第二轮（成员**漂移**——换两个代表词）：同概念仍应认复现 → 铸
        drifted = dict(_cand())
        drifted["members"] = ["azurea", "cerulea", "diantha", "eulalia", "fabella", "galeata"]
        s2 = self._load()
        r2 = sf.feed([drifted], s2, [], min_size=4, pool_path=self.pool,
                     recurrence_path=self.rec)
        self.assertEqual(len(r2["minted"]), 1, r2["skipped"])
        pl = cp.load_pool(self.pool)
        key = self._key()
        self.assertEqual(pl[key]["rounds_seen"], 2)
        self.assertGreaterEqual(len(pl[key].get("sig_seen") or []), 2)   # 两轮签名各异但同键
        self.assertEqual(pl[key].get("minted"), r2["minted"][0]["id"])

    def test_robust_key_by_base(self):
        """键函数：同基底名 → 同键（不依赖成员集一致）。"""
        pool = {"s-alpha": {"members": ["x", "y"], "rounds_seen": 1}}
        self.assertEqual(cp.key_of(pool, {"name": "alpha", "members": ["p", "q"]}), "s-alpha")
        # 基底不着但标签 Jaccard≥0.5 → 归并到既有键
        self.assertEqual(cp.key_of(pool, {"name": "beta", "members": ["x", "y"]}), "s-alpha")
        # 都不着 → 以自身基底立新键
        self.assertEqual(cp.key_of(pool, {"name": "gamma", "members": ["m", "n"]}), "s-gamma")

    def test_min_rounds_one_backcompat(self):
        s = self._load()
        r = sf.feed([_cand()], s, [], min_size=4, pool_path=self.pool,
                    min_rounds=1, recurrence_path=self.rec)
        self.assertEqual(len(r["minted"]), 1)                    # 一票即铸（旧语义）

    def test_pool_without_gate_is_noop(self):
        s = self._load()
        r = sf.feed([_cand()], s, [], min_size=4, recurrence_path=self.rec)
        self.assertEqual(len(r["minted"]), 1)                    # 不给 pool → 闸关
        self.assertFalse(os.path.isfile(self.pool))


if __name__ == "__main__":
    unittest.main(verbosity=2)
