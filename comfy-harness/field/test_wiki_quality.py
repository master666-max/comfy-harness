# -*- coding: utf-8 -*-
"""test_wiki_quality.py — 批D wiki 惯例质量件红绿锁（工单 §四批D）

守 wired_assembly 两个新增纯函数：
  ① expand_query(query, alias_map)：别名→扩展词（词表漂移防线——wiki 重定向页惯例）；
  ② disambiguation_hint(hits)：同查询命中跨域条目 → 域标提示（wiki 消歧义页惯例）；
  ③ 别名注册表文件形态（D-1 裁定独立文件，数据与治理分离）。
红灯先行。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wired_assembly import expand_query, disambiguation_hint, load_alias_map  # noqa: E402


class ExpandQueryTests(unittest.TestCase):
    def test_alias_expands_to_terms(self):
        amap = {"klein": ["flux2"], "FLUX.2": ["flux2"]}
        self.assertEqual(expand_query("klein 布线", amap), "klein 布线 flux2")

    def test_no_alias_query_unchanged(self):
        self.assertEqual(expand_query("anisora 视频", {}), "anisora 视频")

    def test_alias_no_duplicate_expansion(self):
        amap = {"klein": ["flux2"]}
        self.assertEqual(expand_query("klein flux2", amap), "klein flux2")

    def test_case_insensitive_alias_match(self):
        amap = {"klein": ["flux2"]}
        self.assertEqual(expand_query("Klein 布线", amap), "Klein 布线 flux2")


def _hit(eid, keywords):
    return {"id": eid, "keywords": keywords, "facts": None}


class DisambiguationTests(unittest.TestCase):
    def test_cross_domain_hits_get_hint(self):
        hits = [(0.9, _hit("A", ["flux2", "vae"])), (0.8, _hit("B", ["wan22", "vae", "视频"]))]
        hint = disambiguation_hint(hits)
        self.assertIsNotNone(hint)
        # 主体导向：共享的通用件词 vae 不是主体——提示报的是两边的主体词
        self.assertIn("flux2", hint)
        self.assertIn("wan22", hint)
        self.assertIn("A", hint) and self.assertIn("B", hint)

    def test_same_domain_hits_no_hint(self):
        hits = [(0.9, _hit("A", ["flux2", "vae"])), (0.8, _hit("B", ["flux2", "klein"]))]
        self.assertIsNone(disambiguation_hint(hits))

    def test_single_hit_no_hint(self):
        self.assertIsNone(disambiguation_hint([(0.9, _hit("A", ["flux2"]))]))


class AliasFileTests(unittest.TestCase):
    def test_load_alias_map_from_independent_file(self):
        tmp = tempfile.mkdtemp(prefix="alias-")
        p = os.path.join(tmp, "precedent_aliases.json")
        json.dump({"aliases": {"klein": ["flux2"]}}, open(p, "w", encoding="utf-8"))
        self.assertEqual(load_alias_map(p), {"klein": ["flux2"]})

    def test_missing_file_returns_empty(self):
        self.assertEqual(load_alias_map(os.path.join(tempfile.mkdtemp(), "无.json")), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
