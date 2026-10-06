# -*- coding: utf-8 -*-
"""test_flywheel_shaft.py — 批一红绿锁（工单-经验飞轮优化统合-20261005 §二-1-1 全负例）

守的四件扩展契约：
  ① facts 机器槽位：add() 接受可 JSON 化 dict，非 dict/不可序列化响亮拒绝；
  ② verify() draft→verified 机器通道：actor 限 machine:*，回执路径归一化+白名单目录
     +verdict=咬合 三重检查，缺一响亮拒绝（伪回执/仓外路径/无回执/human 冒名全负例）；
  ③ recall_tier() 双层供血：verified+approved 出血带 tier 标、approved 优先，
     draft 不供血（防毒现行），空库返回空列表不炸；
  ④ record_outcome() 油量计：result∈{success,failure}，append-only 只增不改。
红灯先行：本文件先于实现存在。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from precedent_gov import PrecedentStore, GovernanceRefusal  # noqa: E402


def mk(eid, text, owner=""):
    return {"id": eid, "type": "semantic", "importance": 2,
            "keywords": ["布线", "flux2", "验收"],
            "content": {"c": text, "a": "站2沙盒实测", "d": "适用 flux2 系"},
            "evidence": {"artifact": "test", "quote": text[:20], "recalc": "复跑"},
            "owner": owner}


class FactsSlotTests(unittest.TestCase):
    def test_add_accepts_facts_dict(self):
        store = PrecedentStore()
        store.add(mk("F-1", "带机器槽位"), actor="ai:x",
                  facts={"Flux2Scheduler": ["steps", "width", "height"]})
        self.assertEqual(store._get("F-1")["facts"], {"Flux2Scheduler": ["steps", "width", "height"]})

    def test_add_rejects_non_dict_facts(self):
        store = PrecedentStore()
        with self.assertRaises(ValueError):
            store.add(mk("F-2", "字符串槽位"), actor="ai:x", facts="steps,width,height")

    def test_add_rejects_unserializable_facts(self):
        store = PrecedentStore()
        with self.assertRaises(ValueError):
            store.add(mk("F-3", "不可序列化"), actor="ai:x", facts={"fn": object()})


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shaft-")
        self.store = PrecedentStore()
        self.store.add(mk("V-1", "待机器验证件"), actor="machine:线")
        self.good_receipt = os.path.join(self.tmp, "good_receipt.json")
        with open(self.good_receipt, "w", encoding="utf-8") as fh:
            json.dump({"verdict": "咬合"}, fh)

    def test_verify_happy_path(self):
        ev = self.store.verify("V-1", actor="machine:卷十二线-field", receipt=self.good_receipt,
                               whitelist=[self.tmp])
        self.assertEqual(self.store._get("V-1")["gov"], "verified")
        self.assertEqual(ev["kind"], "verify")

    def test_verify_rejects_human_actor(self):
        with self.assertRaises(GovernanceRefusal):
            self.store.verify("V-1", actor="human:假冒机器", receipt=self.good_receipt,
                              whitelist=[self.tmp])

    def test_verify_rejects_missing_receipt(self):
        with self.assertRaises(ValueError):
            self.store.verify("V-1", actor="machine:线", receipt=os.path.join(self.tmp, "无.json"),
                              whitelist=[self.tmp])

    def test_verify_rejects_receipt_outside_whitelist(self):
        outside = os.path.join(tempfile.mkdtemp(prefix="outside-"), "r.json")
        with open(outside, "w", encoding="utf-8") as fh:
            json.dump({"verdict": "咬合"}, fh)
        with self.assertRaises(ValueError):
            self.store.verify("V-1", actor="machine:线", receipt=outside, whitelist=[self.tmp])

    def test_verify_rejects_receipt_without_bite(self):
        bad = os.path.join(self.tmp, "bad_receipt.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump({"verdict": "不咬合"}, fh)
        with self.assertRaises(ValueError):
            self.store.verify("V-1", actor="machine:线", receipt=bad, whitelist=[self.tmp])

    def test_verify_rejects_non_draft(self):
        self.store.verify("V-1", actor="machine:线", receipt=self.good_receipt, whitelist=[self.tmp])
        with self.assertRaises(GovernanceRefusal):
            self.store.verify("V-1", actor="machine:线", receipt=self.good_receipt, whitelist=[self.tmp])


class RecallTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shaft-")
        self.receipt = os.path.join(self.tmp, "r.json")
        with open(self.receipt, "w", encoding="utf-8") as fh:
            json.dump({"verdict": "咬合"}, fh)

    def _store_with_three_tiers(self):
        store = PrecedentStore()
        store.add(mk("T-promoted", "人阀放行件", owner="human:维护者"), actor="ai:x",
                  facts={"K": ["a"]})
        store.promote("T-promoted", actor="human:维护者")
        store.add(mk("T-verified", "机器验证件"), actor="machine:线", facts={"K": ["b"]})
        store.verify("T-verified", actor="machine:线", receipt=self.receipt,
                     whitelist=[self.tmp])
        store.add(mk("T-draft", "草稿不供血"), actor="ai:x")
        return store

    def test_recall_tier_serves_two_excludes_draft(self):
        store = self._store_with_three_tiers()
        hits = store.recall_tier("布线")
        tiers = {e["id"]: e["_tier"] for _, e in hits}
        self.assertIn("T-promoted", tiers)
        self.assertIn("T-verified", tiers)
        self.assertNotIn("T-draft", tiers)

    def test_recall_tier_promoted_first(self):
        store = self._store_with_three_tiers()
        hits = store.recall_tier("布线")
        self.assertEqual(hits[0][1]["_tier"], "approved")

    def test_recall_tier_empty_store_returns_empty(self):
        self.assertEqual(PrecedentStore().recall_tier("布线"), [])

    def test_recall_tier_no_facts_entries_still_served(self):
        """无 facts 的 approved 也供血——消费侧负责跳过计数，不静默。"""
        store = PrecedentStore()
        store.add(mk("T-nofacts", "散文教训", owner="human:维护者"), actor="ai:x")
        store.promote("T-nofacts", actor="human:维护者")
        hits = store.recall_tier("布线")
        self.assertEqual([e["id"] for _, e in hits], ["T-nofacts"])


class OutcomeTests(unittest.TestCase):
    def test_record_outcome_appends(self):
        store = PrecedentStore()
        store.add(mk("O-1", "油量计"), actor="ai:x")
        store.record_outcome("O-1", result="success", context="EXP-1")
        store.record_outcome("O-1", result="failure", context="EXP-2")
        outs = store._get("O-1")["outcomes"]
        self.assertEqual([o["result"] for o in outs], ["success", "failure"])
        self.assertEqual(outs[0]["context"], "EXP-1")

    def test_record_outcome_rejects_bad_result(self):
        store = PrecedentStore()
        store.add(mk("O-2", "油量计"), actor="ai:x")
        with self.assertRaises(ValueError):
            store.record_outcome("O-2", result="maybe", context="X")

    def test_outcome_rides_through_save_load(self):
        store = PrecedentStore()
        store.add(mk("O-3", "持久化"), actor="ai:x", facts={"K": [1]})
        store.record_outcome("O-3", result="failure", context="EXP-3")
        tmp = os.path.join(tempfile.mkdtemp(prefix="shaft-"), "s.json")
        store.save(tmp)
        loaded = PrecedentStore.load(tmp)
        self.assertEqual(loaded._get("O-3")["facts"], {"K": [1]})
        self.assertEqual(len(loaded._get("O-3")["outcomes"]), 1)


class RetrievalQualityGoldenTests(unittest.TestCase):
    """金查询集回归（候裁件④配套 · 检索质量守门）：已知小语料 + 期望命中，
    锁死 recall_tier 的排序行为——语料扩到百条后此集跑红即检索退化报警。
    扩语料时按比例增金查询对（建议 ≥1 对/10 条）。"""

    def _golden_store(self):
        import json as _json
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="golden-")
        receipt = os.path.join(tmp, "r.json")
        with open(receipt, "w", encoding="utf-8") as fh:
            _json.dump({"verdict": "咬合"}, fh)
        store = PrecedentStore()
        corpus = [
            ("G-flux", ["flux2", "布线", "klein"], {"Flux2Scheduler": ["steps"]}),
            ("G-lora", ["noobai", "lora", "风格"], None),
            ("G-video", ["anisora", "视频", "wan22"], {"CLIPLoader.wan": ["clip_name"]}),
        ]
        for eid, kws, facts in corpus:
            e = mk(eid, f"金查询集语料 {eid}")
            e["keywords"] = kws
            store.add(e, actor="machine:golden", facts=facts)
            store.verify(eid, actor="machine:golden", receipt=receipt, whitelist=[tmp])
        return store

    def test_exact_keyword_hits_right_entry_first(self):
        store = self._golden_store()
        hits = store.recall_tier("anisora 视频")
        self.assertEqual(hits[0][1]["id"], "G-video")

    def test_cross_domain_query_does_not_cross_rank(self):
        store = self._golden_store()
        hits = store.recall_tier("noobai lora")
        self.assertEqual(hits[0][1]["id"], "G-lora")
        ids = [e["id"] for _, e in hits]
        self.assertNotIn("G-video", ids[:1])  # 视频条目不得窜到 lora 查询首位

    def test_tier_order_stable_in_golden_set(self):
        store = self._golden_store()
        e = mk("G-promoted", "金标晋升件")
        e["keywords"] = ["flux2", "布线", "金标"]
        store.add(e, actor="ai:x", facts={"Flux2Scheduler": ["steps", "width"]})
        store.promote("G-promoted", actor="human:维护者")
        hits = store.recall_tier("flux2 布线")
        self.assertEqual(hits[0][1]["_tier"], "approved")  # promoted 恒压 verified


if __name__ == "__main__":
    unittest.main(verbosity=2)
