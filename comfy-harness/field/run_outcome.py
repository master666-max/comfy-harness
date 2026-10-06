# -*- coding: utf-8 -*-
"""run_outcome.py — 批二埋点常开助手（工单-经验飞轮优化统合-20261005 §三）

每个 field 实验收尾一行接线：run 的三态 verdict → 判例油量（outcome 轴）。
映射守三态诚实纪律：咬合→success、不咬合→failure、**登记盲区→跳过不落**
（盲区既不证实也不证伪，记哪边都是撒谎）；判例不在库（点题件/库缺席）容错跳过。
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CH = os.path.dirname(_HERE)
sys.path.insert(0, os.path.dirname(_CH))
sys.path.insert(0, os.path.join(_CH, "gov"))
from precedent_gov import PrecedentStore  # noqa: E402

SEED_PATH = os.path.join(_CH, "gov", "precedents_e2_seed.json")

_VERDICT_MAP = {"咬合": "success", "不咬合": "failure"}


def record_run_outcome(eid: str, verdict: str, context: str,
                       store_path: str = SEED_PATH, actor: str = "machine:field-run"):
    """run 收尾油量落账。返回落账记录；盲区/判例缺席返回 None（调用方照常收尾）。"""
    if verdict == "登记盲区":
        print(f"[outcome] {eid} 登记盲区——不落油量（三态诚实：盲区非成败）")
        return None
    result = _VERDICT_MAP.get(verdict)
    if result is None:
        print(f"[outcome] 未知 verdict {verdict!r}——跳过")
        return None
    try:
        store = PrecedentStore.load(store_path)
        rec = store.record_outcome(eid, result=result, context=context, actor=actor)
        store.save(store_path)
        print(f"[outcome] {eid} ← {result}（{context}）")
        return rec
    except (KeyError, FileNotFoundError, ValueError) as exc:
        print(f"[outcome] {eid} 跳过：{exc}")
        return None
