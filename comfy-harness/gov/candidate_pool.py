# -*- coding: utf-8 -*-
"""candidate_pool.py — 候选静置池（工单 P6 · N2 成熟度闸"复现才铸"）

文献对位：RecMem（2605.16045）"Recurrence-based Memory Consolidation"——急切式巩固
（每输入必处理）是缺陷；**复现式**才凝出稳定知识。我们独立同构：
候选首现**不铸**，落静置池按轮计次；**跨轮复现（rounds_seen ≥ min_rounds）才许进铸判闸**。
惊喜类不走上限（obs 轨道独立，首现即铸）。

池状态：style_mine_out/candidate_pool.json —— {sig: {rounds_seen, first_seen, last_seen,
members(前12), evidence_n, minted(可选)}}；每次 observe() = 该批候选记一轮。
"""
from __future__ import annotations

import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, _HERE)
import style_feed as sf            # noqa: E402  （sig_of 复用）

DEFAULT_POOL = os.path.join(_HERE, "style_mine_out", "candidate_pool.json")


def load_pool(path: str = DEFAULT_POOL) -> dict:
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _base_of(name: str) -> str:
    """候选名 → S- 基底（与铸造 id 同约定）。"""
    import re as _re
    s = _re.sub(r"[^A-Za-z0-9]+", "-", str(name)).strip("-")[:28].strip("-") or "cluster"
    return "s-" + s.lower()


def _jac(a: list, b: list) -> float:
    sa, sb = {str(x).lower() for x in a}, {str(x).lower() for x in b}
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def key_of(pool: dict, cand: dict) -> str:
    """鲁棒概念键：①同基底既有键 → ②标签 Jaccard≥0.5 的既有键 → ③精确签名兜底。"""
    base = _base_of(cand.get("name", ""))
    if base in pool:
        return base
    members = list(cand.get("members") or [])
    best, best_j = None, 0.0
    for k, v in pool.items():
        j = _jac(members, list((v or {}).get("members") or []))
        if j > best_j:
            best, best_j = k, j
    if best is not None and best_j >= 0.5:
        return best
    return base          # 首现：以基底立键（跨轮同概念天然同键）


def observe(cands: list, path: str = DEFAULT_POOL, round_date: str | None = None) -> dict:
    """整批记一轮；返回 {sig: rounds_seen}（同时落盘）。"""
    pool = load_pool(path)
    today = round_date or time.strftime("%Y-%m-%d")
    seen = {}
    for c in cands:
        key = key_of(pool, c)                    # 鲁棒键（基底/Jaccard；成员漂移不再算首现）
        st = pool.setdefault(key, {"rounds_seen": 0, "first_seen": today,
                                   "last_seen": today, "members": c["members"][:12],
                                   "evidence_n": len(c.get("evidence", [])),
                                   "sig_seen": []})
        st["rounds_seen"] += 1
        st["last_seen"] = today
        st["members"] = c["members"][:12]
        st["evidence_n"] = len(c.get("evidence", []))
        try:                                     # 保留每轮签名（同一概念的不同代表集，供审计）
            sg = sf.sig_of(c["members"])
            if sg not in st.setdefault("sig_seen", []):
                st["sig_seen"].append(sg)
        except Exception:                        # noqa: BLE001
            pass
        seen[key] = st["rounds_seen"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(pool, open(path, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    return seen


def mark_minted(path: str, sig: str, eid: str) -> None:
    pool = load_pool(path)
    if sig in pool:
        pool[sig]["minted"] = eid
        json.dump(pool, open(path, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=1)
