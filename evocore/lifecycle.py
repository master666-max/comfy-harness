# -*- coding: utf-8 -*-
"""engine/lifecycle.py — memsys 生命周期层（三态 + tombstone + 衰减）
（evocore 平移版 · S1 · 源 memsys/engine/lifecycle.py @ b19c9a4）
三态：intermediate → longterm → attic（公理 F：禁销毁式回退）；tombstone=审计窗口。
"""
from __future__ import annotations
from .tunables import DEFAULTS, decay_mult

STATES = ("intermediate", "longterm", "attic")

def route(entry, tunables=DEFAULTS) -> str:
    """归档路由。v3.9 现行为=importance 阈值规则（R5 起改 decide.promote 挣得管辖）。"""
    imp = int(entry.get("importance", 0) or 0)
    return "longterm" if imp >= tunables.promote_importance_min else "intermediate"

def promote(entry) -> dict:
    """晋升 intermediate→longterm。返回晋升事件 payload（留痕结构）。"""
    if entry.get("state") == "attic": raise ValueError("attic 条目不得直接晋升（须先人工恢复）")
    entry["state"] = "longterm"
    return {"kind": "promotion", "entry_id": entry.get("id"),
            "rationale": "promote_importance_min 达标或 decision 层判定"}

def attic(entry, reason: str, tunables=DEFAULTS) -> dict:
    """回退=移 attic 并登记（公理 F）。永不删除。"""
    entry["state"] = "attic"
    return {"kind": "attic_nomination", "entry_id": entry.get("id"),
            "reason": reason[:tunables.rationale_max]}   # S1v2/T2：截断长入 Tunables

def tombstone(entry) -> dict:
    """墓碑：标记后退出检索但原位保留=审计窗口（v3.10 件五语义）。"""
    entry["tombstone"] = True
    return {"kind": "tombstone", "entry_id": entry.get("id"),
            "note": "退出检索，原位保留（审计窗口）"}

def touch(entry, ts: str) -> None:
    """被检索命中即刷新 last_used_at（w_age 定时炸弹拆除：age 从此起算）。"""
    entry["last_used_at"] = ts

def decay_multiplier(entry, tunables=DEFAULTS) -> float:
    """类型衰减乘数：episodic 快 / semantic 标准 / procedural 零衰减。
    S1v2/T1：委托 tunables.decay_mult（唯一实现）——公开签名与行为不变。"""
    return decay_mult(tunables, entry.get("type", "semantic"))
