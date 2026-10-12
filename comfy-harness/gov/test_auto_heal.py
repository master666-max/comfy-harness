# -*- coding: utf-8 -*-
"""test_auto_heal.py — 自动纠错位红绿（预注册接口·未接线；维护者令 20261008）

锁四件：
  A. propose 只读（不写库不落盘）；
  B. apply 缺 human 签/缺 prereg → 拒（DENY:NO_HUMAN_SIG / NO_PREREG）；WIRED=False
     分支保留（monkeypatch）→ DENY:AUTO_HEAL_UNWIRED；
  C. **接线态**（20261009『全开全接线』缺省）：执行器按 affected 分档动作——
     连坐撤件仅 draft（machine_retracted 可 relist）/ 派生 draft 只打标 /
     人闸面（approved/verified）与标本/墓碑/有自有证据者一律跳过；
  D. 触发器评估=实测读数（形状 + 与物证计数一致）。
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

import auto_heal as ah                     # noqa: E402
import reverse_flywheel as rf              # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402


def _fixture(tmp):
    def _e(eid, **kw):
        d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
             "type": "procedural", "importance": 3,
             "content": {"c": eid, "a": "", "d": ""}, "keywords": [], "evidence": {}}
        d.update(kw)
        return d
    s = PrecedentStore([])
    for e in [_e("P-root", evidence={"artifact": "generation:r.png"}),
              _e("S-dep", content={"c": "依据 P-root", "a": "", "d": ""},
                 evidence={"artifact": "见 P-root"})]:
        s.add(e, actor="ai:test")
        s.promote(e["id"], actor="human:test")
    p = os.path.join(tmp, "seed.json")
    s.save(p)
    return p


class TestPropose(unittest.TestCase):
    def test_propose_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            before = open(seed, encoding="utf-8").read()
            p = ah.propose("P-root", seed)
            self.assertEqual(p["root"], "P-root")
            self.assertEqual({r["node"] for r in p["affected"]}, {"S-dep"})
            self.assertTrue(any("降权/复核" in s for s in p["suggestions"]))
            self.assertEqual(open(seed, encoding="utf-8").read(), before)   # 只读


class TestApplyWired(unittest.TestCase):
    """20261009 维护者令『全开，全接线』：WIRED=True 缺省 + 执行器实现（draft-only 红线）。"""

    def test_default_wired(self):
        self.assertTrue(ah.WIRED)                        # 接线态缺省（维护者令 20261009）

    def test_unwired_branch_still_denies(self):
        og = ah.WIRED
        ah.WIRED = False                                 # 分支保留：回拨开关仍铁面
        try:
            with self.assertRaises(PermissionError) as cm:
                ah.apply({"root": "X"}, actor="human:test", prereg="判据@v1")
            self.assertIn("DENY:AUTO_HEAL_UNWIRED", str(cm.exception))
        finally:
            ah.WIRED = og

    def test_cli_apply_exit3(self):
        # 接线后缺 human 签/缺 prereg 仍 rc=3（闸在动作之前）
        rc = ah.main(["apply", "--id", "P-anything", "--actor", "human:test"])
        self.assertEqual(rc, 3)

    def test_wired_still_requires_human_and_prereg(self):
        with self.assertRaises(PermissionError) as cm:
            ah.apply({"root": "X"}, actor="machine:bot", prereg="判据@v1")
        self.assertIn("DENY:NO_HUMAN_SIG", str(cm.exception))
        with self.assertRaises(PermissionError) as cm2:
            ah.apply({"root": "X"}, actor="human:test", prereg=None)
        self.assertIn("DENY:NO_PREREG", str(cm2.exception))

    def test_executor_skips_human_gate_surfaces(self):
        # 既有 fixture：S-dep 已 promote（人闸面）——执行器跳过不降格，语义级断言
        with tempfile.TemporaryDirectory() as tmp:
            seed = _fixture(tmp)
            p = ah.propose("P-root", seed)
            r = ah.apply(p, actor="human:test", prereg="判据@v1")
            self.assertTrue(r["executed"])
            self.assertEqual(r["retracted"], [])
            self.assertEqual(r["flagged"], [])
            self.assertTrue(all("人闸面" in s["why"] for s in r["skipped"]))
            store = PrecedentStore.load(seed)
            self.assertEqual(store._get("S-dep").get("gov"), "approved")  # 人闸面未被机器降格

    def test_executor_retracts_citation_only_draft(self):
        # 红线内动作：纯引用 draft → 连坐撤件（可 relist）；自有证据 draft → 不动
        with tempfile.TemporaryDirectory() as tmp:
            def _e(eid, **kw):
                d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
                     "type": "procedural", "importance": 3,
                     "content": {"c": eid, "a": "", "d": ""}, "keywords": [],
                     "evidence": {}}
                d.update(kw)
                return d
            s = PrecedentStore([])
            for e in [_e("P-root", evidence={"artifact": "generation:r.png"}),
                      _e("S-cite", content={"c": "依据 P-root", "a": "", "d": ""},
                         evidence={"artifact": "见 P-root"}),
                      _e("S-raw", content={"c": "自有证据件", "a": "", "d": ""},
                         evidence={"artifact": "generation:own.png"})]:
                s.add(e, actor="ai:test")                # 保持 draft
            seed = os.path.join(tmp, "seed.json")
            s.save(seed)
            p = ah.propose("P-root", seed)
            r = ah.apply(p, actor="human:test", prereg="判据@v1")
            self.assertTrue(r["executed"])
            self.assertIn("S-cite", r["retracted"])
            self.assertNotIn("S-raw", r["retracted"])    # raw 红线：有自有证据不动
            store = PrecedentStore.load(seed)
            self.assertTrue(store._get("S-cite").get("machine_retracted"))
            self.assertFalse(store._get("S-raw").get("machine_retracted"))


class TestTriggers(unittest.TestCase):
    def test_shape_and_readouts(self):
        st = ah.trigger_status()
        self.assertEqual({k for k in st if k.startswith("T")}, {"T1", "T2", "T3", "T4"})
        for k in ("T1", "T2", "T3", "T4"):
            self.assertIn("met", st[k])
            self.assertIn("current", st[k])
            self.assertIn("need", st[k])
        # 与物证计数一致（不猜）：标本数 = specimens() 长度
        store = PrecedentStore.load(ah.DEFAULT_STORE)
        n_spec = len(rf.specimens(store, None))
        self.assertEqual(st["T2"]["current"]["specimens"], n_spec)


class TestShadowLoop(unittest.TestCase):
    """影子环路：只算不动手；只挑'证据全靠引用'的在役草案；off 零写盘。"""

    def _store(self, tmp):
        def _mk(eid, **kw):
            d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
                 "type": "procedural", "importance": 3,
                 "content": {"c": eid, "a": "", "d": ""}, "keywords": [], "evidence": {}}
            d.update(kw)
            return d
        s = PrecedentStore([])
        for e in [
            _mk("P-wrong-root", evidence={"artifact": "generation:r.png"},
                facts={"specimen": True, "specimen_note": "判错退场"}),
            _mk("S-cite-only-aa11", content={"c": "依据 P-wrong-root 的结论", "a": "", "d": ""},
                evidence={"artifact": "见 P-wrong-root"}),           # 应被下架
            _mk("S-has-own-bb22", content={"c": "参考 P-wrong-root，但自有实测", "a": "", "d": ""},
                evidence={"artifact": "generation:own.png"}),        # 红线：不动
            _mk("S-unrelated-cc33", content={"c": "与错根无关", "a": "", "d": ""},
                evidence={"artifact": "generation:u.png"}),          # 不应出现
        ]:
            s.add(e, actor="ai:test")
        s.deprecate("P-wrong-root", actor="human:test", reason="判错")
        s.tombstone("P-wrong-root", actor="human:test", reason="判错")
        path = os.path.join(tmp, "seed.json")
        s.save(path)
        return path

    def test_shadow_lists_only_citation_only_and_never_writes(self):
        """shadow 模式=只看不动（默认已改 on，故此处显式指定 shadow）。"""
        import auto_heal as ah2
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._store(tmp)
            log = os.path.join(tmp, "shadow.jsonl")
            before = open(seed, encoding="utf-8").read()
            r = ah2.shadow_scan(seed, log, mode="shadow")
            self.assertEqual(r["roots"], 1)
            self.assertEqual(r["would_retract"], ["S-cite-only-aa11"])   # 只挑纯引用件
            self.assertEqual(open(seed, encoding="utf-8").read(), before)  # 不动库
            lines = [json.loads(x) for x in open(log, encoding="utf-8") if x.strip()]
            self.assertEqual(lines[0]["kind"], "auto_heal_shadow")
            self.assertEqual(ah2.shadow_stats(log)["runs"], 1)

    def test_shadow_off_is_noop(self):
        import auto_heal as ah2
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._store(tmp)
            log = os.path.join(tmp, "shadow.jsonl")
            r = ah2.shadow_scan(seed, log, mode="off")
            self.assertEqual(r["roots"], 0)
            self.assertFalse(os.path.isfile(log))


class TestLoopOnMode(unittest.TestCase):
    """on 模式真动作：纯引用→retract+flag；派生根→只 flag；raw→不动；标本→跳过；可逆。"""

    def _fixture(self, tmp):
        def _mk(eid, **kw):
            d = {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
                 "type": "procedural", "importance": 3,
                 "content": {"c": eid, "a": "", "d": ""}, "keywords": [], "evidence": {}}
            d.update(kw)
            return d
        s = PrecedentStore([])
        for e in [
            _mk("P-bad-root", evidence={"artifact": "generation:r.png"},
                facts={"specimen": True, "specimen_note": "判错退场"}),
            _mk("S-cite-aa11", content={"c": "依据 P-bad-root", "a": "", "d": ""},
                evidence={"artifact": "见 P-bad-root"}),                 # → retract+flag
            _mk("S-derived-bb22", content={"c": "见 P-bad-root（挖掘产物）", "a": "", "d": ""},
                evidence={"artifact": "style_mine_out/x.json 见 P-bad-root"}),  # → 只 flag
            _mk("S-own-cc33", content={"c": "参考 P-bad-root 但自有实测", "a": "", "d": ""},
                evidence={"artifact": "generation:own.png"}),            # → 不动
            _mk("S-spec-dd44", content={"c": "见 P-bad-root", "a": "", "d": ""},
                evidence={"artifact": "见 P-bad-root"},
                facts={"specimen": True, "specimen_note": "标本"}),      # → 跳过（不再降权）
        ]:
            s.add(e, actor="ai:test")
        s.deprecate("P-bad-root", actor="human:test", reason="判错")
        s.tombstone("P-bad-root", actor="human:test", reason="判错")
        path = os.path.join(tmp, "seed.json")
        s.save(path)
        return path

    def test_on_acts_and_is_reversible(self):
        import auto_heal as ah2
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._fixture(tmp)
            log = os.path.join(tmp, "s.jsonl")
            r = ah2.shadow_scan(seed, log, mode="on")
            acted = {x["id"]: x["action"] for x in r["acted"]}
            self.assertEqual(acted.get("S-cite-aa11"), "retract+flag")     # 纯引用→下架+标
            self.assertEqual(acted.get("S-derived-bb22"), "flag")          # 派生根→只标
            self.assertNotIn("S-own-cc33", acted)                          # raw 不动（红线）
            self.assertNotIn("S-spec-dd44", acted)                         # 标本跳过
            s = PrecedentStore.load(seed)
            self.assertTrue(s._get("S-cite-aa11").get("machine_retracted"))
            self.assertTrue((s._get("S-derived-bb22").get("facts") or {}).get("auto_derate"))
            self.assertFalse(s._get("S-own-cc33").get("machine_retracted"))
            ev = [e.get("kind") for e in s.gov_events]
            self.assertIn("retract", ev)                                   # 下架事件入账
            s.relist("S-cite-aa11", actor="human:test", reason="复核误伤")   # 可逆：人签复架
            self.assertFalse(s._get("S-cite-aa11").get("machine_retracted"))

    def test_shadow_mode_still_no_action(self):
        import auto_heal as ah2
        with tempfile.TemporaryDirectory() as tmp:
            seed = self._fixture(tmp)
            r = ah2.shadow_scan(seed, os.path.join(tmp, "s.jsonl"), mode="shadow")
            self.assertEqual(r["acted"], [])
            self.assertTrue(r["would_retract"])
            self.assertFalse(PrecedentStore.load(seed)._get("S-cite-aa11").get("machine_retracted"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
