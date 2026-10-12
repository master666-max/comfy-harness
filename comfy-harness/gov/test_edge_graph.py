# -*- coding: utf-8 -*-
"""test_edge_graph.py — 有向经验图红绿（派生投影/影响面分档/环路/只读红线）"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import edge_graph as eg          # noqa: E402


def _e(eid, **kw):
    d = {"id": eid, "gov": "draft", "task": "t2i", "kind": "style", "level": "specialized",
         "content": {"c": eid, "a": "", "d": ""}, "keywords": [], "evidence": {}}
    d.update(kw)
    return d


class TestExtract(unittest.TestCase):
    def test_merged_from_edge(self):
        g = eg.extract_graph([_e("S-a-1"), _e("S-a-2"),
                              _e("S-merged", facts={"merged_from": ["S-a-1", "S-a-2"]})])
        mf = [x for x in g["edges"] if x["type"] == "merged-from"]
        self.assertEqual({(x["up"], x["down"]) for x in mf},
                         {("S-a-1", "S-merged"), ("S-a-2", "S-merged")})

    def test_cites_edge_with_quote(self):
        g = eg.extract_graph([_e("S-src"), _e("P-t", content={"c": "见 S-src 的结论", "a": "", "d": ""})])
        ci = [x for x in g["edges"] if x["type"] == "cites"]
        self.assertEqual(len(ci), 1)
        self.assertEqual((ci[0]["up"], ci[0]["down"]), ("S-src", "P-t"))   # 被引=上游
        self.assertIn("S-src", ci[0]["quote"])

    def test_symmetric_group_edges(self):
        g = eg.extract_graph([_e("S-k-aa11", _mine_sig="sig1"), _e("S-k-bb22", _mine_sig="sig1"),
                              _e("S-m-cc33", _mine_sig="sig9")])
        sym = [x for x in g["edges"] if x.get("sym")]
        self.assertEqual(len(sym), 1)                    # 只 sig1 那组成边
        self.assertEqual(sym[0]["type"], "cluster-mate")

    def test_evidence_kinds(self):
        g = eg.extract_graph([
            _e("A", evidence={"artifact": "generation:p.png"}),
            _e("B", evidence={"artifact": "style_mine_out/det_candidates.json"}),
            _e("C", evidence={"artifact": "见 A 条目"}, )])
        n = g["nodes"]
        self.assertEqual(n["A"]["evidence_kind"], "raw")
        self.assertEqual(n["B"]["evidence_kind"], "derived")
        self.assertEqual(n["C"]["evidence_kind"], "citation")


class TestImpact(unittest.TestCase):
    def _graph(self):
        # 错误根 root → 1跳依赖者 dep（只引用） / 1跳自证者 own / dep → 2跳 far
        ents = [
            _e("P-root", evidence={"artifact": "generation:r.png"}),
            _e("S-dep", content={"c": "依据 P-root 而来", "a": "", "d": ""},
               evidence={"artifact": "见 P-root"}),
            _e("S-own", content={"c": "依据 P-root 提示，但自有实测", "a": "", "d": ""},
               evidence={"artifact": "generation:mine.png"}),
            _e("S-far", content={"c": "引用 S-dep 的结论", "a": "", "d": ""},
               evidence={"artifact": "gen? 无——只引 S-dep"}),
        ]
        return eg.extract_graph(ents)

    def test_impact_tiers(self):
        r = eg.impact(self._graph(), "P-root", hops=2)
        tiers = {x["node"]: x["tier"] for x in r["rows"]}
        self.assertIn("连坐候选", tiers["S-dep"])        # 1 跳 + 证据只靠引用
        self.assertIn("自证", tiers["S-own"])            # 1 跳 + raw 证据
        self.assertEqual(tiers["S-far"] and "仅标注" in tiers["S-far"], True)  # 2 跳

    def test_impact_hops_bound(self):
        r1 = eg.impact(self._graph(), "P-root", hops=1)
        self.assertNotIn("S-far", [x["node"] for x in r1["rows"]])

    def test_cycles_detected(self):
        g = eg.extract_graph([
            _e("S-x", content={"c": "引用 S-y", "a": "", "d": ""}),
            _e("S-y", content={"c": "又引用 S-x", "a": "", "d": ""})])
        cy = eg.cycles(g)
        self.assertEqual(len(cy), 1)
        self.assertEqual(set(cy[0]), {"S-x", "S-y"})

    def test_symmetric_edges_not_cycles(self):
        g = eg.extract_graph([_e("S-k-aa11", _mine_sig="s"), _e("S-k-bb22", _mine_sig="s")])
        self.assertEqual(eg.cycles(g), [])

    def test_readonly_redline(self):
        ents = [_e("S-a-1"), _e("S-b-2", content={"c": "引用 S-a-1", "a": "", "d": ""})]
        before = [dict(x) for x in ents]
        g = eg.extract_graph(ents)
        eg.impact(g, "S-a-1")
        eg.cycles(g)
        self.assertEqual([x["id"] for x in ents], [x["id"] for x in before])
        self.assertTrue(all("_all_ids" not in x for x in ents))    # 临时字段已清理

    def test_determinism(self):
        ents = [_e("S-a-1"), _e("S-b-2", content={"c": "引用 S-a-1", "a": "", "d": ""})]
        import json as _json
        self.assertEqual(_json.dumps(eg.extract_graph(ents), sort_keys=True),
                         _json.dumps(eg.extract_graph(ents), sort_keys=True))


class TestTombstoneNodes(unittest.TestCase):
    """墓碑件保留为历史节点：边不丢（撤回后仍能答"谁依赖过它"）。"""

    def test_tombstone_node_and_edges_retained(self):
        g = eg.extract_graph([
            _e("P-t", tombstone=True),
            _e("S-c", content={"c": "依据 P-t 的结论", "a": "", "d": ""},
               evidence={"artifact": "见 P-t"})])
        self.assertIn("P-t", g["nodes"])                       # 墓碑仍是节点
        self.assertEqual(g["nodes"]["P-t"]["state"], "tombstone")
        self.assertFalse(g["nodes"]["P-t"]["live"])
        edges = {(x["up"], x["down"]) for x in g["edges"] if x["type"] == "cites"}
        self.assertIn(("P-t", "S-c"), edges)                   # 引用边不丢
        r = eg.impact(g, "P-t", 1)
        self.assertEqual([x["node"] for x in r["rows"]], ["S-c"])
        self.assertEqual(r["root_state"], "tombstone")
        self.assertIn("事后查询", r["note"])                    # 根已墓碑：报告注明事后查询

    def test_deprecated_and_retracted_states(self):
        g = eg.extract_graph([_e("P-d", deprecated=True), _e("P-r", machine_retracted=True),
                              _e("P-l")])
        self.assertEqual(g["nodes"]["P-d"]["state"], "deprecated")
        self.assertEqual(g["nodes"]["P-r"]["state"], "retracted")
        self.assertEqual(g["nodes"]["P-l"]["state"], "live")


if __name__ == "__main__":
    unittest.main(verbosity=2)
