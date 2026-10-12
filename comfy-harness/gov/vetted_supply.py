# -*- coding: utf-8 -*-
"""vetted_supply.py — 机器检定草案供血（维护者令 20261010「③供血替代方案-按建议修改」）

背景：供血池只有 19 条已签件（approved+verified），108 条草案永不供血——飞轮下半圈
被"每条逐个人签"卡死。分级供血（"未验证"标签）被维护者否决：语义模糊。本件=替代方案
**检定陈述制**：供血面永远只陈述机械可复核的事实，不授信任。

**四项检定（供血当时现算，非死标签——任何一项滑落，下一轮供血自动消失）**：
  R1 复现：挖掘签名在候选池 rounds_seen ≥ 2（成熟闸 N2 同源判据）；
  R2 负例：条目文本对负例雷达零命中（与 preflight ② 同一匹配器 nc.match_negs）；
  R3 证据：证据件逐条真实存在（generation:*.png→服务端产物/field·out；style_mine_out/→
      gov 相对路径；条目引用→被引 id 在库）；空证据=败；
  R4 回声：对已签面（approved+verified）最大 cosine < 0.90；无向量=保守败（不猜）。

全过者以"机器检定"分栏供血（preflight ③）；**检定≠签发**——升信任级（promote/verify）
仍 human:* 专属（非放大红线不动）。obs 流入账的 P-obs 草案无挖掘签名，R1 天然不过——
它们仍走人闸（第一手观察不等于人签结论，规格按维护者批准原文执行）。

用法：
  py -X utf8 vetted_supply.py vet [--k 5]        # 全库检定，打印过/落选读数
  （供血走 preflight ③ 分栏；本件 CLI 仅供巡检）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import numpy as np                            # noqa: E402  （嵌入向量统一 ndarray）

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import embed_cache as ec                     # noqa: E402
import neg_chain as nc                       # noqa: E402
from precedent_gov import PrecedentStore     # noqa: E402

DEFAULT_POOL = os.path.join(_HERE, "style_mine_out", "candidate_pool.json")
DEFAULT_CACHE = ec.DEFAULT_CACHE
DEFAULT_COMFY_OUT = os.environ.get(
    "COMFY_OUTPUT_DIR", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\output")
FIELD_OUT = os.path.join(os.path.dirname(_HERE), "field", "out")

MIN_ROUNDS = 2          # R1：候选池复现轮数（与 style_feed 成熟闸同源）
ECHO_COS = 0.90         # R4：对已签面的回声阈值（与 style_feed 近重复闸同源）


# ── R3 证据实存 ─────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))   # 仓根（comfy-harness/..）


def _expand_braces(a: str) -> list:
    """{a,b} 花括号展开（style_feed 历史铸造约定）；无花括号原样返回。"""
    m = re.match(r"^(.*)\{([^{}]+)\}(.*)$", a)
    if not m:
        return [a]
    head, alts, tail = m.groups()
    return [head + alt.strip() + tail for alt in alts.split(",")]


def _file_exists(name: str, comfy_out: str) -> bool:
    bases = (comfy_out, FIELD_OUT, _HERE, os.path.join(_HERE, "style_mine_out"),
             REPO_ROOT)
    return any(os.path.isfile(os.path.join(b, name))
               for b in bases if b)


def evidence_state(e: dict, store_ids: set, comfy_out: str = DEFAULT_COMFY_OUT) -> tuple:
    """证据件逐条核存 → (ok, detail)。三形态：
    ① dict.files（20261010 证据分离纪律：z.py obs --ev-file 产物）——逐件核存在+sha256；
    ② artifact 字符串——分号拆多证据；花括号展开后**全部**落位才算过；
    ③ 条目 id 引用（无路径形态）——被引 id 在库。"""
    ev = e.get("evidence") or {}
    if isinstance(ev, dict) and ev.get("files"):
        import hashlib as _hl
        for f in ev["files"]:
            p = str(f.get("path") or f.get("name") or "")
            hit = p if os.path.isfile(p) else None
            if not hit:
                name = str(f.get("name") or "")
                for b in (comfy_out, FIELD_OUT, _HERE, REPO_ROOT):
                    cand = os.path.join(b, name) if b else name
                    if os.path.isfile(cand):
                        hit = cand
                        break
            if not hit:
                return False, f"证据文件缺失 {p[:60]}"
            sha = f.get("sha256")
            if sha:
                cur = _hl.sha256(open(hit, "rb").read()).hexdigest()
                if cur != str(sha).lower():
                    return False, f"sha256 不符 {f.get('name','')[:40]}"
        return True, f"ok×{len(ev['files'])}(sha核)"
    art = ev.get("artifact") if isinstance(ev, dict) else ev
    art = str(art or "").strip()
    if not art:
        return False, "空证据"
    for a in (x.strip() for x in re.split(r"[;；]", art) if x.strip()):
        name = a[len("generation:"):] if a.startswith("generation:") else a
        if "/" in name or "\\" in name or re.search(
                r"\.(png|jpg|jpeg|py|json)$", name, re.IGNORECASE):
            missing = [x for x in _expand_braces(name)
                       if not (_file_exists(x, comfy_out)
                               or _file_exists(os.path.basename(x), comfy_out))]
            if missing:
                return False, f"证据文件缺失 {missing[0][:60]}"
        else:
            hits = [i for i in store_ids if i != e["id"] and i in name]
            if not hits:
                return False, f"证据不可解析 {a[:60]}"
    return True, "ok"


# ── R4 回声（向量现算，无向量=保守败）───────────────────────────────────────
def _vec_of(eid: str, e: dict, cache: dict, embed_fn):
    it = (cache.get("items") or {}).get(eid)
    if it:
        return ec._unb64(it["vec"], cache.get("dim") or ec.DEFAULT_DIM)
    if embed_fn is not None:
        try:
            return np.asarray(embed_fn([ec.text_of(e)])[0], dtype=float)
        except Exception:                       # noqa: BLE001 端点故障=无向量（保守）
            return None
    return None


def echo_state(e: dict, ratified: list, cache: dict, embed_fn=None) -> tuple:
    """对已签面最大 cosine → (ok, cos|None)。None=无法核（保守败）。"""
    dv = _vec_of(e["id"], e, cache, embed_fn)
    if dv is None:
        return False, None
    best = 0.0
    for r in ratified:
        rv = _vec_of(r["id"], r, cache, embed_fn)
        if rv is not None:
            best = max(best, ec.cosine(dv, rv))
    return best < ECHO_COS, round(best, 4)


# ── 检定主入口 ──────────────────────────────────────────────────────────────
def _pool_rounds(e: dict, pool: dict, minted_of: dict) -> tuple:
    """R1 轮数链接（池键≠条目指纹——两个哈希空间，实测纠错）：①池 minted 反查
    （style_feed 铸条时 mark_minted 记录）②tags 经 cp.key_of 鲁棒键回退。
    返回 (rounds, pool_key|None)。"""
    link = minted_of.get(e["id"])
    if link:
        return link[1].get("rounds_seen", 0), link[0]
    tags = list((e.get("facts") or {}).get("tags") or e.get("keywords") or [])
    if tags:
        try:
            import candidate_pool as cp
            k = cp.key_of(pool, {"members": tags})
            pe = pool.get(k)
            if pe:
                return pe.get("rounds_seen", 0), k
        except Exception:                       # noqa: BLE001 池损坏=R1 不过（保守）
            return 0, None
    return 0, None


def vet(store: PrecedentStore, pool_path: str = DEFAULT_POOL,
        cache_path: str = DEFAULT_CACHE, embed_fn=None,
        comfy_out: str = DEFAULT_COMFY_OUT,
        neg_ctx: tuple | None = None,
        store_path: str | None = None) -> dict:
    """全库草案四项检定 → {vetted, rejected, counts}。现算；不写库、不改 gov 字段。"""
    try:
        pool = json.load(open(pool_path, encoding="utf-8"))
    except (OSError, ValueError):
        pool = {}
    minted_of = {v.get("minted"): (k, v) for k, v in pool.items() if v.get("minted")}
    cache = ec.load_cache(cache_path)
    ratified = [e for e in store.entries
                if e.get("gov") in ("approved", "verified") and not e.get("tombstone")]
    reg, dfs, cap = neg_ctx if neg_ctx else (None, None, None)
    if reg is None:
        if not store_path:
            raise SystemExit("vet 须 neg_ctx 或 store_path（负例台账构建）")
        reg = nc.build_registry(store_path)
        dfs = cap = None                          # 让 match_negs 自算（巡检路径）
    live = [e for e in store.entries
            if e.get("gov") == "draft" and not e.get("tombstone")
            and not e.get("machine_retracted") and not (e.get("facts") or {}).get("specimen")]
    store_ids = {e["id"] for e in store.entries}
    vetted, rejected = [], []
    counts = {"复现不足": 0, "负例命中": 0, "证据缺失": 0, "回声": 0, "无向量": 0}
    for e in live:
        rounds, sig = _pool_rounds(e, pool, minted_of)
        if rounds < MIN_ROUNDS:
            counts["复现不足"] += 1
            rejected.append({"id": e["id"], "fail": "R1复现", "detail": f"{rounds}轮"})
            continue
        text = json.dumps(e.get("content"), ensure_ascii=False)
        hits = nc.match_negs(reg, text, live, dfs, cap)
        if hits:
            counts["负例命中"] += 1
            rejected.append({"id": e["id"], "fail": "R2负例",
                             "detail": f"{len(hits)}命中"})
            continue
        ok, det = evidence_state(e, store_ids, comfy_out)
        if not ok:
            counts["证据缺失"] += 1
            rejected.append({"id": e["id"], "fail": "R3证据", "detail": det})
            continue
        ok, cos = echo_state(e, ratified, cache, embed_fn)
        if cos is None:
            counts["无向量"] += 1
            rejected.append({"id": e["id"], "fail": "R4回声", "detail": "无向量（保守败）"})
            continue
        if not ok:
            counts["回声"] += 1
            rejected.append({"id": e["id"], "fail": "R4回声", "detail": f"cos={cos}"})
            continue
        vetted.append({"id": e["id"], "sig": sig, "rounds": rounds, "echo": cos,
                       "head": str((e.get("content") or {}).get("c", ""))[:80]})
    return {"vetted": vetted, "rejected": rejected, "counts": counts,
            "live_drafts": len(live)}


def render_lines(v: dict, ranked: list | None = None, k: int = 5) -> list:
    """preflight ③ 分栏（纯行文本；ranked=按查询相关性排序后的子集）。"""
    rows = ranked if ranked is not None else v["vetted"]
    L = [f"│ ③ 机器检定草案 {len(rows)} 条（四检定全过·现算·未经人签——检定≠签发）："]
    for x in rows[:k]:
        L.append(f"│    复现{x['rounds']}轮 回声{x['echo']:.2f} {x['id'][:40]:42s} "
                 f"{x['head'][:52]}")
    if not rows:
        L.append("│    （无——无草案通过四项检定）")
    c = v["counts"]
    L.append(f"│    （落选 {sum(c.values())}：复现不足 {c['复现不足']} · 负例命中 "
             f"{c['负例命中']} · 证据缺失 {c['证据缺失']} · 回声 {c['回声']} · "
             f"无向量 {c['无向量']}）")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="机器检定草案供血（四项检定·现算）")
    ap.add_argument("cmd", nargs="?", default="vet", choices=("vet",))
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--store", default=os.path.join(_HERE, "precedents_e2_seed.json"))
    ap.add_argument("--pool", default=DEFAULT_POOL)
    a = ap.parse_args(argv)
    store = PrecedentStore.load(a.store)
    v = vet(store, a.pool, store_path=a.store)
    for x in v["vetted"][:a.k]:
        print(f"  ✓ 复现{x['rounds']}轮 回声{x['echo']:.2f} {x['id'][:48]:50s} {x['head'][:56]}")
    c = v["counts"]
    print(f"[检定] 活草案 {v['live_drafts']} → 过 {len(v['vetted'])} / 落选 "
          f"{sum(c.values())}（复现不足 {c['复现不足']}·负例 {c['负例命中']}·"
          f"证据 {c['证据缺失']}·回声 {c['回声']}·无向量 {c['无向量']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
