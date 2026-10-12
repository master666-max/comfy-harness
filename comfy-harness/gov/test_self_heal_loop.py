# -*- coding: utf-8 -*-
"""自纠环路红绿测试：①bayes act 榜首动作制 ②self_correct.confess 入环 ③红线（转正令 20261010）"""
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import bayes_shadow as bs                  # noqa: E402
import edge_graph as eg                    # noqa: E402
import self_correct as sc                  # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402


def _ent(eid, content, artifact, gov="draft", **kw):
    e = {"id": eid, "task": "t2i", "kind": "pipeline", "level": "specialized",
         "type": "procedural", "importance": 3,
         "content": {"c": content, "a": "", "d": ""}, "keywords": ["k"],
         "evidence": {"artifact": artifact}, "gov": gov}
    e.update(kw)
    return e


def _fixture(tmp):
    """错根（人签墓碑+标本）+ 三种依赖：纯引用 / 自有证据 / 人签面。

    人签件须走真 promote（load 防毒闸：无 human 事件背书的 approved 一律降 draft）。"""
    root = _ent("R-wrong-01", "错根：挂 LoRA 必修复手指、无需二道", "generation:root.png",
                tombstone=True, facts={"specimen": "retired"})
    cite = _ent("A-cite-dep", "沿用 R-wrong-01 的结论：不必跑手部二道", "见 R-wrong-01")
    raw = _ent("M-raw-dep", "提及 R-wrong-01 但有自己的实测", "generation:own.png")
    appr = _ent("Z-appr-dep", "沿用 R-wrong-01 的结论（人签件）", "见 R-wrong-01")
    s = PrecedentStore([root, cite, raw, appr])
    s.promote("Z-appr-dep", actor="human:t", prereg="test@v1")   # 人签背书（gov_events 留痕）
    seed = os.path.join(tmp, "seed.json")
    s.save(seed)
    return seed


def _load(seed):
    return {e["id"]: e for e in PrecedentStore.load(seed).entries}


class TestBayesAct(unittest.TestCase):
    def test_act_top1_retracts_citation_flag_rest_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            g = eg.extract_graph(PrecedentStore.load(seed).entries)
            r = bs.run(g, "R-wrong-01", m="act", log_path=os.path.join(tmp, "b.jsonl"),
                       store_path=seed, root_kind="error")
            self.assertEqual(r["acted"]["acted"], "A-cite-dep")       # 榜一=纯引用件
            self.assertEqual(r["acted"]["action"], "retract+flag")
            es = _load(seed)
            self.assertTrue(es["A-cite-dep"].get("machine_retracted"))
            self.assertTrue(es["A-cite-dep"]["facts"].get("auto_derate"))
            self.assertFalse(es["M-raw-dep"].get("machine_retracted"))  # 自有证据不动
            self.assertNotIn("auto_derate", es["M-raw-dep"].get("facts") or {})
            self.assertFalse(es["Z-appr-dep"].get("machine_retracted"))  # 人签面不动

    def test_act_ratchet_top1_skips_without_creep(self):
        """第二轮：榜一已撤出榜 → 新榜一=人签件 → 留痕即停，绝不顺延到自有证据件。"""
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            g = eg.extract_graph(PrecedentStore.load(seed).entries)
            bs.run(g, "R-wrong-01", "act", os.path.join(tmp, "b.jsonl"), store_path=seed)
            r2 = bs.run(g, "R-wrong-01", "act", os.path.join(tmp, "b.jsonl"),
                        store_path=seed)
            self.assertIsNone(r2["acted"]["acted"])
            self.assertIn("人签面", r2["acted"]["why"])
            es = _load(seed)
            self.assertFalse(es["M-raw-dep"].get("machine_retracted"))  # 未被顺延误伤

    def test_suspect_root_flag_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            g = eg.extract_graph(PrecedentStore.load(seed).entries)
            r = bs.run(g, "R-wrong-01", "act", os.path.join(tmp, "b.jsonl"),
                       store_path=seed, root_kind="suspect")
            self.assertEqual(r["acted"]["action"], "flag")            # 待复核只打标
            es = _load(seed)
            self.assertFalse(es["A-cite-dep"].get("machine_retracted"))

    def test_healthy_root_log_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            g = eg.extract_graph(PrecedentStore.load(seed).entries)
            r = bs.run(g, "R-wrong-01", "act", os.path.join(tmp, "b.jsonl"),
                       store_path=seed, root_kind="healthy")
            self.assertIsNone(r["acted"])                              # 信任根不驱动动作
            es = _load(seed)
            self.assertFalse(es["A-cite-dep"].get("machine_retracted"))

    def test_mode_act_default_and_rejects_junk(self):
        self.assertEqual(bs.DEFAULT_MODE, "act")                       # 转正令
        self.assertEqual(bs.mode(cli=None, env=""), "act")
        with self.assertRaises(SystemExit):
            bs.mode(cli="yes", env="")


class TestSelfCorrect(unittest.TestCase):
    def _live_fixture(self, tmp):
        """在役草案错根（未人签）+ 纯引用依赖——confess 后应整环生效。"""
        root = _ent("R-live-01", "错误结论：vp1 detailer 权重越高越好", "generation:r.png")
        cite = _ent("A-cite-dep", "沿用 R-live-01 的结论：拉满 1.0", "见 R-live-01")
        s = PrecedentStore([root, cite])
        seed = os.path.join(tmp, "seed.json")
        s.save(seed)
        return seed, os.path.join(tmp, "obs.jsonl")

    def test_confess_wires_full_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, obs = self._live_fixture(tmp)
            r = sc.confess("R-live-01", "实测 0.8 以上抹纹理，结论写反了",
                           store_path=seed, obs_path=obs)
            self.assertTrue(r["confessed"])
            es = _load(seed)
            self.assertEqual(es["R-live-01"]["facts"]["specimen"], "ai-self-error")
            self.assertIn("note", es["R-live-01"]["facts"]["self_error"])
            self.assertTrue(es["A-cite-dep"].get("machine_retracted"))  # 贝叶斯 act 即时生效
            lines = [json.loads(l) for l in open(obs, encoding="utf-8") if l.strip()]
            self.assertEqual(len(lines), 1)
            self.assertTrue(lines[0]["对照"])
            self.assertEqual(lines[0]["类"], "异常")

    def test_confess_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, obs = self._live_fixture(tmp)
            sc.confess("R-live-01", "第一次自纠", store_path=seed, obs_path=obs)
            r2 = sc.confess("R-live-01", "第二次自纠", store_path=seed, obs_path=obs)
            self.assertFalse(r2["confessed"])
            self.assertEqual(r2["why"], "已自纠过（幂等）")
            lines = [l for l in open(obs, encoding="utf-8") if l.strip()]
            self.assertEqual(len(lines), 1)                            # 不重复入账

    def test_confess_refuses_ratified_and_tombstoned(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed, obs = self._live_fixture(tmp)
            s = PrecedentStore.load(seed)
            s.add(_ent("P-ok-01", "正常草案件", "generation:ok.png"), actor="human:t")
            s.promote("P-ok-01", actor="human:t", prereg="test@v1")   # 人签背书
            s.save(seed)
            with self.assertRaises(SystemExit) as cm:
                sc.confess("P-ok-01", "试试拒收", store_path=seed, obs_path=obs)
            self.assertIn("DENY:RATIFIED", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
