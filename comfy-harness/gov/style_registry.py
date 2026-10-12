# -*- coding: utf-8 -*-
"""style_registry.py — 概念注册表（工单 P11：N3 跨轮注册 / N6 族谱 / N7 canonical+变体）

**定位**：挖掘件（S- 前缀）的**概念身份账**——同一个概念被多轮重挖反复铸出不同 id
（内容漂移+签名后缀不同），注册表按名字基底把它们收回一个概念名下：

  N3 注册表：跨轮 union——base → {members(各代 id), generations, evidence, state}
     （state: single=只此一件 / twins=同代双胞 / family=≥3 件成族）；
  N6 族谱：**≥min_family（默认 3）件同基 = family 候选，待人签**（机器只提案；
     人签后按 N4 三件套执行：铸家族条+retract 各代+记 merged_from——非放大红线）；
  N7 canonical+变体：每概念定 canonical（代际低→证据多→created_at 早→id 序），
     其余为 variants；产 `entry_variants{canonical:[variants]}` 扩展块（D-1 数据/治理
     分离：并入 precedent_aliases.json 仍须人签，本件只**提议**该块）。

**只读账本、只产提案**：注册表不写 seed JSON（治理写入走 store API+人闸）。
用法：py comfy-harness/gov/style_registry.py [--store P] [--out P] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_OUT = os.path.join(_HERE, "style_mine_out", "style_registry.json")
MIN_FAMILY = 3


def _evidence_n(e: dict) -> int:
    f = e.get("facts") or {}
    if isinstance(f, dict) and isinstance(f.get("evidence_n"), int):
        return f["evidence_n"]
    ev = e.get("evidence")
    return len(ev) if isinstance(ev, list) else 0


def _base(eid: str):
    return eid.rsplit("-", 1)[0].lower() if str(eid).startswith("S-") else None


def _canonical_key(e: dict):
    return (int(e.get("_mine_gen") or 1), -_evidence_n(e),
            str(e.get("created_at") or ""), str(e.get("id")))


def build(entries: list, min_family: int = MIN_FAMILY,
          recurrence: dict | None = None) -> dict:
    """只读构建：S- 挖掘件 → 概念账。退场/墓碑件不入账（retract 后应 relist 或重铸）。
    recurrence=账本（影子权重原料，缺省只计同代重复数）。"""
    live = [e for e in entries
            if e.get("id", "").startswith("S-") and not e.get("tombstone")
            and not e.get("machine_retracted")]
    by = {}
    for e in live:
        by.setdefault(_base(e["id"]), []).append(e)
    concepts, families, canonical_map = {}, [], {}
    for base, es in sorted(by.items()):
        es.sort(key=lambda e: str(e["id"]))
        canonical = min(es, key=_canonical_key)
        variants = [e["id"] for e in es if e["id"] != canonical["id"]]
        gens = sorted({int(e.get("_mine_gen") or 1) for e in es})
        state = ("single" if len(es) == 1
                 else "family" if len(es) >= min_family else "twins")
        concepts[base] = {
            "members": [e["id"] for e in es],
            "generations": gens,
            "evidence_n": {e["id"]: _evidence_n(e) for e in es},
            "gov": {e["id"]: e.get("gov") for e in es},
            "canonical": canonical["id"],
            "variants": variants,
            "state": state,
            "shadow_weight": ((len(es) - 1) + sum(
                int((((recurrence or {}).get(eid)) or {}).get("count") or 0)
                for eid in [e["id"] for e in es])),
            "first_seen": min(str(e.get("created_at") or "") for e in es),
            "last_seen": max(str(e.get("created_at") or "") for e in es),
        }
        if state == "family":
            families.append({"base": base, "members": [e["id"] for e in es],
                             "canonical": canonical["id"], "n": len(es),
                             "hint": (f"族谱候选（人签）：≥{min_family} 件同基=同概念多轮重铸——"
                                      f"人签后可铸 {canonical['id']}-family 家族条并退场各代"
                                      f"（N4 三件套）；机器只提案")})
        for v in variants:
            canonical_map[v] = canonical["id"]
    return {"concepts": concepts, "families": families,
            "canonical_map": canonical_map, "min_family": min_family,
            "counts": {"concepts": len(concepts), "family": len(families),
                       "twins": sum(1 for c in concepts.values() if c["state"] == "twins"),
                       "single": sum(1 for c in concepts.values() if c["state"] == "single"),
                       "entries": len(live)},
            "note": "只读账本；family/canonical 均为提案，执行归人签（非放大红线）"}


def alias_extension(rep: dict) -> dict:
    """N7 提案块：{canonical:[variants]}（并入 precedent_aliases.json 须人签）。"""
    out = {}
    for c in rep["concepts"].values():
        if c["variants"]:
            out[c["canonical"]] = sorted(c["variants"])
    return out


def render(rep: dict) -> str:
    c = rep["counts"]
    L = [f"[概念注册表] 挖掘件 {c['entries']} 条 → 概念 {c['concepts']} 个"
         f"（single {c['single']} / twins {c['twins']} / family {c['family']}）",
         f"  {rep['note']}"]
    for f in rep["families"]:
        L.append(f"  ★ family 候选：{f['base']}（{f['n']} 件，canonical={f['canonical']}，"
                 f"影重 {rep['concepts'][f['base']]['shadow_weight']}）")
    twins = [b for b, v in rep["concepts"].items() if v["state"] == "twins"]
    if twins:
        L.append(f"  twins（2 件同基，走 N5 组视图/合并提示）：{len(twins)} 个")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="概念注册表（N3/N6/N7 · 只读提案）")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min-family", type=int, default=MIN_FAMILY)
    ap.add_argument("--json", action="store_true", help="stdout 打全量 JSON")
    a = ap.parse_args(argv)
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(a.store)
    rec = {}
    try:
        rec = json.load(open(os.path.join(_HERE, "style_mine_out", "recurrence.json"),
                             encoding="utf-8"))
    except (OSError, ValueError):
        pass
    rep = build(store.entries, a.min_family, rec)
    rep["alias_extension_proposal"] = alias_extension(rep)
    print(render(rep))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rep, open(a.out, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    print(f"  注册表落盘 {a.out}")
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
