# -*- coding: utf-8 -*-
"""test_entry_open_surface.py — evocore 开放字段面契约锁（候裁件④收口 · 2026-10-05）

锁死的事实：validate_entry 对未知字段宽容（宿主层富字段——facts/applicability 类——
的存身前提）。两条红线：
  ① 含 facts 形态未知字段的条目必须通过校验；
  ② 未知字段不得影响 content_hash（内容寻址面只锚 c/a/d，宿主字段不进哈希）。
哪天有人给 validate_entry 加严格字段白名单，此锁响亮报红——开放面是契约不是巧合。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from evocore import entry as ec_entry  # noqa: E402


def base_entry(**extra):
    e = {"id": "OPEN-1", "type": "procedural", "importance": 3,
         "keywords": ["布线"],
         "content": {"c": "机器事实槽位宽容性锁", "a": "承候裁件④", "d": "适用全系"},
         "evidence": {"artifact": "test", "quote": "q", "recalc": "r"}}
    e.update(extra)
    return e


class OpenSurfaceTests(unittest.TestCase):
    def test_entry_with_facts_passes_validation(self):
        e = base_entry(facts={"Flux2Scheduler": ["steps", "width", "height"]})
        ec_entry.validate_entry(e)  # 不 raise 即过

    def test_entry_with_multiple_host_fields_passes(self):
        e = base_entry(facts={"K": ["v"]}, applicability={"applies_to": "0.38"},
                       outcomes=[{"result": "success"}])
        ec_entry.validate_entry(e)

    def test_unknown_fields_do_not_affect_content_hash(self):
        plain = base_entry()
        with_facts = base_entry(facts={"K": ["v"]})
        h1 = ec_entry.content_hash_v3(plain["content"])
        h2 = ec_entry.content_hash_v3(with_facts["content"])
        self.assertEqual(h1, h2, "facts 类宿主字段不得进内容寻址面")

    def test_lock_documents_itself(self):
        """锁的自述：本文件存在即契约——docstring 即规格，删锁须改此断言。"""
        import inspect
        src = inspect.getsource(ec_entry.validate_entry)
        self.assertIn("raise ValueError", src)  # 校验面仍是 fail-closed 形态


if __name__ == "__main__":
    unittest.main(verbosity=2)
