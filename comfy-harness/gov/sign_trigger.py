# -*- coding: utf-8 -*-
"""sign_trigger.py — 人工待签池触发器（20261010 维护者令「人工待签池加触发器」）

镜像 mine_trigger（挖掘到期）成熟形制：读数→快照→Δ 阈值→响亮横幅→exit 1。
挖掘触发器盯"新材料够不够挖"，本件盯"**待签积压够不够疼**"——人闸是飞轮下半圈，
积压只涨不吠=飞轮空转（19 条积压两天才清的实录在案，条目 604/607）。

读数（measure，三路）：
  loose_drafts       在役草案数（gov=draft、非墓碑/机撤/标本/自纠标——人闸可签面）
  oldest_draft_days  最老草案龄（天；取 gov_events 的 add 事件 at；无事件=0 不计龄）
  family_candidates  族谱候选组数（style_registry.json 待人签；缺文件=0 不报错）

到期（check）：Δ新增草案 ≥ 阈值（默认 8，与挖掘同节奏）**或** 最老草案龄 ≥ 龄限
（默认 3 天——积压两天中位是实际疼点）→ 打印【待签到期】横幅 + exit 1。
mark：签发批后落快照顺延（promote 脚本收尾调用）。签发消耗积压 → Δ 负数按 0 计
（清账不算债，同 mine 的"产物被清不算负数债"）。

用法：
  py gov/sign_trigger.py check [--threshold N] [--age-days N]
  py gov/sign_trigger.py mark
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # 仓根（evocore 包所在——
# 直跑 CLI 的 subprocess 无导入方代插路径，20261010 实测 ModuleNotFoundError 根因）

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
STATE = os.path.join(_HERE, "style_mine_out", "sign_state.json")
REGISTRY = os.path.join(_HERE, "style_mine_out", "style_registry.json")
DEFAULT_THRESHOLD = 8          # 与 mine_trigger 同节奏
DEFAULT_AGE_DAYS = 3           # 积压两天中位=实际疼点（条目 607 实录）


def _loose(entries: list) -> list:
    """人闸可签面：在役草案（非墓碑/机撤/标本/自纠标）。"""
    return [e for e in entries
            if e.get("gov") == "draft"
            and not e.get("tombstone")
            and not e.get("machine_retracted")
            and not (e.get("facts") or {}).get("specimen")
            and not (e.get("facts") or {}).get("self_error")]


def measure(store_path: str = DEFAULT_STORE) -> dict:
    """当前读数：在役草案数 + 最老草案龄（天）+ 族谱候选组数。"""
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    loose = _loose(store.entries)
    added_at = {}
    for ev in store.gov_events:
        if ev.get("kind") == "add" and ev.get("id") and ev.get("at"):
            prev = added_at.get(ev["id"])
            if prev is None or str(ev["at"]) < prev:
                added_at[ev["id"]] = str(ev["at"])
    now = time.time()
    oldest = 0.0
    for e in loose:
        at = added_at.get(e["id"])
        if not at:
            continue
        try:
            age = (now - datetime.datetime.fromisoformat(at).timestamp()) / 86400
        except ValueError:
            continue
        oldest = max(oldest, age)
    fam = 0
    try:
        reg = json.load(open(REGISTRY, encoding="utf-8"))
        fam = len(reg.get("family_candidates") or reg.get("families") or [])
    except (OSError, ValueError):
        pass
    return {"loose_drafts": len(loose), "oldest_draft_days": round(oldest, 1),
            "family_candidates": fam}


def load_state(state_path: str = STATE) -> dict | None:
    try:
        return json.load(open(state_path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_state(cur: dict, threshold: int, age_days: int,
               state_path: str = STATE) -> None:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    json.dump({"last_mark_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "threshold": threshold, "age_days": age_days,
               "snapshot": cur},
              open(state_path, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)


def check(threshold: int | None = None, age_days: int | None = None,
          state_path: str = STATE, store_path: str = DEFAULT_STORE) -> dict:
    """到期判定：Δ新增草案 ≥ 阈值 或 最老草案龄 ≥ 龄限 → due。首跑静默建基线。"""
    cur = measure(store_path)
    st = load_state(state_path)
    th = threshold if threshold is not None else (st or {}).get("threshold",
                                                                DEFAULT_THRESHOLD)
    ad = age_days if age_days is not None else (st or {}).get("age_days",
                                                              DEFAULT_AGE_DAYS)
    if st is None:
        save_state(cur, th, ad, state_path)   # 首跑建基线（宽限不空报，同 mine）
        return {"due": False, "first": True, "d_new": 0, "threshold": th,
                "oldest": cur["oldest_draft_days"], "age_days": ad, **cur}
    snap = st.get("snapshot") or {}
    d_new = max(0, cur["loose_drafts"] - snap.get("loose_drafts", 0))
    oldest = cur["oldest_draft_days"]
    fam = cur["family_candidates"]
    due = d_new >= th or oldest >= ad
    why = ("Δ新增" if d_new >= th else "") + \
          ("+龄限" if oldest >= ad and d_new >= th else
           ("龄限" if oldest >= ad else ""))
    return {"due": due, "first": False, "d_new": d_new, "threshold": th,
            "oldest": oldest, "age_days": ad, "family_candidates": fam,
            "why": why, "last_mark_at": st.get("last_mark_at", "?"), **cur}


def mark(threshold: int | None = None, age_days: int | None = None,
         state_path: str = STATE, store_path: str = DEFAULT_STORE) -> dict:
    cur = measure(store_path)
    th = threshold if threshold is not None else DEFAULT_THRESHOLD
    ad = age_days if age_days is not None else DEFAULT_AGE_DAYS
    save_state(cur, th, ad, state_path)
    return cur


def _due_mark(cur: dict, th: int, ad: int, state_path: str = STATE) -> int:
    """到期标记：写快照顺延（批后钩子即调；挖掘到期同款）。"""
    save_state(cur, th, ad, state_path)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="人工待签池触发器")
    ap.add_argument("cmd", nargs="?", default="check", choices=("check", "mark"))
    ap.add_argument("--threshold", type=int, default=None)
    ap.add_argument("--age-days", type=int, default=None)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--state", default=STATE)
    a = ap.parse_args(argv)
    if a.cmd == "mark":
        cur = mark(a.threshold, a.age_days, a.state, a.store)
        print(f"[待签] 快照已记：{cur}")
        return 0
    r = check(a.threshold, a.age_days, a.state, a.store)
    if r["first"]:
        print(f"[待签] 首跑建基线（宽限不空报）：loose={r['loose_drafts']} "
              f"oldest={r['oldest_draft_days']}d family={r['family_candidates']}")
        return 0
    tag = f"（{r['why']}）" if r["why"] else ""
    if r["due"]:
        print(f"【待签到期】自上次签发（{r['last_mark_at']}）以来新增草案 "
              f"{r['d_new']} 条（阈值 {r['threshold']}）· 最老草案 {r['oldest']} 天"
              f"（龄限 {r['age_days']}）· 族谱候选 {r['family_candidates']} 组{tag}"
              "——人闸是飞轮下半圈，积压只涨不吠=空转。签发批后 py gov/sign_trigger.py mark 顺延")
        return 1
    print(f"[待签] 未到期：Δ新增 {r['d_new']}（阈值 {r['threshold']}）· "
          f"最老草案 {r['oldest']} 天（龄限 {r['age_days']}）· "
          f"族谱候选 {r['family_candidates']} 组")
    return 0


if __name__ == "__main__":
    sys.exit(main())
