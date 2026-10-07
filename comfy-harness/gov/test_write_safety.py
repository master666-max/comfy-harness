# -*- coding: utf-8 -*-
"""test_write_safety.py — 借鉴批红绿锁（引擎线内核研讨 · 20261007）

三件行：
  ① 写并发保护（CAS 版本戳）：两会话同 load → 后者 save 必须 DENY:STALE_SAVE 拒（禁静默覆盖）
  ② DENY 机读前缀：治理拒绝面消息带可机读码（NO_HUMAN_SIG/BAD_ACTOR/FAKE_RECEIPT/TWO_STAGE）
  ③ promote/verify 留痕带判据指针 prereg（`文件@版本`或 None）
红灯先行。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from precedent_gov import (PrecedentStore, GovernanceRefusal,  # noqa: E402
                           StaleWriteError)


def mk(eid, text="x"):
    return {"id": eid, "type": "semantic", "importance": 2, "keywords": ["k"],
            "content": {"c": f"{text}#{eid}", "a": "y", "d": "z"},   # 内容注入 id 防去重误撞
            "evidence": {"artifact": "t", "quote": "q", "recalc": "r"}, "owner": ""}


class CasWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cas-")
        self.seed = os.path.join(self.tmp, "s.json")
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        s.save(self.seed)

    def test_reload_then_save_ok(self):
        s = PrecedentStore.load(self.seed)
        s.add(mk("B"), actor="ai:x")
        s.save(self.seed)                                    # 无并发：正常
        self.assertEqual({e["id"] for e in PrecedentStore.load(self.seed).entries}, {"A", "B"})

    def test_concurrent_overwrite_refused(self):
        a = PrecedentStore.load(self.seed)
        b = PrecedentStore.load(self.seed)
        a.add(mk("A2"), actor="ai:x")
        a.save(self.seed)                                    # A 先写（rev 推进）
        b.add(mk("B2"), actor="ai:x")
        with self.assertRaises(StaleWriteError) as cm:
            b.save(self.seed)                                # B 基于旧 rev → 拒
        self.assertIn("DENY:STALE_SAVE", str(cm.exception))
        # 磁盘上 A2 在、B2 不在——静默覆盖被拦
        ids = {e["id"] for e in PrecedentStore.load(self.seed).entries}
        self.assertIn("A2", ids)
        self.assertNotIn("B2", ids)

    def test_refused_then_reload_and_retry_ok(self):
        a = PrecedentStore.load(self.seed)
        b = PrecedentStore.load(self.seed)
        a.add(mk("A2"), actor="ai:x")
        a.save(self.seed)
        b = PrecedentStore.load(self.seed)                   # 重载取新 rev
        b.add(mk("B2"), actor="ai:x")
        b.save(self.seed)                                    # 重试成功
        ids = {e["id"] for e in PrecedentStore.load(self.seed).entries}
        self.assertEqual(ids, {"A", "A2", "B2"})

    def test_rev_increments_on_disk(self):
        s = PrecedentStore.load(self.seed)
        s.save(self.seed)
        rev1 = json.load(open(self.seed, encoding="utf-8"))["_meta"]["rev"]
        s2 = PrecedentStore.load(self.seed)
        s2.save(self.seed)
        rev2 = json.load(open(self.seed, encoding="utf-8"))["_meta"]["rev"]
        self.assertEqual(rev2, rev1 + 1)


class DenyPrefixTests(unittest.TestCase):
    def test_human_signature_refusal_prefixed(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.promote("A", actor="ai:冒充")
        self.assertTrue(str(cm.exception).startswith("DENY:NO_HUMAN_SIG"))

    def test_verify_bad_actor_prefixed(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.verify("A", actor="human:冒名", receipt="x")
        self.assertTrue(str(cm.exception).startswith("DENY:BAD_ACTOR"))

    def test_two_stage_refusal_prefixed(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        s.promote("A", actor="human:维护者")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.tombstone("A", actor="human:维护者")
        self.assertTrue(str(cm.exception).startswith("DENY:TWO_STAGE"))

    def test_fake_receipt_refusal_prefixed(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        with self.assertRaises(ValueError) as cm:
            s.verify("A", actor="machine:线", receipt=os.path.join(tempfile.mkdtemp(), "无.json"))
        self.assertTrue(str(cm.exception).startswith("DENY:FAKE_RECEIPT"))


class PreregPointerTests(unittest.TestCase):
    def test_promote_event_carries_prereg_pointer(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        ev = s.promote("A", actor="human:维护者", prereg="落地判据件-v1-20261002.md@v1.1")
        self.assertEqual(ev["prereg"], "落地判据件-v1-20261002.md@v1.1")

    def test_promote_without_prereg_records_none(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        ev = s.promote("A", actor="human:维护者")
        self.assertIsNone(ev["prereg"])

    def test_verify_event_carries_prereg_pointer(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        tmp = tempfile.mkdtemp()
        r = os.path.join(tmp, "r.json")
        json.dump({"verdict": "咬合"}, open(r, "w", encoding="utf-8"))
        s._get("A")["evidence"]["artifact"] = "r.json"      # L3 绑定对齐
        ev = s.verify("A", actor="machine:线", receipt=r, whitelist=[tmp],
                      prereg="判据件@v1.1")
        self.assertEqual(ev["prereg"], "判据件@v1.1")


class SeverityTests(unittest.TestCase):
    """severity_if_wrong=退场路径标（借鉴批）——每笔治理事件自述若判错如何回退。"""

    def test_promote_event_carries_severity(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        ev = s.promote("A", actor="human:维护者")
        self.assertEqual(ev["severity_if_wrong"], "irreversible_ratchet")

    def test_verify_event_carries_severity(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        tmp = tempfile.mkdtemp()
        r = os.path.join(tmp, "r.json")
        json.dump({"verdict": "咬合"}, open(r, "w", encoding="utf-8"))
        s._get("A")["evidence"]["artifact"] = "r.json"      # L3 绑定对齐
        ev = s.verify("A", actor="machine:线", receipt=r, whitelist=[tmp])
        self.assertEqual(ev["severity_if_wrong"], "exitable_via_deprecate")

    def test_tombstone_event_carries_severity(self):
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        ev = s.tombstone("A", actor="human:维护者")
        self.assertEqual(ev["severity_if_wrong"], "audit_preserved")


class TransientAnnotationTests(unittest.TestCase):
    """取证发现（20261007）：_tier/_gov_flag 瞬时标注曾被 save 持久化污染库面——
    save 必须在持久化边界剥离。"""

    def test_transient_annotations_not_persisted(self):
        import tempfile as _tf
        tmp = _tf.mkdtemp()
        seed = os.path.join(tmp, "s.json")
        s = PrecedentStore()
        s.add(mk("A"), actor="ai:x")
        s.promote("A", actor="human:维护者")
        s.recall_tier("k")                      # 产生 _tier 标注
        s.save(seed)
        raw = open(seed, encoding="utf-8").read()
        self.assertNotIn("_tier", raw)
        self.assertNotIn("_gov_flag", raw)

    def test_loader_also_strips_legacy_pollution(self):
        import tempfile as _tf
        tmp = _tf.mkdtemp()
        seed = os.path.join(tmp, "s.json")
        e = mk("A"); e["_tier"] = "approved"    # 历史污染件
        json.dump({"_meta": {"rev": 1}, "entries": [e], "gov_events": []},
                  open(seed, "w", encoding="utf-8"), ensure_ascii=False)
        s = PrecedentStore.load(seed)
        self.assertNotIn("_tier", s.entries[0])


class LifecycleGuardTests(unittest.TestCase):
    """严肃盘查（20261007）：L1 重复ID / L3 回执绑定 / L4 晋升前置态——三处实锤的否决锁。"""

    def test_duplicate_id_rejected(self):
        s = PrecedentStore()
        s.add(mk("DUP-1", "第一版"), actor="ai:x")
        with self.assertRaises(ValueError) as cm:
            s.add(mk("DUP-1", "第二版"), actor="ai:x")
        self.assertIn("DENY:DUP_ID", str(cm.exception))

    def test_verify_requires_receipt_bound_to_evidence(self):
        s = PrecedentStore()
        s.add(mk("V-9", "绑定测试"), actor="ai:x")          # mk artifact="t"
        tmp = tempfile.mkdtemp()
        r = os.path.join(tmp, "unrelated.json")
        json.dump({"verdict": "咬合"}, open(r, "w", encoding="utf-8"))
        with self.assertRaises(ValueError) as cm:
            s.verify("V-9", actor="machine:线", receipt=r, whitelist=[tmp])
        self.assertIn("DENY:UNBOUND_RECEIPT", str(cm.exception))

    def test_verify_bound_receipt_passes(self):
        s = PrecedentStore()
        e = mk("V-10", "绑定正路")
        e["evidence"]["artifact"] = "bound.json"
        s.add(e, actor="ai:x")
        tmp = tempfile.mkdtemp()
        r = os.path.join(tmp, "bound.json")
        json.dump({"verdict": "咬合"}, open(r, "w", encoding="utf-8"))
        ev = s.verify("V-10", actor="machine:线", receipt=r, whitelist=[tmp])
        self.assertEqual(ev["kind"], "verify")

    def test_promote_rejects_deprecated(self):
        s = PrecedentStore()
        s.add(mk("P-9", "退场件"), actor="ai:x")
        s.deprecate("P-9", actor="human:维护者")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.promote("P-9", actor="human:维护者")
        self.assertIn("DENY:BAD_STATE", str(cm.exception))

    def test_promote_rejects_tombstoned(self):
        s = PrecedentStore()
        s.add(mk("T-9", "墓碑件"), actor="ai:x")
        s.tombstone("T-9", actor="human:维护者")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.promote("T-9", actor="human:维护者")
        self.assertIn("DENY:BAD_STATE", str(cm.exception))


class ContentDedupTests(unittest.TestCase):
    """L2 落地：内容幂等键（ec_entry.content_hash）去重——同内容异 ID 拒。"""

    def test_duplicate_content_rejected(self):
        s = PrecedentStore()
        e1 = mk("C-1", "同样的教训")
        e2 = mk("C-2", "同样的教训")
        e2["content"] = dict(e1["content"])          # 内容逐字同（绕开 mk 的 id 注入）
        e2["keywords"] = list(e1["keywords"])
        s.add(e1, actor="ai:x")
        with self.assertRaises(ValueError) as cm:
            s.add(e2, actor="ai:x")
        self.assertIn("DENY:DUP_CONTENT", str(cm.exception))
        self.assertIn("C-1", str(cm.exception))      # 指向既有件

    def test_distinct_content_allowed(self):
        s = PrecedentStore()
        s.add(mk("C-3", "甲教训"), actor="ai:x")
        s.add(mk("C-4", "乙教训"), actor="ai:x")     # 内容不同=合法新件
        self.assertEqual(len(s.entries), 2)


class AmendTests(unittest.TestCase):
    """L6 落地：元数据变更入账（amend）——分类/facts 的修改必须留事件。"""

    def test_amend_records_event_with_diff(self):
        s = PrecedentStore()
        e = mk("M-1", "元数据件")
        e.update(task="t2i", kind="pipeline", level="specialized")
        s.add(e, actor="ai:x")
        n0 = len(s.gov_events)
        ev = s.amend("M-1", {"level": "general", "facts": {"cfg": 4.5}},
                     reason="扩样后升域级", actor="ai:线")
        self.assertEqual(len(s.gov_events), n0 + 1)
        self.assertEqual(ev["kind"], "amend")
        self.assertEqual(ev["old"]["level"], "specialized")
        self.assertEqual(ev["new"]["level"], "general")
        self.assertEqual(s._get("M-1")["level"], "general")
        self.assertEqual(s._get("M-1")["facts"], {"cfg": 4.5})

    def test_amend_rejects_content_and_unknown(self):
        s = PrecedentStore()
        s.add(mk("M-2", "元数据件"), actor="ai:x")
        with self.assertRaises(ValueError) as cm:
            s.amend("M-2", {"content": {"c": "改文本"}}, reason="试探", actor="ai:x")
        self.assertIn("DENY:AMEND_FIELD", str(cm.exception))
        with self.assertRaises(ValueError):
            s.amend("M-2", {"whatever": 1}, reason="试探", actor="ai:x")

    def test_amend_validates_taxonomy_and_facts(self):
        s = PrecedentStore()
        s.add(mk("M-3", "元数据件"), actor="ai:x")
        with self.assertRaises(ValueError):
            s.amend("M-3", {"task": "文生图"}, reason="值域外", actor="ai:x")
        with self.assertRaises(ValueError):
            s.amend("M-3", {"facts": "不是dict"}, reason="形态错", actor="ai:x")

    def test_amend_missing_entry(self):
        with self.assertRaises(KeyError):
            PrecedentStore().amend("不存在", {"level": "general"}, reason="x", actor="ai:x")


class RetractTests(unittest.TestCase):
    """L5 裁定 A+C：机器下架权（machine_retracted 旗）——退出供血但不回退信任级；
    人可复架（relist）。信任级单向棘轮由声明与检查8 维系，不经此通道。"""

    def test_retract_requires_machine_actor(self):
        s = PrecedentStore()
        s.add(mk("R-1", "下架测试件"), actor="ai:x")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.retract("R-1", actor="human:想代劳", reason="x")
        self.assertIn("DENY:NO_MACHINE_SIG", str(cm.exception))

    def test_retract_sets_flag_and_event(self):
        s = PrecedentStore()
        s.add(mk("R-2", "下架测试件"), actor="ai:x")
        s.promote("R-2", actor="human:维护者")
        ev = s.retract("R-2", actor="machine:卷十二线", reason="独立复验失败",
                       evidence="field/out/receipt.json")
        self.assertTrue(s._get("R-2")["machine_retracted"])
        self.assertEqual(ev["kind"], "retract")
        self.assertEqual(ev["severity_if_wrong"], "relistable")

    def test_retracted_excluded_from_supply(self):
        s = PrecedentStore()
        s.add(mk("R-3", "供血测试件"), actor="ai:x")
        s.promote("R-3", actor="human:维护者")
        self.assertIn("R-3", [e["id"] for _, e in s.recall_tier("供血")])
        s.retract("R-3", actor="machine:线", reason="复验失败")
        self.assertNotIn("R-3", [e["id"] for _, e in s.recall_tier("供血")])
        self.assertEqual(s._get("R-3")["gov"], "approved")   # 信任级不动（棘轮不破）

    def test_relist_human_only(self):
        s = PrecedentStore()
        s.add(mk("R-4", "复架测试件"), actor="ai:x")
        s.promote("R-4", actor="human:维护者")
        s.retract("R-4", actor="machine:线", reason="误撤前")
        with self.assertRaises(GovernanceRefusal):
            s.relist("R-4", actor="machine:线")              # 机器不能自复架
        ev = s.relist("R-4", actor="human:维护者", reason="复核后恢复")
        self.assertFalse(s._get("R-4").get("machine_retracted"))
        self.assertEqual(ev["kind"], "relist")
        self.assertIn("R-4", [e["id"] for _, e in s.recall_tier("复架")])

    def test_relist_non_retracted_refused(self):
        s = PrecedentStore()
        s.add(mk("R-5", "未下架件"), actor="ai:x")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.relist("R-5", actor="human:维护者")
        self.assertIn("DENY:BAD_STATE", str(cm.exception))

    def test_retract_tombstoned_refused(self):
        s = PrecedentStore()
        s.add(mk("R-6", "墓碑件"), actor="ai:x")
        s.tombstone("R-6", actor="human:维护者")
        with self.assertRaises(GovernanceRefusal) as cm:
            s.retract("R-6", actor="machine:线", reason="x")
        self.assertIn("DENY:BAD_STATE", str(cm.exception))


class FactsPlaneTests(unittest.TestCase):
    """facts 单面规则（20261007）：每条目 facts 键必须同属一个消费面；未知键构造即拒。
    面登记表=单一事实源（precedent_gov.FACTS_PLANES），提交闸/巡检/构造器共用。"""

    def test_cross_plane_facts_rejected(self):
        s = PrecedentStore()
        with self.assertRaises(ValueError) as cm:
            s.add(mk("PL-1", "混面件"), actor="ai:x",
                  facts={"quality_tags": ["a"], "cfg": 4.5})   # prompt×pipeline 混
        self.assertIn("DENY:PLANE_MIX", str(cm.exception))

    def test_unknown_key_rejected(self):
        s = PrecedentStore()
        with self.assertRaises(ValueError) as cm:
            s.add(mk("PL-2", "未知键件"), actor="ai:x", facts={"whatever": 1})
        self.assertIn("DENY:PLANE_UNKNOWN", str(cm.exception))

    def test_single_plane_ok(self):
        s = PrecedentStore()
        s.add(mk("PL-3", "单面件"), actor="ai:x",
              facts={"quality_tags": ["a"], "eye_tags": ["b"]})   # 同 prompt 面
        self.assertIn("PL-3", [e["id"] for e in s.entries])

    def test_amend_cross_plane_rejected(self):
        s = PrecedentStore()
        e = mk("PL-4", "amend混面")
        e["facts"] = {"cfg": 4.5}
        s.add(e, actor="ai:x")
        with self.assertRaises(ValueError) as cm:
            s.amend("PL-4", {"facts": {"cfg": 4.5, "quality_tags": ["x"]}},
                    reason="试探", actor="ai:x")
        self.assertIn("DENY:PLANE_MIX", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
