# -*- coding: utf-8 -*-
"""test_style_feed.py — 投喂器红绿测试（分流路由/任务路由/签名/跨臂合并/幂等/开关）"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style_feed as sf             # noqa: E402


class TestClassify(unittest.TestCase):
    def test_style_default(self):
        # 场景/光影/人物成分——无强标记 → style
        self.assertEqual(sf.classify(
            ["backlighting", "rim lighting", "sunset", "white hair", "rooftop"]), "style")
        self.assertEqual(sf.classify(
            ["standing at a summer festival street", "yukata", "lantern"]), "style")

    def test_pipeline_markers(self):
        self.assertEqual(sf.classify(["height", "width", "布线"]), "pipeline")
        self.assertEqual(sf.classify(
            ["Hires Upscale Redraw", "P-noobai-v3-pipeline", "Combination Pass"]), "pipeline")

    def test_postproc_markers(self):
        self.assertEqual(sf.classify(["bbox/face_yolov8m.pt", "simple", "面部二道"]), "postproc")
        self.assertEqual(sf.classify(["film grain", "vignette"]), "postproc")

    def test_governance_markers(self):
        self.assertEqual(sf.classify(["判据件v1.0 schema", "E-2正式考"]), "governance")

    def test_model_markers(self):
        self.assertEqual(sf.classify(["NoobAI-XL-Vpred", "High Half-Model"]), "model")


class TestTask(unittest.TestCase):
    def test_t2v_i2v_default(self):
        self.assertEqual(sf.task_of(["AniSora", "KSampler", "帧数契约"]), "t2v")
        self.assertEqual(sf.task_of(["i2v", "图生视频"]), "i2v")
        self.assertEqual(sf.task_of(["backlighting", "sunset"]), "t2i")


class TestSig(unittest.TestCase):
    def test_order_insensitive_and_stable(self):
        a = sf.sig_of(["b", "a", "c"])
        b = sf.sig_of(["C", "B", "a"])
        self.assertEqual(a, b)
        self.assertEqual(len(a), 8)


class TestMerge(unittest.TestCase):
    def test_pair_union_and_passthrough(self):
        det = {"clusters": [
            {"name": "逆光天台", "tags": [{"tag": t} for t in
                                        ["backlighting", "rim lighting", "sunset"]],
             "cohesion": 0.8, "evidence": ["generation:g1.png"]},
            {"name": "布线参数", "tags": [{"tag": t} for t in ["height", "width"]],
             "cohesion": 1.0, "evidence": []},
        ]}
        lr = {"clusters": [
            {"name": "Rooftop Sunset", "members": ["backlighting", "rim lighting",
                                                   "sunset", "city"],
             "cohesion": 1.0, "evidence": ["generation:g1.png", "generation:g2.png"]},
            {"name": "AniSora 契约", "members": ["AniSora", "KSampler"],
             "cohesion": 1.0, "evidence": ["precedent:P-x"]},
        ]}
        merged = sf.merge_candidates(det, lr)
        self.assertEqual(len(merged), 3)
        first = [m for m in merged if "逆光" in m["name"]][0]
        self.assertEqual(first["arms"], ["det", "lightrag"])
        self.assertIn("city", first["members"])
        self.assertIn(len([m for m in merged if "AniSora" in m["name"]][0]["arms"]),
                      (1, 2))


class TestFeedIdempotency(unittest.TestCase):
    def _run_twice(self, tmp_store, corpus):
        from precedent_gov import PrecedentStore
        cands = [{"name": "逆光天台", "members": ["backlighting", "rim lighting", "sunset",
                                                 "white hair", "rooftop"],
                  "arms": ["det", "lightrag"], "cohesion": 0.9,
                  "evidence": ["generation:g1.png"]}]
        store = PrecedentStore.load(tmp_store)
        r1 = sf.feed(cands, store, corpus, min_size=4)
        store.save(tmp_store)
        store2 = PrecedentStore.load(tmp_store)
        r2 = sf.feed(cands, store2, corpus, min_size=4)
        return r1, r2

    def test_mint_once_then_skip(self):
        with tempfile.TemporaryDirectory() as td:
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "precedents_e2_seed.json"),
                        os.path.join(td, "seed.json"))
            tmp_store = os.path.join(td, "seed.json")
            corpus = [{"src": "generation:g1.png", "meta": {"ckpt": "NoobAI-XL-Vpred-v1.0.safetensors"}}]
            r1, r2 = self._run_twice(tmp_store, corpus)
            self.assertEqual(len(r1["minted"]), 1)
            m = r1["minted"][0]
            self.assertEqual(m["kind"], "style")
            self.assertEqual(r1["routed"], {"style": 1})
            self.assertEqual(len(r2["minted"]), 0)          # 签名幂等：第二轮全跳过
            self.assertEqual(len(r2["skipped"]), 1)

    def test_size_filter(self):
        with tempfile.TemporaryDirectory() as td:
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "precedents_e2_seed.json"),
                        os.path.join(td, "seed.json"))
            from precedent_gov import PrecedentStore
            store = PrecedentStore.load(os.path.join(td, "seed.json"))
            cands = [{"name": "小簇", "members": ["a", "b"], "arms": ["det"],
                      "cohesion": 1.0, "evidence": []}]
            r = sf.feed(cands, store, [], min_size=4)
            self.assertEqual(len(r["minted"]), 0)
            self.assertEqual(r["skipped"][0]["why"], "size<4")


class TestTemplateHygiene(unittest.TestCase):
    BLACK = ("机器提案", "挖掘签名", "观察签名", "候选边界", "无主防毒")

    def test_minted_content_clean_and_sig_marked(self):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "precedents_e2_seed.json"), os.path.join(td, "seed.json"))
            from precedent_gov import PrecedentStore
            store = PrecedentStore.load(os.path.join(td, "seed.json"))
            cands = [{"name": "测试簇", "members": ["aaa", "bbb", "ccc", "ddd"],
                      "arms": ["det"], "cohesion": 0.9, "evidence": ["generation:test.png"]}]
            r = sf.feed(cands, store, [], min_size=4)
            self.assertEqual(len(r["minted"]), 1)
            e = next(x for x in store.entries if x["id"] == r["minted"][0]["id"])
            body = json.dumps(e["content"], ensure_ascii=False)
            for w in self.BLACK:
                self.assertNotIn(w, body, f"正文残留流程词 {w}")
            self.assertTrue(e.get("_mine_sig"))

    def test_dedup_via_mine_sig_without_legacy_text(self):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            sp = os.path.join(td, "seed.json")
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "precedents_e2_seed.json"), sp)
            from precedent_gov import PrecedentStore
            store = PrecedentStore.load(sp)
            cands = [{"name": "测试簇", "members": ["aaa", "bbb", "ccc", "ddd"],
                      "arms": ["det"], "cohesion": 0.9, "evidence": ["generation:test.png"]}]
            sf.feed(cands, store, [], min_size=4)
            sig = sf.sig_of(cands[0]["members"])
            e = next(x for x in store.entries if x.get("_mine_sig") == sig)
            e["content"] = {"c": "干净正文", "a": "", "d": ""}     # 模拟旧字串已不在
            r2 = sf.feed(cands, store, [], min_size=4)
            self.assertEqual(len(r2["minted"]), 0)                   # _mine_sig 路径拦下
            self.assertEqual(len(r2["skipped"]), 1)


class TestSwitch(unittest.TestCase):
    def test_switch_env_and_cli(self):
        self.assertTrue(sf.is_disabled(env="off"))
        self.assertTrue(sf.is_disabled(env="0"))
        self.assertTrue(sf.is_disabled(cli_off=True, env=""))
        self.assertFalse(sf.is_disabled(env="on"))
        self.assertFalse(sf.is_disabled(env=""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
