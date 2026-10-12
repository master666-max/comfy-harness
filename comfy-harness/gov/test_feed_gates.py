# -*- coding: utf-8 -*-
"""test_feed_gates.py — P3/P4 四重防线红绿（工单-飞轮根治与向量化统合）

覆盖：①根凭据闸 ②process 出口 ③gen 代数上限 ④近重复闸→recurrence + N1 轮内合并。
cosine 用 DI 字典嵌入精确控制（同一向量→cos 1.0，确定性）。
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".."))
import style_feed as sf             # noqa: E402
import embed_cache as ec            # noqa: E402

PRESET = {}


def dict_embed(texts, base=None, model=None, dim=None):
    out = []
    for t in texts:
        v = PRESET.get(t)
        if v is None:
            rng = np.random.default_rng(
                int(hashlib.sha1(t.encode("utf-8")).hexdigest(), 16) % (2 ** 31))
            v = rng.normal(size=16).astype(np.float32)
        out.append(np.asarray(v, dtype=np.float32))
    return np.asarray(out, dtype=np.float32)


def _cand(name, members, evidence, arms=("det",)):
    return {"name": name, "members": list(members), "arms": list(arms),
            "cohesion": 0.9, "evidence": list(evidence)}


class TestFeedGates(unittest.TestCase):
    def setUp(self):
        PRESET.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "seed.json")
        shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "precedents_e2_seed.json"), self.store)
        self.cache = os.path.join(self.tmp.name, "emb.json")
        ec.refresh(self.store, self.cache, dim=16, embed_fn=dict_embed)
        self.rec = os.path.join(self.tmp.name, "rec.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self):
        from precedent_gov import PrecedentStore
        return PrecedentStore.load(self.store)

    def test_root_gate_all_derived_goes_process(self):
        s = self._load()
        draft_id = next(e["id"] for e in s.entries if e.get("gov") == "draft")
        c = _cand("测试风格束", ["alpha", "beta", "gamma", "delta"],
                  [f"precedent:{draft_id}"])                     # 证据=派生件 → 无根
        r = sf.feed([c], s, [], min_size=4, cache_path=self.cache,
                    embed_fn=dict_embed, recurrence_path=self.rec)
        self.assertEqual(len(r["minted"]), 0)
        self.assertEqual(len(r["process"]), 1)
        self.assertIn("无根凭据", r["process"][0]["why"])

    def test_gen_cap_ban(self):
        s = self._load()
        eid = next(e["id"] for e in s.entries
                   if e.get("gov") == "approved" and e.get("owner"))
        for e in s.entries:
            if e["id"] == eid:
                e["_mine_gen"] = 1                               # 父代=挖掘源
        c = _cand("二代风格束", ["alpha", "beta", "gamma", "delta"],
                  [f"precedent:{eid}"])
        r = sf.feed([c], s, [], min_size=4, cache_path=self.cache,
                    embed_fn=dict_embed, recurrence_path=self.rec)
        self.assertEqual(len(r["minted"]), 0)
        self.assertTrue(any("gen=2" in sk["why"] for sk in r["skipped"]), r["skipped"])

    def test_process_outlet(self):
        c = _cand("Machine Proposal Style Cluster 汇总",
                  ["S-explosive-fireworks-display-9a12ad89", "Mining Signature",
                   "Candidate Boundary Human Gate", "alpha"],
                  ["generation:x.png"])
        s = self._load()
        r = sf.feed([c], s, [], min_size=4, cache_path=self.cache,
                    embed_fn=dict_embed, recurrence_path=self.rec)
        self.assertEqual(len(r["minted"]), 0)
        self.assertEqual(len(r["process"]), 1)

    def test_cosine_near_dup_records_recurrence(self):
        s = self._load()
        eid = next(e["id"] for e in s.entries if e.get("gov") == "approved")
        c = _cand("逆光天台近似版", ["alpha", "beta", "gamma", "delta"],
                  ["generation:x.png"])
        cache = ec.load_cache(self.cache)
        vec = ec._unb64(cache["items"][eid]["vec"], cache["dim"])
        PRESET[sf.candidate_text(c["name"], c["members"])] = vec   # 强制 cos=1.0
        r = sf.feed([c], s, [], min_size=4, cache_path=self.cache,
                    embed_fn=dict_embed, recurrence_path=self.rec)
        self.assertEqual(len(r["minted"]), 0)
        self.assertEqual(len(r["recurred"]), 1)
        self.assertEqual(r["recurred"][0]["into"], eid)
        rec = json.load(open(self.rec, encoding="utf-8"))
        self.assertEqual(rec[eid]["count"], 1)                    # recurrence 落账

    def test_n1_in_batch_merge(self):
        c1 = _cand("天台逆光A", ["alpha", "beta", "gamma", "delta"], ["generation:x.png"])
        c2 = _cand("天台逆光B", ["alpha", "beta", "gamma", "epsilon"], ["generation:x.png"])
        shared = np.array([1.0] * 16, dtype=np.float32)
        PRESET[sf.candidate_text(c1["name"], c1["members"])] = shared
        PRESET[sf.candidate_text(c2["name"], c2["members"])] = shared  # 强制 cos=1.0
        s = self._load()
        r = sf.feed([c1, c2], s, [], min_size=4, cache_path=self.cache,
                    embed_fn=dict_embed, recurrence_path=self.rec)
        self.assertEqual(r["n1_merged"], 1)
        self.assertEqual(len(r["minted"]), 1)
        e = next(x for x in s.entries if x["id"] == r["minted"][0]["id"])
        self.assertIn("epsilon", e["keywords"])                 # N1 并集并入


if __name__ == "__main__":
    unittest.main(verbosity=2)
