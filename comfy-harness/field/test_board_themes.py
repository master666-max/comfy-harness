# -*- coding: utf-8 -*-
"""test_board_themes.py — 预览板与主题库红绿测试（field 注意力优化批）"""
import argparse
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))          # 仓根（z.py 不导入，仅占位一致性）
import board as bd                                   # noqa: E402
import cinematic_gen as cg                           # noqa: E402


class TestThemes(unittest.TestCase):
    def test_load_known(self):
        th = cg.load_theme("candid_mame")
        self.assertIn("M_dz", th["lora"])
        self.assertEqual(th["lora_weight"], 0.7)
        self.assertNotIn("detailer_clean", th)          # 20261008 维护者裁：干净链已撤

    def test_load_unknown_rejects(self):
        with self.assertRaises(SystemExit):
            cg.load_theme("不存在的主题")

    def test_resolve_stacked_default(self):
        args = argparse.Namespace(theme="candid_mame", pos=None, lora=None,
                                  lora_weight=None, neg=None)
        pos, neg, lora, w, skip = cg.resolve_args(args)
        self.assertIn("shopping street", pos)
        self.assertTrue(pos.startswith("masterpiece"))   # 堆叠档=QUALITY 打底
        self.assertEqual(neg, cg.NEG_DEFAULT)             # 堆叠档负词
        self.assertFalse(skip)                            # 堆叠档不挂 skip
        args2 = argparse.Namespace(theme="candid_mame", pos="1girl, solo",
                                   lora="OTHER.safetensors", lora_weight=0.5, neg=None)
        _, neg2, lora2, w2, _ = cg.resolve_args(args2)    # 显式旗覆盖
        self.assertEqual(lora2, "OTHER.safetensors")
        self.assertEqual(w2, 0.5)

    def test_resolve_theme_neg_now_honored(self):
        # 20261009 红绿：主题 neg 此前被静默无视（resolve_args 只认 CLI 旗）——
        # 修复后主题负词生效，CLI 旗仍最高
        args = argparse.Namespace(theme="ron_fem_r11", pos=None, lora=None,
                                  lora_weight=None, neg=None)
        _, neg, _, _, _ = cg.resolve_args(args)
        self.assertIn("spiral eyes", neg)                 # 主题负词真生效
        args2 = argparse.Namespace(theme="ron_fem_r11", pos=None, lora=None,
                                   lora_weight=None, neg="custom_neg_word")
        _, neg2, _, _, _ = cg.resolve_args(args2)
        self.assertEqual(neg2, "custom_neg_word")         # CLI 旗仍压过主题

    def test_graph_upscale_method(self):
        # 20261009 红绿：像素化根源=LatentUpscale nearest-exact（潜单元 8px 整块复制）
        # ——graph() 增 upscale_method 参；缺省=历史可复现，显式传参改节点13
        g = cg.graph(1, "1girl", "lowres", "t")
        self.assertEqual(g["13"]["inputs"]["upscale_method"], "nearest-exact")
        g2 = cg.graph(1, "1girl", "lowres", "t", upscale_method="bislerp")
        self.assertEqual(g2["13"]["inputs"]["upscale_method"], "bislerp")

    def test_graph_clip_skip_and_cnet(self):
        # 20261010 红绿×2：①clip_skip=True 必须建节点"0"（潜伏 bug：官方配方路
        # KeyError '0' 全体 400）②cnet 链完整且无 cnet 时零侵入
        g = cg.graph(1, "1girl", "lowres", "t", clip_skip=True)
        self.assertIn("26", g)                                   # CLIPSetLastLayers 在图（0 号非法）
        self.assertEqual(g["26"]["inputs"]["stop_at_clip_layer"], -2)
        self.assertEqual(g["4"]["inputs"]["clip"], ["26", 0])
        self.assertEqual(g["5"]["inputs"]["clip"], ["26", 0])
        g2 = cg.graph(1, "1girl", "lowres", "t", clip_skip=False,
                      cnet_model="openpose_pre.safetensors", cnet_image="p.png")
        self.assertNotIn("0", g2)
        for n in ("20", "23", "24"):
            self.assertIn(n, g2)                                 # cnet 链在图
        self.assertEqual(g2["7"]["inputs"]["positive"], ["24", 0])
        g3 = cg.graph(1, "1girl", "lowres", "t")
        self.assertEqual(g3["7"]["inputs"]["positive"], ["4", 0])  # 零侵入

    def test_resolve_official_recipe(self):
        th = cg.load_theme("sakura_jk_official")
        self.assertEqual(th["recipe"], "official")
        args = argparse.Namespace(theme="sakura_jk_official", pos=None, lora=None,
                                  lora_weight=None, neg=None)
        pos, neg, lora, w, skip = cg.resolve_args(args)
        self.assertTrue(pos.startswith("score_9"))        # 官方 score 系正向
        self.assertIn("masterpiece", neg)                 # masterpiece 入负（官方卡语义）
        self.assertNotIn("masterpiece, best quality", pos)
        self.assertTrue(skip)                             # official 档默认挂 skip 2

    def test_resolve_without_any_pos_rejects(self):
        args = argparse.Namespace(theme=None, pos=None, lora=None,
                                  lora_weight=None)
        with self.assertRaises(SystemExit):
            cg.resolve_args(args)


class TestBoard(unittest.TestCase):
    def test_build_grid(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            for i, c in enumerate(((200, 30, 30), (30, 200, 30),
                                   (30, 30, 200), (200, 200, 30))):
                Image.new("RGB", (620, 900), c).save(os.path.join(td, f"demo_x_{i}.png"))
            out, n = bd.build("demo_x", directory=td, cols=2, tile=300)
            self.assertEqual(n, 4)
            self.assertTrue(os.path.isfile(out))
            im = Image.open(out)
            self.assertEqual(im.width, 2 * 300 + 3 * 8)   # 边距公式
            im.close()

    def test_empty_prefix_rejects(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                bd.build("nope", directory=td)


if __name__ == "__main__":
    unittest.main(verbosity=2)
