# -*- coding: utf-8 -*-
"""edge_graph.py — 有向经验图（派生投影 · 维护者令 20261008）

**回答的问题**："知识/经验有连接性与因果性，能否再加一种『有向向量』标注过程性？"
工程翻译：向量库里的向量是**点**（无向、无箭头），而"连接/因果"是**边**。
所以要加的不是"另一种向量"，而是一张**有向边表**（edge table）——点归向量、线归边表。
本件=从现有数据里**提取**已存在的边（零新字段、零库改写入），做成可查询的有向图：

  边类型（全部可从现行字段导出）：
    merged-from  由 facts.merged_from 导出（旧条 → 合并条）：血缘/派生
    cites        正文/证据里出现另一条目 id（源 → 被引）：引用（附出处片段）
    cluster-mate 同 _mine_sig（对称边，标 sym）：同簇共源
    base-mate    同 S- 名字基底（对称边）：跨代同概念

  能力：
    impact <id>  影响面报告（目的1：揪错后的爆炸半径控制）——BFS 下游，
                 每条受影响件按 跳数 × 证据独立性 分档：
                   证据只靠引用上游 + 1 跳 → **连坐候选（高）**，人签才动
                   自有实测证据（generation:/图/脚本） → 低（自证，不宜连坐）
                   经挖掘产物为证（派生根） → 中（复核建议）
                   2 跳及以上 → 仅标注（防连坐扩大化）
    cycles       有向环检测（自食铁证：非同名的循环引用）
    stats        规模读数

**纪律**：本件是**派生投影**（可全量重建、不写受治库）；影响面只出**报告**，
连坐/减权/连根拔起一律人签执行（非放大红线：机器不得自行扩散处置）。
用法：
  py -X utf8 edge_graph.py build [--out P] [--store P]
  py -X utf8 edge_graph.py impact <id> [--hops 2]
  py -X utf8 edge_graph.py cycles
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_OUT = os.path.join(_HERE, "style_mine_out", "edge_graph.json")
MAX_CYCLE_LEN = 4


def _text_of(e: dict) -> str:
    c = e.get("content")
    s = json.dumps(c, ensure_ascii=False) if isinstance(c, (dict, list)) else str(c or "")
    return " ".join([s, json.dumps(e.get("evidence"), ensure_ascii=False),
                     " ".join(str(k) for k in (e.get("keywords") or []))])


def evidence_kind(e: dict) -> str:
    """证据独立性三档：raw=自有实测 / derived=挖掘产物（派生根）/ citation=只引条目 / unknown。"""
    ids = e.get("_all_ids") or set()
    ev = e.get("evidence") or {}
    art = str(ev.get("artifact") or "") if isinstance(ev, dict) else str(ev)
    if re.search(r"generation:|\.png|\.py|外部源|论文|arXiv", art):
        return "raw"
    if "style_mine_out/" in art or "挖掘" in art:
        return "derived"
    if any(i in art for i in ids if i != e["id"]):
        return "citation"
    return "unknown"


def extract_graph(entries: list) -> dict:
    """条目 → {nodes, edges}（纯函数；不写库）。"""
    # 墓碑件**保留为历史节点**（审计窗口语义）：若剔除，撤回后就查不到"谁依赖过它"
    # ——实测缺口：库里唯一墓碑有 4 个活条目引用，图里却零边
    live = list(entries)
    ids = {e["id"] for e in live}
    for e in live:
        e["_all_ids"] = ids                    # 证据分类需全 id 表（临时字段，消费后即弃）

    def _state(e):
        if e.get("tombstone"):
            return "tombstone"
        if e.get("deprecated"):
            return "deprecated"
        if e.get("machine_retracted"):
            return "retracted"
        return "live"

    nodes = {e["id"]: {"gov": e.get("gov"), "kind": e.get("kind"),
                       "live": _state(e) == "live",
                       "state": _state(e),
                       "specimen": bool((e.get("facts") or {}).get("specimen")),
                       "shadow_weight": (e.get("facts") or {}).get("shadow_weight"),
                       "evidence_kind": evidence_kind(e)} for e in live}
    edges = []
    for e in live:
        f = e.get("facts") or {}
        for old in (f.get("merged_from") or []):
            if old in ids:
                edges.append({"up": old, "down": e["id"], "type": "merged-from",
                              "why": "facts.merged_from（旧条是上游）"})
        body = _text_of(e)
        for other in sorted(ids):
            if other == e["id"] or other not in body:
                continue
            if other in (f.get("merged_from") or []):     # 已被 merged-from 记过，不重复
                continue
            i = body.find(other)
            edges.append({"up": other, "down": e["id"], "type": "cites",
                          "why": "id 出现于正文/证据（被引者是上游）",
                          "quote": body[max(0, i - 24):i + len(other) + 8]})
    by_sig, by_base = {}, {}
    for e in live:
        if e.get("_mine_sig"):
            by_sig.setdefault(str(e["_mine_sig"]), []).append(e["id"])
        eid = e["id"]
        if eid.startswith("S-"):
            by_base.setdefault(eid.rsplit("-", 1)[0].lower(), []).append(eid)
    seen_pairs = set()
    for group, typ in ((by_sig, "cluster-mate"), (by_base, "base-mate")):
        for key, members in sorted(group.items()):
            if len(members) < 2 or len(members) > 8:
                continue
            ms = sorted(members)
            for a in range(len(ms)):
                for b in range(a + 1, len(ms)):
                    if (ms[a], ms[b]) in seen_pairs:        # 同簇+同基底重合时只留一条
                        continue
                    seen_pairs.add((ms[a], ms[b]))
                    edges.append({"up": ms[a], "down": ms[b], "type": typ, "sym": True,
                                  "why": f"同{'签名' if typ == 'cluster-mate' else '基底'}:{key[:16]}"})
    for e in live:
        e.pop("_all_ids", None)
    counts = {"nodes": len(nodes),
              "live": sum(1 for v in nodes.values() if v["live"]),
              "edges": len(edges),
              "by_type": {t_: sum(1 for e in edges if e["type"] == t_)
                          for t_ in ("merged-from", "cites", "cluster-mate", "base-mate")}}
    return {"nodes": nodes, "edges": edges, "counts": counts}


def _adjacency(graph: dict) -> dict:
    """下游邻接：up → down（对称边双向）。"""
    adj = {}
    for e in graph["edges"]:
        adj.setdefault(e["up"], []).append(e)
        if e.get("sym"):
            adj.setdefault(e["down"], []).append({"up": e["down"], "down": e["up"],
                                                  "type": e["type"] + "（对称）", "why": e["why"]})
    return adj


EDGE_W = {"merged-from": 1.0, "cites": 0.8, "base-mate": 0.5, "cluster-mate": 0.5}
LAMBDA_DECAY = 0.6          # 每远一跳的折扣
DAMPING = 0.85              # 环上阻尼
ITERS = 12                  # 固定迭代次数（可复算）
RAW_SELF_EVIDENCE_DISCOUNT = 0.3   # 自带实测证据的下游：受污染分打折（引用≠同错）


def propagate(graph: dict, root: str, weights: dict | None = None,
              lam: float = LAMBDA_DECAY, damping: float = DAMPING,
              iters: int = ITERS) -> dict:
    """加权衰减传播（确定性；只读）。返回 {node: {score, hop, via, chain}}。

    score(d) 由上游传入的分数 × 边权 × λ^跳数累加；环上按 damping 迭代收敛。
    自带 raw 实测证据的下游打 RAW_SELF_EVIDENCE_DISCOUNT 折（引用≠同错）。
    """
    w = dict(EDGE_W if weights is None else weights)
    adj = _adjacency(graph)
    # 先做确定性 BFS 记录 hop/via（用于 λ^hop 与来源链）
    hop, via = {root: 0}, {root: None}
    frontier = [root]
    for h in range(1, 6):
        nxt = []
        for cur in frontier:
            for e in adj.get(cur, []):
                d = e["down"]
                if d in hop:
                    continue
                hop[d] = h
                via[d] = {"from": cur, "type": e["type"], "why": e.get("why", "")}
                nxt.append(d)
        frontier = nxt
    # 阻尼迭代（确定性：固定次数，节点序固定）
    score = {root: 1.0}
    for _ in range(iters):
        new = {root: 1.0}
        for cur in sorted(adj):
            for e in adj.get(cur, []):
                d = e["down"]
                if d not in hop:
                    continue
                nk = graph["nodes"].get(d, {})
                disc = (RAW_SELF_EVIDENCE_DISCOUNT
                        if nk.get("evidence_kind") == "raw" and nk.get("state") != "tombstone"
                        else 1.0)
                # 衰减语义=每远一跳打一次折（λ），经父分数天然复利；
                # 初版写成 λ^hop 与父分数里的 λ 双重衰减（实测抓出）
                val = (score.get(cur, 0.0) * w.get(e["type"], 0.5)
                       * lam * disc)
                new[d] = max(new.get(d, 0.0), val)
        # 迭代键集=新旧并集（初版只用旧键集→新节点永远进不来，实测抓出）
        for k in sorted(set(score) | set(new)):
            if k == root:
                continue
            score[k] = damping * max(new.get(k, 0.0), 0.0) + (1 - damping) * score.get(k, 0.0)
        score[root] = 1.0
    out = {}
    for n, s in score.items():
        if n == root or s <= 0:
            continue
        out[n] = {"score": round(s, 4), "hop": hop.get(n, 0), "via": via.get(n),
                  "state": (graph["nodes"].get(n) or {}).get("state")}
    return out


def impact(graph: dict, eid: str, hops: int = 2) -> dict:
    """影响面报告：下游 BFS（目的1）。分档=证据独立性 × 跳数；**只报告不动手**。"""
    adj = _adjacency(graph)
    seen = {eid: (0, None)}
    frontier = [eid]
    for h in range(1, hops + 1):
        nxt = []
        for cur in frontier:
            for e in adj.get(cur, []):
                d = e["down"]
                if d in seen:
                    continue
                seen[d] = (h, e)
                nxt.append(d)
        frontier = nxt
    prop = propagate(graph, eid)                 # 加权衰减传播（只读呈现）
    rows = []
    for node, (h, via) in sorted(seen.items()):
        if node == eid:
            continue
        n = graph["nodes"].get(node, {})
        if n.get("state") == "tombstone":
            tier = "历史（已墓碑·仅供追溯）"
        elif not n.get("live", True):
            tier = "历史（已下架）"
        elif h == 1 and n.get("evidence_kind") in ("citation", "unknown"):
            tier = "**连坐候选（高）**：证据全靠引用上游"
        elif n.get("evidence_kind") == "derived":
            tier = "复核建议（中）：证据为挖掘产物（派生根）"
        elif h == 1 and n.get("evidence_kind") == "raw":
            tier = "低（自证）：自有实测证据，不宜连坐"
        else:
            tier = "仅标注（防连坐扩大化）"
        rows.append({"node": node, "hops": h, "via": (via or {}).get("type"),
                     "evidence_kind": n.get("evidence_kind"), "tier": tier,
                     "gov": n.get("gov"), "specimen": n.get("specimen"),
                     "prop_score": (prop.get(node) or {}).get("score")})
    o = [[r for r in rows if r["hops"] == h] for h in range(1, hops + 1)]
    root_state = (graph["nodes"].get(eid) or {}).get("state")
    note = "只出影响面报告；连坐/减权/拔起一律人签（非放大红线）"
    if root_state == "tombstone":
        note = "**事后查询（根已墓碑）**：以下皆为仍存的下游依赖者——" + note
    return {"root": eid, "hops": hops, "total": len(rows), "by_hop": o, "rows": rows,
            "root_state": root_state, "note": note}


def cycles(graph: dict, max_len: int = MAX_CYCLE_LEN) -> list:
    """有向环（非同名的循环引用=自食铁证）。对称边不参与环判定。"""
    adj = {}
    for e in graph["edges"]:
        if e.get("sym"):
            continue
        adj.setdefault(e["up"], []).append(e["down"])
    out, seen_keys = [], set()
    nodes = sorted(adj)

    def dfs(start, path, on_path):
        if len(path) > max_len:
            return
        for nxt in adj.get(path[-1], []):
            if nxt == start and len(path) >= 2:
                key = "→".join(sorted(path))
                if key not in seen_keys:
                    seen_keys.add(key)
                    out.append(list(path) + [start])
            elif nxt not in on_path and nxt > start:      # 规范化：只从最小 id 起环
                dfs(start, path + [nxt], on_path | {nxt})
    for s in nodes:
        dfs(s, [s], {s})
    return out


RECORDS_DIR = os.path.join(_HERE, "style_mine_out", "impact_records")


def impact_text(rep: dict) -> str:
    """影响面报告的文本呈现（人审用；一键出"波及清单"）。"""
    L = [f"[影响面] 根={rep['root']} · 受影响 {rep['total']} 条 · {rep['note']}"]
    for h, rows in enumerate(rep["by_hop"], 1):
        if not rows:
            continue
        L.append(f"  {h} 跳（{len(rows)}）：")
        for x in rows:
            ps = x.get("prop_score")
            L.append(f"    {x['tier']:40s} {x['node'][:52]:54s} via={x['via']}"
                     f"{'' if ps is None else '  传播分=' + str(ps)}")
    if not rep["total"]:
        L.append("  （无下游——撤下它不会波及任何条目）")
    return "\n".join(L)


def save_impact_record(rep: dict, meta: dict, out_dir: str | None = None) -> str:
    """撤回审计入账（目的7）：撤回动作前的影响面快照落盘，可回答"这次教训波及过谁"。
    out_dir 晚绑定（None→RECORDS_DIR）：默认参数在定义期求值，测试补丁会失效（实测事故）。"""
    out_dir = out_dir or RECORDS_DIR
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, f"{rep['root']}-{time.strftime('%Y%m%dT%H%M%S')}.json")
    json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "root": rep["root"],
               "meta": meta, "impact": rep},
              open(fp, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    return fp


def build(store_path: str = DEFAULT_STORE, out: str = DEFAULT_OUT,
          write: bool = True) -> dict:
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    g = extract_graph(store.entries)
    g["note"] = "派生投影：可全量重建；不写受治库（edge_graph.py 只读）"
    if not write:                                # 只读调用（impact）：不落产物（实测污染事故：测试夹具小图曾覆盖生产派生件）
        return g
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(g, open(out, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="有向经验图（派生投影 · 影响面/环路）")
    ap.add_argument("cmd", choices=("build", "impact", "cycles", "stats"))
    ap.add_argument("eid", nargs="?", default=None)
    ap.add_argument("--hops", type=int, default=2)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    g = build(a.store, a.out)
    c = g["counts"]
    if a.cmd in ("build", "stats"):
        print(f"[有向经验图] 节点 {c['nodes']}（活 {c['live']}）· 边 {c['edges']} "
              f"{c['by_type']} → {a.out}")
        cy = cycles(g)
        print(f"  有向环：{len(cy)}" + (f" 例：{cy[0]}" if cy else "（无）"))
        return 0
    if a.cmd == "cycles":
        cy = cycles(g)
        print(f"[有向环] {len(cy)} 个（非同名的循环引用=自食铁证；对称边不计）")
        for x in cy:
            print("  ⟲ " + " → ".join(x))
        return 0
    if not a.eid:
        raise SystemExit("impact 须给条目 id")
    r = impact(g, a.eid, a.hops)
    print(impact_text(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
