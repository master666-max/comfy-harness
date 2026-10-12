# -*- coding: utf-8 -*-
"""test_gov_hygiene.py — P0 治理卫生红绿（工单-飞轮根治与向量化统合）

三修复：
  ① recall()（人侧通道）未排除 machine_retracted——与 recall_tier 口径不一致（审计发现）。
  ② promote() 缺 machine_retracted 护栏（tombstone/deprecated 已拦）——下架提案可被
     直接升格绕过 relist 两步制。
  ③ precedent_cli promote-drafts 未排除已撤场草稿（tombstone 会当场炸循环、
     machine_retracted 会被误转正）——与 status 口径不一致。
"""
import argparse
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), ".."))            # 仓根（evocore）
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "..", "tools"))  # precedent_cli
from precedent_gov import PrecedentStore, GovernanceRefusal  # noqa: E402


class TestGovHygiene(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.seed = os.path.join(self.tmp.name, "seed.json")
        shutil.copy(os.path.join(_HERE, "precedents_e2_seed.json"), self.seed)

    def tearDown(self):
        self.tmp.cleanup()

    def _approved_eid(self, s):
        return next(e["id"] for e in s.entries
                    if e.get("gov") == "approved" and (e.get("owner") or "").startswith("human:"))

    def _draft_eids(self, s, n):
        got = [e["id"] for e in s.entries
               if e.get("gov") == "draft" and not e.get("tombstone")
               and not e.get("machine_retracted")]
        self.assertGreaterEqual(len(got), n)
        return got[:n]

    # ── ① recall 排 machine_retracted ──
    def test_recall_excludes_machine_retracted(self):
        # 差分测试：先用能命中的查询证明基线可见（防"不命中=通过"自欺），再验撤/复架
        Q = "正式考 异族判官"
        s = PrecedentStore.load(self.seed)
        eid = self._approved_eid(s)
        base = [e["id"] for _, e in s.recall(Q, k=200)]
        self.assertIn(eid, base, "前置：查询应命中该件（否则测试自欺）")
        s.retract(eid, actor="machine:test", reason="复验失败")
        got = [e["id"] for _, e in s.recall(Q, k=200)]
        self.assertNotIn(eid, got, "retract 后 recall() 仍返回该件（供血面漏排）")
        got2 = [e["id"] for _, e in s.recall_tier(Q, k=200)]
        self.assertNotIn(eid, got2)
        s.relist(eid, actor="human:tester", reason="复核恢复")     # 人签复架应恢复供血
        got3 = [e["id"] for _, e in s.recall(Q, k=200)]
        self.assertIn(eid, got3)

    # ── ② promote 拒 machine_retracted ──
    def test_promote_rejects_machine_retracted(self):
        s = PrecedentStore.load(self.seed)
        eid = self._draft_eids(s, 1)[0]
        s.retract(eid, actor="machine:test", reason="撤场")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.promote(eid, actor="human:tester")
        self.assertIn("BAD_STATE", str(cm.exception))

    # ── ③ promote-drafts 排已撤场 ──
    def test_promote_drafts_cli_skips_withdrawn(self):
        import precedent_cli
        s = PrecedentStore.load(self.seed)
        d_tomb, d_ret, d_ok = self._draft_eids(s, 3)
        s.tombstone(d_tomb, actor="human:tester", reason="测试撤场")
        s.retract(d_ret, actor="machine:test", reason="测试下架")
        s.save(self.seed)
        rc = precedent_cli.cmd_promote_drafts(
            argparse.Namespace(seed=self.seed, actor="human:tester", prereg=None))
        self.assertEqual(rc, 0)                                    # 不得中途炸
        s2 = PrecedentStore.load(self.seed)
        gov = {e["id"]: e.get("gov") for e in s2.entries}
        self.assertEqual(gov[d_ok], "approved")                    # 干净件照常转正
        self.assertEqual(gov[d_tomb], "draft")                     # 墓碑件不动
        self.assertEqual(gov[d_ret], "draft")                      # 下架件不动


if __name__ == "__main__":
    unittest.main(verbosity=2)
