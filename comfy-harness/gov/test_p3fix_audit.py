# -*- coding: utf-8 -*-
"""P3 审计修复红绿锁 · comfy-harness（承 reports/audit p3-comfyui/audit-report.md 修复段）

P3-1 治理状态持久化：save/load（原子写 + 载入防毒再验证）+ promote 落 owner（闭环断链修复）；
P4-1 e2 机械锚 0.0 边界：edge_energy=0.0 不再当缺失吞掉。
红灯先行（本文件先于实现存在，跑出 fail 才动 production 代码）。
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
from precedent_gov import PrecedentStore, GovernanceRefusal  # noqa: E402


def mk(eid, text, owner=""):
    return {"id": eid, "type": "semantic", "importance": 2,
            "keywords": ["黄鸭", "裁剪", "验收"],
            "content": {"c": text, "a": "站2沙盒实测", "d": "适用裁剪去鸭场景"},
            "evidence": {"artifact": "调研-卷十二-C1站2-沙盒", "quote": text[:20], "recalc": "复跑 E2"},
            "owner": owner}


class PromoteOwnerTests(unittest.TestCase):
    """闭环断链修复：promote 须让无主判例落到签署人名下（种子自述'promote后进召回'）。"""

    def test_promote_stamps_owner_when_empty(self):
        store = PrecedentStore()
        store.add(mk("X-1", "无主草稿"), actor="ai:线")
        store.promote("X-1", actor="human:维护者")
        self.assertEqual(store._get("X-1")["owner"], "human:维护者")
        ids = [e["id"] for _, e in store.recall("黄鸭 裁剪")]
        self.assertIn("X-1", ids)

    def test_promote_preserves_existing_owner(self):
        store = PrecedentStore()
        store.add(mk("X-2", "有主判例", owner="human:原主"), actor="ai:线")
        store.promote("X-2", actor="human:另一人")
        self.assertEqual(store._get("X-2")["owner"], "human:原主")


class PersistenceTests(unittest.TestCase):
    """P3-1：save/load 往返 + 载入防毒再验证（fail-closed，不静默信任盘面）。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="p3fix-")
        self.path = os.path.join(self.tmpdir, "precedents.json")

    def _seed(self):
        store = PrecedentStore()
        store.add(mk("R-1", "正路晋升件"), actor="ai:线")
        store.add(mk("R-2", "留仓草稿"), actor="ai:线")
        store.promote("R-1", actor="human:维护者")
        store.deprecate("R-2", actor="human:维护者", reason="演练")
        return store

    def test_roundtrip_preserves_state_and_events(self):
        store = self._seed()
        store.save(self.path)
        loaded = PrecedentStore.load(self.path)
        self.assertEqual(loaded._get("R-1")["gov"], "approved")
        self.assertEqual(loaded._get("R-1")["owner"], "human:维护者")
        self.assertEqual(loaded._get("R-2")["gov"], "draft")
        self.assertTrue(loaded._get("R-2").get("deprecated"))
        self.assertEqual(len(loaded.gov_events), len(store.gov_events))
        ids = [e["id"] for _, e in loaded.recall("黄鸭 裁剪")]
        self.assertIn("R-1", ids)
        self.assertNotIn("R-2", ids)  # deprecated 仍可召回但本例关键词同池——owner 在即可召回,退场旗另测

    def test_two_stage_exit_survives_roundtrip(self):
        store = self._seed()
        store.save(self.path)
        loaded = PrecedentStore.load(self.path)
        with self.assertRaises(GovernanceRefusal):
            loaded.tombstone("R-1", actor="human:维护者")  # approved 未 deprecate 先墓碑=拒
        loaded.tombstone("R-2", actor="human:维护者")      # deprecated→墓碑=两段式正路
        self.assertTrue(loaded._get("R-2").get("tombstone"))

    def test_load_downgrades_forged_approved(self):
        forged = {"entries": [mk("F-1", "伪造核准——无 promote 事件背书", owner="human:伪造者")],
                  "gov_events": [{"kind": "add", "id": "F-1", "actor": "ai:线", "at": "t"}]}
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(forged, fh, ensure_ascii=False)
        loaded = PrecedentStore.load(self.path)
        e = loaded._get("F-1")
        self.assertEqual(e["gov"], "draft")      # 核准态无事件背书→降回草稿
        self.assertEqual(e["owner"], "")         # 可召回面一并收回（无主防毒）
        kinds = [ev["kind"] for ev in loaded.gov_events]
        self.assertIn("load_anomaly", kinds)     # 异常响亮留痕，不静默

    def test_load_keeps_tombstone_without_resurrection(self):
        ent = mk("T-1", "盘面墓碑无事件")
        ent["tombstone"] = True
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"entries": [ent], "gov_events": []}, fh, ensure_ascii=False)
        loaded = PrecedentStore.load(self.path)
        self.assertTrue(loaded._get("T-1").get("tombstone"))  # 保守态保留（禁销毁式回退）
        self.assertEqual([e["id"] for _, e in loaded.recall("黄鸭")], [])

    def test_save_is_atomic_no_tmp_leftover(self):
        store = self._seed()
        store.save(self.path)
        leftovers = [f for f in os.listdir(self.tmpdir) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("entries", data) and self.assertIn("gov_events", data)


def _load_e2mod():
    spec = importlib.util.spec_from_file_location(
        "e2mod", os.path.join(_ROOT, "comfy-harness", "e2", "e2_deepseek_exam.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AnchorZeroTests(unittest.TestCase):
    """P4-1：机械锚 0.0 是实测值不是缺失——不得被 falsy 判断吞掉。"""

    def test_zero_edge_energy_is_emitted(self):
        mod = _load_e2mod()
        txt = mod.anchors_text({"S_mean": 0.0, "colorfulness": 0.0, "edge_energy": 0.0})
        self.assertIn("边缘能量=0.00", txt)

    def test_none_edge_energy_omitted(self):
        mod = _load_e2mod()
        txt = mod.anchors_text({"S_mean": 1.0, "colorfulness": 2.0, "edge_energy": None})
        self.assertNotIn("边缘能量", txt)

    def test_normal_edge_energy_emitted(self):
        mod = _load_e2mod()
        txt = mod.anchors_text({"S_mean": 1.0, "colorfulness": 2.0, "edge_energy": 5.95})
        self.assertIn("边缘能量=5.95", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
