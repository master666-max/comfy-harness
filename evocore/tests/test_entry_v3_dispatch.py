# -*- coding: utf-8 -*-
"""test_entry_v3_dispatch.py — v3 写侧分发测试（20260929 分支1·框架 · 排期配套，0.6.0 登记项清账）

守的契约：
  ①**跨形态逐字节对拍**（本测试存在的唯一理由）：entry.content_hash_v3 / entry.seg_hash
     与 project.content_hash_v3 / project.seg_hash **同规两处实现**（分层契约禁止
     entry←project 互引）——任何一侧改动公式，本测试立即红。不靠注释声称，靠字节。
  ②content_hash 形态分发：dict content → v3（== content_hash_v3）；字符串 → v2
     （且 v2 路径逐字节不变——`test_content_hash_divergence.py` 既有断言不动）；
  ③validate_entry：dict content 合法形态过 / c 空 / a 非 str 必拒；
  ④前缀视图闭环：写侧 v3 条目经 project_human_view → verify_prefix_entry 过；
     人读文本被篡改 → 必红（写侧承诺被人读面消费的完整闭环）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from evocore import (content_hash, content_hash_v3 as entry_v3,                  # noqa: E402
                     project_human_view, seg_hash as entry_seg,
                     validate_entry, verify_prefix_entry)
from evocore import project as proj_mod                                            # noqa: E402

C, A, D = "结论：玻璃 IOR 1.45", "论证：实测三点布光", "细节：_cycles 4096"
CONTENT = {"c": C, "a": A, "d": D}


class TestCrossFormByteEquality(unittest.TestCase):
    """① 同规两处实现——跨形态逐字节对拍（架构约束的看门测试）。"""

    def test_seg_hash_byte_equal(self):
        for v in (C, A, "", {"nested": ["x", 1]}, None):
            with self.subTest(v=v):
                self.assertEqual(entry_seg(v), proj_mod.seg_hash(v))

    def test_content_hash_v3_byte_equal(self):
        self.assertEqual(entry_v3(CONTENT), proj_mod.content_hash_v3(CONTENT))
        self.assertEqual(entry_v3({"c": "只结论"}),
                         proj_mod.content_hash_v3({"c": "只结论", "a": "", "d": ""}))


class TestDispatch(unittest.TestCase):
    def test_dict_content_goes_v3(self):
        """② dict content → v3（== content_hash_v3(content)）。"""
        e = {"id": "e1", "content": CONTENT}
        self.assertEqual(content_hash(e), entry_v3(CONTENT))

    def test_string_content_unchanged_v2(self):
        """② 字符串 content → v2 逐字节不变（基线回归：v2 路径一字未动）。"""
        e = {"id": "e2", "content": "玻璃材质", "type": "semantic"}
        body = {"content": "玻璃材质", "type": "semantic"}
        import json
        canon = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        import hashlib
        self.assertEqual(content_hash(e), hashlib.sha256(canon.encode("utf-8")).hexdigest())

    def test_v2_v3_different_for_same_words(self):
        """② 同一句话，v2 与 v3 指纹不同（算法版本可区分——v3 前缀设计）。"""
        e2 = {"id": "x", "content": C}
        self.assertNotEqual(content_hash(e2), entry_v3({"c": C}))

    def test_metadata_not_in_v3(self):
        """② v3 只锚三段：type/importance 变化不改 v3 指纹（内容寻址设计）。"""
        a = content_hash({"id": "x", "content": CONTENT, "type": "semantic"})
        b = content_hash({"id": "x", "content": CONTENT, "type": "procedural"})
        self.assertEqual(a, b)


class TestValidate(unittest.TestCase):
    def test_dict_content_ok(self):
        """③ dict content 合法（c 必填，a/d 缺省）。"""
        validate_entry({"id": "e", "content": CONTENT})
        validate_entry({"id": "e", "content": {"c": "只结论"}})

    def test_dict_content_rejected(self):
        """③ c 空 / c 非串 / a 非串 必拒。"""
        for bad in ({"c": ""}, {"c": "  "}, {"a": 3}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_entry({"id": "e", "content": {"c": "x", **bad}})


class TestPrefixLoop(unittest.TestCase):
    def test_write_to_human_view_loop(self):
        """④ 写侧 v3 → 投影 → 人读前缀 → 离线验证过；篡改必红（完整闭环）。"""
        rows = [(1, "2026-09-29T10:00:00", "llm:test", "entry_append",
                 json_dumps({"entry_id": "e1", "content": CONTENT,
                             "content_hash": entry_v3(CONTENT)}),
                 "p" * 64, "h" * 64),
                (2, "2026-09-29T10:01:00", "llm:test", "slim_mark",
                 json_dumps({"node_id": "e1", "subset": "human_default",
                             "action": "mark", "by": "human:owner", "reason": "枢纽"}),
                 "p" * 64, "h" * 64)]
        hv = project_human_view(rows)
        key = ("e1", entry_v3(CONTENT))
        self.assertIn(key, hv["entries"])
        self.assertIsNone(verify_prefix_entry(hv["entries"][key]))
        hv["entries"][key]["c"] = "被篡改"
        self.assertIsNotNone(verify_prefix_entry(hv["entries"][key]))


def json_dumps(o):
    import json
    return json.dumps(o, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
