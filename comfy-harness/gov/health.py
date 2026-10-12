# -*- coding: utf-8 -*-
"""health.py — 飞轮健康度读数（工单 P9）

**三读数**（调研三条修正之二：占比记账入报告头）：
  ①raw:ratified:draft = 生成面文档数 : 已签条目数（approved+verified）: 草案数
    ——MLA 式配比记账（原料/成品/在制品），自食风险的**体量仪表**；
  ②approved 率 = approved / (approved+verified)（已签面里人签占比——机器 verified
    件不进召回的守门统计）；
  ③签名覆盖率 = (approved+verified) / 全条目（Biba no-write-up 面：未签者占比）；
  ④回声簇率 = 挖掘候选簇对已签条目最近 cosine ≥ 0.90 的占比（**簇到源距量化**：
    越高=新涌现在重述旧知识=自食仪表；候治理位裁，非闸）。

**T-a/T-b**（向量化触发器的原判据，转为常设读数）：
  T-a 语义失效率 = 探针零命中率（probes.json 固化集，离线确定性）；
  T-b 重铸率 = 草案里名字基底双胞组数 / 草案数（跨代重铸的量化）。
  阈值 T_A=0.30 / T_B=0.05（工单原式：>30% / >5% 命中即"该装向量层"——20261008
  两个都已命中，层已装；本读数此后作**常设哨兵**：回升即提醒）。

用法：py comfy-harness/gov/health.py [--json OUT]
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
DEFAULT_PROBES = os.path.join(_HERE, "style_mine_out", "probes.json")
DEFAULT_CANDIDATES = [os.path.join(_HERE, "style_mine_out", "det_candidates.json"),
                      os.path.join(_HERE, "style_mine_out", "lightrag_candidates.json")]
ECHO_COS = 0.90                                # 回声判据（簇到源距）
T_A = 0.30                                     # 语义失效率阈值（工单原式）
T_B = 0.05                                     # 重铸率阈值（工单原式）


def _sanctioned(entries):
    return [e for e in entries
            if e.get("gov") in ("approved", "verified")
            and not e.get("tombstone") and not e.get("machine_retracted")]


def _drafts(entries):
    return [e for e in entries
            if e.get("gov") == "draft" and not e.get("tombstone")
            and not e.get("machine_retracted")]


def entry_health(entries, gen_docs=None) -> dict:
    ap = [e for e in entries if e.get("gov") == "approved"]
    ve = [e for e in entries if e.get("gov") == "verified"]
    dr = _drafts(entries)
    ratified = len(ap) + len(ve)
    total = len(entries) or 1
    return {"gen_docs": gen_docs, "approved": len(ap), "verified": len(ve),
            "draft": len(dr), "ratified": ratified, "total": len(entries),
            "ratio": f"{gen_docs if gen_docs is not None else '?'}:{ratified}:{len(dr)}",
            "approved_rate": round(len(ap) / ratified, 4) if ratified else None,
            "ratified_rate": round(ratified / total, 4)}


def probe_health(store_path: str = DEFAULT_STORE, cache_path: str = DEFAULT_CACHE,
                 probes_path: str = DEFAULT_PROBES, k: int = 3) -> dict:
    """T-a：探针零命中率（离线确定性——夹具查询向量 + 缓存条目向量）。"""
    import base64
    import numpy as np
    from precedent_gov import PrecedentStore
    import recall_hybrid as rh
    fx = json.load(open(probes_path, encoding="utf-8"))
    cache = ec.load_cache(cache_path)
    if cache.get("prefix_scheme") != ec.PREFIX_SCHEME:
        raise RuntimeError(f"缓存前缀方案={cache.get('prefix_scheme')} ≠ 现役 "
                           f"{ec.PREFIX_SCHEME}——先 embed_cache.py --rebuild")
    by_q = {p["q"]: np.frombuffer(base64.b64decode(p["vec"]), dtype=np.float32).copy()
            for p in fx["probes"]}

    def fn(texts, **kw):
        return np.array([by_q[t] for t in texts], dtype=np.float32)

    store = PrecedentStore.load(store_path)
    pool = _sanctioned(store.entries)
    misses, hits = [], 0
    for p in fx["probes"]:
        ranked = rh.rank(pool, p["q"], k=k, cache_path=cache_path, embed_fn=fn)
        ids = [e["id"] for _, e in ranked]
        if set(p["expected"]) & set(ids):
            hits += 1
        else:
            misses.append(p["q"])
    n = len(fx["probes"]) or 1
    return {"probes": len(fx["probes"]), "hits": hits, "misses": misses,
            "zero_hit_rate": round(len(misses) / n, 4),
            "over_threshold": len(misses) / n > T_A}


def echo_health(entries, candidates: list, cache_path: str = DEFAULT_CACHE,
                cos: float = ECHO_COS, embed_fn=None, cache: dict | None = None) -> dict:
    """④回声簇率：候选簇 vs 已签条目（+全库口径）的最近 cosine。
    embed_fn / cache 双 DI（测试离线；cache 传入则不再读盘）。"""
    import style_feed as sf
    cache = cache if cache is not None else ec.load_cache(cache_path)
    if not cache.get("items"):
        raise RuntimeError(f"嵌入缓存为空（{cache_path}）——回声读数不降级")
    dim = cache.get("dim") or ec.DEFAULT_DIM
    san = _sanctioned(entries)
    all_ok = [e for e in entries if not e.get("tombstone")]
    items = cache.get("items") or {}
    san_vecs = [(e["id"], ec._unb64(items[e["id"]]["vec"], dim))
                for e in san if e["id"] in items]
    all_vecs = [(e["id"], ec._unb64(items[e["id"]]["vec"], dim))
                for e in all_ok if e["id"] in items]
    cands = [c for c in candidates if _members_of(c)]
    if not cands:
        return {"candidates": 0, "echoes": 0, "rate": None,
                "echoes_all": 0, "rate_all": None, "samples": []}
    texts = [sf.candidate_text(c.get("name", ""), _members_of(c)) for c in cands]
    fn = embed_fn or ec.embed_docs
    vecs = fn(texts)
    echoes, echoes_all, samples = 0, 0, []
    for c, v in zip(cands, vecs, strict=False):
        if not san_vecs:
            break
        eid, s = max(((i, ec.cosine(v, sv)) for i, sv in san_vecs), key=lambda x: x[1])
        # 全库口径（含草案）——自食度量：候选是否在重述库内（含在制品）知识
        _eid2, s_all = max(((i, ec.cosine(v, sv)) for i, sv in all_vecs),
                           key=lambda x: x[1]) if all_vecs else (None, 0.0)
        if s >= cos:
            echoes += 1
        if s_all >= cos:
            echoes_all += 1
        samples.append({"candidate": str(c.get("name", ""))[:48], "nearest": eid,
                        "cos": round(s, 3), "nearest_all": _eid2, "cos_all": round(s_all, 3)})
    samples.sort(key=lambda x: -x["cos_all"])
    return {"candidates": len(cands), "echoes": echoes,
            "rate": round(echoes / len(cands), 4), "cos_cut": cos,
            "echoes_all": echoes_all, "rate_all": round(echoes_all / len(cands), 4),
            "samples": samples[:5]}


def reforge_health(entries) -> dict:
    """T-b：重铸率 = 草案名字基底双胞组数 / 草案数。"""
    dr = _drafts(entries)
    bases = {}
    for e in dr:
        eid = str(e.get("id", ""))
        if eid.startswith("S-"):
            bases.setdefault(eid.rsplit("-", 1)[0].lower(), []).append(eid)
    twins = {b: m for b, m in bases.items() if len(m) > 1}
    n = len(dr) or 1
    return {"drafts": len(dr), "twin_groups": len(twins), "twins": twins,
            "rate": round(len(twins) / n, 4), "over_threshold": len(twins) / n > T_B}


def _members_of(c: dict) -> list:
    if isinstance(c.get("members"), list):
        return [str(m) for m in c["members"]]
    if isinstance(c.get("tags"), list):
        return [str(t.get("tag")) for t in c["tags"] if isinstance(t, dict) and t.get("tag")]
    return []


def load_candidates(paths=None) -> list:
    out = []
    for p in (paths or DEFAULT_CANDIDATES):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out += list(d.get("clusters") or d.get("candidates") or [])
    return out


def readings(store_path: str = DEFAULT_STORE, cache_path: str = DEFAULT_CACHE,
             probes_path: str = DEFAULT_PROBES, candidates=None, gen_docs=None) -> dict:
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    r = {"entry": entry_health(store.entries, gen_docs)}
    try:
        r["probe"] = probe_health(store_path, cache_path, probes_path)
    except Exception as ex:                                    # noqa: BLE001 响亮不静默
        r["probe"] = {"error": f"{type(ex).__name__}: {ex}"}
    try:
        r["echo"] = echo_health(store.entries,
                                candidates if candidates is not None else load_candidates(),
                                cache_path)
    except Exception as ex:                                    # noqa: BLE001
        r["echo"] = {"error": f"{type(ex).__name__}: {ex}"}
    r["reforge"] = reforge_health(store.entries)
    try:
        import edge_graph as _eg
        _g = _eg.extract_graph(store.entries)
        _cy = _eg.cycles(_g)
        r["cycles"] = {"n": len(_cy), "sample": _cy[:3], "edges": _g["counts"]}
    except Exception as ex:                                    # noqa: BLE001
        r["cycles"] = {"error": f"{type(ex).__name__}: {ex}"}
    try:
        import reverse_flywheel as _rf
        r["anti"] = _rf.stats()
    except Exception as ex:                                    # noqa: BLE001
        r["anti"] = {"error": f"{type(ex).__name__}: {ex}"}
    r["thresholds"] = {"T_A": T_A, "T_B": T_B, "ECHO_COS": ECHO_COS}
    return r


def format_readings(r: dict, indent: str = "") -> str:
    e = r["entry"]
    L = [f"{indent}健康度读数（P9）：raw:ratified:draft = {e['ratio']}"
         f"（生成面 {e['gen_docs']} / 已签 {e['ratified']} / 草案 {e['draft']}）"]
    L.append(f"{indent}  ①approved 率 = {e['approved']}/{e['ratified']} = "
             f"{_pct(e['approved_rate'])}；②签名覆盖率 = {e['ratified']}/{e['total']} = "
             f"{_pct(e['ratified_rate'])}")
    p = r.get("probe") or {}
    if p.get("error"):
        L.append(f"{indent}  T-a 语义失效率：读数不可用（{p['error']}）")
    else:
        flag = "  ⚠超阈（>30%）" if p["over_threshold"] else ""
        L.append(f"{indent}  T-a 语义失效率 = {len(p['misses'])}/{p['probes']} = "
                 f"{_pct(p['zero_hit_rate'])}{flag}（探针固化集，离线）")
    ec_ = r.get("echo") or {}
    if ec_.get("error"):
        L.append(f"{indent}  ③回声簇率：读数不可用（{ec_['error']}）")
    else:
        L.append(f"{indent}  ③回声簇率 = 对已签 {ec_.get('echoes', 0)}/{ec_.get('candidates', 0)}"
                 f" = {_pct(ec_.get('rate'))}；对全库（含草案·自食度量）= "
                 f"{ec_.get('echoes_all', 0)}/{ec_.get('candidates', 0)} = "
                 f"{_pct(ec_.get('rate_all'))}（阈值 cos≥{ec_.get('cos_cut')}）")
        for s in (ec_.get("samples") or [])[:3]:
            L.append(f"{indent}     近义样本：{s['candidate']} → 已签 {s['nearest'][:30]} "
                     f"cos={s['cos']} / 全库 {str(s.get('nearest_all'))[:30]} "
                     f"cos={s.get('cos_all')}")
    rf = r.get("reforge") or {}
    flag = "  ⚠超阈（>5%）" if rf.get("over_threshold") else ""
    L.append(f"{indent}  T-b 重铸率 = {rf.get('twin_groups', 0)} 双胞组/{rf.get('drafts', 0)} "
             f"草案 = {_pct(rf.get('rate'))}{flag}")
    an = r.get("anti") or {}
    if an.get("error"):
        L.append(f"{indent}  T-c 反例雷达：读数不可用（{an['error']}）")
    else:
        L.append(f"{indent}  T-c 反例雷达（反向飞轮·影子）= 扫描 {an.get('scans', 0)} 轮 / "
                 f"命中 {an.get('hits', 0)}；命中率 {_pct(an.get('hit_rate'))}")
    cy = r.get("cycles") or {}
    if cy.get("error"):
        L.append(f"{indent}  T-d 有向环：读数不可用（{cy['error']}）")
    else:
        flagd = "  ⚠ 自食环嫌疑" if cy.get("n") else ""
        eu = (cy.get("edges") or {}).get("edges", "?")
        L.append(f"{indent}  T-d 有向环 = {cy.get('n', 0)} 个"
                 f"（非同名声循环引用=自食铁证）{flagd}｜经验图边数 {eu}")
    return "\n".join(L)


def _pct(x):
    return "—" if x is None else f"{round(x * 100, 1)}%"


def main(argv=None):
    ap = argparse.ArgumentParser(description="飞轮健康度读数（P9）")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    try:
        import mine_trigger as mt
        gen = mt.measure().get("gen_docs")
    except Exception:                                          # noqa: BLE001
        gen = None
    r = readings(a.store, a.cache, gen_docs=gen)
    print(format_readings(r))
    if a.json:
        json.dump(r, open(a.json, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=1)
        print(f"JSON 落盘 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
