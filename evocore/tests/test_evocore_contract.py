# -*- coding: utf-8 -*-
"""test_evocore_contract.py — 分层契约测试（S1v2 · T5③；契约矩阵=《S1设计v2》§2.3）

契约（谁可 import 谁，AST 静态判定；违者 FAIL）：
  tunables.py    → 仅标准库
  retrieval.py   → 标准库 + .tunables
  lifecycle.py   → 标准库 + .tunables
  decision.py    → 标准库 + .tunables
  __init__.py    → 包内四件
  任何件          → ✗ 绝对导入（包外一切：audit-kit/memsys/宿主）
判别力（负向断言必配正向对照）：故意违规样例必须被判 FAIL；合规样例必须不被误报。
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_STDLIB = {  # 与门④白名单同源（tools/code_quality_gate.py STDLIB）
    "__future__", "argparse", "ast", "base64", "collections", "contextlib", "copy", "csv",
    "dataclasses", "datetime", "enum", "fnmatch", "functools", "hashlib", "importlib", "inspect",
    "io", "itertools", "json", "logging", "math", "operator", "os", "pathlib", "re", "random",
    "shutil", "sqlite3", "statistics", "struct", "subprocess", "sys", "tempfile", "textwrap",
    "time", "types", "typing", "unicodedata", "unittest", "uuid", "warnings", "zlib", "abc",
}
_ALLOWED_RELATIVE = {
    "tunables.py": set(),
    "retrieval.py": {"tunables"},
    "lifecycle.py": {"tunables"},
    "decision.py": {"tunables"},
    "entry.py": {"lifecycle"},                      # S3/T1：STATES 自 lifecycle 引入（单一事实源）
    "project.py": set(),                            # S4/T1：仅标准库（纯投影，零包内依赖）
    "__init__.py": {"tunables", "retrieval", "lifecycle", "decision", "entry", "project"},
}


def violations_of(fname: str, src: str):
    """返回违反分层契约的条目（空=合规）。本函数同时服务真实件与判别力样例。"""
    allowed = _ALLOWED_RELATIVE[fname]
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _STDLIB:
                    bad.append(f"L{node.lineno} 绝对导入 {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                root = (node.module or "").split(".")[0]
                if root not in _STDLIB:            # 标准库 from-导入放行（判别力测试对照面）
                    bad.append(f"L{node.lineno} 绝对导入 from {node.module}")
                continue
            names = [node.module] if node.module else [n.name for n in node.names]
            for nm in names:
                if nm not in allowed:
                    bad.append(f"L{node.lineno} 越界相对导入 .{nm}（白名单 {sorted(allowed)}）")
    return bad


class TestContractOnRealFiles(unittest.TestCase):
    def test_all_modules_satisfy_matrix(self):
        """契约矩阵：五件逐件零违例。"""
        pkg = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        for fname in _ALLOWED_RELATIVE:
            with open(os.path.join(pkg, fname), encoding="utf-8") as f:
                bad = violations_of(fname, f.read())
            self.assertEqual(bad, [], f"{fname} 契约违例：{bad}")


class TestContractDiscrimination(unittest.TestCase):
    def test_flags_cross_layer_relative_import(self):
        """判别力①：retrieval 反向依赖 lifecycle（越界横向）必被抓。"""
        bad = violations_of("retrieval.py", "from .lifecycle import route\n")
        self.assertTrue(bad, "越界相对导入未被抓")

    def test_flags_absolute_import_anywhere(self):
        """判别力②：任何绝对导入（包外依赖）必被抓。"""
        for fname in _ALLOWED_RELATIVE:
            bad = violations_of(fname, "from ledger import Ledger\n")
            self.assertTrue(bad, f"{fname} 的绝对导入未被抓")

    def test_flags_tunables_reaching_up(self):
        """判别力③：最低层 tunables 不可引包内任何件。"""
        bad = violations_of("tunables.py", "from .retrieval import score\n")
        self.assertTrue(bad, "tunables 越界导入未被抓")

    def test_clean_samples_not_flagged(self):
        """正向对照：合规样例（标准库+白名单相对导入）不得误报。"""
        self.assertEqual(violations_of("tunables.py", "import ast\nfrom dataclasses import dataclass\n"), [])
        self.assertEqual(violations_of("retrieval.py", "from .tunables import DEFAULTS\n"), [])
        self.assertEqual(violations_of("__init__.py", "from . import decision\nfrom .decision import adjudicate_merge\n"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
