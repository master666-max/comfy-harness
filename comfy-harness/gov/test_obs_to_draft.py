# -*- coding: utf-8 -*-
"""test_obs_to_draft.py — 观察流铸判器红绿测试（够格闸/幂等/写回/开关）"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obs_to_draft as od      # noqa: E402


def _ledger(dirpath, rows, name="test_obs.jsonl"):
    p = os.path.join(dirpath, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


class TestMint(unittest.TestCase):
    def _fixture_rows(self):
        return [
            {"类": "增益", "现象": "干净链修复把倒影鬼影重绘成镜像构图",
             "条件": "M_dz@0.7+--detailer-clean 湿地商店街", "证据": "_hand_candid07c.png",
             "对照": True, "可复算": "cinematic_gen.py --detailer-clean 同种子"},
            {"类": "减损", "现象": "风格LoRA的blur训练DNA把指缘糊掉",
             "条件": "M_dz@1.0 持物构图", "证据": "_hand_candid_26100761.png",
             "对照": True, "可复算": "同种子去LoRA对照已做"},
            {"类": "增益", "现象": "已经铸过的观察", "条件": "x", "证据": "e",
             "对照": True, "可复算": "y", "minted": "P-obs-already-aaaaaaaa"},
            {"类": "异常", "现象": "无法解释的怪象", "条件": "?", "证据": "e",
             "对照": False, "可复算": ""},
            {"类": "增益", "现象": "没有对照的宣称", "条件": "x", "证据": "e",
             "对照": False, "可复算": "z"},
        ]

    def _run(self, tmp, rows=None):
        from precedent_gov import PrecedentStore
        seed = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "precedents_e2_seed.json")
        shutil.copy(seed, os.path.join(tmp, "seed.json"))
        _ledger(tmp, rows if rows is not None else self._fixture_rows())
        store = PrecedentStore.load(os.path.join(tmp, "seed.json"))
        rows_loaded = od.load_ledgers(tmp)
        r1 = od.mint(rows_loaded, store, dry=False)
        store.save(os.path.join(tmp, "seed.json"))
        od.writeback(rows_loaded)
        store2 = PrecedentStore.load(os.path.join(tmp, "seed.json"))
        rows2 = od.load_ledgers(tmp)
        r2 = od.mint(rows2, store2, dry=False)
        return r1, r2

    def test_mint_qualifying_only(self):
        with tempfile.TemporaryDirectory() as td:
            r1, r2 = self._run(td)
            self.assertEqual(len(r1["minted"]), 2)          # 增益+减损，够格
            kinds = {m["kind"] for m in r1["minted"]}
            self.assertTrue(kinds and kinds <= {"pipeline", "postproc", "style"})
            # 20261010 白名单扩容后：已铸1 + 无对照增益1 + 无对照异常1 = 3 条进 skipped
            #（类不再静默拦截——证据闸才是机制门，见 obs_to_draft docstring）
            self.assertEqual(len(r1["skipped"]), 3)

    def test_idempotent_second_run(self):
        with tempfile.TemporaryDirectory() as td:
            r1, r2 = self._run(td)
            self.assertEqual(len(r2["minted"]), 0)          # 双闸：minted 写回+库内签名
            # run2 跳过=两条本轮铸的(写回minted)+既有minted1+无对照2（含异常行）
            self.assertEqual(len(r2["skipped"]), 5)

    def test_sentinel_minted_zero_not_counted(self):
        # 20261010 毒标修复：--minted=0 误用（'0' 为 truthy）曾伪装已铸——哨兵视为未铸
        with tempfile.TemporaryDirectory() as td:
            from precedent_gov import PrecedentStore
            seed = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "precedents_e2_seed.json")
            shutil.copy(seed, os.path.join(td, "seed.json"))
            rows = [
                {"类": "配方", "现象": "配方类条目在扩容后可铸",
                 "条件": "同种子四臂", "证据": "o.png",
                 "对照": True, "可复算": "py x.py", "minted": "0",
                 "env": {"ckpt": "NoobAI-XL-Vpred-v1.0.safetensors",
                         "zsnr_default": True}},   # L1 指纹随行入 facts（须已登记，否则 DENY:PLANE_UNKNOWN）
                {"类": "复审", "现象": "复审类条目带毒标同样可铸",
                 "条件": "翻倒前提", "证据": "t.png",
                 "对照": True, "可复算": "py y.py", "minted": 0},
            ]
            _ledger(td, rows)
            store = PrecedentStore.load(os.path.join(td, "seed.json"))
            loaded = od.load_ledgers(td)
            r = od.mint(loaded, store, dry=False)
            self.assertEqual(len(r["minted"]), 2)           # 两条毒标行都铸
            self.assertEqual(len(r["skipped"]), 0)
            got = store._get(r["minted"][0]["id"])
            self.assertEqual(got["facts"]["env"]["zsnr_default"], True)  # 指纹进 facts

    def test_writeback_marks_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            self._run(td)
            p = os.path.join(td, "test_obs.jsonl")
            lines = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
            minted_flags = [l.get("minted") for l in lines[:2]]
            self.assertTrue(all(minted_flags))              # 前两条已写回 minted

    def test_switch(self):
        self.assertTrue(od.is_disabled(env="off"))
        self.assertTrue(od.is_disabled(env="0"))
        self.assertTrue(od.is_disabled(cli_off=True, env=""))
        self.assertFalse(od.is_disabled(env="on"))
        self.assertFalse(od.is_disabled(env=""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
