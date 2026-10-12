# -*- coding: utf-8 -*-
"""test_embed_cache.py — 嵌入缓存红绿（派生投影/模型钉版/增量/响亮失败）"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import embed_cache as ec            # noqa: E402


def _fake_embed(texts, base=None, model=None, dim=None):
    """确定性伪嵌入：按文本哈希铺向量（测试不触网）。"""
    out = []
    for t in texts:
        seed = int(ec._hash(t), 16) % (2 ** 31)
        rng = np.random.default_rng(seed)
        out.append(rng.normal(size=dim or ec.DEFAULT_DIM).astype(np.float32))
    return np.asarray(out, dtype=np.float32)


class TestEmbedCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "seed.json")
        shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "precedents_e2_seed.json"), self.store)
        self.cache = os.path.join(self.tmp.name, "emb.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_incremental_and_removed(self):
        r1 = ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
        self.assertGreater(r1["to_embed"], 50)                     # 全量首建
        r2 = ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
        self.assertEqual(r2["to_embed"], 0)                        # 二次零重嵌
        # 改一条内容 → 只重嵌一条
        from precedent_gov import PrecedentStore
        s = PrecedentStore.load(self.store)
        s.entries[0]["content"] = {"c": "被改动的正文（测试）", "a": "", "d": ""}
        s.save(self.store)
        r3 = ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
        self.assertEqual(r3["to_embed"], 1)

    def test_model_pinning_refuses_mix(self):
        ec.refresh(self.store, self.cache, model="nomic-embed", dim=768, embed_fn=_fake_embed)
        with self.assertRaises(RuntimeError) as cm:
            ec.refresh(self.store, self.cache, model="other-model", dim=768, embed_fn=_fake_embed)
        self.assertIn("全量重嵌", str(cm.exception) + " --rebuild")
        r = ec.refresh(self.store, self.cache, model="other-model", dim=768,
                       rebuild=True, embed_fn=_fake_embed)
        self.assertTrue(r["to_embed"] > 50)                        # rebuild 全量

    def test_check_mode_no_write(self):
        r = ec.refresh(self.store, self.cache, check=True, embed_fn=_fake_embed)
        self.assertTrue(r["check"])
        self.assertFalse(os.path.isfile(self.cache), "check 模式不得动盘")

    def test_offline_loud(self):
        def boom(texts, base=None, model=None, dim=None):
            raise RuntimeError("嵌入端点不可用（测试）")
        with self.assertRaises(RuntimeError):
            ec.refresh(self.store, self.cache, embed_fn=boom)

    def test_doc_query_prefix_routing(self):
        """非对称检索分路：写侧 refresh=文档前缀，读侧 embed_query=查询前缀，
        候选比较 embed_docs=文档前缀（不对称=近重复闸 0.90 判据失真）。"""
        seen = {}

        def spy(texts, base=None, model=None, dim=None):
            seen["refresh"] = list(texts)
            return _fake_embed(texts, dim=dim)

        ec.refresh(self.store, self.cache, embed_fn=spy)
        self.assertTrue(seen["refresh"] and
                        all(t.startswith(ec.DOC_PREFIX) for t in seen["refresh"]))
        # 读侧/候选侧前缀路由**离线**验证（原版直连 live 端点——端点不在线即红，
        # 违反"测试不依赖外部服务"；改 monkeypatch embed_texts 捕获前缀）
        orig = ec.embed_texts
        routed = {}

        def spy2(texts, base=None, model=None, dim=None):
            routed["texts"] = list(texts)
            return np.ones((len(texts), ec.DEFAULT_DIM), dtype=np.float32)

        ec.embed_texts = spy2
        try:
            self.assertEqual(ec.embed_query(["Q"]).shape[0], 1)
            self.assertTrue(all(t.startswith(ec.QUERY_PREFIX) for t in routed["texts"]))
            self.assertEqual(ec.embed_docs(["D"]).shape[0], 1)
            self.assertTrue(all(t.startswith(ec.DOC_PREFIX) for t in routed["texts"]))
        finally:
            ec.embed_texts = orig

    def test_prefix_scheme_in_hash(self):
        """前缀方案入 content_hash：换方案 = 旧缓存全量失配 → 全量重嵌（防半新半旧）。"""
        ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
        r = ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
        self.assertEqual(r["to_embed"], 0)
        old = ec.PREFIX_SCHEME
        try:
            ec.PREFIX_SCHEME = "nomic-task-v999"              # 模拟换方案
            r2 = ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
            self.assertGreater(r2["to_embed"], 50)
        finally:
            ec.PREFIX_SCHEME = old

    def test_nearest_sanity(self):
        ec.refresh(self.store, self.cache, embed_fn=_fake_embed)
        c = ec.load_cache(self.cache)
        eid = next(iter(c["items"]))
        v = ec._unb64(c["items"][eid]["vec"], c["dim"])
        top = ec.nearest(c, v, k=1)
        self.assertEqual(top[0][1], eid)                           # 自身最近
        self.assertAlmostEqual(top[0][0], 1.0, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
