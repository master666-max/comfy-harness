# -*- coding: utf-8 -*-
"""test_neg_chain.py — 三段一体红绿（反向飞轮→纠错环路→影响传播）

维护者令：环路不该只管"机器自己的引用错误"，应按**条件**命中所有满足条件的条目。
本件锁：① 负例台账四源（标本/裁撤件/观察/线索）；② **条件命中不依赖引用边**（核心）；
③ 分档（strong/mention/refute）与动作（prescriptive→下架；仅同域提及→打标；纠正源→不动作）；
④ 降噪闸（模板套话剥离 / 语料 DF / 锚点词）；⑤ 靶排除（负例自身不作靶）。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import edge_graph as eg          # noqa: E402
import neg_chain as nc           # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402


def _mk(eid, content, evidence=None, keywords=None, facts=None):
    d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
         "type": "procedural", "importance": 3,
         "content": {"c": content, "a": "", "d": ""},
         "keywords": keywords or [], "evidence": {"artifact": evidence or "generation:x.png"}}
    if facts:
        d["facts"] = facts
    return d


class TestNegChain(unittest.TestCase):
    def _fixture(self, tmp):
        s = PrecedentStore([])
        # 负例：标本（讲 M_dz@1.0 糊指）
        s.add(_mk("N-spec-aa11", "负例：M_dz@1.0 在握持构图下把手指糊成面团（糊指 DNA）",
                  facts={"specimen": True, "specimen_note": "M_dz@1.0 + holding 构图 → 糊指"}), actor="ai:t")
        # 靶 1：**推荐**该错组合（无自有证据）→ 应下架
        s.add(_mk("S-bad-aa11", "LoRA 配方：固定用 M_dz 权重 1.0，在握持构图下照抄即可（认为糊指问题已解决）",
                  evidence="见 N-spec-aa11"), actor="ai:t")
        # 靶 2：仅同域提及（不推荐，无自有证据）→ 应只打标
        s.add(_mk("S-mid-bb22", "M_dz 这个 LoRA 在 holding 类构图下的表现记录"),
              actor="ai:t")
        # 靶 3：纠正源（自述复测推翻）→ 不动作
        s.add(_mk("S-ref-cc33", "复测推翻：M_dz@1.0 在握持构图下手指实测反而清晰、糊指不成立，附同种子对照",
                  evidence="generation:recheck.png"), actor="ai:t")
        # 靶 4：无关件 → 不命中
        s.add(_mk("S-irr-dd44", "樱花树下逆光场景的提示词排列（与 LoRA 权重无关）"), actor="ai:t")
        for i in range(10):        # 填充件：模拟真实语料规模（否则 DF 闸把"构图"这类语料常见词全剔）
            s.add(_mk(f"S-fill-{i:02d}", f"本地实验编号 {i} 的参数与结果备注（独立术语集 {i}）",
                      evidence=f"generation:fill{i}.png"), actor="ai:t")
        path = os.path.join(tmp, "seed.json")
        s.save(path)
        # 观察账本（减损+对照 → 可动作）
        obs = os.path.join(tmp, "out")
        os.makedirs(obs, exist_ok=True)
        with open(os.path.join(obs, "x_obs.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"类": "减损", "现象": "vp1 detailer 在 0.8 权重下把细网纹抹成噪点墙",
                                 "条件": "vp1 detailer 权重 0.8 + fence 细密纹理",
                                 "证据": "fence_xx.png", "对照": True, "可复算": "同种子重渲"},
                                ensure_ascii=False) + "\n")
            # 伪影类（20261010 准入：已定根因的缺陷与减损同族）
            fh.write(json.dumps({"类": "伪影", "现象": "LatentUpscale nearest-exact 潜放大出块状色块",
                                 "条件": "upscale_method nearest-exact + denoise 0.6",
                                 "证据": "blk_xx.png", "对照": True, "可复算": "换 bislerp 同种子对照"},
                                ensure_ascii=False) + "\n")
        return path

    def test_registry_collects_four_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._fixture(tmp)
            reg = nc.build_registry(seed, os.path.join(tmp, "out"))
            srcs = {n["src"] for n in reg}
            self.assertIn("specimen_live", srcs)          # 标本
            self.assertIn("obs_减损", srcs)                # 观察（对照=true → 可动作）
            self.assertIn("obs_伪影", srcs)                # 伪影（20261010 准入，同族可动作）
            obs = [n for n in reg if n["src"] == "obs_减损"][0]
            self.assertTrue(obs["actionable"])
            art = [n for n in reg if n["src"] == "obs_伪影"][0]
            self.assertTrue(art["actionable"])

    def test_condition_match_without_citation_edge(self):
        """核心：靶 2 与负例**没有引用边**，仍应被条件命中。"""
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._fixture(tmp)
            s = PrecedentStore.load(seed)
            g = eg.extract_graph(s.entries)
            cites = {(x["up"], x["down"]) for x in g["edges"] if x["type"] == "cites"}
            self.assertNotIn(("N-spec-aa11", "S-mid-bb22"), cites)     # 确无引用边
            r = nc.scan(seed, os.path.join(tmp, "out"), os.path.join(tmp, "lg.jsonl"),
                        mode="shadow")
            hit = {h["entry"]: h for h in r["hits"]}
            self.assertIn("S-mid-bb22", hit)             # 条件命中（不靠引用边）

    def test_tiers_and_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._fixture(tmp)
            r = nc.scan(seed, os.path.join(tmp, "out"), os.path.join(tmp, "lg.jsonl"), mode="on")
            hit = {h["entry"]: h for h in r["hits"]}
            self.assertEqual(hit["S-bad-aa11"]["action"], "retract+flag")   # 推荐该组合→下架
            self.assertEqual(hit["S-mid-bb22"]["action"], "flag")           # 仅提及→打标
            self.assertEqual(hit["S-ref-cc33"]["tier"], "refute")           # 纠正源→不动作
            self.assertNotIn("S-irr-dd44", hit)                            # 无关件不命中
            s = PrecedentStore.load(seed)
            self.assertTrue(s._get("S-bad-aa11").get("machine_retracted"))
            self.assertTrue((s._get("S-mid-bb22").get("facts") or {}).get("auto_derate"))
            self.assertFalse(s._get("S-ref-cc33").get("machine_retracted"))

    def test_specimen_never_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._fixture(tmp)
            r = nc.scan(seed, os.path.join(tmp, "out"), os.path.join(tmp, "lg.jsonl"),
                        mode="shadow")
            self.assertNotIn("N-spec-aa11", [h["entry"] for h in r["hits"]])   # 靶排除

    def test_anchor_and_boilerplate_gates(self):
        self.assertFalse(nc._is_anchor("cinematic"))       # 通用词
        self.assertTrue(nc._is_anchor("noobai-xl"))        # 锚点（连字符）
        self.assertTrue(nc._is_anchor("c0b46271"))         # 锚点（数字）
        stripped = nc._strip("机器提案·风格簇「x」：双挖掘器涌现（det+lightrag）——证据 26 文档可回源")
        self.assertNotIn("lightrag", stripped.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
