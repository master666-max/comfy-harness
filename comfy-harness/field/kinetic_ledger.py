# -*- coding: utf-8 -*-
"""kinetic_ledger.py — J-1 动能账本判据件（M1 修订口径版 · 治理位 20261007 开工令）

判据锚（零改动）：调研-卷十三-落地判据件草案-20261003.md §J-1（输出契约四件）＋
E1 菜单原文阈值＋ X3-M1 D1'/D3' 修订口径（tmp/卷十三站2/X3/x3_m1_run.py 冻结实现）。

输出契约四件：①日报（分段成本表＋越界旗标＋L=λW 对账读数）②账行流（每圈一行）③
消费链动作流（验证窗偏差>20%→降速标记；段残差>20%→停转复核标记）④检力自检行
（删失臂检力比>5 为有检力）。

R1 出生免疫（统合总工单 §二）：账行强制 attribution 非空 fail-closed；坏行计数
不静默跳过；账行为单行 JSONL 追加（fsync 落盘）。

判定序=kill→反噬→咬合→空转（pre-research 技能 v1.3.0 序）。
零生产写：账文件路径由调用方给定（本判据件不固定任何生产路径）。
"""
from __future__ import annotations

import bisect
import json
import os
import random
import statistics
import time

# ── 冻结常数（E1 菜单原文＋X3-M1 修订；改动即新预注册） ──
DEV_THRESHOLD = 0.20             # 偏差阈：验证窗圈→降速标记 / 段残差→停转复核
KILL_THRESHOLD = 0.50            # kill 候选阈（归因侧由回执裁定，机械面只报候选）
OVERHEAD_RATIO_THRESHOLD = 0.10  # 开销比阈（反噬面）
POWER_RATIO_MIN = 5.0            # 检力比阈
CENSOR_FRAC = 0.10               # 删失臂比例
K_GRID = 2000                    # 库存通道网格采样点数
CHARS_PER_TOKEN = 2.5            # 折算系数（两通道同）
PRICE_CHAR_U_PER_KTOK = 1.0      # 字符单价（u/千 token 当量）
PRICE_MACHINE_U_PER_S = 10.0     # 机时单价（u/s）
CALIB_FRACTION = 0.2             # 标定窗=前 20% 圈（G≥10 时前 2/10 段同构）；G<10 全体验证窗


class KineticLedger:
    """动能账本：账行流（JSONL append-only）＋日报＋消费链动作＋三态判定。"""

    def __init__(self, path: str):
        self.path = path
        self.bad_lines = 0

    # ── D1' 账面公式（X3-M1 冻结） ──
    @staticmethod
    def est_u(m_c: float, n: int, m_t: float) -> float:
        """est_u = m_c×n÷2.5÷1000×1.0 ＋ m_t×n×10.0（m_c=每行引文字符中位、m_t=每行耗时中位）。"""
        return (m_c * n / CHARS_PER_TOKEN / 1000.0 * PRICE_CHAR_U_PER_KTOK
                + m_t * n * PRICE_MACHINE_U_PER_S)

    # ── 账行流 ──
    def record_round(self, round_name: str, n: int, chars_per_row: float,
                     t_per_row: float, meas_u: float, attribution: str) -> dict:
        if not str(attribution or "").strip():
            raise ValueError("R1 fail-closed：账行 attribution 非空校验失败（归因恒空=审计半盲，拒绝入账）")
        rows, _ = self.load_rounds()
        per_row_chars = [r.get("chars_per_row", 0.0) for r in rows] + [chars_per_row]
        per_row_t = [r.get("t_per_row", 0.0) for r in rows] + [t_per_row]
        m_c = statistics.median(per_row_chars)
        m_t = statistics.median(per_row_t)
        est = self.est_u(m_c=m_c, n=n, m_t=m_t)
        dev = abs(est - meas_u) / max(est, 1e-9)
        row = {"round": round_name, "n": n, "chars_per_row": chars_per_row,
               "t_per_row": t_per_row, "est_u": round(est, 6),
               "meas_u": round(meas_u, 6), "dev": round(dev, 6),
               "attribution": attribution, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return row

    def load_rounds(self):
        """读账行流；坏行计数上报不静默跳过（R1）。"""
        rows, bad = [], 0
        if not os.path.exists(self.path):
            return rows, bad
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    bad += 1
        self.bad_lines = bad
        return rows, bad

    # ── 消费链动作流 ──
    def _calib_split(self, rows):
        g = len(rows)
        calib_n = max(1, int(g * CALIB_FRACTION)) if g >= 10 else 0
        return rows[:calib_n], rows[calib_n:]

    def consumption_actions(self) -> list:
        """验证窗偏差>20% 的圈→降速标记；段残差>20% 的段→停转复核标记。"""
        rows, _ = self.load_rounds()
        if not rows:
            return []
        _, verify = self._calib_split(rows) if len(rows) >= 10 else (None, rows)
        actions = []
        for rr in verify:
            if rr["dev"] > DEV_THRESHOLD:
                actions.append({"action": "降速标记", "exp": rr["round"],
                                "dev": rr["dev"]})
        for s, seg in enumerate(self._segments(rows, 10), 1):
            seg_resid = statistics.median([r["dev"] for r in seg]) if seg else 0.0
            if seg_resid > DEV_THRESHOLD:
                actions.append({"action": "停转复核标记", "seg": s,
                                "resid": round(seg_resid, 4)})
        return actions

    # ── 日报 ──
    @staticmethod
    def _segments(rows, n_segments):
        if not rows:
            return []
        if len(rows) >= n_segments:
            # 按位次十分位切（X3-M1 同构：段=行位 1/10 窗），段数恒=n_segments
            edges = [round(i * len(rows) / n_segments) for i in range(n_segments + 1)]
            return [rows[edges[i]:edges[i + 1]] or [rows[-1]]
                    for i in range(n_segments)]
        return [[r] for r in rows]

    def daily_report(self, n_segments: int = 10, little: dict | None = None,
                     power_ratio: float | None = None) -> dict:
        rows, bad = self.load_rounds()
        segs = []
        for s, seg in enumerate(self._segments(rows, n_segments), 1):
            resid = statistics.median([r["dev"] for r in seg]) if seg else 0.0
            segs.append({"segment": s, "rounds": len(seg),
                         "est_u": round(sum(r["est_u"] for r in seg), 3),
                         "meas_u": round(sum(r["meas_u"] for r in seg), 3),
                         "dev_median": round(resid, 4),
                         "flag": resid > DEV_THRESHOLD})
        return {"report_written": True, "segments": segs, "bad_lines": bad,
                "little": little or {}, "power_ratio": power_ratio,
                "actions": self.consumption_actions()}

    def render_report_md(self, report: dict) -> str:
        lines = ["# 动能账本日报（J-1 · M1 修订口径）", "",
                 "| 段 | 圈数 | est_u 合计 | meas_u 合计 | 偏差中位 | 越界旗标 |",
                 "|---|---|---|---|---|---|"]
        for s in report["segments"]:
            lines.append(f"| {s['segment']} | {s['rounds']} | {s['est_u']} | "
                         f"{s['meas_u']} | {s['dev_median']} | {'⚠' if s['flag'] else ''} |")
        lit = report.get("little") or {}
        lines += ["", f"- L=λW 对账：L̄={lit.get('L_bar', '缺测')}，λ̄={lit.get('lambda_bar', '缺测')}，"
                      f"W̄={lit.get('W_bar', '缺测')}，残差={lit.get('resid', '缺测')}"]
        pr = report.get("power_ratio")
        lines.append(f"- 检力自检：检力比={pr if pr is not None else '未跑'}"
                     f"（阈 >{POWER_RATIO_MIN}）")
        acts = report.get("actions") or []
        lines.append(f"- 消费链动作：{len(acts)} 项"
                     + ("（" + "；".join(f"{a['action']}@{a.get('exp', a.get('seg'))}" for a in acts) + ")" if acts else "——空转机械面"))
        return "\n".join(lines) + "\n"

    # ── 三态判定（判定序=kill→反噬→咬合→空转） ──
    def verdict(self, overhead_ratio: float, power_ratio: float,
                report_written: bool, actions: list,
                max_dev: float | None = None) -> str:
        if max_dev is not None and max_dev > KILL_THRESHOLD:
            return "kill"   # 候选——归因侧回执裁定，机械面只报
        if overhead_ratio > OVERHEAD_RATIO_THRESHOLD:
            return "反噬"    # 记账开销>被记成本 10%
        if report_written and actions and power_ratio > POWER_RATIO_MIN:
            return "咬合"    # 账出日报＋有人消费＋对账有检力
        return "空转"        # 有账无人消费（或检力面失明）


# ── D3' L=λW 三通道独立测量 ──
def little_law(arrivals, dones, k_grid: int = K_GRID):
    """λ̄=G/T（到达计数）；W̄=mean(D−A)（配对时戳差）；L̄=K 网格瞬时库存采样。

    允许 arrivals/dones 长度不等（检力臂删失形态）：配对按索引取 min 长度，
    库存通道两列表全量参与——删失即拉大库存-λW 失衡，检力由此而来。
    """
    arr = sorted(arrivals)
    don = sorted(dones)
    if not arr:
        return 0.0, 0.0, 0.0, 0.0
    t0, t1 = arr[0], max(arr[-1], don[-1] if don else arr[-1])
    span = max(t1 - t0, 1e-9)
    lam = len(arr) / span
    pairs = list(zip(arr, don))
    w_bar = statistics.median([d - a for a, d in pairs]) if pairs else 0.0
    samples = []
    for i in range(k_grid):
        t = t0 + span * (i + 0.5) / k_grid
        samples.append(bisect.bisect_right(arr, t) - bisect.bisect_right(don, t))
    l_bar = statistics.mean(samples)
    resid = l_bar - lam * w_bar
    return l_bar, lam, w_bar, resid


def censor_arrivals(arrivals, frac: float = CENSOR_FRAC, seed: int = 7):
    """检力臂：λ 通道删失 frac 比例到场事件（确定性 seed）。"""
    k = max(1, int(len(arrivals) * frac))
    drop = set(random.Random(seed).sample(range(len(arrivals)), k))
    return [a for i, a in enumerate(arrivals) if i not in drop]
