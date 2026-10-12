# -*- coding: utf-8 -*-
"""style_mine_det.py — 风格簇挖掘器 A：确定性共现聚类（无 LLM · 可复算 · 可审计）

链路（维护者令·20261008·双挖掘器并行对比"自动涌现"）：
  共用语料 corpus.json（style_corpus.py 产）→ 统计每个 tag 的文档支持度
  → 同文档内 tag 两两共现计数 → 阈值过滤（support≥S, 共现≥E）→ 并查集聚类
  → 候选风格簇（每簇=一组高频共现 tag，附证据文档链）。

为什么确定性可当"自动涌现"基线：聚类结构**不是人写的**——是从语料统计里长出来的；
且全程无随机、无 LLM（同输入必同输出），每条结论都能回放验证。

开关（维护者令"两个都加个开关"）：环境变量 STYLE_MINE_DET=off/0/false/no
（或 CLI --off）→ 关闭：退出 0、不写产物、不报错（恒可用性不受影响）。

用法：
  py -X utf8 style_mine_det.py [--corpus PATH] [--out PATH] [--off]
      [--min-support 2] [--min-edge 2] [--min-cluster 3]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.join(_HERE, "style_mine_out", "corpus.json")
DEFAULT_OUT = os.path.join(_HERE, "style_mine_out", "det_candidates.json")

_OFF_VALUES = {"0", "off", "false", "no", "disable", "disabled"}
ENV_SWITCH = "STYLE_MINE_DET"


def is_disabled(cli_off: bool = False, env: str | None = None) -> bool:
    """开关判定：CLI --off 或环境变量（默认读 STYLE_MINE_DET）命中关闭词表。"""
    if cli_off:
        return True
    v = (env if env is not None else os.environ.get(ENV_SWITCH, "")).strip().lower()
    return v in _OFF_VALUES


def mine(docs: list, min_support: int = 2, min_edge: int = 2,
         min_cluster: int = 3, stopword_ratio: float = 0.7,
         min_jaccard: float = 0.5, resolution: float = 1.5) -> dict:
    """核心：确定性共现聚类。返回候选风格簇结构（纯函数，无 IO）。

    stopword_ratio：文档占比超过该值的 tag 判停用词（1girl/masterpiece 这类全语料常驻词
    会把所有簇桥接成一大坨——高频≠风格信息，先剔）。0.7=出现于七成以上文档者不参与聚类。
    min_jaccard：边权相对重叠阈值。**单靠共现计数会被"链式桥接"聚成一坨**（实测 103tag
    巨簇）；jaccard=c/(sa+sb-c) 把"两词几乎总是一起"与"只是碰巧都常出现"分开——
    剪断低比链边后簇才分立。
    """
    supp = collections.Counter()
    for d in docs:
        for t in set(d.get("tags") or []):
            supp[t] += 1
    cap = max(min_support, int(stopword_ratio * len(docs))) if docs else 0
    elig = {t for t, c in supp.items() if min_support <= c <= cap}
    stopwords = sorted(t for t, c in supp.items() if c > cap)

    pair = collections.Counter()
    for d in docs:
        ts = sorted(set(d.get("tags") or []) & elig)
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                pair[(ts[i], ts[j])] += 1
    edges = {}
    for (a, b), c in pair.items():
        if c < min_edge:
            continue
        j = c / (supp[a] + supp[b] - c)
        if j >= min_jaccard:
            edges[(a, b)] = (c, round(j, 4))

    # 聚类：优先加权社区检测（Louvain——按边密度切分，不被链式桥接拉成巨块；
    # seed=42 固定→同输入同输出；resolution 控粒度：越大越细）。
    # networkx 缺席时回落单链连通分量（同一输入仍确定性，只是切分粒度退化为连通性）。
    algo = "modularity"
    try:
        import networkx as nx
        G = nx.Graph()
        G.add_nodes_from(sorted(elig))
        for (a, b), (_c, j) in edges.items():
            G.add_edge(a, b, weight=j)
        comms = [set(c) for c in
                 nx.algorithms.community.louvain_communities(
                     G, weight="weight", resolution=resolution, seed=42)]
    except ImportError:                                   # pragma: no cover - 环境回落
        algo = "components(networkx 缺席回落)"
        parent = {t: t for t in elig}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in edges:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
        buckets = collections.defaultdict(set)
        for t in elig:
            buckets[find(t)].add(t)
        comms = list(buckets.values())

    clusters, misc = [], []
    for members in comms:
        members = sorted(members, key=lambda t: (-supp[t], t))
        if len(members) < min_cluster:
            misc.extend(members)
            continue
        mset = set(members)
        rep = collections.defaultdict(list)     # 代表度=与簇内他词的均 jaccard——命名取最凝聚词，
        j_in = []                               # 不按支持度（否则通用词老顶在前面）
        for (a, b), (_c, j) in edges.items():
            if a in mset and b in mset:
                rep[a].append(j)
                rep[b].append(j)
                j_in.append(j)
        rep_score = {t: (sum(v) / len(v) if v else 0.0) for t, v in rep.items()}
        top = sorted(members, key=lambda t: (-rep_score.get(t, 0.0), -supp[t], t))[:3]
        ev = [d["src"] for d in docs if len(set(d.get("tags") or []) & mset) >= 2]
        clusters.append({
            "name": " · ".join(top),
            "size": len(members),
            "tags": [{"tag": t, "support": supp[t]} for t in members],
            "cohesion": round(sum(j_in) / len(j_in), 2) if j_in else 0.0,
            "evidence": ev,
        })
    clusters.sort(key=lambda c: (-c["size"], c["name"]))
    misc.sort()
    return {"clusters": clusters, "misc": misc,
            "stats": {"n_docs": len(docs), "n_tags_total": len(supp),
                      "n_tags_eligible": len(elig), "n_edges": len(edges),
                      "n_stopwords": len(stopwords), "stopwords": stopwords,
                      "algo": algo}}


def main(argv=None):
    ap = argparse.ArgumentParser(description="风格簇挖掘器 A（确定性共现聚类）")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--off", action="store_true", help="开关：关闭本挖掘器")
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--min-edge", type=int, default=2)
    ap.add_argument("--min-cluster", type=int, default=3)
    ap.add_argument("--stopword-ratio", type=float, default=0.7)
    ap.add_argument("--min-jaccard", type=float, default=0.5)
    ap.add_argument("--resolution", type=float, default=1.5,
                    help="社区检测分辨率：越大簇越细（1.0=粗块，1.5=风格束粒度）")
    a = ap.parse_args(argv)

    if is_disabled(a.off):
        print(f"[style-det] 已关闭（开关 {ENV_SWITCH} / --off）——不产出")
        return 0

    t0 = time.time()
    payload = json.load(open(a.corpus, encoding="utf-8"))
    docs = payload["docs"]
    res = mine(docs, a.min_support, a.min_edge, a.min_cluster, a.stopword_ratio,
               a.min_jaccard, a.resolution)
    out = {"method": "det-cooc", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "corpus_n_docs": len(docs),
           "params": {"min_support": a.min_support, "min_edge": a.min_edge,
                      "min_cluster": a.min_cluster, "stopword_ratio": a.stopword_ratio,
                      "min_jaccard": a.min_jaccard, "resolution": a.resolution},
           "clusters": res["clusters"], "misc": res["misc"],
           "stats": res["stats"], "elapsed_s": round(time.time() - t0, 2)}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"[style-det] {len(out['clusters'])} 簇（tag 面 {res['stats']['n_tags_eligible']}"
          f"/{res['stats']['n_tags_total']}，边 {res['stats']['n_edges']}）"
          f" · {out['elapsed_s']}s → {a.out}")
    for c in out["clusters"]:
        print(f"  {c['size']:2d} tag · cohesion {c['cohesion']:>5} · {c['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
