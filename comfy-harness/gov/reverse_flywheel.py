# -*- coding: utf-8 -*-
"""reverse_flywheel.py — 反向飞轮（反例通道 · M1 自食雷达；维护者令 20261008）

依据：报告-反例飞轮可行性-致维护者-20261008.md（M0 已落：标本/影重/promote 守卫）。
本件=**M1 自食雷达**：拿标本库（facts.specimen）对照"即将成形的知识"，
像的就给提示——**只提示不拦、不碰供血池、不改任何闸阈值**（反例三纪律）。

**三态开关**（维护者令：「可以从影子、关闭、开启 3 种形态切换」）：
  off    关闭：零计算零写盘（连影子日志都不碰）
  shadow 影子：只对照+落影子日志（anti_shadow.jsonl），**不注入**消费面
  on     开启（默认，20261009 维护者令『全开，全接线』）：对照 + 日志 + injected=True
         ——feed 侧命中件在报告中打 anti_hit 标记（消费面可见；拦截仍人闸）
解析序：CLI 参数 > 环境变量 ANTI_FLYWHEEL > 默认 on；非法值 → 响亮拒绝（不静默降级）。

判据（确定性，二选一即命中）：
  ①形态闸：is_process(名称,成员) ≥ 2（与铸前 process 出口同源；单独命中=纯规则面）
  ②标本同形：与任一标本条目 cosine ≥ cos_cut（默认 0.90，与近重复闸同刻）
红线的体现：命中只写"提示"；**不生成拒绝、不改候选集、不写受治库**。

用法：
  py -X utf8 reverse_flywheel.py stats                # 影子日志统计（含 T-c）
  py -X utf8 reverse_flywheel.py scan --candidates P  # 对一批候选跑雷达（默认 shadow）
  py -X utf8 reverse_flywheel.py scan --candidates P --mode on
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

import embed_cache as ec                       # noqa: E402
import style_feed as sf                        # noqa: E402

MODE_ENV = "ANTI_FLYWHEEL"
MODES = ("off", "shadow", "on")
DEFAULT_MODE = "on"       # 20261009 维护者令『全开，全接线』（原 shadow 观察期结束：T1 达标）
DEFAULT_SHADOW = os.path.join(_HERE, "style_mine_out", "anti_shadow.jsonl")
DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
COS_CUT = 0.90
PROCESS_CUT = 2


def resolve_mode(cli: str | None = None, env: str | None = None) -> str:
    """三态解析：CLI > 环境变量 > 默认 shadow。非法值响亮拒绝（禁静默降级）。"""
    raw = (cli if cli is not None else (env if env is not None
                                        else os.environ.get(MODE_ENV)) or DEFAULT_MODE)
    m = str(raw).strip().lower()
    if m not in MODES:
        raise SystemExit(f"DENY:BAD_MODE 反向飞轮模式 {raw!r} 非法——合法值 {MODES}"
                         f"（off 关闭 / shadow 影子 / on 开启）")
    return m


def specimens(store, cache: dict | None = None) -> list:
    """标本条目（facts.specimen 真值）+ 其向量（缓存可缺，缺则只在形态闸上有用）。"""
    out = []
    items = (cache or {}).get("items") or {}
    dim = (cache or {}).get("dim") or ec.DEFAULT_DIM
    for e in store.entries:
        f = e.get("facts") or {}
        if not f.get("specimen"):
            continue                                   # 退场标本**要收**：人签退的错条正是最佳标本
        it = items.get(e["id"])
        retired = bool(e.get("tombstone") or e.get("deprecated") or e.get("machine_retracted"))
        out.append({"id": e["id"],
                    "note": str(f.get("specimen_note") or "")[:120],
                    "shadow_weight": f.get("shadow_weight"),
                    "retired": retired,                # 呈现面标注（退场标本与在役标本区分）
                    "vec": ec._unb64(it["vec"], dim) if it else None})
    return out


def judge(name: str, members: list, spec: list, cache_path: str = ec.DEFAULT_CACHE,
          embed_fn=None, cos_cut: float = COS_CUT) -> dict:
    """单候选判定（纯逻辑；embed 可 DI）。返回 {verdict, by[], nearest, process_hits}。"""
    hits = sf.is_process(str(name), list(members))
    by = []
    if hits >= PROCESS_CUT:
        by.append(f"形态闸：流程词命中 {hits}（≥{PROCESS_CUT}）")
    nearest = {"id": None, "cos": None}
    with_vec = [s for s in spec if s.get("vec") is not None]
    if with_vec and members:
        fn = embed_fn or ec.embed_docs
        try:
            v = fn([sf.candidate_text(str(name), list(members))])[0]
            best = max(((s["id"], ec.cosine(v, s["vec"])) for s in with_vec),
                       key=lambda x: x[1])
            nearest = {"id": best[0], "cos": round(float(best[1]), 4)}
            if best[1] >= cos_cut:
                by.append(f"标本同形：{best[0]} cos={round(float(best[1]), 4)}（≥{cos_cut}）")
        except Exception as ex:                                # noqa: BLE001 响亮不静默
            by.append(f"标本对照跳过（{type(ex).__name__}: {str(ex)[:60]}）")
    return {"verdict": "hit" if by else "clear", "by": by,
            "process_hits": hits, "nearest": nearest}


def _append(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run(cands: list, store, mode: str | None = None, shadow_path: str = DEFAULT_SHADOW,
        cache_path: str = ec.DEFAULT_CACHE, embed_fn=None, source: str = "feed") -> dict:
    """对一批候选跑雷达。off=零动作；shadow=只写影子日志；on=同样的记录 + injected=True。"""
    m = resolve_mode(mode)
    if m == "off":
        return {"mode": "off", "checked": 0, "hits": [], "injected": False}
    cache = ec.load_cache(cache_path)
    spec = specimens(store, cache)
    hits, checked = [], 0
    for c in cands:
        checked += 1
        r = judge(c.get("name", ""), c.get("members") or [], spec,
                  cache_path=cache_path, embed_fn=embed_fn)
        if r["verdict"] == "hit":
            hits.append({"candidate": str(c.get("name", ""))[:60], **r})
    _append(shadow_path, {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "scan",
                          "mode": m, "source": source, "checked": checked,
                          "hits": len(hits), "specimens": len(spec)})
    for h in hits:
        _append(shadow_path, {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "hit",
                              "mode": m, "source": source, **h})
    return {"mode": m, "checked": checked, "hits": hits,
            "injected": m == "on", "specimens": len(spec)}


def stats(shadow_path: str = DEFAULT_SHADOW) -> dict:
    """影子日志统计（T-c 原料）：扫描轮数/受检数/命中数。"""
    scans, hits, checked, last = 0, 0, 0, None
    if os.path.isfile(shadow_path):
        for line in open(shadow_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "scan":
                scans += 1
                hits += int(r.get("hits") or 0)
                checked += int(r.get("checked") or 0)
                last = r
    return {"scans": scans, "hits": hits, "checked": checked,
            "hit_rate": round(hits / checked, 4) if checked else None,
            "last": last}


def main(argv=None):
    ap = argparse.ArgumentParser(description="反向飞轮（反例通道 · 三态：off/shadow/on）")
    ap.add_argument("cmd", choices=("stats", "scan"))
    ap.add_argument("--candidates", default=None, help="候选 JSON（style_mine_out 格式）")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--shadow", default=DEFAULT_SHADOW)
    ap.add_argument("--cache", default=ec.DEFAULT_CACHE)
    ap.add_argument("--mode", default=None, help="off|shadow|on（缺省读 ANTI_FLYWHEEL，再缺省 shadow）")
    a = ap.parse_args(argv)
    if a.cmd == "stats":
        s = stats(a.shadow)
        print(f"[反向飞轮·影子日志] 扫描 {s['scans']} 轮 · 命中 {s['hits']} · "
              f"最近命中率 {s['hit_rate']}")
        if s["last"]:
            print(f"  最近一轮：{s['last']}")
        return 0
    if not a.candidates:
        raise SystemExit("scan 须 --candidates P")
    d = json.load(open(a.candidates, encoding="utf-8"))
    cands = d.get("clusters") or d.get("candidates") or []
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(a.store)
    # source 记相对路径（含目录）：回放基准（remine_baseline/…）须可被 T1 波动口径识别过滤
    try:
        src = os.path.relpath(os.path.abspath(a.candidates), _HERE).replace(os.sep, "/")
    except ValueError:
        src = os.path.basename(a.candidates)
    r = run(cands, store, a.mode, a.shadow, a.cache, source=src)
    print(f"[反向飞轮] 模式={r['mode']} 标本 {r.get('specimens', 0)} 族 · 受检 {r['checked']} · "
          f"命中 {len(r['hits'])}"
          + ("（影子：仅落日志，不注入）" if r["mode"] == "shadow" else
             "（开启：提示生效）" if r["mode"] == "on" else ""))
    for h in r["hits"]:
        print(f"  ⚠ {h['candidate']}\n     {'；'.join(h['by'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
