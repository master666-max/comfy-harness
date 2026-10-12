# -*- coding: utf-8 -*-
"""test_vetted_supply.py — 检定陈述制供血红绿测试（20261010 裁决③）

红线：检定≠签发——vet 只读（不写库/不改 gov 字段）；四项检定独立可红；无向量=保守败。"""
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import vetted_supply as vs                        # noqa: E402
import neg_chain as nc                            # noqa: E402
from precedent_gov import PrecedentStore          # noqa: E402


def _ent(eid, content, artifact="generation:v.png", **kw):
    e = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
         "type": "procedural", "importance": 3,
         "content": {"c": content, "a": "", "d": ""}, "keywords": ["风格"],
         "evidence": {"artifact": artifact}}
    e.update(kw)
    return e


def _fixture(tmp):
    """已签 1 + 六草案：全过 1(minted反查) / R1 红 / R2 红 / R3 红 / R4 红(回声) /
    引用证据过(key_of 回退)。池形态=真实形态（minted 链接+members）。"""
    appr = _ent("P-ok-01", "干净链 detailer 0.6/640 实测不抹纹理", "generation:ok.png")
    good = _ent("S-good-aa", "深海生物荧光蓝辉配方：bioluminescence+caustics 组合",
                "generation:v_good.png",
                facts={"tags": ["生物荧光", "蓝辉", "深海", "水下"]})
    r1 = _ent("S-once-bb", "单轮涌现未成熟配方", "generation:v_once.png",
              facts={"tags": ["单轮", "未成熟"]})
    r2 = _ent("S-neg-cc", "fence 细密纹理场景挂 vp1 detailer 高权重配方",
              "generation:v_neg.png", facts={"tags": ["fence", "细密纹理"]})
    r3 = _ent("S-ev-dd", "证据文件不存在的配方", "generation:no_such_file_zz.png",
              facts={"tags": ["证据"]})
    r4 = _ent("S-echo-ee", "干净链 detailer 配方（复述已签件）", "generation:v_echo.png",
              facts={"tags": ["干净链"]})
    r6 = _ent("S-cite-ff", "引用已签件的深海荧光变体", "见 P-ok-01",
              facts={"tags": ["深海", "荧光", "变体"]})
    s = PrecedentStore([appr, good, r1, r2, r3, r4, r6])
    s.promote("P-ok-01", actor="human:t", prereg="test@v1")
    seed = os.path.join(tmp, "seed.json")
    s.save(seed)
    pool = {
        "s-deepsea-glow": {"rounds_seen": 3, "minted": "S-good-aa",
                           "members": ["生物荧光", "蓝辉", "深海", "水下"]},
        "s-once": {"rounds_seen": 1, "minted": "S-once-bb",
                   "members": ["单轮", "未成熟"]},
        "s-neg": {"rounds_seen": 4, "minted": "S-neg-cc",
                  "members": ["fence", "细密纹理"]},
        "s-ev": {"rounds_seen": 4, "minted": "S-ev-dd", "members": ["证据"]},
        "s-echo": {"rounds_seen": 4, "minted": "S-echo-ee", "members": ["干净链"]},
        "s-cite": {"rounds_seen": 2, "members": ["深海", "荧光", "变体"]},   # 无 minted→key_of
    }
    pool_p = os.path.join(tmp, "pool.json")
    json.dump(pool, open(pool_p, "w", encoding="utf-8"))
    out = os.path.join(tmp, "comfy_out")
    os.makedirs(out, exist_ok=True)
    for fn in ("ok.png", "v_good.png", "v_once.png", "v_neg.png", "v_echo.png"):
        open(os.path.join(out, fn), "wb").write(b"\x89PNG\r\n")
    return seed, pool_p, out


# 负例台账夹具：specimen 条目（fence+vp1 detailer 组合判负）
def _neg_fixture(tmp, seed):
    spec = _ent("N-fence-01", "负例标本：fence 细密纹理下 vp1 detailer 0.8 抹成噪点墙",
                "generation:neg_spec.png",
                facts={"specimen": "retired"}, tombstone=True)
    s = PrecedentStore.load(seed)
    s.entries.append(spec)
    s.save(seed)


# 嵌入注入：good/cite 与已签件不同向（cos<0.9）；echo 与已签件同向（cos=1.0）
def _embed_fn(texts):
    out = []
    for t in texts:
        if "复述已签件" in t or "干净链" in t and "变体" not in t:
            out.append([1.0, 0.0])
        elif "变体" in t or "生物荧光" in t:
            out.append([0.0, 1.0])
        else:
            out.append([0.7, 0.7])
    return out


def _vet(tmp, seed, pool_p, out, **kw):
    s = PrecedentStore.load(seed)
    reg = nc.build_registry(seed, tmp)
    return vs.vet(s, pool_path=pool_p, cache_path=os.path.join(tmp, "none.json"),
                  embed_fn=_embed_fn, comfy_out=out,
                  neg_ctx=(reg, None, None), **kw)


class TestVettedSupply(unittest.TestCase):
    def test_four_checks_classify(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, pool_p, out = _fixture(tmp)
            _neg_fixture(tmp, seed)
            v = _vet(tmp, seed, pool_p, out)
            ids = {x["id"] for x in v["vetted"]}
            self.assertIn("S-good-aa", ids)
            self.assertIn("S-cite-ff", ids)          # 引用证据：被引 id 在库 → 过
            self.assertNotIn("S-once-bb", ids)       # R1 单轮
            self.assertNotIn("S-neg-cc", ids)        # R2 负例命中
            self.assertNotIn("S-ev-dd", ids)         # R3 证据缺失
            self.assertNotIn("S-echo-ee", ids)       # R4 回声 cos=1.0
            self.assertEqual(v["counts"]["复现不足"], 1)
            fails = {x["id"]: x["fail"] for x in v["rejected"]}
            self.assertEqual(fails["S-once-bb"], "R1复现")
            self.assertEqual(fails["S-neg-cc"], "R2负例")
            self.assertEqual(fails["S-ev-dd"], "R3证据")
            self.assertEqual(fails["S-echo-ee"], "R4回声")

    def test_no_vector_conservative_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, pool_p, out = _fixture(tmp)
            s = PrecedentStore.load(seed)
            reg = nc.build_registry(seed, tmp)
            v = vs.vet(s, pool_path=pool_p, cache_path=os.path.join(tmp, "none.json"),
                       embed_fn=None, comfy_out=out, neg_ctx=(reg, None, None))
            self.assertFalse(v["vetted"])            # 全体无向量 → 全保守败
            self.assertEqual(len(v["rejected"]), 6)  # 检定序：R1/R2 先拦，余者 R4 无向量
            self.assertEqual(v["counts"]["无向量"], 4)

    def test_vet_is_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, pool_p, out = _fixture(tmp)
            before = json.load(open(seed, encoding="utf-8"))
            _vet(tmp, seed, pool_p, out)
            after = json.load(open(seed, encoding="utf-8"))
            self.assertEqual(before, after)          # 库零写入

    def test_ratified_never_vetted_and_specimen_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, pool_p, out = _fixture(tmp)
            _neg_fixture(tmp, seed)
            v = _vet(tmp, seed, pool_p, out)
            ids = {x["id"] for x in v["vetted"]} | {x["id"] for x in v["rejected"]}
            self.assertNotIn("P-ok-01", ids)         # 已签面不在检定池
            self.assertNotIn("N-fence-01", ids)      # 标本/墓碑不在检定池

    def test_render_lines_declares_unratified(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, pool_p, out = _fixture(tmp)
            _neg_fixture(tmp, seed)
            v = _vet(tmp, seed, pool_p, out)
            lines = vs.render_lines(v)
            head = "\n".join(lines)
            self.assertIn("未经人签", head)
            self.assertIn("检定≠签发", head)
            self.assertIn("落选", head)


if __name__ == "__main__":
    unittest.main()
