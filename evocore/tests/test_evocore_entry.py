# -*- coding: utf-8 -*-
"""test_evocore_entry.py — 条目构造校验测试（S3/T1；`evocore/entry.py`）

守的契约（负向必配正向对照）：
  ① 合法条目（最小形态/全形态）通过；
  ② 四类非法各必拒：缺 id/content · type 非法 · state 非法 · importance 非法（负/浮点/字符串）；
  ③ 与融合形态同语义：type/state 枚举与衰减/三态面一致（TYPES × decay_multiplier 全覆盖）；
  ④ STATES 单一事实源：与 lifecycle.STATES 同一对象（非副本）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from evocore import DEFAULTS, TYPES, Tunables, decay_multiplier, validate_entry  # noqa: E402
from evocore.lifecycle import STATES  # noqa: E402


class TestValidateEntry(unittest.TestCase):
    def test_minimal_entry_passes(self):
        """①a 最小形态（仅 id+content）合法。"""
        validate_entry({"id": "e1", "content": "玻璃材质 IOR 1.45"})

    def test_full_entry_passes(self):
        """①b 全形态合法（含 keywords/type/state/importance/source）。"""
        validate_entry({"id": "e2", "content": "三点布光", "keywords": ["布光"],
                        "type": "procedural", "state": "longterm", "importance": 8,
                        "source": "manual"})

    def test_missing_id_or_content_rejected(self):
        """②a 缺 id/content 必拒。"""
        for e in ({"content": "x"}, {"id": "x"}, {"id": "  ", "content": "x"}):
            with self.assertRaises(ValueError):
                validate_entry(e)

    def test_bad_type_rejected(self):
        """②b type 非法必拒（默认 semantic 合法）。"""
        validate_entry({"id": "e", "content": "c"})                       # 默认值合法（正向对照）
        with self.assertRaises(ValueError):
            validate_entry({"id": "e", "content": "c", "type": "记忆"})

    def test_bad_state_rejected(self):
        """②c state 非法必拒（默认 intermediate 合法）。"""
        validate_entry({"id": "e", "content": "c", "state": "attic"})     # 正向对照
        with self.assertRaises(ValueError):
            validate_entry({"id": "e", "content": "c", "state": "deleted"})

    def test_bad_importance_rejected(self):
        """②d importance 非负整数之外必拒（0 与正整数合法）。"""
        validate_entry({"id": "e", "content": "c", "importance": 0})      # 正向对照
        for bad in (-1, 1.5, "8", None):
            with self.assertRaises(ValueError):
                validate_entry({"id": "e", "content": "c", "importance": bad})

    def test_types_consistent_with_decay(self):
        """③ TYPES 每一型在衰减面都有定义（跨模块语义一致——同门凭据的包内形态）。"""
        for t in TYPES:
            m = decay_multiplier({"id": "e", "content": "c", "type": t}, DEFAULTS)
            self.assertIn(m, (0.0, 1.0, 2.0), f"{t} 衰减乘数异常：{m}")
        self.assertEqual(Tunables().decay_mult_procedural, 0.0)           # 程序记忆零衰减（正典）

    def test_states_single_source(self):
        """④ STATES 与 lifecycle 同源（同一对象，非副本）。"""
        import evocore.entry as entry_mod
        self.assertIs(entry_mod.STATES, STATES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
