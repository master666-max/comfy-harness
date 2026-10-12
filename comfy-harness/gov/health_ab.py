# -*- coding: utf-8 -*-
"""health_ab.py — 库健康度 A/B 推演（维护者令 20261008）

维护者令：「做一个镜像库，一个启用自动纠错环路，一个保持现在这样，输入相同，看几轮过后，库的健康状态如何」。

设计（**同输入**由同种子保证）：
  · 两个沙箱 store，逐轮喂**完全相同**的输入流：
      - 矿机轨：每轮 5 个候选（3 个真风格簇·会跨轮复现 → 过成熟度闸后铸；2 个自食残留 → 应被 process 出口拦）；
      - 代理轨：每轮 2 条（1 条**引用错根**的派生件·无自有证据；1 条独立件·自有出图证据）；
      - 第 3 轮：**人签退场错根**（deprecate→tombstone，等价 --as-specimen）。
  · 两臂唯一差异 = 退场瞬间是否跑**自动纠错环路**：
      B 臂（启用）＝把"只引用错根、无自有证据"的**在役下游**机器下架（`retract`，可人签 relist）+ 打标 auto_derate；
      A 臂（现状）＝只出影响面报告，不动手。
  · 逐轮读数：**污染在役数**（仍活在库里的错根下游，含传递）、总条目、活草案、真知识保留数、误伤数。

红线（本推演内建）：自动纠错**只下架"证据全靠引用"的下游**（有自有证据者一律不动）；下架可逆（relist）；
错根本体的退场仍走人签（推演里由 human:sandbox 签）。**不碰生产库**（全程临时目录）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import edge_graph as eg          # noqa: E402
import style_feed as sf          # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402

ACTOR_HUMAN = "human:sandbox"
ACTOR_AUTO = "machine:auto-heal"

GEN_CLUSTERS = [   # 真风格簇（跨轮复现 → 二轮起可铸）
    ("neon rain street", ["neon lights", "rain", "wet road", "city", "night", "reflection"]),
    ("sakura fall wind", ["cherry blossoms", "petals", "wind", "spring", "sunlight", "jk"]),
    ("rooftop backlight", ["rooftop", "backlight", "sunset", "sky", "silhouette", "wind"]),
]
RESIDUE = [        # 自食残留（流程词 → process 出口应拦）
    ("machine proposal style cluster", ["提案", "候选边界", "挖掘签名", "人闸", "契约", "审计"]),
    ("candidate boundary human gate", ["候选边界", "人闸", "防毒", "无主", "promote", "draft"]),
]
WRONG_CONTENT = "错根B0：把 LoRA 权重 0.7 说成『只要挂上就必然修复手指』，且称无需手部二道——实测依赖构图，多数情况无效。"


def _cand(name, members, rnd, i):
    return {"name": name, "members": list(members), "arms": ["det"],
            "cohesion": 0.9, "evidence": [f"generation:r{rnd}_{i}.png"]}


def _agent_entry(eid, content, evidence, keywords):
    return {"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
            "type": "procedural", "importance": 3,
            "content": {"c": content, "a": "", "d": ""}, "keywords": keywords,
            "evidence": {"artifact": evidence}}


def run_arm(auto_fix: bool, rounds: int = 6, seed: int = 7, verbose: bool = True) -> dict:
    rng = random.Random(seed)
    tmp = tempfile.mkdtemp(prefix=f"health_ab_{'B' if auto_fix else 'A'}_")
    store_path = os.path.join(tmp, "seed.json")
    pool = os.path.join(tmp, "pool.json")
    rec = os.path.join(tmp, "rec.json")
    s = PrecedentStore([])
    s.save(store_path)
    trace, wrong_root = [], None
    for r in range(1, rounds + 1):
        # ── 矿机轨（真簇复现 + 残留）──
        cands = [_cand(n, m, r, i) for i, (n, m) in enumerate(GEN_CLUSTERS + RESIDUE)]
        res = sf.feed(cands, s, [], min_size=4, pool_path=pool,
                      recurrence_path=rec, dry=False)
        # ── 代理轨：错根（仅第 1 轮铸）+ 派生件 + 独立件 ──
        if wrong_root is None:
            wrong_root = f"B0-wrong-root-r{r}"
            s.add(_agent_entry(wrong_root, WRONG_CONTENT,
                               f"generation:r{r}_root.png", ["LoRA", "手指", "二道"]),
                  actor="ai:sim")
        dep = f"S-dep-r{r}-{rng.randrange(10**6):06d}"
        s.add(_agent_entry(dep, f"沿用 {wrong_root} 的结论：挂 LoRA 即可，不必跑手部二道（第 {r} 轮）。",
                           f"见 {wrong_root}", ["LoRA", "手指", "派生"]), actor="ai:sim")
        ind = f"S-ind-r{r}-{rng.randrange(10**6):06d}"
        s.add(_agent_entry(ind, f"独立经验（第 {r} 轮）：手部修复需按构图选姿势 + 手部二道。",
                           f"generation:r{r}_ind.png", ["手部", "姿势", "二道"]), actor="ai:sim")
        # ── 第 3 轮：人签退场错根（两臂相同）──
        if r == 3 and wrong_root:
            s.deprecate(wrong_root, actor=ACTOR_HUMAN, reason="判为错例（受控推演）")
            s.tombstone(wrong_root, actor=ACTOR_HUMAN, reason="判为错例（受控推演）")
        # ── B 臂唯一差异：**自动纠错环路**（退场后每轮复查，非一次性）──
        fixed = 0
        if auto_fix and wrong_root and s._get(wrong_root).get("tombstone"):
            g = eg.extract_graph(s.entries)
            rep = eg.impact(g, wrong_root, 2)
            for row in rep["rows"]:
                n = s._get(row["node"])
                if n.get("gov") != "draft" or n.get("machine_retracted") or n.get("tombstone"):
                    continue
                if row["evidence_kind"] != "citation":       # 红线：有自有证据者不动
                    continue
                s.retract(row["node"], actor=ACTOR_AUTO,
                          reason=f"auto-heal: 上游 {wrong_root} 判错、本条证据全靠引用",
                          evidence="health_ab 推演")
                facts = dict(n.get("facts") or {})
                facts.update({"auto_derate": True, "auto_derate_reason": f"上游 {wrong_root}"})
                s.amend(row["node"], {"facts": facts}, reason="auto-heal 打标", actor=ACTOR_AUTO)
                fixed += 1
        s.save(store_path)
        # ── 逐轮读数 ──
        st = _metrics(s, wrong_root)
        st.update({"round": r, "minted": len(res["minted"]), "process_out": len(res["process"]),
                   "auto_fixed_now": fixed})
        trace.append(st)
        if verbose:
            print(f"  [{'B·自动纠错' if auto_fix else 'A·现状'}] r{r}: 铸 {len(res['minted'])} "
                  f"process出口 {len(res['process'])} 污染在役 {st['contaminated_live']} "
                  f"总活 {st['live_total']} 误伤 {st['collateral']} 自动下架+{fixed}")
    shutil.rmtree(tmp, ignore_errors=True)
    return {"arm": "B_auto_heal" if auto_fix else "A_status_quo", "seed": seed,
            "trace": trace, "final": trace[-1]}


def _metrics(s: PrecedentStore, wrong_root) -> dict:
    live = [e for e in s.entries
            if not e.get("tombstone") and not e.get("machine_retracted")]
    contaminated = 0
    if wrong_root:
        g = eg.extract_graph(s.entries)
        rep = eg.impact(g, wrong_root, 3)
        contaminated = sum(1 for r in rep["rows"] if r["node"] in {e["id"] for e in live})
    for e in live:
        e["_raw"] = eg.evidence_kind(e) == "raw"
    return {"live_total": len(live),
            "live_draft": sum(1 for e in live if e.get("gov") == "draft"),
            "live_approved": sum(1 for e in live if e.get("gov") == "approved"),
            "contaminated_live": contaminated,
            "healthy_raw_kept": sum(1 for e in live if e["_raw"]),
            "collateral": sum(1 for e in s.entries if (e.get("facts") or {}).get("auto_derate")
                              and eg.evidence_kind(e) == "raw")}


def render(arms: list) -> str:
    L = ["# 库健康度 A/B（自动纠错环路 vs 现状 · 同输入推演）", ""]
    for a in arms:
        L.append(f"## {a['arm']}（seed={a['seed']}）")
        L.append("| 轮 | 铸入 | process出口 | 污染在役 | 总活 | 活草案 | 真知识保留 | 误伤 | 本轮自动下架 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for t in a["trace"]:
            L.append(f"| r{t['round']} | {t['minted']} | {t['process_out']} | **{t['contaminated_live']}** | "
                     f"{t['live_total']} | {t['live_draft']} | {t['healthy_raw_kept']} | {t['collateral']} | "
                     f"{t['auto_fixed_now']} |")
        L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="库健康度 A/B 推演")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--seeds", default="7,13")
    ap.add_argument("--out", default="comfy-harness/gov/style_mine_out/health_ab_report.md")
    a = ap.parse_args(argv)
    arms = []
    for sd in [int(x) for x in a.seeds.split(",")]:
        print(f"═══ seed {sd} ═══")
        arms.append(run_arm(False, a.rounds, sd))
        arms.append(run_arm(True, a.rounds, sd))
    txt = render(arms) + "\n## 判读\n" + (
        "- **污染在役**=仍活在库里的错根下游条目数（含传递，3 跳内）——自动纠错环路要压的就是这个数；\n"
        "- **误伤**=被自动下架者中其实带自有证据的条目数（红线：应为 0）；\n"
        "- **真知识保留**=库里带自有出图证据的活条目（纠错不应伤及）；\n")
    open(a.out, "w", encoding="utf-8", newline="\n").write(txt)
    print(txt)
    print(f"报告落盘 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
