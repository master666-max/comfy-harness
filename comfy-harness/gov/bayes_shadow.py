# -*- coding: utf-8 -*-
"""bayes_shadow.py — 贝叶斯传播·序数版（20261010 维护者令「贝叶斯影子转正」）

依据：报告-传播算法与反向飞轮评估 §八（风险清单 R1-R8 + 安全形态）。
**纪律（转正令修订，写死在代码里）**：
  ① 输出**序数**（名次 + 高/中/低档），**不输出百分比概率**——未校准的分数会冒充精确（R1）；
  ② **转正=act 缺省**（20261010「贝叶斯影子转正」）：**榜首动作制**——每根每轮只对榜一
     可动靶执行**一个**机器面可逆动作：error 根→纯引用 draft 下架（人签 relist 可复架）；
     派生 draft→打标；suspect 根（前提翻倒依赖）→只打标；healthy 根→只入账不动。
     榜一如不可动（标本/人签面/自有证据）→ 留痕即停，**不向下顺延**（禁静默升级）。
     轮次棘轮：已下架件自然出榜，下轮榜一自动轮替，逐轮走完整榜；
  ③ 动作权限面：只碰 draft；approved/verified/标本/墓碑/已撤件一律跳过；gov 字段不动
     （deprecate/tombstone/promote 仍人闸专属）——非放大红线；
  ④ **动作不按分档阈值**：0.5/0.2 是未校准拍值，不配驱动撤件——按**名次**（榜一）执行，
     分档只做呈现。似然比仍是拍值，校准须等人签复核样本 ≥3（评估件 §五 T3）。

似然比（**未校准·拍值·待人签样本校准**）：merged-from 1.5 / cites 1.2 / base-mate 1.05 / cluster-mate 1.05
算法：与 edge_graph.propagate 同构的确定性阻尼迭代（12 轮 / damping 0.85），结果取序分档后落日志。

用法：
  py -X utf8 bayes_shadow.py run --id X [--mode off|shadow|on|act] [--root-kind error|suspect|healthy]
  py -X utf8 bayes_shadow.py stats
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

MODE_ENV = "BAYES_SHADOW"
DEFAULT_MODE = "act"      # 20261010 维护者令『贝叶斯影子转正』（榜首动作制；off/shadow/on 三态保留）
DEFAULT_LOG = os.path.join(_HERE, "style_mine_out", "bayes_shadow.jsonl")
DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
# 未校准似然比（拍值；校准须等人签复核样本 ≥3 —— 见评估件 §五 T3）
LR_TABLE = {"merged-from": 1.5, "cites": 1.2, "base-mate": 1.05, "cluster-mate": 1.05}
BAND_HIGH, BAND_MID = 0.5, 0.2
UNcalib_NOTE = "未校准先验（拍值）——仅供影子比对，禁作决策依据"


def mode(cli: str | None = None, env: str | None = None) -> str:
    raw = (cli if cli is not None else (env if env is not None
                                        else os.environ.get(MODE_ENV)) or DEFAULT_MODE)
    m = str(raw).strip().lower()
    if m not in ("off", "shadow", "on", "act"):
        raise SystemExit(f"DENY:BAD_MODE 贝叶斯模式 {raw!r} 非法（off/shadow/on/act）")
    return m


def posterior_ordinal(graph: dict, root: str, lr: dict | None = None,
                      iters: int = eg.ITERS, damping: float = eg.DAMPING) -> list:
    """序数后验：返回 [{node, rank, band, lr_used, hop}]——**不含概率数字**。"""
    table = dict(LR_TABLE if lr is None else lr)
    # 衰减与主传播同刻（λ=0.6）：距离支配、似然比只区分边型——
    # 初版 λ=1.0 时 2 跳血缘链(LR1.5²=2.25)会压过 1 跳引用(1.2)，与"越远越弱"直觉相悖
    sc = eg.propagate(graph, root, weights=table, lam=eg.LAMBDA_DECAY,
                      damping=damping, iters=iters)
    ranked = sorted(sc.items(), key=lambda kv: (-kv[1]["score"], kv[0]))
    out = []
    for i, (n, v) in enumerate(ranked, 1):
        band = ("high" if v["score"] >= BAND_HIGH else
                "mid" if v["score"] >= BAND_MID else "low")
        out.append({"node": n, "rank": i, "band": band, "hop": v["hop"],
                    "lr_used": {k: table.get(k) for k in sorted(table)},
                    "uncalibrated": True})
    return out


def _act_top(graph: dict, root: str, ranked: list, store_path: str,
             root_kind: str) -> dict:
    """榜首动作制：从榜一找第一件**可动**靶，动一件即停（禁向下顺延=禁静默升级）。

    可动靶（全机器权限面·可逆）：
      error 根   纯引用 draft → retract（人签 relist 可复架）+ 打标；派生 draft → 只打标
      suspect 根 任何 draft   → 只打标（前提翻倒依赖是"待复核"不是"已判坏"）
    榜一是标本 / 人签面 / 自有证据(raw) / 墓碑已撤之外不可动 → 留痕即停。"""
    if not ranked:
        return {"acted": None, "why": "空榜"}
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    ek = {r["node"]: r.get("evidence_kind")
          for r in eg.impact(graph, root, 2)["rows"]}
    for top in ranked:
        node = top["node"]
        try:
            e = store._get(node)
        except Exception:                                   # noqa: BLE001 节点不在库=不可动
            continue
        if e.get("tombstone") or e.get("machine_retracted"):
            continue                                        # 死件不占榜一，顺延找活靶
        if (e.get("facts") or {}).get("specimen"):
            return {"acted": None, "why": f"榜首 {node} 是标本（跳过不动作）"}
        if e.get("gov") in ("approved", "verified"):
            return {"acted": None, "why": f"榜首 {node} 人签面（降格须人签）"}
        k = ek.get(node, "unknown")
        if k == "raw":
            return {"acted": None, "why": f"榜首 {node} 自有实测证据（红线不动）"}
        facts = dict(e.get("facts") or {})
        facts["auto_derate"] = {"reason": f"bayes-act: 根 {root} 后验榜一(第{top['rank']}名)",
                                "by": "machine:bayes-act", "root": root}
        retracted = False
        if root_kind == "error" and k == "citation" and e.get("gov") == "draft":
            store.retract(node, actor="machine:bayes-act",
                          reason=f"bayes-act: 根 {root} 已判坏、本条证据全靠引用"
                                 f"（人签 relist 可复架）",
                          evidence="bayes_shadow act-mode 榜首动作")
            retracted = True
        store.amend(node, {"facts": facts}, reason="bayes-act 榜首打标",
                    actor="machine:bayes-act")
        store.save(store_path)
        return {"acted": node, "action": "retract+flag" if retracted else "flag",
                "evidence_kind": k, "rank": top["rank"]}
    return {"acted": None, "why": "榜上无可动靶"}


def run(graph: dict, root: str, m: str | None = None, log_path: str = DEFAULT_LOG,
        lr: dict | None = None, store_path: str = DEFAULT_STORE,
        root_kind: str = "error") -> dict:
    m = mode(m)
    if m == "off":
        return {"mode": "off", "checked": 0, "ranked": [], "injected": False,
                "acted": None}
    if root_kind not in ("error", "suspect", "healthy"):
        raise SystemExit(f"DENY:BAD_ROOT_KIND root_kind {root_kind!r} 非法"
                         "（error|suspect|healthy）")
    ranked = posterior_ordinal(graph, root, lr)
    acted = None
    if m == "act" and root_kind != "healthy":               # healthy 根=只入账（信任根不驱动动作）
        acted = _act_top(graph, root, ranked, store_path, root_kind)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "posterior_ordinal",
           "mode": m, "root": root, "root_kind": root_kind, "n": len(ranked),
           "ranked": ranked, "acted": acted,
           "note": (UNcalib_NOTE if m != "act" else
                    "act=榜首动作制（draft-only·机器面可逆·relist 可复架）；分档阈值不驱动动作")}
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"mode": m, "checked": len(ranked), "ranked": ranked, "acted": acted,
            "injected": m in ("on", "act")}


def stats(log_path: str = DEFAULT_LOG) -> dict:
    runs, n_roots = 0, set()
    if os.path.isfile(log_path):
        for line in open(log_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "posterior_ordinal":
                runs += 1
                n_roots.add(r.get("root"))
    return {"runs": runs, "roots": len(n_roots),
            "note": "账本（似然比未校准；act=榜首动作制·draft-only·可逆）"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="贝叶斯传播·序数版（转正：榜首动作制）")
    ap.add_argument("cmd", choices=("run", "stats"))
    ap.add_argument("--id", default=None)
    ap.add_argument("--mode", default=None, help="off|shadow|on|act（缺省 act）")
    ap.add_argument("--root-kind", default="error", choices=("error", "suspect", "healthy"))
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--store", default=DEFAULT_STORE)
    a = ap.parse_args(argv)
    if a.cmd == "stats":
        s = stats(a.log)
        print(f"[贝叶斯] 运行 {s['runs']} 次 · 覆盖根 {s['roots']} 条 · {s['note']}")
        return 0
    if not a.id:
        raise SystemExit("run 须 --id X")
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(a.store)
    g = eg.extract_graph(store.entries)
    r = run(g, a.id, a.mode, a.log, store_path=a.store, root_kind=a.root_kind)
    tag = {"off": "（off：零动作）", "shadow": "（仅入账）",
           "on": "（仅入账）", "act": "（act：榜首动作制）"}[r["mode"]]
    print(f"[贝叶斯] 模式={r['mode']} 根型={a.root_kind} 序数结果 {r['checked']} 条{tag}")
    for x in r["ranked"][:8]:
        print(f"  #{x['rank']} [{x['band']}] hop={x['hop']} {x['node'][:52]}")
    if r.get("acted"):
        ax = r["acted"]
        if ax.get("acted"):
            print(f"  ▶ 动作 {ax['action']} → {ax['acted'][:52]}（证据档={ax['evidence_kind']}）")
        else:
            print(f"  ▷ 榜一未动：{ax.get('why')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
