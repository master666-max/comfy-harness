# -*- coding: utf-8 -*-
"""test_cross_family.py — A 案跨族常态对读红绿锁（引擎线转呈件回执 · 20261007）

守 e2_deepseek_exam.py 的对拍纯函数契约：
  attr_divergences(read_a, read_b)：逐属性对答案，返回分歧属性名列表；
  判官一句话理由字段不参与对拍；空读/缺属性按"该属性缺判"计分歧。
"""
import importlib.util
import os
import sys
import unittest

def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "e2mod", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "e2", "e2_deepseek_exam.py"))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except (AssertionError, KeyError, OSError) as err:
        raise unittest.SkipTest(f"判官 provider 未配置，跳过（{err}）")
    return mod


class AttrDivergencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_mod()

    def test_identical_reads_zero_divergence(self):
        a = {"红方块": 1, "木桌": 1, "黄鸭": 1, "影棚光效": 1, "一句话理由": "x"}
        b = {"红方块": 1, "木桌": 1, "黄鸭": 1, "影棚光效": 1, "一句话理由": "y"}
        self.assertEqual(self.mod.attr_divergences(a, b), [])

    def test_single_attr_diff_detected(self):
        a = {"红方块": 1, "木桌": 1, "黄鸭": 1, "影棚光效": 1}
        b = {"红方块": 1, "木桌": 0, "黄鸭": 1, "影棚光效": 1}
        self.assertEqual(self.mod.attr_divergences(a, b), ["木桌"])

    def test_missing_attr_counts_as_divergence(self):
        a = {"红方块": 1, "木桌": 1, "黄鸭": 1, "影棚光效": 1}
        b = {"红方块": 1, "木桌": 1}
        self.assertEqual(sorted(self.mod.attr_divergences(a, b)), ["影棚光效", "黄鸭"])

    def test_reason_field_excluded(self):
        a = {"红方块": 1, "一句话理由": "甲说东"}
        b = {"红方块": 1, "一句话理由": "乙说西"}
        self.assertEqual(self.mod.attr_divergences(a, b), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
