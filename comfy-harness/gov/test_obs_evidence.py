# -*- coding: utf-8 -*-
"""test_obs_evidence.py — obs 证据分离纪律红绿测试（20261010 维护者令：19条全签+改进obs字段）

背景：19/20 P-obs 证据为散文形机器不可回源（实锤）。本件锁三段：
  ① z._ev_files：--ev-file → {files:[{name,path,sha256}]}（坏指针 DENY 拒写；相对路径对 field/out 解析）
  ② vetted_supply.evidence_state：dict.files 逐件核存在+sha256
  ③ obs_to_draft.mint：dict 证据 → artifact=干净路径串 + evidence.files(name+sha)，散文降级 note"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))     # 仓根（z.py）
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))     # repo root

import z                                        # noqa: E402
import vetted_supply as vs                      # noqa: E402
import obs_to_draft as od                       # noqa: E402
from precedent_gov import PrecedentStore        # noqa: E402


def _img(tmp, name, blob=b"\x89PNG-fixture"):
    p = os.path.join(tmp, name)
    open(p, "wb").write(blob)
    return p, hashlib.sha256(blob).hexdigest()


class TestEvFiles(unittest.TestCase):
    def test_ok_shape_and_sha(self):
        with tempfile.TemporaryDirectory() as td:
            p, sha = _img(td, "miku_a_001.png")
            ev = z._ev_files(os.path.abspath(p), "对照组", td)
            self.assertEqual(len(ev["files"]), 1)
            f = ev["files"][0]
            self.assertEqual(f["name"], "miku_a_001.png")
            self.assertEqual(f["sha256"], sha)
            self.assertTrue(os.path.isabs(f["path"]))
            self.assertEqual(ev["note"], "对照组")          # 散文降级为 note

    def test_relative_resolves_against_field_out(self):
        with tempfile.TemporaryDirectory() as td:
            p, sha = _img(td, "neon_01.png")
            ev = z._ev_files("neon_01.png", "", td)          # 相对名 → field/out 基座解析
            self.assertEqual(ev["files"][0]["sha256"], sha)

    def test_missing_pointer_denied(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit) as cm:
                z._ev_files("no_such_img.png", "", td)
            self.assertIn("DENY:EV_MISSING", str(cm.exception))

    def test_multi_separator_variants(self):
        with tempfile.TemporaryDirectory() as td:
            _img(td, "a.png")
            _img(td, "b.png")
            ev = z._ev_files("a.png, b.png", "", td)         # 逗号+空格
            self.assertEqual([f["name"] for f in ev["files"]], ["a.png", "b.png"])
            ev2 = z._ev_files("a.png；b.png", "", td)         # 全角分号
            self.assertEqual(len(ev2["files"]), 2)

    def test_multi_mixed_missing_denies(self):
        with tempfile.TemporaryDirectory() as td:
            _img(td, "a.png")
            with self.assertRaises(SystemExit) as cm:
                z._ev_files("a.png；missing.png", "", td)    # 一件缺失=整体拒写
            self.assertIn("DENY:EV_MISSING", str(cm.exception))


class TestEvidenceStateFiles(unittest.TestCase):
    def _ent(self, files):
        return {"id": "E-x", "evidence": {"files": files}}

    def test_ok_with_sha(self):
        with tempfile.TemporaryDirectory() as td:
            p, sha = _img(td, "v.png")
            ok, det = vs.evidence_state(
                self._ent([{"name": "v.png", "path": os.path.abspath(p), "sha256": sha}]),
                {"E-x"})
            self.assertTrue(ok, det)
            self.assertIn("sha核", det)

    def test_sha_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p, _ = _img(td, "v.png")
            ok, det = vs.evidence_state(
                self._ent([{"name": "v.png", "path": os.path.abspath(p),
                            "sha256": "0" * 64}]), {"E-x"})
            self.assertFalse(ok)
            self.assertIn("sha256 不符", det)

    def test_missing_fails(self):
        ok, det = vs.evidence_state(
            self._ent([{"name": "ghost.png", "path": r"D:\no\ghost.png",
                        "sha256": "x"}]), set())
        self.assertFalse(ok)
        self.assertIn("缺失", det)


class TestMintDictEvidence(unittest.TestCase):
    @staticmethod
    def _wrap(rec, td):
        return {"path": os.path.join(td, "x_obs.jsonl"), "rec": rec}

    def test_dict_evidence_maps_clean(self):
        with tempfile.TemporaryDirectory() as td:
            p1, sha1 = _img(td, "m1.png")
            p2, sha2 = _img(td, "m2.png")
            rec = {"类": "增益", "现象": "证据分离后的观察铸条",
                   "条件": "tmp", "对照": True, "可复算": "同种子重跑",
                   "证据": {"files": [
                       {"name": "m1.png", "path": os.path.abspath(p1), "sha256": sha1},
                       {"name": "m2.png", "path": os.path.abspath(p2), "sha256": sha2}],
                       "note": "对照批"}}
            store = PrecedentStore([])
            od.mint([self._wrap(rec, td)], store, dry=False)
            e = store.entries[0]
            self.assertEqual(e["evidence"]["artifact"],
                             f"{os.path.abspath(p1)};{os.path.abspath(p2)}")
            fl = e["evidence"]["files"]
            self.assertEqual([f["sha256"] for f in fl], [sha1, sha2])
            self.assertNotIn("note", fl[0])
            self.assertIn("m1.png；m2.png", e["content"]["a"])
            self.assertIn("对照批", e["content"]["a"])

    def test_string_evidence_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            rec = {"类": "增益", "现象": "散文证据老路径仍通",
                   "条件": "tmp", "对照": True, "可复算": "同种子重跑",
                   "证据": "见 P-ok-01"}
            store = PrecedentStore([])
            od.mint([self._wrap(rec, td)], store, dry=False)
            e = store.entries[0]
            self.assertEqual(e["evidence"]["artifact"], "见 P-ok-01")
            self.assertNotIn("files", e["evidence"])


if __name__ == "__main__":
    unittest.main()
