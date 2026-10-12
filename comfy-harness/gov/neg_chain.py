# -*- coding: utf-8 -*-
"""neg_chain.py — 反向飞轮→纠错环路→影响传播 **三段一体**（维护者令 20261008）

维护者指出：窄版（auto_heal 只跑"人判过错的下游纯引用件"）对"反向经验飞轮"而言太窄——
负知识不该只在**引用边**上生效，更该按**条件**命中所有满足条件的条目（哪怕从未引用过它）。

**三段**：
  ① 反向飞轮·负例台账（`build_registry`）：把四类负知识并成一张台账——
     标本件（facts.specimen）/ 人签裁撤件（tombstone+specimen）/ **减损·异常观察**（obs 账本）/
     反证线索（条目自述"推翻/复测不成立"）。每条带【条件】与【特征词】。
  ② 纠错环路·条件命中（`scan`）：逐条活经验做**条件匹配**（不依赖引用边）——
     命中分档：`strong`（≥2 ASCII 特征词 或 1 词+≥3 中文双字）/ `mention`（弱命中）/
     `refute`（条目自述反证=纠正源，**不动作**）。
  ③ 影响传播·排序（复用 edge_graph）：命中项按 `传播分 × (1+下游数)` 排优先级——
     先处置"影响面大"的，而非按发现顺序。

**动作口径（红线不变）**：`strong` 且**无自有证据** → retract（机器面·可逆）+ auto_derate；
`strong` 有自有证据 / `mention` → 只打标；`refute` → 不动作只登记。
开关：`NEG_CHAIN=off|shadow|on`（默认 on，维护者令『别保守』）；日志 style_mine_out/neg_chain.jsonl。
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

import edge_graph as eg                     # noqa: E402

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_LOG = os.path.join(_HERE, "style_mine_out", "neg_chain.jsonl")
OBS_DIR = os.path.join(_HERE, "..", "field", "out")
ACTOR = "machine:neg-chain"
ENV = "NEG_CHAIN"
_OFF = {"0", "off", "false", "no"}
REFUTE_PAT = re.compile(r"反证|推翻|无法复现|复测不成立|证伪|不可复现|已废弃|不采纳")
# 规范性措辞：条目在"推荐/固定用"该组合——条件命中+推荐才允许下架（仅同域提及→只打标）
PRESCRIPTIVE = re.compile(r"推荐|固定用|照抄|建议|必用|统一用|标准做法|直接用|据此|务必")
# 模板套话剥离（实测：不剥则同模板旧条目互相命中=假阳性主源）
BOILER = re.compile(
    r"机器提案·风格簇|双挖掘器涌现|可回源|style_mine_out/\S+|det\+lightrag\S*|deepseek-v4\S*|"
    r"挖掘签名\s*\S*|观察签名\s*\S*|凝聚度\s*[\d.]+|臂=[^\s，。;；]*|成员\s*\d+\s*项|"
    r"候选边界|无主防毒|人签晋升|两段式退场")
ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]+")
MAX_DF = 0.05            # 特征词文档频率上限（超=通用词出表）
MIN_DF_CAP = 3           # DF 绝对值下限（小语料下保证锚点词不被全杀）
ANCHOR_RE = re.compile(r"[0-9_.\-]")    # 含数字/点/连字符/下划线 = 具体锚点词（如 noobai-xl/v1.0/c0b46271）
MAX_NEG_DF = 3           # 特征词在负例台账里的出现条数上限（超=负例间通用词）


def match_negs(reg: list, text: str, live: list, dfs=None, cap: int | None = None) -> list:
    """条件命中（公开匹配器，20261010 抽取）：text 对负例台账的分档命中列表。

    语义与 scan/preflight ② 完全同源（DF 闸→锚点分档→refute 不列）；
    preflight ②（配置文本告警）与 vetted_supply R2（草案检定）共用本件——
    两处匹配语义漂移曾在设计中出现风险，抽此处一源两用根治。
    live=活件列表（算 DF 用）；dfs/cap 可传预计算值（批量检定时省 O(n²)）。
    返回 [{tier, neg, src, cond, hits}]（tier ∈ strong/mention；miss/refute 不列）。"""
    from collections import Counter
    if dfs is None:
        dfs = Counter()
        for e in live:
            t_ = json.dumps(e.get("content"), ensure_ascii=False)
            a_, c_ = _features(t_)
            for tok in a_ | c_:
                dfs[tok] += 1
    n_live = max(1, len(live))
    if cap is None:
        cap = max(MIN_DF_CAP, int(n_live * MAX_DF))
    out = []
    for neg in reg:
        st = _strength(neg, text)
        if st["tier"] == "miss":
            continue
        st["ascii_hits"] = [x for x in st["ascii_hits"] if dfs[x] <= cap]
        st["cjk_hits"] = [x for x in st["cjk_hits"] if dfs[x] <= cap]
        anchors = [x for x in st["ascii_hits"] if _is_anchor(x)]
        tier = ("strong" if (len(anchors) >= 2 or (anchors and len(st["cjk_hits"]) >= 3))
                else "mention" if (anchors and (len(anchors) + len(st["cjk_hits"])) >= 3)
                or len(st["cjk_hits"]) >= 5 else "miss")
        if tier == "miss" or REFUTE_PAT.search(text):
            continue
        out.append({"tier": tier, "neg": neg["ref"], "src": neg["src"],
                    "cond": neg["cond"][:140], "hits": (anchors + st["cjk_hits"])[:6]})
    out.sort(key=lambda x: (x["tier"] != "strong", x["neg"]))
    return out


def is_disabled(cli_off: bool = False, env: str | None = None) -> bool:
    v = (env if env is not None else os.environ.get(ENV, "")).strip().lower()
    return cli_off or v in _OFF


def _is_anchor(tok: str) -> bool:
    """具体锚点词：带数字/分隔符，或长度 ≥9 的英文词——'cinematic/clean/style' 这类通用词不算。"""
    return bool(ANCHOR_RE.search(tok)) or len(tok) >= 14   # ≥14 才认长词（cinematic=9 属通用）


def _strip(text: str) -> str:
    return BOILER.sub(" ", str(text))


def _features(text: str) -> tuple:
    """特征词：ASCII 词（模型/参数/文件名词）∪ 中文双字（去单字噪声）；先剥模板套话。"""
    text = _strip(text)
    ascii_toks = set()
    for m in ASCII_RE.finditer(text):
        tok = m.group().lower()
        ascii_toks.add(tok)
        if re.search(r"[_.\-]", tok):                      # 文件名/包名：分隔符切分 + **n-gram 连接**（≤3 段）
            parts = [p for p in re.split(r"[_.\-]+", tok) if p]
            ascii_toks |= {p for p in parts if len(p) >= 2}
            for i in range(len(parts)):
                for j in range(i + 2, min(i + 4, len(parts) + 1)):
                    ascii_toks.add("_".join(parts[i:j]))    # 例：M_dz_nbv_… → 亦产 'm_dz'（与负例的独立 m_dz 可对上）
    ascii_toks.discard("safetensors")
    cjk = set()
    for w in CJK.findall(text):
        cjk |= {w[i:i + 2] for i in range(len(w) - 1)} if len(w) > 1 else {w}
    return ascii_toks, cjk


def build_registry(store_path: str = DEFAULT_STORE, obs_dir: str = OBS_DIR) -> list:
    """① 负例台账：标本 / 裁撤件 / 减损·异常观察 / 反证线索 —— 每条带条件与特征词。"""
    from precedent_gov import PrecedentStore
    s = PrecedentStore.load(store_path)
    reg = []
    for e in s.entries:
        f = e.get("facts") or {}
        if not f.get("specimen"):
            continue
        kind = "retired_wrong" if e.get("tombstone") else "specimen_live"
        cond = str(f.get("specimen_note") or "")
        text = json.dumps(e.get("content"), ensure_ascii=False) + " " + cond
        a, c = _features(text)
        reg.append({"src": kind, "ref": e["id"], "cond": cond[:200],
                    "feature_ascii": sorted(a), "feature_cjk": sorted(c)[:40]})
    for fname in sorted(os.listdir(obs_dir)) if os.path.isdir(obs_dir) else []:
        if not fname.endswith("_obs.jsonl"):
            continue
        for ln in open(os.path.join(obs_dir, fname), encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            # 复审（平反/翻案）不入负例台账：台账=负例名册，平反的机械归宿是
            # premises.py 翻倒票（20261009）——混入会污染 DF 降噪闸并反向加固误判
            if o.get("类") not in ("减损", "异常", "伪影"):
                continue
            cond = str(o.get("条件") or "")
            text = f"{o.get('现象', '')} {cond} {o.get('证据', '')}"
            a, c = _features(text)
            reg.append({"src": "obs_" + str(o.get("类")), "ref": f"{fname}:{cond[:40]}",
                        "cond": cond[:200], "对照": bool(o.get("对照")),
                        "actionable": bool(o.get("对照")) and str(o.get("类")) in ("减损", "伪影"),
                        "可复算": str(o.get("可复算") or "")[:120],
                        "feature_ascii": sorted(a), "feature_cjk": sorted(c)[:40]})
    for n in reg:                                     # 标本/裁撤件视为已对照（可动作）
        n.setdefault("actionable", True)
    # ── 降噪闸（台账级）：负例间通用词出表
    from collections import Counter
    df = Counter()
    for n in reg:
        for tok in set(n["feature_ascii"]) | set(n["feature_cjk"]):
            df[tok] += 1
    for n in reg:
        n["feature_ascii"] = [x for x in n["feature_ascii"] if df[x] < MAX_NEG_DF]
        n["feature_cjk"] = [x for x in n["feature_cjk"] if df[x] < MAX_NEG_DF]
    return reg


def _strength(neg: dict, text: str) -> dict:
    a, c = _features(text)
    sa = set(neg["feature_ascii"]) & a
    sc = set(neg["feature_cjk"]) & c
    strong = len(sa) >= 2 or (len(sa) >= 1 and len(sc) >= 3)
    mention = (len(sa) + len(sc)) >= 3
    return {"ascii_hits": sorted(sa), "cjk_hits": sorted(sc)[:6],
            "tier": "strong" if strong else "mention" if mention else "miss"}


def scan(store_path: str = DEFAULT_STORE, obs_dir: str = OBS_DIR,
         log_path: str = DEFAULT_LOG, mode: str = "on", dry: bool = False) -> dict:
    """②③ 条件命中（不看引用边）+ 传播排序；按模式动作（on 真动作 / shadow 只报）。"""
    from precedent_gov import PrecedentStore
    s = PrecedentStore.load(store_path)
    reg = [n for n in build_registry(store_path, obs_dir)
           if n["src"] not in ("specimen_live", "retired_wrong") or True]
    live = [e for e in s.entries
            if e.get("gov") == "draft" and not e.get("tombstone") and not e.get("machine_retracted")
            and not (e.get("facts") or {}).get("specimen")]      # ② 靶排除：负例自身不作靶
    from collections import Counter
    dfs = Counter()                                   # ① 语料文档频率（判通用词）
    corpus_feats = []
    for e in live:
        txt = (json.dumps(e.get("content"), ensure_ascii=False) + " "
               + " ".join(str(k) for k in (e.get("keywords") or [])))
        a, c = _features(txt)
        corpus_feats.append((a, c))
        for tok in a | c:
            dfs[tok] += 1
    n_live = max(1, len(live))
    g = eg.extract_graph(s.entries)
    indeg = {}
    for edge in g["edges"]:
        indeg[edge["up"]] = indeg.get(edge["up"], 0) + 1        # 下游数（谁引用它）
    hits, acted = [], []
    for e, (ea, ec_) in zip(live, corpus_feats):
        text = (json.dumps(e.get("content"), ensure_ascii=False) + " "
                + " ".join(str(k) for k in (e.get("keywords") or [])))
        best = None
        for neg in reg:
            if (neg["src"], neg["ref"]) == ("__self__", e["id"]):
                continue
            st = _strength(neg, text)
            if st["tier"] == "miss":
                continue
            # ① 语料 DF 闸：命中词若在活件里过半常见 → 视为通用词剔除
            cap = max(MIN_DF_CAP, int(n_live * MAX_DF))
            st["ascii_hits"] = [x for x in st["ascii_hits"] if dfs[x] <= cap]
            st["cjk_hits"] = [x for x in st["cjk_hits"] if dfs[x] <= cap]
            if not st["ascii_hits"] and not st["cjk_hits"]:
                continue
            if st.get("tier") == "miss":                      # 锚点不足：不算命中
                continue
            anchors = [x for x in st["ascii_hits"] if _is_anchor(x)]
            st["anchors"] = anchors
            st["tier"] = ("strong" if (len(anchors) >= 2
                                       or (anchors and len(st["cjk_hits"]) >= 3))
                          else "mention" if (anchors and (len(anchors) + len(st["cjk_hits"])) >= 3)
                          or len(st["cjk_hits"]) >= 5 else "miss")
            if st["tier"] == "miss":
                continue                                      # 重算后仍 miss：不算命中（原漏网）
            # ③ 可动作性：非对照观察最多 mention（只打标）
            if not neg.get("actionable", True) and st["tier"] == "strong":
                st["tier"] = "mention"
            ek = eg.evidence_kind(e)
            if REFUTE_PAT.search(text):
                tier, action = "refute", "none（纠正源，不动作）"
            elif (st["tier"] == "strong" and ek != "raw" and PRESCRIPTIVE.search(text)):
                tier, action = "strong", "retract+flag"      # 强命中+在推荐该组合+无自有证据 → 下架
            elif st["tier"] == "strong":
                tier, action = "strong", "flag"              # 强命中但不属"推荐"→ 只打标（人审队列）
            else:
                tier, action = st["tier"], "flag"
            priority = round((2.0 if tier == "strong" else 1.0) * (1 + 0.2 * indeg.get(e["id"], 0)), 3)
            rec = {"entry": e["id"], "neg": neg["ref"], "neg_src": neg["src"], "tier": tier,
                   "action": action, "evidence_kind": ek, "priority": priority,
                   "ascii_hits": st["ascii_hits"], "cjk_hits": st["cjk_hits"]}
            if best is None or priority > best["priority"]:
                best = rec
        if best is None:
            continue
        hits.append(best)                                    # 每活件只留最高优先级一条
        neg = {"ref": best["neg"]}
        if mode == "on" and best["action"].startswith(("retract", "flag")) and not dry:
            facts = dict(e.get("facts") or {})
            facts.update({"auto_derate": True, "auto_derate_reason": f"条件命中负例 {neg['ref']}"})
            if best["action"] == "retract+flag":
                s.retract(e["id"], actor=ACTOR,
                          reason=f"neg-chain: 条件命中负例（{neg['ref']}）且无自有证据",
                          evidence="neg_chain 条件扫描")
            s.amend(e["id"], {"facts": facts}, reason="neg-chain 打标", actor=ACTOR)
            acted.append(best)
    if acted:
        s.save(store_path)
    hits.sort(key=lambda x: -x["priority"])
    out = {"mode": "off" if is_disabled(mode == "off") else mode, "negatives": len(reg),
           "live_scanned": len(live), "hits": hits, "acted": acted,
           "note": ("条件命中不依赖引用边；strong 且无自有证据才 retract（机器面·可逆）；"
                    "refute=纠正源不动作；优先级=强度×(1+下游数)")}
    if mode != "off":
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        tail = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "neg_chain_scan",
                "mode": mode, "negatives": len(reg), "live_scanned": len(live),
                "hits": len(hits), "acted": len(acted),
                "top": hits[:10]}
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(tail, ensure_ascii=False) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="反向飞轮→纠错环路→影响传播 三段一体")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--obs-dir", default=OBS_DIR)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--mode", default="on", choices=("off", "shadow", "on"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--registry", action="store_true", help="只打印负例台账")
    a = ap.parse_args(argv)
    if a.registry:
        for n in build_registry(a.store, a.obs_dir):
            print(f"[{n['src']:14s}] {n['ref'][:58]:60s} 特征词 {n['feature_ascii'][:6]}")
        return 0
    r = scan(a.store, a.obs_dir, a.log, a.mode, a.dry_run)
    print(f"[neg-chain] 模式={r['mode']} 负例 {r['negatives']} 条 × 活件 {r['live_scanned']} 条 "
          f"→ 命中 {len(r['hits'])}（真动作 {len(r['acted'])}）")
    for h in r["hits"][:12]:
        print(f"   [{h['tier']:7s}] {h['action']:14s} 优先级={h['priority']:5} "
              f"{h['entry'][:44]:46s} ← {h['neg'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
