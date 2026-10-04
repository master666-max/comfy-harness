# -*- coding: utf-8 -*-
"""engine/decision.py — memsys 决策层（v1 规则版；LLM tool call = W7 接入点）
（evocore 平移版 · S1 · 源 memsys/engine/decision.py @ b19c9a4）
三 intent（conflict/merge/promote）判定接口 + 强制留痕结构。
v1=代码规则（现行为迁移）；W7 起 LLM 接管按 prereg/金标判据-v1.md 挣得，
代码规则永久兜底（回退率进监控）。
"""
from __future__ import annotations
import datetime
from .tunables import DEFAULTS

def _now(): return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def _trace(intent, entries, decision, rationale, tunables=DEFAULTS, prereg=None,
           deviation_declared=None):
    """留痕结构（强制返回）：可写 events 账（kind='memory_adjudicate'）。
    S1v2/T2：rationale 截断长走 tunables.rationale_max（原魔法数 200 收编）。
    **S8-5②（20260923 开工批）**：新增 `prereg` 字段=判据指针（`<判据件>@<版本>`；
    无合格判据件则 `None`）——「判据先于实现」由口号落到**每条决策**上：读账即知这条判定
    当时有没有判据可依。加法式新增（老留痕无此键，读侧按 None 容错）；指针的发现与格式检
    在治理核 `core/prereg.py`（宿主侧调用，本包保持零依赖、不碰文件系统）。"""
    return {"kind": "memory_adjudicate", "intent": intent,
            "entries": [e.get("id", "?") for e in entries],
            "decision": decision, "rationale": rationale[:tunables.rationale_max],
            "prereg": prereg,
            "deviation_declared": deviation_declared,   # A22（M1 注册报告语义）：偏离协议须显式申报，不可默认
            "ts": _now(), "actor": "fallback:rule",
            "severity_if_wrong": "irreversible" if intent == "conflict" and
                                 any(e.get("source") == "manual" for e in entries) else "redundant"}

def adjudicate_conflict(entries, tunables=DEFAULTS, prereg=None,
                        deviation_declared=None):
    """冲突：两条记忆矛盾，保谁。v1 规则：manual 来源 > 高 importance > 新 created_at。"""
    if len(entries) < 2: raise ValueError("conflict 需 ≥2 条")
    ranked = sorted(entries, key=lambda e: (
        1 if e.get("source") == "manual" else 0,          # 人工录入信任最高
        int(e.get("importance", 0) or 0),
        e.get("created_at", "")), reverse=True)
    win, lose = ranked[0], ranked[1:]
    return _trace("conflict", entries, f"keep:{win.get('id','?')}",
                  "v1 规则：manual>importance>new；金标挣得后由 LLM 接管（金标判据 §二）",
                  tunables, prereg, deviation_declared), win, lose

def adjudicate_merge(entries, tunables=DEFAULTS, prereg=None,
                     deviation_declared=None):
    """合并：判断两条是否同义。v1 规则：**拒绝自动合并**（保守拒绝，金标判据奖励）——
    同义判断写不成规则（评估②实锤），规则期一律 defer 给人工/未来 LLM。"""
    if len(entries) < 2: raise ValueError("merge 需 ≥2 条（与 conflict 守卫对称）")
    return _trace("merge", entries, "defer",
                  "v1 规则保守拒绝：同义判断不可规则化，待 LLM 金标挣得（prereg §二）",
                  tunables, prereg, deviation_declared)

def adjudicate_promote(entries, tunables=DEFAULTS, prereg=None,
                       deviation_declared=None):
    """晋升：v1 规则=importance 阈值（现行为），阈值进 TUNABLES（不再硬编码）。"""
    out = []
    for e in entries:
        imp = int(e.get("importance", 0) or 0)
        out.append((e, imp >= tunables.promote_importance_min))
    return _trace("promote", entries,
                  ",".join(f"{e.get('id','?')}:{'promote' if ok else 'hold'}" for e, ok in out),
                  f"v1 规则：importance>={tunables.promote_importance_min}（TUNABLES 外置）",
                  tunables, prereg, deviation_declared), out
