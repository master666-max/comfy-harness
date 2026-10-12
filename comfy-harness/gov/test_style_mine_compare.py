# -*- coding: utf-8 -*-
"""test_style_mine_compare.py — 对比器红绿测试（纯函数面：成员匹配/跨臂配对/读数/报告渲染）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style_mine_compare as cm            # noqa: E402


def _det_cluster(name, tags, ev=()):
    return {"name": name, "size": len(tags),
            "tags": [{"tag": t, "support": 3} for t in tags],
            "cohesion": 1.0, "evidence": list(ev)}


def _lr_cluster(name, members, ev=()):
    return {"name": name, "size": len(members), "members": members,
            "cohesion": 3.0, "evidence": list(ev)}


class TestMatch(unittest.TestCase):
    def test_norm_and_exact(self):
        self.assertTrue(cm.match_members("Backlighting", "backlighting"))
        self.assertTrue(cm.match_members("rim lighting", "rim lighting"))

    def test_containment_with_min_len(self):
        self.assertTrue(cm.match_members("backlighting", "Backlighting effect"))
        self.assertFalse(cm.match_members("ab", "abcdef"))       # 短词不判包含

    def test_similarity_one_to_one(self):
        a = {"backlighting", "rim lighting", "sunset"}
        b = {"backlighting", "rim lighting", "sunset", "girl"}
        self.assertEqual(cm.cluster_similarity(a, b), 3)


class TestPairing(unittest.TestCase):
    def test_pair_and_unmatched(self):
        det = [_det_cluster("backlighting · rim lighting · sunset",
                            ["backlighting", "rim lighting", "sunset"]),
               _det_cluster("deepseek · e-2 · 异族判官", ["deepseek", "e-2", "异族判官"])]
        lr = [_lr_cluster("逆光黄昏", ["backlighting", "rim lighting", "sunset", "city"]),
              _lr_cluster("花火大会", ["fireworks", "yukata"])]
        r = cm.pair_clusters(det, lr)
        self.assertEqual(len(r["pairs"]), 1)
        self.assertEqual(r["pairs"][0]["det_name"], "backlighting · rim lighting · sunset")
        self.assertEqual(r["pairs"][0]["lr_name"], "逆光黄昏")
        self.assertEqual(r["pairs"][0]["score"], 1.0)
        self.assertEqual(r["det_only"], ["deepseek · e-2 · 异族判官"])
        self.assertEqual(r["lr_only"], ["花火大会"])


class TestCompareAndReport(unittest.TestCase):
    def _outs(self):
        det = {"method": "det-cooc", "params": {"resolution": 1.5}, "elapsed_s": 0.4,
               "clusters": [_det_cluster("a · b · c", ["a", "b", "c"], ["g1", "g2"])],
               "stats": {"algo": "modularity", "n_tags_eligible": 10,
                         "n_tags_total": 20, "n_edges": 5}}
        lr = {"method": "lightrag", "params": {"llm": "m", "embed": "e"},
              "clusters": [_lr_cluster("风格一", ["a", "b", "c", "d"], ["g1"])],
              "stats": {"n_entities": 30, "n_relations": 40, "insert_s": 100}}
        return det, lr

    def test_compare_outputs(self):
        det, lr = self._outs()
        c = cm.compare_outputs(det, lr, 55)
        self.assertEqual(c["det"]["n_clusters"], 1)
        self.assertEqual(c["lr"]["evidence_cover"], 1)
        self.assertEqual(len(c["pairing"]["pairs"]), 1)

    def test_compare_missing_side(self):
        det, _ = self._outs()
        c = cm.compare_outputs(det, None, 55)
        self.assertIsNone(c["pairing"])
        md = cm.render_report(c, "ran（0.4s）", "disabled", det, None)
        self.assertIn("disabled", md)

    def test_report_renders(self):
        det, lr = self._outs()
        c = cm.compare_outputs(det, lr, 55)
        md = cm.render_report(c, "ran", "ran", det, lr)
        for k in ("跨臂配对", "A 独有", "B 独有", "判读素材", "A 臂全簇", "B 臂全簇"):
            self.assertIn(k, md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
