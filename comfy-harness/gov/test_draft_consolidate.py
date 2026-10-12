# -*- coding: utf-8 -*-
"""test_draft_consolidate.py — N4 更迭三件套 + N8 衰减红绿（工单 P5）"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".."))
import draft_consolidate as dc      # noqa: E402
from precedent_gov import PrecedentStore  # noqa: E402


class TestConsolidate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "seed.json")
        shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "precedents_e2_seed.json"), self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _drafts(self, s, n=2, need=None):
        out = [e for e in s.entries if e.get("gov") == "draft"
               and not e.get("tombstone") and not e.get("machine_retracted")]
        if need:
            out = [e for e in out if need(e)]
        self.assertGreaterEqual(len(out), n)
        return out[:n]

    def test_merge_three_piece_chain(self):
        s = PrecedentStore.load(self.store)
        olds = self._drafts(s, 2)
        old_ids = [e["id"] for e in olds]
        r = dc.merge(s, old_ids, name="合并测试束")
        self.assertTrue(r["new"].startswith("S-"))
        s.save(self.store)
        s2 = PrecedentStore.load(self.store)
        new = s2._get(r["new"])
        self.assertEqual(new.get("gov"), "draft")                   # 非放大：仍 draft
        self.assertEqual(new["_mine_gen"], r["gen"])
        self.assertEqual(new["facts"]["merged_from"], old_ids)      # amend 链落定
        for oid in old_ids:                                          # ② 旧条已机器下架
            o = s2._get(oid)
            self.assertTrue(o.get("machine_retracted"))
            self.assertEqual(o.get("gov"), "draft")                 # 信任级未动
        kinds = [ev.get("kind") for ev in s2.gov_events if ev.get("id") in old_ids + [r["new"]]]
        self.assertIn("retract", kinds)
        self.assertIn("amend", kinds)                                # ③ amend 事件在账
        s2.relist(old_ids[0], actor="human:tester", reason="复核恢复")  # 可复架
        self.assertFalse(s2._get(old_ids[0]).get("machine_retracted"))

    def test_merge_refuses_approved(self):
        s = PrecedentStore.load(self.store)
        approved = next(e["id"] for e in s.entries if e.get("gov") == "approved")
        with self.assertRaises(SystemExit):
            dc.merge(s, [approved, approved], dry=True)

    def test_decay_exemptions_and_stale(self):
        s = PrecedentStore.load(self.store)
        approved_kw = set()
        for e in s.entries:
            if e.get("gov") in ("approved", "verified"):
                approved_kw |= {str(k).lower() for k in (e.get("keywords") or [])}
        # 找一条与已签条目无≥2词重叠的草案当 stale 靶
        target = None
        for e in s.entries:
            if e.get("gov") != "draft" or e.get("tombstone"):
                continue
            kw = {str(k).lower() for k in (e.get("keywords") or [])}
            if len(kw & approved_kw) < 2:
                target = e
                break
        self.assertIsNotNone(target, "找不到无关联草案靶（夹具环境变化）")
        target["_added_at"] = (datetime.datetime.now()
                               - datetime.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
        s.save(self.store)
        rec = {self._drafts(s, 1, need=lambda e: e["id"] != target["id"])[0]["id"]:
               {"count": 2, "rounds": []}}
        r = dc.decay(s, rec, max_age_days=3)
        self.assertIn(target["id"], r["stale"])
        self.assertNotIn(rec and list(rec)[0], r["stale"])           # 复现者豁免
        s.save(self.store)
        s2 = PrecedentStore.load(self.store)
        self.assertTrue(s2._get(target["id"]).get("machine_retracted"))   # 已出清
        self.assertEqual(s2._get(target["id"]).get("gov"), "draft")       # 信任级未动


if __name__ == "__main__":
    unittest.main(verbosity=2)
