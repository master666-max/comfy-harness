# -*- coding: utf-8 -*-
"""test_evocore_projection_family.py — 投影族测试（排期 4-6 · D11 · 20260928 走闸 v0.6.0）

守的契约（D11 §三；实现=evocore/project.py 0.6.0 增量段）：
  ① slim 视图：slim_mark 末次事件定去留（mark/unmark/再 mark 三拍）；R1 子集性
     （未标记节点不入集）；R4 收缩（tombstone/corrected/superseded 自动出列）；
  ② 人读视图：depth=1 前缀条目形态 {c, h_a, h_d, v3}——**不携带 a/d 明文**（嵌套段序截断）；
     depth≠1 拒（fail-closed，未定义档不猜）；
  ③ 前缀绑定离线验证两步（verify_prefix_entry）：正=结论段重算绑定过；负=文本篡改必红
     （人读文本不绑定账本承诺）；v2 存量条目（扁平字符串）走宽松道；
  ④ 映射校验 verify_view_mapping 五检查点：正=全过空清单；负A=幽灵条目（human 多于 agent）
     必红 V2；负B=V1 异源拒续（seq 区间不齐即返回）；
  ⑤ 纯函数性：同 rows 同 subset 同输出（视图=投影不是第二真相源，公理 A2）。
判别力（负向断言必配正向对照）：②③④ 各含至少一负；① 的 R4 三动词各一负。
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from evocore import (project_slim, project_human_view, project_agent_view,          # noqa: E402
                     verify_view_mapping, verify_prefix_entry, SLIM_MARK_KIND)


def row(seq, kind, payload, ts):
    return (seq, ts, "llm:test", kind, json.dumps(payload, ensure_ascii=False),
            "p" * 64, "h" * 64)


TS = "2026-09-28T10:00:00"
CH = "c" * 64


def v3_entry(eid, c, a="", d=""):
    """v3 形态条目（content=dict 三段）；content_hash 由测试自算承诺（挂账面约定）。"""
    from evocore import content_hash_v3
    return {"entry_id": eid, "content": {"c": c, "a": a, "d": d},
            "content_hash": content_hash_v3({"c": c, "a": a, "d": d})}


def base_rows():
    """两 v3 条目（e1 标记入 slim，e2 未标记）+ e1 的 slim_mark 事件。
    CH_DELAYED=True 的键值在模块级按真实承诺值派生（test 上不可用字面占位）。"""
    r = [
        row(1, "entry_append", v3_entry("e1", "结论一", "论证一", "细节一"), TS),
        row(2, "entry_append", v3_entry("e2", "结论二"), TS),
        row(3, SLIM_MARK_KIND,
            {"node_id": "e1", "subset": "human_default", "action": "mark",
             "by": "human:owner", "reason": "枢纽"}, TS),
    ]
    return r


E1_KEY = ("e1", v3_entry("e1", "结论一", "论证一", "细节一")["content_hash"])
E2_KEY = ("e2", v3_entry("e2", "结论二")["content_hash"])


class TestSlimView(unittest.TestCase):
    def test_mark_unmark_remark_last_wins(self):
        """① 三拍：mark→入集；unmark→出集；再 mark→回集（末次事件定去留）。"""
        rows = base_rows()
        self.assertEqual(project_slim(rows), {E1_KEY})
        rows2 = rows + [row(4, SLIM_MARK_KIND,
                            {"node_id": "e1", "subset": "human_default",
                             "action": "unmark", "by": "human:owner", "reason": "退"}, TS)]
        self.assertEqual(project_slim(rows2), set())
        rows3 = rows2 + [row(5, SLIM_MARK_KIND,
                             {"node_id": "e1", "subset": "human_default",
                              "action": "mark", "by": "human:owner", "reason": "回"}, TS)]
        self.assertEqual(project_slim(rows3), {E1_KEY})

    def test_r1_unmarked_never_in(self):
        """① R1：从未标记的 e2 永不入人读集（增长只走人，不自动入 slim）。"""
        self.assertNotIn(E2_KEY, project_slim(base_rows()))

    def test_r4_closing_verbs_evict(self):
        """① R4 三动词：tombstone/corrected/superseded 任一即出列（带病不留人读视图）。"""
        # supersede 已接线（0.6.2 排期件3）：{entry_id|node_id, reason} → status=superseded
        # ——账本条目流三关闭动词全可达；decision_tree 节点面语义不变（D6 两套分立）。
        for kind, extra in (("tombstone", {}), ("memory_correction", {}),
                            ("supersede", {"reason": "判死"})):
            rows = base_rows() + [row(4, kind, {"entry_id": "e1", **extra}, TS)]
            self.assertEqual(project_slim(rows), set(), kind)


class TestHumanView(unittest.TestCase):
    def test_depth1_prefix_no_leak(self):
        """② depth=1 前缀条目：带 c 与承诺 h_a/h_d，不带 a/d 明文。"""
        hv = project_human_view(base_rows())
        e = hv["entries"][E1_KEY]
        self.assertEqual(e["c"], "结论一")
        self.assertEqual(e["v3"], True)
        self.assertNotIn("a", e)
        self.assertNotIn("d", e)
        self.assertTrue(e["h_a"] and e["h_d"])

    def test_depth_other_rejected(self):
        """② fail-closed：depth≠1 拒（未定义档不猜）。"""
        with self.assertRaises(ValueError):
            project_human_view(base_rows(), depth=2)

    def test_pure_function(self):
        """⑤ 纯函数：同 rows 同 subset 同输出（公理 A2：视图=投影）。"""
        self.assertEqual(project_human_view(base_rows()), project_human_view(base_rows()))


class TestPrefixBinding(unittest.TestCase):
    def test_verify_ok(self):
        """③ 正：真结论段两步验证过（None）。"""
        hv = project_human_view(base_rows())
        for k, pv in hv["entries"].items():
            self.assertIsNone(verify_prefix_entry(pv), k)

    def test_verify_tampered_text_red(self):
        """③ 负：人读文本被改 → 重算绑定 ≠ 账本承诺 → 必红。"""
        hv = project_human_view(base_rows())
        pv = hv["entries"][E1_KEY]
        pv["c"] = "被篡改的结论"
        msg = verify_prefix_entry(pv)
        self.assertIsNotNone(msg)
        self.assertIn("V4", msg)

    def test_v2_legacy_loose_path(self):
        """③ v2 存量（扁平字符串）：走宽松道（c 非空即过，无承诺可绑不误报）。"""
        rows = [row(1, "entry_append", {"entry_id": "old", "content": "旧条目",
                                        "content_hash": "abc"}, TS),
                row(2, SLIM_MARK_KIND, {"node_id": "old", "subset": "human_default",
                                        "action": "mark", "by": "human:owner",
                                        "reason": "旧"}, TS)]
        hv = project_human_view(rows)
        pv = hv["entries"][("old", "abc")]
        self.assertIsNone(verify_prefix_entry(pv))


class TestViewMapping(unittest.TestCase):
    def test_mapping_clean(self):
        """④ 正：human ⊆ agent 同源，五检查点全过（空清单）。"""
        rows = base_rows()
        self.assertEqual(verify_view_mapping(rows, project_human_view(rows),
                                             project_agent_view(rows)), [])

    def test_mapping_ghost_red(self):
        """④ 负A：human 视图混入 agent 没有的键（幽灵条目）→ V2 必红。"""
        rows = base_rows()
        hv = project_human_view(rows)
        hv["entries"][("ghost", E1_KEY[1])] = dict(hv["entries"][E1_KEY])
        bad = verify_view_mapping(rows, hv, project_agent_view(rows))
        self.assertTrue(any("V2" in m for m in bad))

    def test_mapping_divergent_source_red(self):
        """④ 负B：两视图 seq 区间不齐（异源）→ V1 拒续。"""
        rows = base_rows()
        agent = project_agent_view(rows)
        agent["seq_end"] = 99
        bad = verify_view_mapping(rows, project_human_view(rows), agent)
        self.assertTrue(any("V1" in m for m in bad))


if __name__ == "__main__":
    unittest.main(verbosity=2)
