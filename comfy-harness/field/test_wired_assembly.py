# -*- coding: utf-8 -*-
"""test_wired_assembly.py — 批一-2 传动轴消费者红绿锁（工单 §二-1-2）

守 wired_assembly 的三个契约：
  ① facts 提取：recall_tier 命中带 facts 条目 → 按 class 抽机器事实，facts_source="recall"；
  ② 无 facts 跳过并计数：散文教训条目被跳过进 skipped_no_facts 计数（禁静默）；
  ③ 零召回回退：空供血 → naive_prior 原样返回，facts_source="naive_fallback" + 计数披露。
红灯先行：本文件先于 wired_assembly.py 存在。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wired_assembly import extract_wiring, NAIVE_PRIOR  # noqa: E402


class _Hit:
    def __init__(self, eid, facts=None):
        self.id = eid
        self.facts = facts


class ExtractWiringTests(unittest.TestCase):
    """假件用 dict 形态——与 evocore 条目真实形状一致（recall_tier 出的是 entry dict）。"""

    @staticmethod
    def _hit(eid, facts=None):
        return {"id": eid, "facts": facts}

    def test_recall_hit_injects_facts(self):
        hits = [(0.9, self._hit("P-1", facts={"Flux2Scheduler": ["steps", "width", "height"]}))]
        w = extract_wiring("flux2 布线", hits)
        self.assertEqual(w["facts_source"], "recall")
        self.assertEqual(w["facts"]["Flux2Scheduler"], ["steps", "width", "height"])
        self.assertEqual(w["skipped_no_facts"], 0)

    def test_no_facts_entry_skipped_and_counted(self):
        hits = [(0.8, self._hit("P-2", facts=None))]
        w = extract_wiring("flux2 布线", hits)
        self.assertEqual(w["facts_source"], "naive_fallback")
        self.assertEqual(w["skipped_no_facts"], 1)
        self.assertEqual(w["facts"], {})

    def test_mixed_hits_skip_counted_recall_wins(self):
        hits = [(0.9, self._hit("P-3", facts=None)),
                (0.7, self._hit("P-4", facts={"K": ["v"]}))]
        w = extract_wiring("q", hits)
        self.assertEqual(w["facts_source"], "recall")
        self.assertEqual(w["skipped_no_facts"], 1)
        self.assertEqual(w["facts"], {"K": ["v"]})

    def test_empty_supply_falls_back_naive(self):
        w = extract_wiring("flux2 布线", [])
        self.assertEqual(w["facts_source"], "naive_fallback")
        self.assertEqual(w["naive_prior"], NAIVE_PRIOR)
        self.assertIn("model", NAIVE_PRIOR["suspect_keys"])   # 可疑键=活体 schema 必拒的两个


class PipelineScopeGateTests(unittest.TestCase):
    """管线域外闸（NoobAI 专项限定）：facts.applies_to.model 与目标模型不符 → 跳过+计数。"""

    @staticmethod
    def _hit(eid, facts=None):
        return {"id": eid, "facts": facts}

    def test_out_of_scope_facts_skipped_and_counted(self):
        facts = {"cfg": 4.5, "applies_to": {"model": ["NoobAI-XL-Vpred-v1.0"]}}
        w = extract_wiring("出图配置", [(0.9, self._hit("NB-1", facts))],
                           target_model="flux-2-klein-4b")
        self.assertEqual(w["facts_source"], "naive_fallback")
        self.assertEqual(w["skipped_out_of_scope"], 1)
        self.assertEqual(w["skipped_no_facts"], 0)

    def test_in_scope_facts_served(self):
        facts = {"cfg": 4.5, "applies_to": {"model": ["NoobAI-XL-Vpred-v1.0"]}}
        w = extract_wiring("出图配置", [(0.9, self._hit("NB-1", facts))],
                           target_model="NoobAI-XL-Vpred-v1.0")
        self.assertEqual(w["facts_source"], "recall")
        self.assertEqual(w["facts"]["cfg"], 4.5)
        self.assertEqual(w["skipped_out_of_scope"], 0)

    def test_registry_fallback_scopes_approved_entries(self):
        """已晋升判例 facts 不动——域由注册表补（审批件免改内容）。"""
        facts = {"cfg": 4.5}                       # 无 applies_to
        scope_map = {"NB-1": ["NoobAI-XL-Vpred-v1.0"]}
        w = extract_wiring("出图配置", [(0.9, self._hit("NB-1", facts))],
                           target_model="flux-2-klein-4b", scope_map=scope_map)
        self.assertEqual(w["skipped_out_of_scope"], 1)

    def test_unscoped_facts_backward_compatible(self):
        """无域信息的件照旧供血（向后兼容，禁静默改变现有行为）。"""
        facts = {"K": ["v"]}
        w = extract_wiring("q", [(0.9, self._hit("X", facts))], target_model="any-model")
        self.assertEqual(w["facts_source"], "recall")
        self.assertEqual(w["skipped_out_of_scope"], 0)

    def test_no_target_means_no_gate(self):
        facts = {"cfg": 4.5, "applies_to": {"model": ["NoobAI-XL-Vpred-v1.0"]}}
        w = extract_wiring("q", [(0.9, self._hit("NB-1", facts))])   # 不传目标=老行为
        self.assertEqual(w["facts_source"], "recall")

    def test_filename_variant_substring_match(self):
        """目标名带扩展名/长尾——子串双向容忍。"""
        facts = {"cfg": 4.5, "applies_to": {"model": ["NoobAI-XL-Vpred-v1.0"]}}
        w = extract_wiring("q", [(0.9, self._hit("NB-1", facts))],
                           target_model="NoobAI-XL-Vpred-v1.0.safetensors")
        self.assertEqual(w["facts_source"], "recall")


if __name__ == "__main__":
    unittest.main(verbosity=2)
