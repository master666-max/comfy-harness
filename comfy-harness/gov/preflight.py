# -*- coding: utf-8 -*-
"""preflight.py — 生图前预检（飞轮"复用"腿接线；维护者问『是否每轮生图前都有一轮（召回）』）

现状（查实）：生图入口（cinematic_gen/flux_gen/z.py batch）**完全不碰经验库**；召回是纯拉取，
无排程。本件=把预检接进生图前：**每轮生图前跑一轮**，做两件事——

  ① **复用量**：拿主题配置（提示词/标签/LoRA/参数）去 `recall_tier` 召回**已签经验**
     （approved+verified；draft 永不供血）→ 打印 top-k，供写作/调参参考；
  ② **负例量**：把同一份配置文本喂 `neg_chain` 的**条件命中**→ 列出"该组合有前车之鉴"的告警
     （strong/mention 分级；refute 不列）。

**只警告、不改配置**（warn-only；`--mode off` 关闭）；每轮落 `style_mine_out/preflight.jsonl` 记账。
用法：
  py gov/preflight.py --theme ron_fem_r11 [--text "自定义配置文本"] [--k 5] [--mode off]
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

import neg_chain as nc                       # noqa: E402
from precedent_gov import PrecedentStore     # noqa: E402

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_THEMES = os.path.join(_HERE, "..", "field", "themes.json")
DEFAULT_LOG = os.path.join(_HERE, "style_mine_out", "preflight.jsonl")


def theme_text(theme: str, themes_path: str = DEFAULT_THEMES) -> str:
    """主题 → 预检文本（提示词 + 采样参数 + LoRA，全部参与召回与负例匹配）。"""
    d = json.load(open(themes_path, encoding="utf-8"))
    th = d.get(theme) or {}
    parts = [str(th.get("pos", "")), str(th.get("neg", "")), str(th.get("lora") or ""),
             f"steps {th.get('steps', 32)} cfg {th.get('cfg', 4.8)} "
             f"hires_denoise {th.get('hires_denoise', 0.45)} grain {th.get('grain', 5.5)} "
             f"zsnr {th.get('zsnr', True)}"]
    return " ".join(p for p in parts if p).strip()


def preflight(theme: str | None = None, text: str | None = None, k: int = 5,
              store_path: str = DEFAULT_STORE, log_path: str = DEFAULT_LOG,
              mode: str = "on") -> dict:
    if mode == "off":
        return {"mode": "off", "query": "", "recall": [], "neg_warnings": [],
                "vetted": [], "vetted_counts": {}}
    q = text or (theme_text(theme) if theme else "")
    s = PrecedentStore.load(store_path)
    # ① 复用量：已签经验召回（recall_tier 只供 approved+verified）
    hits = [(round(float(sc), 4), e["id"], str((e.get("content") or {}).get("c"))[:110])
            for sc, e in s.recall_tier(q, k=k)]
    # ② 负例量：条件命中（匹配器一源两用：nc.match_negs，与草案检定 R2 同件）
    reg = nc.build_registry(store_path)
    from collections import Counter
    live = [e for e in s.entries
            if e.get("gov") == "draft" and not e.get("tombstone")
            and not e.get("machine_retracted") and not (e.get("facts") or {}).get("specimen")]
    dfs = Counter()
    for e in live:
        t_ = json.dumps(e.get("content"), ensure_ascii=False)
        a, c = nc._features(t_)
        for tok in a | c:
            dfs[tok] += 1
    n_live = max(1, len(live))
    cap = max(nc.MIN_DF_CAP, int(n_live * nc.MAX_DF))
    warns = nc.match_negs(reg, q, live, dfs, cap)
    # ③ 机器检定草案（检定陈述制 20261010）：四检定全过者分栏供血，检定≠签发
    vet_rows, vet_counts = [], {}
    try:
        import vetted_supply as vs
        v = vs.vet(s, neg_ctx=(reg, dfs, cap), store_path=store_path)
        vet_rows = v["vetted"]
        try:                                     # 按查询相关性排序（词法；失败按原序供）
            from evocore import retrieval as ecr
            by_id = {x["id"]: x for x in vet_rows}
            pool = [e for e in s.entries if e["id"] in by_id]
            if pool:
                order = {e["id"]: i for i, (_s, e) in enumerate(
                    ecr.retrieve(pool, q, k=len(pool)))}
                vet_rows = sorted(vet_rows, key=lambda x: order.get(x["id"], 10**9))
        except Exception:                        # noqa: BLE001
            pass
        vet_counts = v["counts"]
    except SystemExit:
        raise
    except Exception as ex:                      # noqa: BLE001 响亮不拦预检主功能
        print(f"[预检] ③检定分栏跳过（{type(ex).__name__}: {ex}）")
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "preflight", "theme": theme,
           "query_len": len(q), "recall": hits, "neg_warnings": warns,
           "vetted": [x["id"] for x in vet_rows], "vetted_counts": vet_counts}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"mode": mode, "query": q[:200], "recall": hits, "neg_warnings": warns,
            "vetted": vet_rows, "vetted_counts": vet_counts}


def render(r: dict) -> str:
    if r["mode"] == "off":
        return "[预检] 已关闭"
    L = ["┌─ 生图前预检（飞轮复用腿）" + ("─" * 20)]
    L.append(f"│ ① 已签经验召回 {len(r['recall'])} 条（draft 不供血）：")
    for sc, eid, head in r["recall"]:
        L.append(f"│    {sc:6} {eid[:44]:46s} {head[:60]}")
    if not r["recall"]:
        L.append("│    （无命中——本主题尚无已签经验可复用）")
    L.append(f"│ ② 负例条件告警 {len(r['neg_warnings'])} 条（只警告不改配置）：")
    for w in r["neg_warnings"][:8]:
        L.append(f"│    [{w['tier']:7s}] {w['neg'][:44]:46s} 命中词 {w['hits'][:4]}")
        if w["cond"]:
            L.append(f"│             条件：{w['cond'][:96]}")
    if not r["neg_warnings"]:
        L.append("│    （无——本配置未撞已知负例）")
    # ③ 机器检定草案（检定陈述制 20261010）：与 vetted_supply.render_lines 同源
    try:
        import vetted_supply as vs
        L.extend(vs.render_lines({"vetted": r.get("vetted", []),
                                  "counts": r.get("vetted_counts",
                                                  {"复现不足": 0, "负例命中": 0,
                                                   "证据缺失": 0, "回声": 0, "无向量": 0})},
                                 ranked=r.get("vetted", []), k=5))
    except Exception:                            # noqa: BLE001 分栏失败不拦主预检
        pass
    L.append("└" + ("─" * 40))
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生图前预检（召回+负例条件）")
    ap.add_argument("--theme", default=None)
    ap.add_argument("--text", default=None)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--mode", default="on", choices=("off", "on"))
    a = ap.parse_args(argv)
    if not a.theme and not a.text:
        raise SystemExit("preflight 须 --theme 或 --text")
    print(render(preflight(a.theme, a.text, a.k, a.store, a.log, a.mode)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
