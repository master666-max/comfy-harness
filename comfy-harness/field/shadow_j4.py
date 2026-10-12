# -*- coding: utf-8 -*-
"""shadow_j4.py — 影子 J-4 判卷台账（治理位 20261007 令「设立影子 J-4，积累数据」）

**影子语义**：只记录、不进闸。本账本不参与任何生产判定/告警/档位设计——唯一
消费者=滚动 q̂（real_q_estimator）与裁2 真实裁判复标（候令）。影子期主体行
truth=None（真值候裁决回填），裁决后由治理层补齐即自动进入可计分面。

**积累面与用途对映**：
- 逐读行（判官/对象/判读/真值?/捕获层?/源锚）→ 滚动 q̂（机械层捕获率，量级跟踪）
- 真值回填历史 → 裁2 复标数据（判官族×判读行为的真实分布）
- 捕获层标注 → 漏捕归因的持续验证面（跨族对读 A 案落地后的天然实验记录）

R1 出生免疫：src 非空 fail-closed；坏行计数不静默。追加式 JSONL（fsync）。
零生产写：账本路径由调用方给定；本件不接任何生产闸。

**regime 约定（自审查 S-2）**：src 前缀即代际标记——legacy 三前缀（e2_results/e2_blind/判据件）
=史实普查面（机械监控旧定义）；`E2-*`=A 案双族常态对读 regime（机械监控新定义）。
两代 q̂ 不同构：`rolling_q()` 全量混算只读量级、不读趋势；legacy 面用
`tools/estimate_real_q.build_census`（按前缀取史实行），新 regime 面候 ④ 构念仲裁后另立。
"""
from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), os.pardir, "tools"))
sys.path.insert(0, os.path.join(_HERE))

from real_q_estimator import estimate  # noqa: E402


class ShadowLedger:
    def __init__(self, path: str):
        self.path = path
        self.bad_lines = 0

    def _lock(self, timeout: float = 5.0):
        """S-5 并发防护：互斥锁文件（O_EXCL；陈旧锁 >30s 收破）。
        单写者假设弱化为「锁内写者」——record/backfill 全走此锁。"""
        lp = self.path + ".lock"
        end = time.time() + timeout
        while True:
            try:
                fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return lp
            except FileExistsError:
                if time.time() > end:
                    if time.time() - os.path.getmtime(lp) > 30:
                        os.unlink(lp)          # 陈旧锁收破，重试一轮
                        end = time.time() + timeout
                        continue
                    raise TimeoutError(f"影子账锁占用超时：{lp}") from None
                time.sleep(0.05)

    def _unlock(self, lock_path: str):
        if os.path.exists(lock_path):
            os.unlink(lock_path)

    def record(self, judge: str, target: str, verdict,
               truth=None, captured_by=None, src: str = "", ts: str | None = None,
               lock_timeout: float = 5.0) -> dict:
        if not str(src or "").strip():
            raise ValueError("R1 fail-closed：影子行 src 非空校验失败（无源锚行不入账）")
        row = {"judge": judge, "target": target, "verdict": verdict,
               "truth": truth, "captured_by": captured_by,
               "src": src, "ts": ts or time.strftime("%Y-%m-%dT%H:%M:%S")}
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        lp = self._lock(lock_timeout)
        try:
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        finally:
            self._unlock(lp)
        return row

    def load(self):
        """读影子账；坏行计数上报不静默（R1）。"""
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

    def census(self):
        """可计分行=真值已裁（truth 非 None）；候裁行留账不进 q。"""
        rows, _ = self.load()
        return [r for r in rows if r.get("truth") is not None]

    def pending(self):
        """候裁行（影子期主体）——治理层回填真值的工作队列。"""
        rows, _ = self.load()
        return [r for r in rows if r.get("truth") is None]

    def rolling_q(self):
        """滚动 q̂：与 real_q_estimator 同口径（机械层/人审层/overall 分层）。
        ⚠ S-2 注：全量混算跨新旧两代监控 regime——量级可读、趋势不可读；
        legacy 面请用 tools/estimate_real_q.build_census（src 前缀过滤）。"""
        return estimate(self.census())


def milestone_check(path):
    """C-4 消费链手动节律工具（S-6 兑现）：影子账每次接入/回填后随手一跑。

    n_errors<10 → 量级读数即可（禁精用）；过 10 → 出重估回执；过 30 → 出精估版。
    """
    out = ShadowLedger(path).rolling_q()
    ne = out["n_errors"]
    if ne >= 30:
        action = "出精估版回执"
        milestone = 30
    elif ne >= 10:
        action = "出重估回执"
        milestone = 10
    else:
        action = "量级读数即可（禁精用）"
        milestone = None
    return {"n_errors": ne, "milestone": milestone, "action": action}

    def backfill_truth(self, target, truth, captured_by=None, lock_timeout: float = 5.0):
        """裁决后回填：按 target 批量补真值与捕获层（治理层专用入口）。
        S-5：重写全程持锁（与 record 互斥），消除回填吞并发追加的窗口。"""
        lp = self._lock(lock_timeout)
        try:
            rows, _ = self.load()
            hit = 0
            for _i, r in enumerate(rows):
                if r["target"] == target and r.get("truth") is None:
                    r["truth"] = truth
                    if captured_by is not None:
                        r["captured_by"] = captured_by
                    hit += 1
            if hit:
                tmp = self.path + ".rewrite"
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)   # 原子替换防半写
            return hit
        finally:
            self._unlock(lp)
