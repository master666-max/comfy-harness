# -*- coding: utf-8 -*-
"""test_kinetic_ledger.py — J-1 动能账本判据件红绿锁（M1 修订口径版 · 治理位 20261007 开工令）

判据锚=调研-卷十三-落地判据件草案-20261003.md §J-1（输出契约四件+冻结阈）＋
E1 菜单原文阈值（偏差 20%/开销比 10%/kill 50%）＋ X3-M1 D1'/D3' 修订口径。
红锁先行：本文件先于 kinetic_ledger.py 写出跑红，实现后转绿——判据零改动。
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kinetic_ledger import (  # noqa: E402
    DEV_THRESHOLD, KILL_THRESHOLD, OVERHEAD_RATIO_THRESHOLD,
    POWER_RATIO_MIN, CENSOR_FRAC, K_GRID,
    KineticLedger, little_law, censor_arrivals,
)


# ── 冻结常量在案 ──
def test_frozen_thresholds():
    assert DEV_THRESHOLD == 0.20
    assert KILL_THRESHOLD == 0.50
    assert OVERHEAD_RATIO_THRESHOLD == 0.10
    assert POWER_RATIO_MIN == 5.0
    assert CENSOR_FRAC == 0.10
    assert K_GRID == 2000


# ── R1 出生免疫：归因非空 fail-closed ──
def test_attribution_fail_closed(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    with pytest.raises(ValueError, match="attribution"):
        kl.record_round("r1", n=10, chars_per_row=100.0, t_per_row=0.5,
                        meas_u=1.0, attribution="")


# ── D1' 账面公式：est_u=m_c×n÷2.5÷1000×1.0＋m_t×n×10.0 ──
def test_est_u_formula():
    kl = KineticLedger.__new__(KineticLedger)  # 不走 I/O，只测公式
    est = kl.est_u(m_c=2500.0, n=10, m_t=0.001)
    # = 2500*10/2.5/1000*1.0 + 0.001*10*10.0 = 10.0 + 0.1
    assert math.isclose(est, 10.1, rel_tol=1e-12)


# ── 账行流：每圈一行，字段契约 ──
def test_round_row_contract(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    row = kl.record_round("r1", n=10, chars_per_row=2500.0, t_per_row=0.001,
                          meas_u=12.0, attribution="test:回路自检")
    for k in ("round", "n", "est_u", "meas_u", "dev", "attribution", "ts"):
        assert k in row
    rows, bad = kl.load_rounds()
    assert bad == 0 and len(rows) == 1


# ── R1 出生免疫：坏行计数不静默跳过 ──
def test_bad_line_counted(tmp_path):
    p = tmp_path / "ledger.jsonl"
    p.write_text('{"round":"ok","n":1}\n{broken json\n', encoding="utf-8")
    rows, bad = KineticLedger(str(p)).load_rounds()
    assert bad == 1 and len(rows) == 1


# ── 消费链动作流：验证窗偏差>20%→降速；段残差>20%→停转复核 ──
def test_consumption_actions(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    # 一圈高偏差（验证窗）→ 降速标记；一圈低偏差 → 无动作
    kl.record_round("hot", n=10, chars_per_row=2500.0, t_per_row=0.001,
                    meas_u=100.0, attribution="t")   # dev 远超 20%
    kl.record_round("cool", n=10, chars_per_row=2500.0, t_per_row=0.001,
                    meas_u=10.1, attribution="t")    # dev≈1%
    actions = kl.consumption_actions()
    kinds = [a["action"] for a in actions]
    assert "降速标记" in kinds
    assert [a for a in actions if a.get("exp") == "cool"] == []


# ── 三态判定（判定序=kill→反噬→咬合→空转）──
def test_verdict_idle_when_no_actions(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    kl.record_round("c1", n=10, chars_per_row=2500.0, t_per_row=0.001,
                    meas_u=10.1, attribution="t")
    v = kl.verdict(overhead_ratio=0.05, power_ratio=10.0,
                   report_written=True, actions=[])
    assert v == "空转"          # 有账无人消费


def test_verdict_backfire_before_engage(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    kl.record_round("c1", n=10, chars_per_row=2500.0, t_per_row=0.001,
                    meas_u=10.1, attribution="t")
    acts = [{"action": "降速标记", "exp": "c1"}]
    v = kl.verdict(overhead_ratio=0.15, power_ratio=10.0,
                   report_written=True, actions=acts)
    assert v == "反噬"          # 开销比 15%>10%，即便对账通过且有人消费


def test_verdict_engage(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    kl.record_round("c1", n=10, chars_per_row=2500.0, t_per_row=0.001,
                    meas_u=10.1, attribution="t")
    acts = [{"action": "降速标记", "exp": "c1"}]
    v = kl.verdict(overhead_ratio=0.05, power_ratio=10.0,
                   report_written=True, actions=acts)
    assert v == "咬合"


# ── L=λW 三通道 + 删失检力臂 ──
def test_little_law_consistent():
    # 均匀到达间隔 1.0s、服务耗时 0.5s 的定常流：L 应≈λW
    arrivals = [i * 1.0 for i in range(200)]
    dones = [a + 0.5 for a in arrivals]
    L_bar, lam, W_bar, resid = little_law(arrivals, dones, k_grid=2000)
    assert math.isclose(lam, 1.0, rel_tol=0.01)
    assert math.isclose(W_bar, 0.5, rel_tol=0.01)
    assert abs(resid) < 0.05


def test_power_arm_detects_censoring():
    arrivals = [i * 1.0 for i in range(200)]
    dones = [a + 0.5 for a in arrivals]
    cens = censor_arrivals(arrivals, frac=0.10, seed=7)
    _, lam0, _, resid0 = little_law(arrivals, dones, k_grid=2000)
    _, lam1, _, resid1 = little_law(cens, dones, k_grid=2000)
    power = abs(resid1) / max(abs(resid0), 1e-12)
    assert power > POWER_RATIO_MIN


# ── 日报契约：文件存在且覆盖全部分段=「账本出日报」 ──
def test_daily_report_contract(tmp_path):
    kl = KineticLedger(str(tmp_path / "ledger.jsonl"))
    for i in range(12):
        kl.record_round(f"r{i}", n=10, chars_per_row=2500.0, t_per_row=0.001,
                        meas_u=10.1, attribution="t")
    report = kl.daily_report(n_segments=10)
    assert report["report_written"] is True
    segs = report["segments"]
    assert len(segs) == 10                      # 覆盖全部分段
    assert {s["segment"] for s in segs} == set(range(1, 11))
    md = kl.render_report_md(report)
    assert "| 段 |" in md and "L=λW" in md
