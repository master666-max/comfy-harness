# -*- coding: utf-8 -*-
"""test_shadow_j4.py — 影子 J-4 红绿锁（治理位 20261007 令「设立影子 J-4，积累数据」）

影子语义（写进本测试即契约）：只记录、不进闸——影子账本不参与任何生产判定，
唯一消费者=滚动 q̂ 与复标（裁2）。积累面=逐读行（判官/对象/判读/真值/捕获层），
真值可后置（候裁决补齐——影子期大量行 truth=None，裁决后回填）。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))

from shadow_j4 import ShadowLedger  # noqa: E402
from real_q_estimator import estimate  # noqa: E402


def test_record_requires_src(tmp_path):
    sl = ShadowLedger(str(tmp_path / "shadow.jsonl"))
    with pytest.raises(ValueError, match="src"):
        sl.record(judge="X", target="img:attr", verdict=1)


def test_record_pending_truth_roundtrip(tmp_path):
    """影子期主体=真值未裁的行（truth=None）——必须原样积累不丢。"""
    sl = ShadowLedger(str(tmp_path / "shadow.jsonl"))
    sl.record(judge="DSK", target="img_X:红方块", verdict=1, src="exam1")
    sl.record(judge="DSK", target="img_X:木桌", verdict=0, truth=1,
              captured_by="治理位人审", src="exam1")
    rows, _ = sl.load()
    assert len(rows) == 2
    assert rows[0]["truth"] is None and "ts" in rows[0]
    assert rows[1]["captured_by"] == "治理位人审"


def test_census_excludes_pending(tmp_path):
    """census()=可计分行（真值已裁）；真值未裁行留账但不进 q。"""
    sl = ShadowLedger(str(tmp_path / "shadow.jsonl"))
    sl.record(judge="A", target="t1", verdict=1, truth=1, src="e")
    sl.record(judge="A", target="t2", verdict=0, src="e")          # 候裁
    sl.record(judge="A", target="t3", verdict=0, truth=1, src="e")  # 错判
    census = sl.census()
    assert len(census) == 2
    assert all(r["truth"] is not None for r in census)


def test_rolling_q_matches_estimator(tmp_path):
    sl = ShadowLedger(str(tmp_path / "shadow.jsonl"))
    sl.record(judge="A", target="t1", verdict=0, truth=1,
              captured_by="机械分歧监控", src="e")
    sl.record(judge="A", target="t2", verdict=0, truth=1, captured_by=None, src="e")
    sl.record(judge="A", target="t3", verdict=1, truth=1, src="e")
    out = sl.rolling_q()
    assert out["n_total"] == 3 and out["n_errors"] == 2
    assert out["layers"]["机械分歧监控"]["q"] == pytest.approx(0.5)


def test_bad_line_counted(tmp_path):
    p = tmp_path / "shadow.jsonl"
    p.write_text('{"judge":"a"}\n{broken\n', encoding="utf-8")
    rows, bad = ShadowLedger(str(p)).load()
    assert bad == 1 and len(rows) == 1


def test_bootstrap_reproduces_real_q(tmp_path):
    """种子链路锚：影子账本灌入 E-2 真实台账（31 读）后，滚动 q̂ 必须复现
    定谳值 1/3——影子机制与真实 q 估计器之间无口径漂移。"""
    from estimate_real_q import build_census
    sl = ShadowLedger(str(tmp_path / "shadow.jsonl"))
    for row in build_census():
        sl.record(judge=row["judge"], target=row["target"], verdict=row["verdict"],
                  truth=row["truth"], captured_by=row["captured_by"], src=row["src"])
    out = sl.rolling_q()
    assert out["n_total"] == 31
    assert out["layers"]["机械分歧监控"]["q"] == pytest.approx(0.3333)
