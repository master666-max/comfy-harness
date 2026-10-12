# -*- coding: utf-8 -*-
"""test_impact_flow.py — 人审影响面流程红绿（impact 一键 / retire 人签 + 撤回审计 / 不连坐红线）

维护者令 20261008：「开干」——把影响面一键接进人审流程 + 环检测进健康度。
本件锁：① impact 命令只读；② retire 先出影响面并落审计记录再动；
③ retire 仍 human:* 专属（machine 被拒）；④ **受影响件一律不动**（机器不连坐）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import edge_graph as eg                       # noqa: E402
from precedent_gov import PrecedentStore      # noqa: E402


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


def _fixture(tmp):
    """错根 root（approved）→ 引用者 dep（只引用，无自证）+ 自证者 own（有实测）。

    **经 store API 立项**：approved 必须有人签 promote 事件背书——
    手写 gov='approved' 会被 load() 防毒再验证降回 draft（本次实测抓出的正解）。"""
    s = PrecedentStore([])
    for e in [
        _e("P-root", content={"c": "原始结论", "a": "", "d": ""},
           evidence={"artifact": "generation:r.png"}),
        _e("S-dep", content={"c": "依据 P-root 得出（引用）", "a": "", "d": ""},
           evidence={"artifact": "见 P-root"}),
        _e("S-own", content={"c": "P-root 提示 + 自有实测", "a": "", "d": ""},
           evidence={"artifact": "generation:mine.png"}),
    ]:
        s.add(e, actor="ai:test")
        s.promote(e["id"], actor="human:test")           # 合法立项（事件背书）
    path = os.path.join(tmp, "seed.json")
    s.save(path)
    return path


class TestImpactCommand(unittest.TestCase):
    def test_impact_readonly(self):
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            before = open(seed, encoding="utf-8").read()
            rc = cli.main(["precedent_cli.py", "impact", "--seed", seed,
                           "--id", "P-root", "--hops", "2"])
            self.assertEqual(rc, 0)
            self.assertEqual(open(seed, encoding="utf-8").read(), before)   # 只读

    def test_impact_lists_affected(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = PrecedentStore.load(_fixture(tmp))
            rep = eg.impact(eg.extract_graph(s.entries), "P-root", 2)
            nodes = {x["node"] for x in rep["rows"]}
            self.assertEqual(nodes, {"S-dep", "S-own"})
            tiers = {x["node"]: x["tier"] for x in rep["rows"]}
            self.assertIn("连坐候选", tiers["S-dep"])
            self.assertIn("自证", tiers["S-own"])


class TestRetireFlow(unittest.TestCase):
    def test_dry_run_touches_nothing(self):
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            before = open(seed, encoding="utf-8").read()
            rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "P-root",
                           "--mode", "deprecate", "--actor", "human:test", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertEqual(open(seed, encoding="utf-8").read(), before)

    def test_machine_actor_refused(self):
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            with self.assertRaises(Exception) as cm:
                cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "P-root",
                          "--mode", "tombstone", "--actor", "machine:bot"])
            self.assertIn("DENY:NO_HUMAN_SIG", str(cm.exception))

    def test_human_retire_writes_record_and_not_connected(self):
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            rec_dir = os.path.join(tmp, "records")
            og_dir = eg.RECORDS_DIR
            eg.RECORDS_DIR = rec_dir                          # 记录改落临时目录（不碰生产）
            try:
                rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "P-root",
                               "--mode", "deprecate", "--actor", "human:test",
                               "--reason", "验收测试"])
                self.assertEqual(rc, 0)
                files = os.listdir(rec_dir)
                self.assertEqual(len(files), 1)               # 撤回审计入账
                rec = json.load(open(os.path.join(rec_dir, files[0]), encoding="utf-8"))
                self.assertEqual(rec["root"], "P-root")
                self.assertEqual(len(rec["impact"]["rows"]), 2)
                s = PrecedentStore.load(seed)
                self.assertTrue(s._get("P-root").get("deprecated"))       # 本体已退场
                self.assertEqual(s._get("S-dep").get("gov"), "approved")  # **不连坐**
                self.assertEqual(s._get("S-own").get("gov"), "approved")
            finally:
                eg.RECORDS_DIR = og_dir

    def test_tombstone_two_stage_enforced(self):
        """两段式退场实测：approved 直接墓碑被拒（DENY:TWO_STAGE）；先 deprecate 再墓碑通过。"""
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            og_dir = eg.RECORDS_DIR
            eg.RECORDS_DIR = os.path.join(tmp, "r")
            try:
                with self.assertRaises(Exception) as cm:
                    cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "S-dep",
                              "--mode", "tombstone", "--actor", "human:test"])
                self.assertIn("DENY:TWO_STAGE", str(cm.exception))
                self.assertFalse(PrecedentStore.load(seed)._get("S-dep").get("tombstone"))
                rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "S-dep",
                               "--mode", "deprecate", "--actor", "human:test"])
                self.assertEqual(rc, 0)
                rc = cli.main(["precedent_cli.py", "retire", "--seed", seed, "--id", "S-dep",
                               "--mode", "tombstone", "--actor", "human:test"])
                self.assertEqual(rc, 0)
                self.assertTrue(PrecedentStore.load(seed)._get("S-dep").get("tombstone"))
            finally:
                eg.RECORDS_DIR = og_dir


class TestHealthTd(unittest.TestCase):
    def test_health_has_td_reading(self):
        import health as H
        r = H.readings()
        self.assertIn("cycles", r)
        self.assertIn("n", r["cycles"])
        txt = H.format_readings(r)
        self.assertIn("T-d 有向环", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
