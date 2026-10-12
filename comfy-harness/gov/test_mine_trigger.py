# -*- coding: utf-8 -*-
"""test_mine_trigger.py — 挖掘到期触发器红绿测试（宽限初快照/到期判定/mark顺延/阈值）"""
import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "comfy-harness", "gov"))


class TestMineTrigger(unittest.TestCase):
    def setUp(self):
        self._old = {k: os.environ.get(k) for k in ("Z_REPO", "COMFY_OUTPUT_DIR")}
        self.tmp = tempfile.TemporaryDirectory()
        repo = os.path.join(self.tmp.name, "repo")
        self.out = os.path.join(self.tmp.name, "comfy_out")
        os.makedirs(os.path.join(repo, "comfy-harness", "field", "out"))
        os.makedirs(os.path.join(repo, "comfy-harness", "gov"))
        os.makedirs(self.out)
        with open(os.path.join(repo, "comfy-harness", "gov", "precedents_e2_seed.json"),
                  "w", encoding="utf-8") as f:
            f.write('{"entries": [{"id": "a"}, {"id": "b"}]}')
        self.repo = repo
        self.obs = os.path.join(repo, "comfy-harness", "field", "out", "t_obs.jsonl")
        with open(self.obs, "w", encoding="utf-8") as f:
            f.write('{"类":"无"}\n')
        os.environ["Z_REPO"] = repo
        os.environ["COMFY_OUTPUT_DIR"] = self.out
        import mine_trigger
        self.mt = importlib.reload(mine_trigger)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def _add(self, n_png=0, n_obs=0):
        for i in range(n_png):
            open(os.path.join(self.out, f"x{i}.png"), "wb").write(b"p")
        with open(self.obs, "a", encoding="utf-8") as f:
            for _ in range(n_obs):
                f.write('{"类":"增益"}\n')

    def test_grace_init_then_due_then_mark(self):
        self.assertEqual(self.mt.main(["check"]), 0)          # 无状态 → 宽限建快照
        self.assertTrue(os.path.isfile(self.mt.STATE))
        self.assertEqual(self.mt.main(["check"]), 0)          # 刚建快照 → 未到期
        self._add(n_png=4, n_obs=4)                           # Δ=8 ≥ 默认阈值8
        self.assertEqual(self.mt.main(["check"]), 1)          # 到期！
        self.assertEqual(self.mt.main(["mark"]), 0)           # 顺延
        self.assertEqual(self.mt.main(["check"]), 0)          # mark 后未到期

    def test_threshold_override(self):
        self.mt.main(["check"])                               # 宽限
        self._add(n_png=2, n_obs=1)                           # Δ=3
        self.assertEqual(self.mt.main(["check", "--threshold", "3"]), 1)
        self.assertEqual(self.mt.main(["check", "--threshold", "10"]), 0)

    def test_shrink_clamped_no_negative(self):
        self.mt.main(["check"])
        self._add(n_png=5, n_obs=0)
        self.assertEqual(self.mt.main(["check"]), 0)          # Δ=5 < 8
        os.remove(os.path.join(self.out, "x0.png"))           # 产物被清 → 不产生负债
        self.assertEqual(self.mt.main(["check"]), 0)          # 仍 0（clamp）


if __name__ == "__main__":
    unittest.main(verbosity=2)
