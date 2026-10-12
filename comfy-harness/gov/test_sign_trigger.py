# -*- coding: utf-8 -*-
"""test_sign_trigger.py — 人工待签池触发器红绿测试（20261010 维护者令①）

镜像 test 面形制：首跑静默基线 / Δ 阈值 / 龄限 / mark 顺延 / 签发消耗 clamp 0 /
loose 谓词排除（标本/墓碑/机撤/自纠标）/ CLI 退出码。"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import sign_trigger as sg                     # noqa: E402
from precedent_gov import PrecedentStore      # noqa: E402

PY = sys.executable


def _draft(eid):
    return {"id": eid, "task": "t2i", "kind": "pipeline", "level": "specialized",
            "type": "procedural", "importance": 3,
            "content": {"c": f"draft {eid}", "a": "", "d": ""},
            "keywords": ["k"], "evidence": {"artifact": "generation:x.png"}}


def _store(tmp, n=3, mark_specimen=False):
    s = PrecedentStore([])
    for i in range(n):
        s.add(_draft(f"D-{i:02d}"), actor="ai:test")
    if mark_specimen:
        e = s._get("D-00")
        f = dict(e.get("facts") or {})
        f["specimen"] = "retired"
        s.amend("D-00", {"facts": f}, reason="标本化", actor="human:t")
    seed = os.path.join(tmp, "seed.json")
    s.save(seed)
    return seed


def _backdate_add(seed, eid, days):
    d = json.load(open(seed, encoding="utf-8"))
    old = (datetime.datetime.now() - datetime.timedelta(days=days)
           ).isoformat(timespec="seconds")
    for ev in d.get("gov_events", []):
        if ev.get("kind") == "add" and ev.get("id") == eid:
            ev["at"] = old
    json.dump(d, open(seed, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _add_one(seed):
    s = PrecedentStore.load(seed)
    s.add(_draft(f"D-x-{len(s.entries):02d}"), actor="ai:test")
    s.save(seed)


def _cli(args, seed, state):
    return subprocess.run(
        [PY, os.path.join(_HERE, "sign_trigger.py")] + args
        + ["--store", seed, "--state", state],
        capture_output=True, text=True, encoding="utf-8")


class TestSignTrigger(unittest.TestCase):
    def test_first_run_silent_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            seed = _store(td, n=2)
            st = os.path.join(td, "state.json")
            r = sg.check(state_path=st, store_path=seed)
            self.assertTrue(r["first"])
            self.assertFalse(r["due"])
            self.assertTrue(os.path.isfile(st))          # 基线已落

    def test_delta_due_and_mark_reset(self):
        with tempfile.TemporaryDirectory() as td:
            seed = _store(td, n=2)
            st = os.path.join(td, "state.json")
            sg.check(state_path=st, store_path=seed)     # 基线 loose=2
            _add_one(seed)
            r = sg.check(threshold=1, state_path=st, store_path=seed)
            self.assertTrue(r["due"])                    # Δ=1 ≥ 1
            self.assertIn("Δ新增", r["why"])
            sg.mark(state_path=st, store_path=seed)      # 顺延
            r2 = sg.check(threshold=1, state_path=st, store_path=seed)
            self.assertFalse(r2["due"])                  # Δ 归零
            self.assertEqual(r2["d_new"], 0)

    def test_sign_consumes_clamps_negative(self):
        """签发消耗积压：loose 反降 → Δ 负数按 0 计（清账不算债）。"""
        with tempfile.TemporaryDirectory() as td:
            seed = _store(td, n=3)
            st = os.path.join(td, "state.json")
            sg.check(state_path=st, store_path=seed)     # 基线 loose=3
            s = PrecedentStore.load(seed)
            s.promote("D-00", actor="human:t", prereg="test@v1")
            s.promote("D-01", actor="human:t", prereg="test@v1")
            s.save(seed)
            r = sg.check(threshold=1, state_path=st, store_path=seed)
            self.assertEqual(r["d_new"], 0)              # -2 → clamp 0
            self.assertFalse(r["due"])

    def test_age_condition_fires(self):
        with tempfile.TemporaryDirectory() as td:
            seed = _store(td, n=2)
            _backdate_add(seed, "D-00", 4)
            st = os.path.join(td, "state.json")
            sg.check(state_path=st, store_path=seed)     # 基线（已含 4 天老草案）
            r = sg.check(threshold=99, age_days=3, state_path=st, store_path=seed)
            self.assertTrue(r["due"])                    # Δ 不足但龄限到
            self.assertIn("龄限", r["why"])

    def test_loose_predicate_excludes(self):
        with tempfile.TemporaryDirectory() as td:
            seed = _store(td, n=3, mark_specimen=True)   # D-00 标本化
            s = PrecedentStore.load(seed)
            s.retract("D-01", actor="machine:t", reason="测试机撤")
            s.save(seed)
            r = sg.measure(seed)
            self.assertEqual(r["loose_drafts"], 1)       # 只剩 D-02

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            seed = _store(td, n=1)
            st = os.path.join(td, "state.json")
            self.assertEqual(_cli(["check", "--threshold", "1"], seed, st).returncode, 0)
            _add_one(seed)
            r2 = _cli(["check", "--threshold", "1"], seed, st)
            self.assertEqual(r2.returncode, 1)
            self.assertIn("待签到期", r2.stdout)
            self.assertEqual(_cli(["mark"], seed, st).returncode, 0)
            self.assertEqual(_cli(["check", "--threshold", "1"], seed, st).returncode, 0)


if __name__ == "__main__":
    unittest.main()
