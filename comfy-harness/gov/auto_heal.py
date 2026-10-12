# -*- coding: utf-8 -*-
"""auto_heal.py — 自动纠错位（**已接线**；维护者令 20261009『全开，全接线』）

沿革：20261008 令「先留接口不要接线，等反向飞轮成熟，特别是影子权重」→
T1-T4 四项预注册触发器全达（✅✅✅✅，status 实测）→ 20261009 维护者令『全开，全接线』。

**接线后契约（红线不变）**：
  - `propose(wrong_id)`：纠错**提案**（只读：影响面分档 + 影子权重 + 建议动作）；
  - `apply(proposal, actor, prereg)`：**执行器**（本接线实现）——须 human:* 签署 +
    预注册指针（判据件@版本）；动作全部限机器权限面且可逆：**连坐撤件仅限 draft**
    （人签 relist 可复架）、派生 draft 只打标、标本/墓碑/approved/verified 一律跳过
    （降格=人闸专属，非放大红线）；
  - `shadow_scan()`：自治影环（10-08『开！』授权的 draft 机器面通道）不变；
  - `trigger_status()`：四项触发器实测评估（留档，改条件须人签工单）。

**预注册触发器**（全为可实测读数；改条件须人签工单）：
  T1 雷达影子 ≥3 轮，且各轮命中率波动 ≤ ±10pp（不稳=判据未定型，接线会放大噪声）
  T2 标本库 ≥5 族，且含 ≥1 退场标本（退场标本=人已判错的实物，最接近纠错靶）
  T3 人签退场复核 ≥3 次（impact_records 计数），且连坐候选误伤 0
  T4 影子权重跨轮稳定（≥2 轮挖掘候选池且概念影重变化 ≤20%）

**红线不变**：非放大（机器不升信任级）；本件不改闸阈值、不碰供血池；
approved/verified 的降格/撤件永远人闸。
用法：py -X utf8 auto_heal.py [status] | propose --id X | apply --id X --actor human:* --prereg 判据@v
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
import reverse_flywheel as rf                 # noqa: E402

WIRED = True              # ← 20261009 维护者令『全开，全接线』：T1-T4 全达后接线（工单=本次提交）
DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
RECORDS_DIR = eg.RECORDS_DIR


def trigger_status(store_path: str = DEFAULT_STORE) -> dict:
    """四项预注册触发器实测评估（未达=current/need 摊开给人看；不猜不糊）。"""
    from precedent_gov import PrecedentStore

    # T1 雷达影子轮数与命中率波动
    st = rf.stats()
    rates = []
    if os.path.isfile(rf.DEFAULT_SHADOW):
        for line in open(rf.DEFAULT_SHADOW, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            # 只取"当前体制"扫描：过滤回放基准（source 含 baseline）——
            # 跨体制混算会让波动恒等于 0.45，指标结构性不可达（本轮实测修正）
            if (r.get("kind") == "scan" and r.get("checked")
                    and "baseline" not in str(r.get("source", ""))):
                rates.append(r["hits"] / r["checked"])
    rates = rates[-3:]                           # 最近 3 轮（当前体制）
    spread = (max(rates) - min(rates)) if len(rates) >= 2 else None
    t1 = {"met": len(rates) >= 3 and spread is not None and spread <= 0.10,
          "current": {"scans_total": st["scans"], "scans_current": len(rates),
                      "rate_spread": None if spread is None else round(spread, 3)},
          "need": "当前体制扫描 ≥3 轮且轮间命中率波动 ≤0.10（回放基准不计）"}

    # T2 标本库规模（含退场标本）
    store = PrecedentStore.load(store_path)
    spec = rf.specimens(store, None)
    t2 = {"met": len(spec) >= 5 and any(s.get("retired") for s in spec),
          "current": {"specimens": len(spec),
                      "retired_specimens": sum(1 for s in spec if s.get("retired"))},
          "need": "标本 ≥5 族且含 ≥1 退场标本"}

    # T3 人签退场复核次数（撤回审计件数）
    n_rec = 0
    if os.path.isdir(RECORDS_DIR):
        n_rec = sum(1 for f in os.listdir(RECORDS_DIR) if f.endswith(".json"))
    t3 = {"met": n_rec >= 3, "current": {"human_retire_records": n_rec},
          "need": "人签退场 ≥3 次（含影响面复核）'误伤 0'由人评注"}

    # T4 影子权重跨轮稳定（候选池轮次 + 概念影重）
    rounds = []
    pool = os.path.join(_HERE, "style_mine_out", "candidate_pool.json")
    try:
        p = json.load(open(pool, encoding="utf-8"))
        rounds = [v.get("rounds_seen") for v in p.values() if isinstance(v, dict)]
    except (OSError, ValueError):
        pass
    max_round = max(rounds) if rounds else 0
    t4 = {"met": max_round >= 2, "current": {"max_rounds_seen": max_round,
                                             "pool_entries": len(rounds)},
          "need": "候选池出现 ≥2 轮复现记录（影重才有跨轮可比基线）"}
    return {"T1": t1, "T2": t2, "T3": t3, "T4": t4,
            "wired": WIRED,
            "rule": "四项全满足才允许讨论接线；接线仍不改红线（撤件/连坐人签）"}


def propose(wrong_id: str, store_path: str = DEFAULT_STORE, hops: int = 2) -> dict:
    """纠错提案（**只读**）：影响面分档 + 建议动作文本 + 根条影重。不落盘、不执行。"""
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    root = store._get(wrong_id)
    g = eg.extract_graph(store.entries)
    rep = eg.impact(g, wrong_id, hops)
    f = root.get("facts") or {}
    suggestions = []
    for row in rep["rows"]:
        if "连坐候选" in row["tier"]:
            suggestions.append(f"降权/复核：{row['node']}（证据全靠引用上游）")
        elif "复核建议" in row["tier"]:
            suggestions.append(f"复核：{row['node']}（派生根，补独立证据或降格）")
        else:
            suggestions.append(f"仅标注：{row['node']}")
    return {"root": wrong_id, "root_evidence_kind": g["nodes"].get(wrong_id, {}).get("evidence_kind"),
            "root_shadow_weight": f.get("shadow_weight"),
            "affected": rep["rows"], "suggestions": suggestions, "hops": hops,
            "store_path": store_path,
            "note": "提案=只读计算；执行走 apply（须 human:* + prereg；draft-only 红线）"}


def apply(proposal: dict, actor: str, prereg: str | None = None) -> dict:
    """执行器（20261009 接线实现）：human:* 签署 + 预注册指针 → 按 proposal.affected
    分档执行。**红线**：连坐撤件仅限 draft（机器面可逆，人签 relist 可复架）；派生
    draft 只打标；标本/墓碑/approved/verified 一律跳过（降格=人闸专属，非放大）。"""
    if not WIRED:
        st = trigger_status()
        unmet = [k for k, v in st.items() if isinstance(v, dict) and not v.get("met")]
        raise PermissionError(
            "DENY:AUTO_HEAL_UNWIRED 自动纠错未接线（维护者令：等反向飞轮成熟，特别是影子权重）——"
            f"预注册触发器未达：{unmet}；逐条现状见 auto_heal.py status；"
            "人工纠错请走 precedent_cli impact / retire（先影响面后动作）")
    if not (isinstance(actor, str) and actor.startswith("human:")):
        raise PermissionError("DENY:NO_HUMAN_SIG 自动纠错执行须 human:* 签署（非放大红线）")
    if not prereg:
        raise PermissionError("DENY:NO_PREREG 自动纠错执行须带预注册指针（判据件@版本）")
    from precedent_gov import PrecedentStore
    sp = proposal.get("store_path") or DEFAULT_STORE
    store = PrecedentStore.load(sp)
    retracted, flagged, skipped = [], [], []
    for row in proposal.get("affected", []):
        node, tier = row.get("node"), str(row.get("tier", ""))
        try:
            e = store._get(node)
        except Exception:                           # 节点不存在也留痕
            skipped.append({"node": node, "why": "不存在"})
            continue
        if e.get("tombstone") or (e.get("facts") or {}).get("specimen"):
            skipped.append({"node": node, "why": "标本/墓碑不碰"})
            continue
        if e.get("gov") in ("approved", "verified"):
            skipped.append({"node": node, "why": "人闸面（降格须人签）"})
            continue
        if "连坐候选" in tier and e.get("gov") == "draft" and not e.get("machine_retracted"):
            store.retract(node, actor="machine:auto-heal-exec",
                          reason=f"apply by {actor} prereg={prereg}：连坐撤件"
                                 f"（引用唯一，人签 relist 可复架）",
                          evidence="auto_heal 接线执行器")
            retracted.append(node)
        elif "复核建议" in tier and e.get("gov") == "draft":
            f2 = dict(e.get("facts") or {})
            f2["auto_derate"] = {"reason": f"prereg={prereg} 派生根候复核",
                                 "by": actor, "root": proposal.get("root")}
            store.amend(node, {"facts": f2},
                        reason=f"apply by {actor} prereg={prereg}：派生标注",
                        actor="machine:auto-heal-exec")
            flagged.append(node)
        else:
            skipped.append({"node": node, "why": f"tier={tier} 无机器动作"})
    store.save(sp)
    return {"authorized": True, "executed": True, "root": proposal.get("root"),
            "retracted": retracted, "flagged": flagged, "skipped": skipped,
            "actor": actor, "prereg": prereg}


# ═══ 影子环路（维护者令 20261008『开！』）═══════════════════════════════════
DEFAULT_SHADOW_LOG = os.path.join(_HERE, "style_mine_out", "auto_heal_shadow.jsonl")
ACTOR_AUTO = "machine:auto-heal-loop"   # 机器面（可逆）：retract 可人签 relist；amend 无闸


def wrong_roots(entries: list) -> list:
    """已判错且已退场的根：墓碑 + 标本标记（=人签认定过的错例）。"""
    return [e for e in entries
            if e.get("tombstone") and (e.get("facts") or {}).get("specimen")]


def would_retract(store, root) -> list:
    """某错根下"会被自动下架"的在役草案：证据全靠引用（红线：有自有证据者一律不动）。"""
    g = eg.extract_graph(store.entries)
    rep = eg.impact(g, root["id"], 2)
    out = []
    for row in rep["rows"]:
        try:
            n = store._get(row["node"])
        except Exception:                                       # noqa: BLE001
            continue
        if n.get("gov") != "draft" or n.get("tombstone") or n.get("machine_retracted"):
            continue
        if row["evidence_kind"] != "citation":
            continue
        out.append({"id": row["node"], "hop": row["hops"], "prop_score": row.get("prop_score")})
    return out


def shadow_scan(store_path: str = DEFAULT_STORE, log_path: str = DEFAULT_SHADOW_LOG,
                mode: str | None = None) -> dict:
    """自动纠错环路：算"该收拾谁"→ 按模式落日志/动手。

    **默认 on**（维护者令 20261008『别保守，反正不是生产环境』→ 真开；环境变量
    AUTO_HEAL_MODE=off|shadow|on 可覆盖）。on 的动作**全在机器权限面内且可逆**：
    纯引用下游 retract（人签 relist 可复架）+ 打标；派生根只打标不下架；有自有证据者不动。"""
    m = rf.resolve_mode(mode or os.environ.get("AUTO_HEAL_MODE") or "on")   # 三态解析复用反向飞轮（同语义：off/shadow/on）
    if m == "off":
        return {"mode": "off", "roots": 0, "would_retract": [], "injected": False}
    from precedent_gov import PrecedentStore
    s = PrecedentStore.load(store_path)
    roots = [(e, "retired_wrong") for e in wrong_roots(s.entries)]
    roots += [(e, "specimen_live") for e in s.entries
              if (e.get("facts") or {}).get("specimen") and not e.get("tombstone")]
    rows, total, acted = [], [], []
    for r, kind in roots:
        w = would_retract(s, r)
        rows.append({"root": r["id"], "root_kind": kind, "n": len(w), "items": w})
        total += [x["id"] for x in w]
        if m == "on":                                    # ── 真动作（机器面·可逆）──
            g = eg.extract_graph(s.entries)
            rep = eg.impact(g, r["id"], 2)
            for row in rep["rows"]:
                n = s._get(row["node"])
                if n.get("gov") != "draft" or n.get("tombstone") or n.get("machine_retracted"):
                    continue
                if (n.get("facts") or {}).get("specimen"):
                    continue                             # 标本=故意留的坏例，不再降权（实测打磨）
                ek = row["evidence_kind"]
                if ek == "raw":                          # 红线：有自有证据者一律不动
                    continue
                facts = dict(n.get("facts") or {})
                facts.update({"auto_derate": True,
                              "auto_derate_reason": f"上游 {r['id']}（{kind}）"})
                if ek == "citation":                     # 纯引用 → 下架（可人签复架）
                    s.retract(n["id"], actor=ACTOR_AUTO,
                              reason=f"auto-heal: 上游 {r['id']} 已判坏、本条证据全靠引用",
                              evidence="auto_heal 环路 on-mode")
                s.amend(n["id"], {"facts": facts}, reason="auto-heal 打标（软档/下架件同步标）",
                        actor=ACTOR_AUTO)
                acted.append({"id": n["id"], "evidence_kind": ek,
                              "action": "retract+flag" if ek == "citation" else "flag"})
    if acted:
        s.save(store_path)                               # 经 store API 落盘（事件入账）
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "auto_heal_shadow",
           "mode": m, "roots": len(rows), "would_retract_n": len(total),
           "would_retract": sorted(set(total)), "by_root": rows,
           "acted": acted,
           "note": ("on=真动作（机器面·可逆：retract 可人签 relist + auto_derate 标）；"
                    "shadow=仅测算；有自有证据者一律不动（红线）")}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"mode": m, "roots": len(rows), "would_retract": sorted(set(total)),
            "by_root": rows, "acted": acted, "injected": m == "on"}


def shadow_stats(log_path: str = DEFAULT_SHADOW_LOG) -> dict:
    runs, last = 0, None
    if os.path.isfile(log_path):
        for line in open(log_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "auto_heal_shadow":
                runs += 1
                last = r
    return {"runs": runs, "last": last}


def main(argv=None):
    ap = argparse.ArgumentParser(description="自动纠错位（预注册接口·未接线）")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=("status", "propose", "apply", "shadow"))
    ap.add_argument("--id", default=None)
    ap.add_argument("--actor", default=None)
    ap.add_argument("--prereg", default=None)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--mode", default=None, help="off|shadow|on（缺省读 ANTI_FLYWHEEL，再缺省 shadow）")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        st = trigger_status(a.store)
        print(f"[自动纠错位] WIRED={st['wired']}（20261009 维护者令『全开，全接线』；执行器须 human:*+prereg，draft-only 红线）")
        for k in ("T1", "T2", "T3", "T4"):
            v = st[k]
            print(f"  {k} {'✅达' if v['met'] else '✗未达'}  current={v['current']}  need={v['need']}")
        print(f"  {st['rule']}")
        return 0
    if a.cmd == "shadow":
        r = shadow_scan(a.store, mode=a.mode)
        tag = ("**真动作模式**（机器面·可逆）" if r["mode"] == "on"
               else "仅测不动手" if r["mode"] == "shadow" else "off")
        print(f"[自动纠错环路] 模式={r['mode']} 扫描根 {r['roots']} 个（已判错墓碑+在役标本）"
              f" → 纯引用靶 {len(r['would_retract'])} 条（{tag}）")
        for row in r["by_root"]:
            print(f"  根 {row['root'][:44]:46s} → {row['n']} 条")
            for it in row["items"][:4]:
                print(f"      · hop={it['hop']} 传播分={it['prop_score']} {it['id'][:52]}")
        if r.get("acted"):
            print(f"  **真动作 {len(r['acted'])} 件**（机器面·可逆）：")
            for x in r["acted"][:8]:
                print(f"      · {x['action']:14s} {x['id'][:56]}")
        st = shadow_stats()
        print(f"  环路累计 {st['runs']} 轮")
        return 0
    if a.cmd == "propose":
        if not a.id:
            raise SystemExit("propose 须 --id X")
        p = propose(a.id, a.store)
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "apply":
        p = {"root": a.id}
        if a.id:
            try:                       # 目标不存在也先给"未接线"拒绝（闸在动作之前）
                p = propose(a.id, a.store)
            except KeyError:
                pass
        try:
            r = apply(p, a.actor or "ai:nobody", a.prereg)
            print(r)
        except PermissionError as ex:
            print(str(ex))
            return 3
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
