# -*- coding: utf-8 -*-
"""self_correct.py — 自纠通道（维护者令 20261010「你自己纠自己的错…这才叫 LLM 的自动飞轮」）

缺口实锤：纠错环路的根入口（auto_heal.wrong_roots）只认**人签件**——墓碑+标本都是人签
动作。AI 自己发现/承认的错没有入口，只能等人判。本件补上这个入口：

  confess(id, note)：AI 自判错误入环——
    ① amend 打标：facts.self_error={note,at,by,evidence} + facts.specimen="ai-self-error"
       （amend 机器面无闸；**gov 字段不动**——deprecate/tombstone/promote 仍人闸专属）；
    ② 标本化后自动成为纠错环路根（auto_heal.wrong_roots 认 live 标本）→ 连坐传播照常生效；
    ③ 贝叶斯转正档（act·error 根）即时跑该根：榜一纯引用 draft 下架（relist 可复架）；
    ④ obs 流写异常行（对照=true）→ 负例雷达/审计自动入账——同一错误模式进 preflight 告警面。

**红线**：
  - 只收 draft：approved/verified 拒收（DENY:RATIFIED，人签面走 precedent_cli 人闸）；
  - 已墓碑件拒收（已是人签结论，无需自纠）；
  - 幂等：已自纠件二次 confess 只报告不重复落标；
  - 一切动作可逆（relist 复架；打标 amend 可人签改回），全程事件留痕。

用法：
  py -X utf8 self_correct.py confess --id X --note "错在哪" [--evidence f.png] [--store P]
  py -X utf8 self_correct.py stats [--obs P]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import edge_graph as eg                       # noqa: E402
import bayes_shadow as bs                     # noqa: E402

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_OBS = os.path.join(os.path.dirname(_HERE), "field", "out",
                           "selferr_obs.jsonl")
SPECIMEN_TAG = "ai-self-error"


def confess(eid: str, note: str, evidence: str = "", actor: str = "ai:self",
            store_path: str = DEFAULT_STORE, obs_path: str = DEFAULT_OBS) -> dict:
    """AI 自判错误入环：打标→贝叶斯 act→环路清扫→obs 入账。返回各步凭据。"""
    if not note or not note.strip():
        raise SystemExit("DENY:NO_NOTE 自纠必须写明错在哪（无反思不入环）")
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    try:
        e = store._get(eid)
    except Exception as ex:                                 # noqa: BLE001
        raise SystemExit(f"DENY:NO_ENTRY {eid} 不在库（{type(ex).__name__}）")
    if e.get("tombstone"):
        raise SystemExit(f"SKIP:TOMBSTONED {eid} 已被人签墓碑——无需自纠")
    if e.get("gov") in ("approved", "verified"):
        raise SystemExit(f"DENY:RATIFIED {eid} 是人签面（{e.get('gov')}）——"
                         "自纠通道只收草案；人签面纠错走 precedent_cli（人闸专属）")
    f = e.get("facts") or {}
    if f.get("self_error"):
        return {"confessed": False, "why": "已自纠过（幂等）", "id": eid,
                "self_error": f["self_error"]}
    f["self_error"] = {"note": note.strip(), "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "by": actor, "evidence": evidence or ""}
    f.setdefault("specimen", SPECIMEN_TAG)                  # 标本化=进纠错环路根集合
    store.amend(eid, {"facts": f},
                reason=f"自纠入环：{note.strip()[:60]}", actor=actor)
    store.save(store_path)
    # ③ 贝叶斯 act（转正缺省档）：即时对自纠根跑榜一动作
    g = eg.extract_graph(PrecedentStore.load(store_path).entries)
    rb = bs.run(g, eid, store_path=store_path, root_kind="error")
    # ④ obs 异常行（对照=true → 负例雷达可动作）
    os.makedirs(os.path.dirname(obs_path), exist_ok=True)
    obs_line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "类": "异常",
                "现象": f"自纠[{eid}] {note.strip()}",
                "条件": "自纠通道（AI 自判错误）",
                "证据": evidence or "见条目 facts.self_error",
                "对照": True, "可复算": f"store:{eid} facts.self_error"}
    with open(obs_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obs_line, ensure_ascii=False) + "\n")
    return {"confessed": True, "id": eid, "note": note.strip(),
            "bayes_mode": rb["mode"],
            "bayes_acted": rb.get("acted"),
            "obs_line": obs_line}


def stats(obs_path: str = DEFAULT_OBS) -> dict:
    n, items = 0, []
    if os.path.isfile(obs_path):
        for line in open(obs_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("条件") == "自纠通道（AI 自判错误）":
                n += 1
                items.append(r)
    return {"self_errors": n, "last": items[-3:]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="自纠通道（AI 自判错误入纠错环路）")
    ap.add_argument("cmd", choices=("confess", "stats"))
    ap.add_argument("--id", default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--evidence", default="")
    ap.add_argument("--actor", default="ai:self")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--obs", default=DEFAULT_OBS)
    a = ap.parse_args(argv)
    if a.cmd == "stats":
        s = stats(a.obs)
        print(f"[自纠通道] 累计自纠 {s['self_errors']} 次")
        for it in s["last"]:
            print(f"  {it.get('ts')} {str(it.get('现象'))[:70]}")
        return 0
    if not a.id or not a.note:
        raise SystemExit("confess 须 --id X --note '错在哪'")
    r = confess(a.id, a.note, a.evidence, a.actor, a.store, a.obs)
    if r["confessed"]:
        print(f"[自纠] {r['id']} 已入环：标本化+贝叶斯 act（模式 {r['bayes_mode']}）")
        ax = r.get("bayes_acted") or {}
        if ax.get("acted"):
            print(f"  ▶ 榜一动作 {ax['action']} → {ax['acted']}")
        elif ax:
            print(f"  ▷ 榜一未动：{ax.get('why')}")
        print(f"  obs 异常行已入账（负例雷达下一轮生效）")
    else:
        print(f"[自纠] {r['id']} 未动：{r.get('why')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
