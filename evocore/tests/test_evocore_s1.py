# -*- coding: utf-8 -*-
"""test_evocore_s1.py — S1 验收测试（包内可测面；层1/层3 机械验收见 tools/S1_verify_*.py）

守不变量：
  ① 版本与 SPEC 声明在位（0.1.0 · SPEC-内核接口与宿主契约-v1）；
  ② __all__ 全部可解析且可调用面为 callable；
  ③ 零依赖隔离：四源件无任何绝对导入（只许 stdlib 与包内相对导入）；
  ④ 行为钉：公开面确定性输出（S1 平移零语义变更的包内锚）。
"""
import ast
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from evocore import (DEFAULTS, Tunables, adjudicate_conflict, adjudicate_merge,   # noqa: E402
                     adjudicate_promote, attic, decay_multiplier, promote, retrieve, route, score, tombstone, touch)

import evocore  # noqa: E402

NOW = datetime.datetime(2026, 9, 21, 12, 0, 0)
_SRC = ("__init__.py", "tunables.py", "retrieval.py", "lifecycle.py", "decision.py", "entry.py",
        "project.py")
_STDLIB = {"__future__", "dataclasses", "datetime", "re", "sys", "os", "json", "hashlib",
           "math", "typing", "enum", "collections", "itertools", "functools", "copy", "abc"}


def entry(**kw):
    base = {"id": "e1", "content": "用户偏好深色主题", "keywords": ["偏好"],
            "importance": 5, "created_at": "2026-09-20T00:00:00", "type": "semantic",
            "state": "intermediate"}
    base.update(kw)
    return base


class TestS1Surface(unittest.TestCase):
    def test_version_and_spec(self):
        """不变量①：版本与 SPEC 声明在位。"""
        self.assertEqual(evocore.__version__, "0.6.2")   # 0.6.2=supersede 接线（0.6.1=v3 写侧分发）
        self.assertEqual(evocore.SPEC, "SPEC-内核接口与宿主契约-v1")

    def test_all_names_resolve(self):
        """不变量②：__all__ 每名可在包上解析；函数名为 callable、常量非 None。"""
        for name in evocore.__all__:
            self.assertTrue(hasattr(evocore, name), name)
        for name in evocore.__all__:
            if name not in ("__version__", "SPEC", "Tunables", "DEFAULTS", "TYPES",
                            "OVERRIDE_KIND", "SLIM_MARK_KIND"):   # kind 名字符串常量（非 callable）
                self.assertTrue(callable(getattr(evocore, name)), name)
        self.assertIsInstance(DEFAULTS, Tunables)

    def test_zero_dependency_absolute_imports(self):
        """不变量③：四源件零包外依赖（stdlib 放行；相对导入=包内，放行）。"""
        here = os.path.dirname(os.path.abspath(__file__))
        pkg = os.path.normpath(os.path.join(here, ".."))
        violations = []
        for fn in _SRC:
            with open(os.path.join(pkg, fn), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.split(".")[0] not in _STDLIB:
                            violations.append(f"{fn}:{node.lineno} import {a.name}")
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    if node.module.split(".")[0] not in _STDLIB:
                        violations.append(f"{fn}:{node.lineno} from {node.module} import …")
        self.assertEqual(violations, [], f"包外依赖违例：{violations}")


class TestS1BehaviorPins(unittest.TestCase):
    def test_score_pin(self):
        """不变量④a：五参数打分钉值（filter_zero 生效面 + 类型衰减 + last_used 起算）。"""
        self.assertEqual(score(entry(), "偏好", DEFAULTS, NOW), 5.391)

    def test_route_and_decay_pins(self):
        """不变量④b：三态路由阈值边界 + 类型衰减乘数（procedural 零衰减）。"""
        self.assertEqual(route(entry(importance=7)), "longterm")
        self.assertEqual(route(entry(importance=6)), "intermediate")
        self.assertEqual(decay_multiplier(entry(type="episodic")), 2.0)
        self.assertEqual(decay_multiplier(entry(type="procedural")), 0.0)
        self.assertEqual(decay_multiplier(entry(type="未知型")), 1.0)

    def test_retrieve_tiebreak_and_tombstone(self):
        """不变量④c：同分平局按 id 破序（确定性）；墓碑退出检索。"""
        a = entry(id="a1", content="偏好", created_at="2026-09-21T12:00:00")
        b = entry(id="b1", content="偏好", created_at="2026-09-21T12:00:00")
        got = retrieve([b, a], "偏好", k=5, now=NOW)
        self.assertEqual([e["id"] for _, e in got], ["a1", "b1"])
        dead = entry(id="d1", content="偏好")
        tombstone(dead)
        self.assertEqual(score(dead, "偏好", DEFAULTS, NOW), 0.0)

    def test_decision_pins(self):
        """不变量④d：三 intent——conflict manual 优先 / merge 恒 defer / promote 阈值。
        （返回形态：conflict=三元组 / merge=单留痕 dict / promote=二元组——S1 平移原样。）"""
        old = entry(id="old", importance=9, created_at="2026-01-01T00:00:00")
        new = entry(id="new", importance=9, created_at="2026-09-21T00:00:00")
        man = entry(id="man", importance=1, created_at="2026-01-01T00:00:00", source="manual")
        _, win, _ = adjudicate_conflict([old, new, man])
        self.assertEqual(win["id"], "man")
        tr = adjudicate_merge([entry(id="x"), entry(id="y")])
        self.assertEqual(tr["decision"], "defer")
        _, out = adjudicate_promote([entry(id="p7", importance=7), entry(id="p6", importance=6)])
        self.assertEqual([ok for _, ok in out], [True, False])

    def test_touch_and_promote_side_effects(self):
        """不变量④e：touch 刷 last_used_at；attic 后禁直接晋升（公理 F 守卫）。"""
        e = entry()
        touch(e, "2026-09-21T00:00:00")
        self.assertEqual(e["last_used_at"], "2026-09-21T00:00:00")
        a = entry(id="a9")
        ev = attic(a, "降权理由")
        self.assertEqual((a["state"], ev["kind"]), ("attic", "attic_nomination"))
        with self.assertRaises(ValueError):
            promote(a)

    def test_bad_ts_degrades_pinned(self):
        """不变量④g（S1v2/T3 钉桩 · 登记 D1 → 20261003 语义变更）：坏时间戳=100 年龄降权。
        语义变更依据=四项目审计 P2-2（治理位七批令）：原 v3.9 的 age=0 使坏 ts 条目**置顶**
        （检索污染面：age=0 优于一切真实条目）；修复后 age=36500 → 分数深负（降权到底）。
        精确读数钉死=-3644.459（新语义，按本测夹具 NOW/entry 取值）；与融合形态（evo_seat 同日同款修复）的分歧已由
        conformance §对拍.2 钉死统一。改语义必先改此测试（登记触发器同步=本次审计修复批二）。"""
        self.assertEqual(score(entry(created_at="not-a-date"), "偏好", DEFAULTS, NOW), -3644.459)

    def test_tunables_construction_guard(self):
        """不变量④f：Tunables 构造期非法值拒（w_kw<=0 / filter_zero=2）。"""
        with self.assertRaises(ValueError):
            Tunables(w_kw=0.0)
        with self.assertRaises(ValueError):
            Tunables(filter_zero=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
