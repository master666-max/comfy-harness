# -*- coding: utf-8 -*-
"""test_style_mine.py — 风格挖掘红绿测试（语料面 + 挖掘器 A 确定性臂）

覆盖：tag 归一（权重/大小写/超长）· 判例文档/PNG 元数据文档构建 ·
共现聚类（两簇分离/证据链/确定性）· 停用词桥接防护（大众词剔后簇才分立）·
开关判定（ENV/CLI 双通道）。挖掘器 B（LightRAG）不做联网测试——
其产物流水线由 style_mine_compare 用桩数据验证（见 test_style_mine_compare.py）。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style_corpus as sc          # noqa: E402
import style_mine_det as sd        # noqa: E402


class TestTagNorm(unittest.TestCase):
    def test_weight_and_case(self):
        self.assertEqual(sc.norm_tag("(Masterpiece:1.2)"), "masterpiece")
        self.assertEqual(sc.norm_tag("((white hair))"), "white hair")
        self.assertEqual(sc.norm_tag("  Backlighting "), "backlighting")

    def test_drop_long_and_empty(self):
        self.assertEqual(sc.norm_tag(""), "")
        self.assertEqual(sc.norm_tag("x" * 80), "")

    def test_norm_tags_dedup_order(self):
        self.assertEqual(sc.norm_tags("a, b, (a:1.1), c"), ["a", "b", "c"])


class TestCorpusDocs(unittest.TestCase):
    def test_precedent_doc(self):
        e = {"id": "P-x", "gov": "approved", "kind": "pipeline", "task": "t2i",
             "level": "specialized", "content": {"c": "甲", "a": "乙", "d": "丙"},
             "keywords": ["夜景"], "facts": {"official_prefix_add": "highres, safe", "steps": 32}}
        d = sc.doc_from_precedent(e)
        self.assertEqual(d["src"], "precedent:P-x")
        self.assertIn("highres", d["tags"])
        self.assertIn("safe", d["tags"])
        self.assertIn("夜景", d["tags"])
        self.assertNotIn("32", d["tags"])          # 数字不当 tag

    def test_png_doc_with_meta(self):
        from PIL import Image, PngImagePlugin
        g = {
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "1girl, white hair, sunset"}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "worst quality, low quality"}},
            "7": {"class_type": "KSampler", "inputs": {"steps": 32, "cfg": 4.8,
                                                       "sampler_name": "euler", "scheduler": "normal"}},
        }
        info = PngImagePlugin.PngInfo()
        info.add_text("prompt", json.dumps(g))
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "t.png")
            Image.new("RGB", (8, 8)).save(p, pnginfo=info)
            d = sc.doc_from_png(p)
        self.assertIsNotNone(d)
        self.assertIn("white hair", d["tags"])
        self.assertIn("sunset", d["tags"])
        self.assertNotIn("worst quality", d["tags"])   # 负词不混入正词 tag 面
        self.assertEqual(d["meta"]["steps"], 32)

    def test_png_without_meta_none(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "t.png")
            Image.new("RGB", (8, 8)).save(p)
            self.assertIsNone(sc.doc_from_png(p))

    def test_build_corpus_end_to_end(self):
        seed = {"entries": [{"id": "P-1", "gov": "approved", "content": {"c": "种子"},
                             "keywords": ["kw"], "facts": {}}]}
        with tempfile.TemporaryDirectory() as td:
            sp = os.path.join(td, "seed.json")
            json.dump(seed, open(sp, "w", encoding="utf-8"), ensure_ascii=False)
            out = os.path.join(td, "out")
            os.makedirs(out)
            from PIL import Image, PngImagePlugin
            info = PngImagePlugin.PngInfo()
            info.add_text("prompt", json.dumps({"4": {"class_type": "CLIPTextEncode",
                                                      "inputs": {"text": "a, b"}}}))
            Image.new("RGB", (8, 8)).save(os.path.join(out, "x.png"), pnginfo=info)
            docs = sc.build_corpus(sp, out)
        self.assertEqual(len(docs), 2)
        self.assertEqual({d["type"] for d in docs}, {"precedent", "generation"})


def _doc(src, tags):
    return {"src": src, "type": "generation", "text": "", "tags": sorted(tags), "meta": {}}


class TestDetMiner(unittest.TestCase):
    @staticmethod
    def _fixture():
        docs = []
        for s in ("g1", "g2", "g3"):
            docs.append(_doc(s, {"backlighting", "rim lighting", "sunset", "1girl"}))
        for s in ("h1", "h2", "h3"):
            docs.append(_doc(s, {"film grain", "vignette", "contrast", "1girl"}))
        docs.append(_doc("n1", {"solo", "random one"}))
        return docs

    def test_two_clusters_with_stopword_guard(self):
        r = sd.mine(self._fixture())
        self.assertEqual(len(r["clusters"]), 2, [c["name"] for c in r["clusters"]])
        all_tags = {t["tag"] for c in r["clusters"] for t in c["tags"]}
        self.assertIn("backlighting", all_tags)
        self.assertIn("film grain", all_tags)
        # 大众词 1girl 被停用词过滤，不在任何簇里
        self.assertNotIn("1girl", all_tags)
        self.assertIn("1girl", r["stats"]["stopwords"])

    def test_stopword_off_lets_bridging_tag_enter(self):
        # 停用词关：大众词 1girl 进候选面（孤立落 misc）；开：直接剔出场（stats.stopwords）
        r = sd.mine(self._fixture(), stopword_ratio=1.0)
        self.assertIn("1girl", r["misc"])
        self.assertNotIn("1girl", r["stats"]["stopwords"])
        r2 = sd.mine(self._fixture())
        self.assertIn("1girl", r2["stats"]["stopwords"])
        self.assertNotIn("1girl", r2["misc"])

    def test_evidence_chain(self):
        r = sd.mine(self._fixture())
        clust = [c for c in r["clusters"]
                 if "backlighting" in [t["tag"] for t in c["tags"]]][0]
        self.assertEqual(sorted(clust["evidence"]), ["g1", "g2", "g3"])

    def test_determinism(self):
        a = sd.mine(self._fixture())
        b = sd.mine(self._fixture())
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_min_support_drops_noise(self):
        r = sd.mine(self._fixture())
        all_tags = {t["tag"] for c in r["clusters"] for t in c["tags"]}
        self.assertNotIn("random one", all_tags)     # support=1
        self.assertNotIn("solo", all_tags)

    def test_min_cluster_moves_small_to_misc(self):
        r = sd.mine(self._fixture(), min_cluster=4)
        self.assertEqual(len(r["clusters"]), 0)
        self.assertIn("backlighting", r["misc"])

    def test_jaccard_guards_low_overlap(self):
        # common 8 篇、rare 2 篇、共现 2 次：j=2/(8+2-2)=0.25 < 0.5 → 不成边（链式桥接被剪）
        docs = [_doc(f"c{i}", {"common"}) for i in range(6)]
        docs += [_doc("c6", {"common", "rare"}), _doc("c7", {"common", "rare"})]
        docs += [_doc("c8", {"common"}), _doc("c9", {"common"})]
        r = sd.mine(docs, stopword_ratio=1.0)
        self.assertEqual(len(r["clusters"]), 0)
        self.assertIn("rare", r["misc"])
        self.assertIn("common", r["misc"])

    def test_switch_env_and_cli(self):
        self.assertTrue(sd.is_disabled(env="off"))
        self.assertTrue(sd.is_disabled(env="FALSE"))
        self.assertTrue(sd.is_disabled(env="0"))
        self.assertTrue(sd.is_disabled(cli_off=True, env=""))
        self.assertFalse(sd.is_disabled(env="on"))
        self.assertFalse(sd.is_disabled(env=""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
