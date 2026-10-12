# -*- coding: utf-8 -*-
"""test_premises.py — 前提依赖登记·翻倒传播·重审队列 红绿（20261009 vp1 冤案根治）

判据先锁（对根治承诺的可测化）：
  ① 指纹：capture_env 双层（签名缺省+主题簿正则计数）；env 自动随 obs/草稿入账
  ② 翻倒：watched 值变 = 翻倒事件 → 依赖枚举 → 自动出票（确定性传播，可注入测试）
  ③ 机会主义：match 关键词命中 → 搭车匹配；mark_retried/close 状态机
  ④ 回填：存量无指纹件显式登记；翻倒前提下回填立即出票
  ⑤ lint：教义句无指针 = 违规；挂条目id/obs账本/票号 = 通过
  ⑥ 隔离：全部走 tmp 路径（生产件在 conftest WATCH 哨兵名单上）
"""
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", "field"))
import premises as pm          # noqa: E402


def _seed_store(path: str, entries: list) -> None:
    json.dump({"entries": entries}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False)


class TestPremises(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pp = os.path.join(self.tmp.name, "premises.json")
        self.qp = os.path.join(self.tmp.name, "queue.json")
        self.sp = os.path.join(self.tmp.name, "store.json")
        _seed_store(self.sp, [])
        # 隔离：依赖枚举绝不扫生产 obs（20261009 实锤——生产 env 行漏进测试）
        self._obs_dirs = pm.OBS_DIRS
        self.obsd = os.path.join(self.tmp.name, "obs")
        os.makedirs(self.obsd)
        pm.OBS_DIRS = [self.obsd]

    def tearDown(self):
        pm.OBS_DIRS = self._obs_dirs
        self.tmp.cleanup()

    def test_flip_enumerates_dependents_and_enqueues(self):
        # 判据②：翻倒 → 依赖枚举 → 出票。注入：两条带 env 的记录 + 一条无关的
        rows = [
            {"类": "减损", "现象": "vp1@0.8 多指姿势糊指", "env": {"zsnr_default": True}},
            {"类": "增益", "现象": "无关条目", "env": {"zsnr_default": False}},
        ]
        for i, r in enumerate(rows):
            with open(os.path.join(self.obsd, f"t{i}_obs.jsonl"), "w",
                      encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _seed_store(self.sp, [{"id": "P-entry-old", "gov": "draft",
                               "facts": {"env": {"zsnr_default": True}},
                               "content": {"c": "旧前提下结论"}}])
        reg, q = pm.load(self.pp), pm.load_queue(self.qp)
        # 首见 True（登记基线，无翻倒）
        r1 = pm.observe_env({"zsnr_default": True}, reg, q, self.pp,
                            self.qp, self.sp)
        self.assertEqual(len(r1["flips"]), 0)
        # 值变 True→False = 翻倒 → 恰好 2 个依赖出票，无关条目不入
        r2 = pm.observe_env({"zsnr_default": False}, reg, q, self.pp,
                            self.qp, self.sp)
        self.assertEqual(len(r2["flips"]), 1)
        self.assertEqual(r2["flips"][0]["key"], "zsnr_default")
        pend = [t for t in q["tickets"] if t["status"] == "pending"]
        self.assertEqual(len(pend), 2)
        refs = {t["target"]["ref"] for t in pend}
        self.assertIn("t0_obs.jsonl:1", refs)
        self.assertIn("P-entry-old", refs)
        self.assertNotIn("P-nope", refs)
        # 去重：同前提同目标不重复出票
        r3 = pm.observe_env({"zsnr_default": False}, reg, q, self.pp,
                            self.qp, self.sp)
        self.assertEqual(len(r3["flips"]), 0)
        self.assertEqual(len([t for t in q["tickets"]
                              if t["status"] == "pending"]), 2)

    def test_backfill_then_flip_tickets_retro_targets(self):
        # 判据④：存量回填 → 翻倒 → 回填目标出票（vp1 案的机制化重演）
        reg, q = pm.load(self.pp), pm.load_queue(self.qp)
        tg = [("entry", "P-old-a"), ("entry", "P-old-b")]
        pm.backfill("zsnr_default", True, tg, ref="P-obs-zsnr",
                    note="r时代条目", reg=reg, q=q, premises_path=self.pp,
                    queue_path=self.qp, store_path=self.sp)
        self.assertEqual(len([t for t in q["tickets"]]), 0)   # 未翻倒先不出票
        pm.declare_flip("zsnr_default", True, False, ref="P-obs-zsnr",
                        reg=reg, q=q, premises_path=self.pp,
                        queue_path=self.qp, store_path=self.sp)
        pend = [t for t in q["tickets"] if t["status"] == "pending"]
        self.assertEqual({t["target"]["ref"] for t in pend},
                         {"P-old-a", "P-old-b"})

    def test_close_lifecycle_and_states(self):
        # 判据③：状态机 pending→retried→closed-overturn；close 后依赖枚举仍完整
        reg, q = pm.load(self.pp), pm.load_queue(self.qp)
        pm.backfill("zsnr_default", True, [("entry", "P-old-a")], ref="R",
                    reg=reg, q=q, premises_path=self.pp, queue_path=self.qp,
                    store_path=self.sp)
        pm.declare_flip("zsnr_default", True, False, ref="R", reg=reg, q=q,
                        premises_path=self.pp, queue_path=self.qp,
                        store_path=self.sp)
        t = q["tickets"][0]
        pm.mark_retried(q=q, queue_path=self.qp, tid=t["id"],
                        artifact="out/retrial_T001_1.png", seed=26100901)
        self.assertEqual(q["tickets"][0]["status"], "retried")
        pm.close(q, t["id"], "overturn", artifact="out/x.png", note="六臂重试平反")
        self.assertEqual(q["tickets"][0]["status"], "closed-overturn")
        # 重复 close 拒绝
        with self.assertRaises(AssertionError):
            pm.close(q, t["id"], "confirm")

    def test_piggyback_match(self):
        # 判据③：match 关键词命中才搭车（ vp1 票 vs 无关批次上下文）
        q = pm.load_queue(self.qp)
        t = pm.enqueue(q, {"kind": "entry", "ref": "P-x"}, "zsnr_default=true",
                       "zsnr_default=false", claim="糊指",
                       suspect={"lora": "NOOB_vp1.safetensors",
                                "lora_weight": 0.8},
                       match=["vp1"])
        self.assertIsNotNone(t)
        self.assertEqual(pm.piggyback_matches("主题: miku 深海少女", q), [])
        self.assertEqual(len(pm.piggyback_matches("使用 vp1 detailer 风格", q)), 1)

    def test_lint_doctrine_without_pointer_fails_with_pointer_passes(self):
        # 判据⑤：教义句无指针=违规；挂条目id/obs账本/票号=通过
        self.assertTrue(pm.lint_file("x", "无LoRA是实测结论"))       # 无指针
        self.assertFalse(pm.lint_file("x", "无LoRA结论见 ronfem_obs.jsonl"))
        self.assertFalse(pm.lint_file("x", "vp1平反见 T-001"))
        self.assertFalse(pm.lint_file("x", "M_dz胜出（P-obs-vp1-0-8-902）"))
        # 非论断句不触发
        self.assertFalse(pm.lint_file("x", "今天是晴天"))

    def test_capture_env_double_layer(self):
        # 判据①：双层指纹——签名缺省 + 主题簿正则计数（zsnr 翻案教训：只抓声明值漏翻转）
        from cinematic_gen import capture_env
        env = capture_env()
        self.assertIn("zsnr_default", env)
        self.assertIn("themes_any_zsnr_false", env)
        self.assertIn("themes_any_bislerp", env)
        self.assertIsInstance(env["themes_n"], int)


if __name__ == "__main__":
    unittest.main(verbosity=2)
