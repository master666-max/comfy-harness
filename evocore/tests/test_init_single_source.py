# -*- coding: utf-8 -*-
"""test_init_single_source.py — __init__ 导出单源锁（清账令工单 A2 · P1-P4-2 F811 治本）

守的契约：
  ①evocore.content_hash_v3 / evocore.seg_hash 的导出对象必须 **is** entry 版
    （__init__ 曾从 .entry 与 .project 连续两行导入同名——F811 阴影，project 版
    静默覆盖 entry 版；两版同规由 test_entry_v3_dispatch 逐字节对拍钉死，但
    阴影导入使"导出的是哪一份"成为维护雷）；
  ②源码锁：__init__ 的 project 导入行不得再出现这两个名字（防回归）；
  ③同规哨保留：entry 版与 project 版对样本集输出恒等（任一侧改公式即红——
    分层契约禁止互引，双实现有意存在，哨兵在此）。
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import evocore  # noqa: E402

CONTENT = {"c": "结论：单源锁样本", "a": "论证段", "d": ""}


class TestInitSingleSource(unittest.TestCase):
    def test_exported_hash_is_entry_version(self):
        self.assertIs(evocore.content_hash_v3, evocore.entry.content_hash_v3,
                      "__init__ 导出的 content_hash_v3 不是 entry 版（阴影导入复发）")
        self.assertIs(evocore.seg_hash, evocore.entry.seg_hash,
                      "__init__ 导出的 seg_hash 不是 entry 版（阴影导入复发）")

    def test_init_source_no_shadow_import(self):
        init = os.path.join(os.path.dirname(evocore.__file__), "__init__.py")
        src = open(init, encoding="utf-8").read()
        m = re.search(r"from \.project import \(([^)]*)\)", src, re.S)
        self.assertIsNotNone(m, "__init__ 缺 project 导入行")
        names = {n.strip().rstrip(",") for n in m.group(1).split(",")}
        self.assertNotIn("content_hash_v3", names, "project 导入行仍阴影 content_hash_v3")
        self.assertNotIn("seg_hash", names, "project 导入行仍阴影 seg_hash")

    def test_dual_impl_parity_sentinel(self):
        for v in (CONTENT, {"c": "只结论"}, "str 形态走 seg_hash"):
            with self.subTest(v=v):
                if isinstance(v, dict):
                    self.assertEqual(evocore.entry.content_hash_v3(v),
                                     evocore.project.content_hash_v3(v))
                self.assertEqual(evocore.entry.seg_hash(v), evocore.project.seg_hash(v))


if __name__ == "__main__":
    unittest.main()
