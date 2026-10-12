# -*- coding: utf-8 -*-
"""test_retire_specimen_interface.py — 退场↔反向飞轮接口红绿（维护者令 20261008）

维护者令：「这个撤销命令，记得留好和反向飞轮的接口呦」。
接口三面：
  ① retire --as-specimen：人签退场同时把错条转入标本库（facts.specimen，并入不覆盖）；
  ② 雷达收**退场标本**（tombstone/deprecated 的标本是最有价值的错例——原先被跳过）；
  ③ 向量缓存为标本件保向量（哪怕退场）——雷达相似度臂靠它；退场件不进召回池=无泄漏。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import embed_cache as ec                  # noqa: E402
import reverse_flywheel as rf             # noqa: E402
from precedent_gov import PrecedentStore  # noqa: E402


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "precedent_cli",
        os.path.join(os.path.dirname(os.path.dirname(_HERE)), "tools", "precedent_cli.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _e(eid, **kw):
    d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
         "type": "procedural", "importance": 3,
         "content": {"c": eid, "a": "", "d": ""}, "keywords": [], "evidence": {}}
    d.update(kw)
    return d


def _seed(tmp, entries):
    s = PrecedentStore([])
    for e in entries:
        s.add(e, actor="ai:test")
        s.promote(e["id"], actor="human:test")
    path = os.path.join(tmp, "seed.json")
    s.save(path)
    return path


def _cache_with(vec_map, dim=4):
    items = {}
    for eid, v in vec_map.items():
        a = np.zeros(dim, dtype=np.float32)
        a[v] = 1.0
        items[eid] = {"hash": "x", "vec": ec._b64(a)}
    return {"dim": dim, "items": items}


class TestRetireAsSpecimen(unittest.TestCase):
    def test_flag_converts_to_specimen_and_radar_sees_it(self):
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _seed(tmp, [
                _e("S-bad-aa11", content={"c": "错误经验：把提案词当风格", "a": "", "d": ""},
                   evidence={"artifact": "generation:b.png"}),
                _e("S-ref-aa22", content={"c": "依据 S-bad-aa11", "a": "", "d": ""},
                   evidence={"artifact": "见 S-bad-aa11"}),
            ])
            import edge_graph as eg
            og_dir = eg.RECORDS_DIR
            eg.RECORDS_DIR = os.path.join(tmp, "rec")
            try:
                # 两段式退场（approved 须先 deprecate）：第一段转标本，第二段墓碑
                rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "S-bad-aa11",
                               "--mode", "deprecate", "--actor", "human:test",
                               "--reason", "判为错例", "--as-specimen"])
                self.assertEqual(rc, 0)
                rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "S-bad-aa11",
                               "--mode", "tombstone", "--actor", "human:test",
                               "--reason", "两段式收尾"])
                self.assertEqual(rc, 0)
                s = PrecedentStore.load(seed)
                e = s._get("S-bad-aa11")
                self.assertTrue(e.get("tombstone"))                      # 已退场
                self.assertTrue((e.get("facts") or {}).get("specimen"))   # 且转标本
                self.assertIn("判为错例", (e.get("facts") or {}).get("specimen_note", ""))
                # 雷达收取：退场标本也在列（核心行为）
                spec = rf.specimens(s, _cache_with({"S-bad-aa11": 0}))
                self.assertEqual([x["id"] for x in spec], ["S-bad-aa11"])
                self.assertTrue(spec[0]["retired"])                       # 标为退场标本
                # 相似候选被命中（相似度臂）
                fn = lambda texts, **kw: np.array([[1.0, 0, 0, 0]], dtype=np.float32)
                r = rf.judge("新候选", ["tag one"], spec, embed_fn=fn)
                self.assertEqual(r["verdict"], "hit")
                self.assertIn("标本同形", "；".join(r["by"]))
            finally:
                eg.RECORDS_DIR = og_dir

    def test_no_flag_no_specimen(self):
        """未加 --as-specimen：退场就是不转标本（防误触——接口须明示）。"""
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _seed(tmp, [_e("S-plain-aa11", evidence={"artifact": "generation:p.png"})])
            import edge_graph as eg
            og_dir = eg.RECORDS_DIR
            eg.RECORDS_DIR = os.path.join(tmp, "rec")
            try:
                rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "S-plain-aa11",
                               "--mode", "deprecate", "--actor", "human:test", "--reason", "普通退场"])
                self.assertEqual(rc, 0)
                e = PrecedentStore.load(seed)._get("S-plain-aa11")
                self.assertFalse((e.get("facts") or {}).get("specimen"))
            finally:
                eg.RECORDS_DIR = og_dir


class TestCacheKeepsSpecimenVector(unittest.TestCase):
    def test_refresh_keeps_tombstoned_specimen_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = os.path.join(tmp, "seed.json")
            PrecedentStore([_e("S-spec-1", tombstone=True,
                               facts={"specimen": True, "specimen_note": "退场标本"}),
                            _e("S-dead-2", tombstone=True),
                            _e("S-live-3")]).save(seed)
            cache = os.path.join(tmp, "emb.json")

            def fake(texts, base=None, model=None, dim=None):
                return np.ones((len(texts), ec.DEFAULT_DIM), dtype=np.float32)
            ec.refresh(seed, cache, embed_fn=fake)
            items = ec.load_cache(cache)["items"]
            self.assertIn("S-spec-1", items)      # 标本退场也保向量（雷达靠它）
            self.assertNotIn("S-dead-2", items)   # 普通退场件照旧清除
            self.assertIn("S-live-3", items)


class TestReadonlyRedline(unittest.TestCase):
    def test_radar_still_readonly_with_retired_specimen(self):
        s = PrecedentStore([_e("S-spec-1", tombstone=True,
                               facts={"specimen": True, "specimen_note": "x"})])
        n0, e0 = len(s.entries), len(s.gov_events)
        spec = rf.specimens(s, _cache_with({"S-spec-1": 0}))
        rf.judge("候选", ["a"], spec, embed_fn=lambda t, **k: np.array([[1.0, 0, 0, 0]],
                                                                       dtype=np.float32))
        self.assertEqual((len(s.entries), len(s.gov_events)), (n0, e0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
