# -*- coding: utf-8 -*-
"""test_recipe_base.py — 配方基座继承制红绿测试（20261010 裁决④）"""
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))
import cinematic_gen as cg                            # noqa: E402

BASE_ARGS = {"upscale_method": "bislerp", "zsnr": False}
# 迁移五卡（继承基座=行为变更的目的地）；ron 两档钉住值
LAGGING = {"candid_mame", "neon_night_rain", "rooftop_sunset",
           "sakura_jk", "sakura_jk_official"}
RON_FALSE = {f"ron_fem_r{i}" for i in range(5, 12)}
RON_ALL = ({f"ron_fem_r{i}" for i in range(1, 12)}
           | {"ron_fem", "ron_fem_e3", "ron_fem_f4",
              "ron_fem_v2", "ron_fem_v3", "ron_fem_v4", "ron_fem_v5"})


class TestBaseFile(unittest.TestCase):
    def test_shape_and_signature(self):
        b = cg.load_recipe_base()
        self.assertIsInstance(b, dict)
        self.assertIsInstance(b["version"], int)
        self.assertGreaterEqual(b["version"], 1)
        self.assertTrue(str(b.get("human_signed", "")).startswith("human:"),
                        "基座升版=人签：human_signed 必须在案")
        self.assertEqual(b["args"], BASE_ARGS)

    def test_bad_base_loud(self):
        """基座文件损坏=响亮拒启（fail-closed，不静默吞）。"""
        orig = cg.RECIPE_BASE_PATH
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{broken")
            p = fh.name
        cg.RECIPE_BASE_PATH = p
        try:
            with self.assertRaises(SystemExit):
                cg.load_recipe_base()
        finally:
            cg.RECIPE_BASE_PATH = orig
            os.unlink(p)

    def test_missing_base_is_none(self):
        orig = cg.RECIPE_BASE_PATH
        cg.RECIPE_BASE_PATH = os.path.join(tempfile.gettempdir(),
                                           "no_such_recipe_base_xyz.json")
        try:
            self.assertIsNone(cg.load_recipe_base())
        finally:
            cg.RECIPE_BASE_PATH = orig

    def test_capture_env_stamps_version(self):
        env = cg.capture_env()
        self.assertEqual(env.get("recipe_base_version"), 1)
        self.assertTrue(env.get("recipe_base_sha"))


class TestResolveRegime(unittest.TestCase):
    def test_priority_cli_over_theme_over_base_over_default(self):
        th = {"zsnr": True, "upscale_method": "nearest-exact"}
        self.assertEqual(cg.resolve_regime(th, BASE_ARGS), (True, "nearest-exact"))
        self.assertEqual(cg.resolve_regime({}, BASE_ARGS), (False, "bislerp"))
        self.assertEqual(cg.resolve_regime({}, {}), (True, "nearest-exact"))
        self.assertEqual(cg.resolve_regime({}, BASE_ARGS, no_zsnr=True),
                         (False, "bislerp"))
        self.assertEqual(cg.resolve_regime({"zsnr": True}, BASE_ARGS,
                                           cli_upscale="bislerp"),
                         (True, "bislerp"))
        self.assertEqual(cg.resolve_regime({"zsnr": False}, {}), (False, "nearest-exact"))


class TestMigrationInvariants(unittest.TestCase):
    """迁移后全库有效体制盘点：5 卡变更（目的地=基座），其余零变化。"""

    def setUp(self):
        self.themes = json.load(open(cg.THEMES_PATH, encoding="utf-8"))

    def _regime(self, name):
        return cg.resolve_regime(self.themes[name], BASE_ARGS)

    def test_lagging_five_now_inherit_base(self):
        for n in LAGGING:
            self.assertNotIn("zsnr", self.themes[n], f"{n} 应无显式拷贝")
            self.assertEqual(self._regime(n), (False, "bislerp"), n)

    def test_ron_arms_pinned_unchanged(self):
        for n in RON_ALL:
            c = self.themes[n]
            self.assertIn("override_reason", c, f"{n} 缺钉住理由")
            self.assertEqual(c["upscale_method"], "nearest-exact", n)
            want = False if n in RON_FALSE else True
            self.assertIs(c["zsnr"], want, n)
            self.assertEqual(self._regime(n), (want, "nearest-exact"), n)

    def test_copy_cards_dropped_and_inherit(self):
        for n in ("miku_deepsea", "st_water", "back_xmc", "handexp_ctl"):
            self.assertNotIn("zsnr", self.themes[n])
            self.assertNotIn("upscale_method", self.themes[n])
            self.assertEqual(self._regime(n), (False, "bislerp"), n)

    def test_bfl_cards_untouched(self):
        for n in ("bfl_coast", "bfl_sentinel_tree"):
            self.assertEqual(self.themes[n].get("backend"), "klein")
            self.assertNotIn("zsnr", self.themes[n])
            self.assertNotIn("upscale_method", self.themes[n])

    def test_premises_watches_base_version(self):
        import premises as pm
        self.assertIn("recipe_base_version", pm.DEFAULT_WATCHED)
        p = json.load(open(pm.DEFAULT_PREMISES, encoding="utf-8"))
        self.assertIn("recipe_base_version", p.get("watched", []),
                      "存量 premises.json 自带 watched——迁移须补键")


if __name__ == "__main__":
    unittest.main()
