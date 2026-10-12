# -*- coding: utf-8 -*-
"""draft_review.py — N5 评审组视图（工单 P8 · 人闸推动器）

**服务对象=人签面**（不是机器面）：63 条草木稿逐条看不可行，人需要的是
"哪些草案其实是同一件事" → 分组 + canonical 建议 + 合并提示（N4 三件套是机器
执行的，但**合并决策点在人**：机器只呈现组，不并条）。

分组判据（OR；20261008 live 校准——**cos 已实证不可判别，降为呈现面**）：
  ①slug 基底相等（S- 前缀挖掘件，跨代重铸）；②_mine_sig 相等（同批同簇）；
  ③facts.tags Jaccard ≥ 0.5（矿机自身 min_jaccard 同源；长标签表对公共成分
    不敏感——实测不同概念 J=0~0.125 vs 同族 J=0.93~1.0，而 cos 恰好反转）。
  完全链接聚合（min 判据 ≥ 阈值才并；单链并查集曾把 62 条连成 59 条巨团）。
  cos 仅入呈现面：组内 cos 区间 + 跨组 cos≥0.95 注意力清单（人判读）。
canonical 建议序（确定性）：代际低者优先（原始件）→ 证据多者优先 → created_at
早者 → id 字典序。**只建议，不动作**（非放大红线：机器不得自行升格/合并决定）。

无嵌入缓存 → 响亮报错（组视图不降级：无向量=看不见组=人闸失明）。
用法：py comfy-harness/gov/draft_review.py [--seed P] [--group-cos F] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # 仓根（evocore 包所在）

import embed_cache as ec                       # noqa: E402

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_CACHE = ec.DEFAULT_CACHE
DEFAULT_GROUP_JACCARD = 0.5      # = 矿机自身 min_jaccard（同源判别）
COS_ATTENTION = 0.95              # 跨组高 cos 注意力阈值（呈现，不作判据）


def _drafts(entries: list) -> list:
    return [e for e in entries
            if e.get("gov") == "draft" and not e.get("tombstone")
            and not e.get("machine_retracted")]


def _evidence_n(e: dict) -> int:
    f = e.get("facts") or {}
    if isinstance(f, dict) and isinstance(f.get("evidence_n"), int):
        return f["evidence_n"]
    ev = e.get("evidence")
    return len(ev) if isinstance(ev, list) else 0


def _slug_base(eid: str):
    """S- 前缀挖掘件的名字基底（同基=同概念，跨代重铸兜底判据）。"""
    return eid.rsplit("-", 1)[0].lower() if str(eid).startswith("S-") else None


def _tagset(e: dict):
    f = e.get("facts") or {}
    t = f.get("tags") if isinstance(f, dict) else None
    if isinstance(t, list) and t:
        return {str(x).lower() for x in t}
    return None


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else None


def _canonical_key(e: dict):
    return (int(e.get("_mine_gen") or 1), -_evidence_n(e),
            str(e.get("created_at") or ""), str(e.get("id")))


def group_drafts(entries: list, cache: dict | None, group_jaccard: float = DEFAULT_GROUP_JACCARD,
                 cos_attention: float = 0.95, recurrence: dict | None = None) -> dict:
    """纯函数（无 I/O）：草案 → 分组报告。cache 仅用于 cos 呈现面（可为 None）。

    **判据（实测校准，20261008 P8）**：主判据=①名字基底相等（S- 前缀，跨代重铸）
    ②_mine_sig 相等（同批同簇）③facts.tags Jaccard ≥ group_jaccard（默认 0.5 =
    矿机自身 min_jaccard 同源）——完全链接聚合（min 判据 ≥ 阈值才并）。
    **cos 不作判据（实证反例）**：同批草案上 cos 反转——不同概念对 cos 0.972、
    同概念跨代对 cos 0.874（模板措辞+公共标签 1Girl/Cherry Blossoms 支配嵌入，
    长标签表的 Jaccard 反而不受公共成分淹没）。cos 降为呈现面：组内 cos 区间 +
    **跨组高 cos 注意力清单**（cos≥0.95 但不同组=疑似公共成分或漏并，人判读）。"""
    drafts = sorted(_drafts(entries), key=lambda e: str(e["id"]))
    es = {e["id"]: e for e in drafts}
    tags = {i: _tagset(es[i]) for i in es}
    missing = []
    vec = {}
    dim = (cache or {}).get("dim") or ec.DEFAULT_DIM
    for i in es:
        it = ((cache or {}).get("items") or {}).get(i)
        if it:
            vec[i] = ec._unb64(it["vec"], dim)
        elif cache is not None:
            missing.append(i)                       # 有缓存仍缺件=必须现形（禁静默丢件）

    def pair_cos_or_none(a, b):
        if a in vec and b in vec:
            return ec.cosine(vec[a], vec[b])
        return None

    ids = sorted(es)
    clusters = [[i] for i in ids]
    merges_by = []

    def merge_in(src, tgt, why):
        if src is tgt:
            return
        tgt.extend(src)
        clusters.remove(src)
        merges_by.append(why)

    # ①名字基底（S- 前缀）
    by_base = {}
    for i in ids:
        b = _slug_base(i)
        if b:
            by_base.setdefault(b, []).append(i)
    for b, members in sorted(by_base.items()):
        if len(members) < 2:
            continue
        tgt = next(c for c in clusters if members[0] in c)
        for other in members[1:]:
            merge_in(next(c for c in clusters if other in c), tgt, f"base:{b}")
    # ②_mine_sig 相等
    by_sig = {}
    for i in ids:
        s = es[i].get("_mine_sig")
        if s:
            by_sig.setdefault(str(s), []).append(i)
    for s, members in sorted(by_sig.items()):
        if len(members) < 2:
            continue
        tgt = next(c for c in clusters if members[0] in c)
        for other in members[1:]:
            merge_in(next(c for c in clusters if other in c), tgt, f"sig:{s[:12]}")
    # ③tags Jaccard 完全链接
    def min_jac(A, B):
        vals = [_jaccard(tags[a], tags[b]) for a in A for b in B]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None

    while True:
        best = None
        for ci in range(len(clusters)):
            for cj in range(ci + 1, len(clusters)):
                A, B = clusters[ci], clusters[cj]
                m = min_jac(A, B)
                if m is None or m < group_jaccard:
                    continue
                key = (-m, sorted(A), sorted(B))
                if best is None or key < best[0]:
                    best = (key, m, ci, cj)
        if best is None:
            break
        _k, m, ci, cj = best
        clusters[ci].extend(clusters[cj])
        clusters.pop(cj)
        merges_by.append(f"tags J={round(m, 3)}")
    out_groups = []
    for members in sorted([sorted(c) for c in clusters if len(c) > 1]):
        canonical = min(members, key=lambda i: _canonical_key(es[i]))
        cs = [pair_cos_or_none(a, b) for ai, a in enumerate(members) for b in members[ai + 1:]]
        cs = [c for c in cs if c is not None]
        out_groups.append({
            "members": [{"id": i, "gen": int(es[i].get("_mine_gen") or 1),
                         "evidence_n": _evidence_n(es[i]),
                         "sig": es[i].get("_mine_sig", ""),
                         "slug_base": _slug_base(i),
                         "tags_n": len(tags[i]) if tags[i] else 0,
                         "created_at": str(es[i].get("created_at") or "")}
                        for i in members],
            "canonical": canonical,
            "shadow_weight": (len(members) - 1) + sum(
                int((((recurrence or {}).get(i)) or {}).get("count") or 0) for i in members),
            "min_pair_cos": round(min(cs), 4) if cs else None,
            "max_pair_cos": round(max(cs), 4) if cs else None,
            "min_pair_jaccard": round(min(
                [_jaccard(tags[a], tags[b]) for ai, a in enumerate(members)
                 for b in members[ai + 1:] if _jaccard(tags[a], tags[b]) is not None] or [0]), 4),
            "specimen": all((es[i].get("facts") or {}).get("specimen") for i in members),
            "hint": (("**标本组（反例面·勿并勿 promote）**——维护者令已裁定留作标本："
                      + str((es[canonical].get("facts") or {}).get("specimen_note") or ""))
                     if all((es[i].get("facts") or {}).get("specimen") for i in members)
                     else (f"合并提示（人裁）：铸 {canonical}-merged（并集证据，gen 不升），"
                           f"retract 其余 {len(members) - 1} 条（reason=consolidated into）——"
                           f"执行走 draft_consolidate.merge；本条仅呈现")),
        })
    out_groups.sort(key=lambda g: (-len(g["members"]), g["canonical"]))
    grouped = {m["id"] for g in out_groups for m in g["members"]}
    singles = [i for i in ids if i not in grouped]
    # 跨组高 cos 注意力清单（cos 不作判据，但值得人看）
    attention = []
    group_sets = [set(m["id"] for m in g["members"]) for g in out_groups]
    for ai, a in enumerate(ids):
        for b in ids[ai + 1:]:
            if any({a, b} <= gs for gs in group_sets):
                continue                            # 已同组的不列
            c = pair_cos_or_none(a, b)
            if c is not None and c >= cos_attention:
                ja = _jaccard(tags[a], tags[b])
                attention.append({"a": a, "b": b, "cos": round(c, 4),
                                  "jaccard": round(ja, 4) if ja is not None else None})
    attention.sort(key=lambda p: (-p["cos"], p["a"], p["b"]))
    return {"drafts": len(drafts), "with_vec": len(vec), "missing_vec": missing,
            "groups": out_groups, "single_count": len(singles), "singles": singles,
            "group_jaccard": group_jaccard, "merges_by": merges_by,
            "cos_attention": attention[:20], "cos_attention_total": len(attention),
            "note": ("机器只呈现组；合并/升格决策与执行归人闸（非放大红线）。"
                     "判据=基底/签名/标签 Jaccard；cos 仅呈现（实测不可判别："
                     "不同概念 cos 0.972 vs 同概念重铸 0.874）")}


def review(store_path: str = DEFAULT_STORE, cache_path: str = DEFAULT_CACHE,
           group_jaccard: float = DEFAULT_GROUP_JACCARD) -> dict:
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    cache = ec.load_cache(cache_path)
    if not cache.get("items"):
        raise RuntimeError(
            f"嵌入缓存为空/不存在（{cache_path}）——组视图不降级（无向量=人闸失明）；"
            f"先跑 `py comfy-harness/gov/embed_cache.py`")
    if cache.get("prefix_scheme") != ec.PREFIX_SCHEME:
        raise RuntimeError(
            f"缓存前缀方案={cache.get('prefix_scheme')} 与现役 {ec.PREFIX_SCHEME} 不符——"
            f"先 `embed_cache.py --rebuild`（半新半旧=向量漂移，分组判据失真）")
    rec = {}
    try:
        rec = json.load(open(os.path.join(_HERE, "style_mine_out", "recurrence.json"),
                             encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return group_drafts(store.entries, cache, group_jaccard, COS_ATTENTION, rec)


def format_report(rep: dict) -> str:
    lines = [f"[评审组视图] 草案 {rep['drafts']} 条（有向量 {rep['with_vec']}），"
             f"组 {len(rep['groups'])} 个，散件 {rep['single_count']}；"
             f"判据=基底/签名/标签Jaccard≥{rep['group_jaccard']}（完全链接）",
             f"  {rep['note']}"]
    if rep["missing_vec"]:
        lines.append(f"  ⚠ 无向量草案 {len(rep['missing_vec'])} 条（先跑 embed_cache.py 增量重嵌）："
                     f"{rep['missing_vec'][:5]}{'…' if len(rep['missing_vec']) > 5 else ''}")
    for gi, g in enumerate(rep["groups"], 1):
        lines.append(f"  组{gi}: {len(g['members'])} 条  canonical={g['canonical']}"
                     f"  影重={g.get('shadow_weight')}"
                     f"  cos∈[{g['min_pair_cos']}, {g['max_pair_cos']}]")
        for m in sorted(g["members"], key=lambda x: (-x["evidence_n"], x["id"])):
            mark = "★" if m["id"] == g["canonical"] else " "
            lines.append(f"    {mark} {m['id'][:52]:54s} gen={m['gen']} ev={m['evidence_n']}"
                         f"{'  base=' + m['slug_base'] if m['slug_base'] else ''}")
        lines.append(f"    → {g['hint']}")
    if rep["singles"]:
        lines.append(f"  散件（不成组，逐条人看）：{len(rep['singles'])} 条")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="N5 评审组视图（呈现，不动作）")
    ap.add_argument("--seed", default=DEFAULT_STORE)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--group-jaccard", type=float, default=DEFAULT_GROUP_JACCARD)
    ap.add_argument("--json", default=None, help="报告另存 JSON 路径")
    a = ap.parse_args(argv)
    rep = review(a.seed, a.cache, a.group_jaccard)
    print(format_report(rep))
    if a.json:
        json.dump(rep, open(a.json, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=1)
        print(f"  JSON 落盘 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
