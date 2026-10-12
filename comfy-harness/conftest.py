# -*- coding: utf-8 -*-
"""conftest.py — 测试污染哨兵（会话级）

**由来（三次实录）**：本会话测试三次写入生产件——
  ① 族谱测试漏传 recurrence_path → 污染 style_mine_out/recurrence.json
  ② retire 测试默认参数早绑定 → 污染 style_mine_out/impact_records/
  ③ impact 命令顺手写产物 → 测试夹具小图覆盖 style_mine_out/edge_graph.json
单次修补治不了这一类；本哨兵=机械化根治：整个测试会话前后对生产件取内容哈希，
会话结束时若有变化 → **测试失败**并点名文件（谁污染谁现形，禁静默）。

纪律：测试一律用临时路径（tmp_path/TemporaryDirectory）；本哨兵只兜底，不替代 DI。
"""
from __future__ import annotations

import hashlib
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))   # comfy-harness/
_GOV = os.path.join(_HERE, "gov")
# pytest 误采防线（20261009）：field/shaft_bearing_test.py 是活体承重实验脚本
# （模块级执行+sys.exit+依赖 8188 服务器+写共享库），unittest 发现（test*.py 模式）
# 从不收集它；pytest 的 *_test.py 模式会误采 → 收集期即炸。按实验脚本对待，不按单测。
collect_ignore = ["field/shaft_bearing_test.py"]
# 生产件清单：派生件 + 账本（测试绝不该碰）
WATCH = [
    os.path.join(_GOV, "style_mine_out", "recurrence.json"),
    os.path.join(_GOV, "style_mine_out", "candidate_pool.json"),
    os.path.join(_GOV, "style_mine_out", "edge_graph.json"),
    os.path.join(_GOV, "style_mine_out", "health.json"),
    os.path.join(_GOV, "style_mine_out", "review_groups.json"),
    os.path.join(_GOV, "style_mine_out", "style_registry.json"),
    os.path.join(_GOV, "style_mine_out", "anti_shadow.jsonl"),
    os.path.join(_GOV, "style_mine_out", "embeddings.json"),
    os.path.join(_GOV, "precedents_e2_seed.json"),
    os.path.join(_GOV, "style_mine_out", "feed_report.json"),
    os.path.join(_GOV, "style_mine_out", "premises.json"),       # 20261009 前提登记
    os.path.join(_GOV, "style_mine_out", "retrial_queue.json"),  # 20261009 重审队列
]


def _snap():
    out = {}
    for p in WATCH:
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                out[p] = hashlib.sha256(fh.read()).hexdigest()
        else:
            out[p] = "<absent>"
    # impact_records 目录：文件级快照
    d = os.path.join(_HERE, "style_mine_out", "impact_records")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            fp = os.path.join(d, f)
            with open(fp, "rb") as fh:
                out[fp] = hashlib.sha256(fh.read()).hexdigest()
    return out


@pytest.fixture(scope="session", autouse=True)
def _production_artifacts_untouched():
    before = _snap()
    yield
    after = _snap()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    if changed:
        pytest.fail("测试写入了生产件（违反测试卫生，请改用临时路径）：\n  "
                    + "\n  ".join(os.path.relpath(c, _HERE) for c in changed))


@pytest.fixture(autouse=True)
def _reset_vector_breaker():
    """进程级熔断器逐测试重置。

    由头：recall_hybrid 的向量路熔断窗口（60s）是**进程级状态**——前一个测试把 live 端点
    打失败后，后一个"注入假编码器"的测试会被误判在窗口内而跳过向量路（实测：三条探针测试
    连红）。凡进程级可变状态，测试间必须隔离；这里统一在每测试前清零。
    """
    try:
        import recall_hybrid as _rh
        _rh._VEC_DOWN_UNTIL = 0.0
    except ImportError:
        pass
    yield
