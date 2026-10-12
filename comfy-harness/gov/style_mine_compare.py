# -*- coding: utf-8 -*-
"""style_mine_compare.py — 双挖掘器并行编排 + 涌现对比报告（维护者令·20261008）

维护者令："风格簇和lightrag全都要做，看最后的自动涌现，来对比那个更好，同步并行运行，
记得两个都加个开关。" 本件=编排者与记分员，不代做终判——它负责让两边的涌现**可比**
（同语料/同构输出/同表读数），"哪个更好"的判读素材摆齐后交给维护者。

编排：
  1) 语料：style_corpus.build_corpus 刷 corpus.json（两臂同吃一份）；
  2) A 臂（确定性）：线程内跑 style_mine_det.main() → det_candidates.json；
  3) B 臂（LightRAG）：线程内子进程拉起 venv python 跑 style_mine_lightrag.py
     → lightrag_candidates.json（解释器 STYLE_LR_PY，默认 style-lightrag venv）；
     两臂 concurrent.futures 并行（"同步并行运行"）。
  4) 开关：STYLE_MINE_DET / STYLE_MINE_LIGHTRAG=off（或 --no-det / --no-lr）——
     关掉的臂不跑，报告里如实标 disabled。
  5) 对比：规模/证据覆盖/耗时/确定性 + 跨臂簇配对（成员名归一：等值或包含）——
     "两边都看到的"=配对表，"各自独有"=单向表。产出 md + compare.json。

用法（主环境即可跑；B 臂的 venv 由本件按 stdlib 子进程方式拉起）：
  py -X utf8 style_mine_compare.py [--no-det] [--no-lr] [--report PATH]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import style_corpus as sc                     # noqa: E402
import style_mine_det as sd                   # noqa: E402
import style_mine_lightrag as sl              # noqa: E402  （仅取其 is_disabled，无重依赖）

OUT_DIR = os.path.join(_HERE, "style_mine_out")
CORPUS = os.path.join(OUT_DIR, "corpus.json")
DET_OUT = os.path.join(OUT_DIR, "det_candidates.json")
LR_OUT = os.path.join(OUT_DIR, "lightrag_candidates.json")
DEFAULT_REPORT = os.path.join(OUT_DIR, "compare_report.md")
LR_LOG = os.path.join(OUT_DIR, "lightrag_run.log")
DEFAULT_LR_PY = os.environ.get(
    "STYLE_LR_PY", os.path.join(os.path.expanduser("~"), ".venvs", "style-lightrag",
                 "Scripts", "python.exe"))
MATCH_MIN = 0.25                                # 跨臂配对阈值（相似度）


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def match_members(a: str, b: str) -> bool:
    """单对成员匹配：归一后等值，或（长度≥3）互为子串。"""
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return False
    if x == y:
        return True
    if len(x) >= 3 and len(y) >= 3:
        return x in y or y in x
    return False


def cluster_similarity(mem_a: set, mem_b: set) -> int:
    """两簇匹配成员数（A 每词至多配 B 一词，贪心一一对应）。"""
    used, n = set(), 0
    for x in sorted(mem_a):
        for y in sorted(mem_b):
            if y in used:
                continue
            if match_members(x, y):
                used.add(y)
                n += 1
                break
    return n


def pair_clusters(det_clusters: list, lr_clusters: list, thr: float = MATCH_MIN) -> dict:
    """跨臂配对：每 A 簇找最佳 B 簇（相似度=匹配数/min(尺寸)）。"""
    pairs, matched_b = [], set()
    for i, dc in enumerate(det_clusters):
        a = {t["tag"] for t in dc["tags"]} if "tags" in dc else set(dc.get("members", []))
        best, best_s = None, 0.0
        for j, lc in enumerate(lr_clusters):
            b = set(lc.get("members", []))
            n = cluster_similarity(a, b)
            s = n / min(len(a), len(b)) if a and b else 0.0
            if s > best_s:
                best, best_s = j, s
        if best is not None and best_s >= thr:
            pairs.append({"det": i, "det_name": dc["name"], "det_size": len(a),
                          "lr": best, "lr_name": lr_clusters[best]["name"],
                          "lr_size": len(lr_clusters[best].get("members", [])),
                          "score": round(best_s, 2)})
            matched_b.add(best)
    det_un = [dc["name"] for i, dc in enumerate(det_clusters)
              if not any(p["det"] == i for p in pairs)]
    lr_un = [lc["name"] for j, lc in enumerate(lr_clusters) if j not in matched_b]
    return {"pairs": pairs, "det_only": det_un, "lr_only": lr_un}


def compare_outputs(det: dict | None, lr: dict | None, n_docs: int) -> dict:
    """纯函数：两份同构输出 → 对比读数（供报告与测试）。"""
    out = {"n_docs": n_docs, "det": None, "lr": None, "pairing": None}

    def _side(o: dict) -> dict:
        cov = {s for c in o["clusters"] for s in c.get("evidence", [])}
        sizes = [c["size"] for c in o["clusters"]]
        return {"n_clusters": len(o["clusters"]), "max_size": max(sizes) if sizes else 0,
                "avg_size": round(sum(sizes) / len(sizes), 1) if sizes else 0.0,
                "evidence_cover": len(cov), "method": o.get("method"),
                "params": o.get("params"), "stats": o.get("stats")}

    if det is not None:
        out["det"] = _side(det)
    if lr is not None:
        out["lr"] = _side(lr)
    if det is not None and lr is not None:
        out["pairing"] = pair_clusters(det["clusters"], lr["clusters"])
    return out


def render_report(cmp: dict, det_status: str, lr_status: str,
                  det_out: dict | None, lr_out: dict | None) -> str:
    L = []
    L.append(f"# 风格挖掘对比报告 · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append("")
    L.append(f"语料：{cmp['n_docs']} 文档（两臂同吃 corpus.json）")
    L.append("")
    try:                                                       # P9 健康度读数块（读数失败不拦报告）
        import health as _health
        L.append("## 〇-0 健康度读数（P9 · 占比记账/签名面/回声簇率/T 哨兵）")
        L.append("")
        L.append("```")
        L.append(_health.format_readings(_health.readings(gen_docs=cmp["n_docs"])))
        L.append("```")
        L.append("")
    except Exception as _ex:                                   # noqa: BLE001 响亮不静默
        L.append(f"## 〇-0 健康度读数（P9）：读数不可用（{type(_ex).__name__}: {_ex}）")
        L.append("")
    L.append("## 〇 运行面")
    L.append("")
    L.append(f"- **A 臂（确定性共现+社区检测）**：{det_status}"
             + (f" · 参数 {cmp['det']['params']} · {cmp['det']['stats'].get('algo')}"
                f" · 耗时 {det_out.get('elapsed_s', '?')}s" if cmp["det"] else ""))
    L.append(f"- **B 臂（LightRAG 图谱）**：{lr_status}"
             + (f" · LLM={cmp['lr']['params'].get('llm')}"
                f" · 嵌入={cmp['lr']['params'].get('embed')}"
                f" · insert {cmp['lr']['stats'].get('insert_s', '?')}s" if cmp["lr"] else ""))
    L.append("")
    L.append("## 一 规模与覆盖（读数）")
    L.append("")
    L.append("| 指标 | A 确定性 | B LightRAG |")
    L.append("|---|---|---|")
    def _row(name, ka, kb=None):
        a = cmp["det"][ka] if cmp["det"] else "—"
        kb = kb or ka
        b = cmp["lr"][kb] if cmp["lr"] else "—"
        L.append(f"| {name} | {a} | {b} |")
    _row("簇数", "n_clusters")
    _row("最大簇", "max_size")
    _row("平均簇大小", "avg_size")
    _row("证据覆盖（可回源文档数）", "evidence_cover")
    if cmp["det"]:
        L.append(f"| 实体/关系规模 | tag 面 {cmp['det']['stats'].get('n_tags_eligible')}"
                 f"/{cmp['det']['stats'].get('n_tags_total')}，边 {cmp['det']['stats'].get('n_edges')}"
                 f" | 实体 {cmp['lr']['stats'].get('n_entities') if cmp['lr'] else '—'}"
                 f"，关系 {cmp['lr']['stats'].get('n_relations') if cmp['lr'] else '—'} |")
    L.append("")
    if cmp["pairing"]:
        p = cmp["pairing"]
        L.append("## 二 跨臂配对（同一风格，两边都看到了吗）")
        L.append("")
        L.append("| A 簇（确定性） | B 簇（LightRAG） | 匹配词 | 相似度 |")
        L.append("|---|---|---|---|")
        for row in p["pairs"]:
            L.append(f"| {row['det_name']}（{row['det_size']}） | {row['lr_name']}"
                     f"（{row['lr_size']}） | {round(row['score'] * min(row['det_size'], row['lr_size']))}"
                     f" | {row['score']} |")
        L.append("")
        L.append(f"**A 独有**（确定性聚出、LightRAG 未成簇/未对上）：{p['det_only'] or '（无）'}")
        L.append("")
        L.append(f"**B 独有**（LightRAG 聚出、确定性未成簇/未对上）：{p['lr_only'] or '（无）'}")
        L.append("")
    L.append("## 三 判读素材（工具不代判）")
    L.append("")
    L.append("- 确定性：A 臂同输入必同输出；B 臂 LLM 抽取/命名含温度扰动（社区切分本身固定 seed）。")
    L.append("- 证据链：两臂 evidence 均可回源（A=文档 src；B=chunk→文档映射）。")
    L.append("- 粒度/命名质量/独有发现见上两节；终判归维护者。")
    L.append("")
    if det_out is not None:
        L.append("### A 臂全簇")
        for c in det_out["clusters"]:
            L.append(f"- {c['size']} tag · cohesion {c['cohesion']} · {c['name']}")
        L.append("")
    if lr_out is not None:
        L.append("### B 臂全簇")
        for c in lr_out["clusters"]:
            L.append(f"- {c['size']} 实体 · cohesion {c['cohesion']} · {c['name']}")
        L.append("")
    return "\n".join(L)


def run_all(no_det: bool, no_lr: bool, report_path: str, no_feed: bool = False) -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    det_disabled = sd.is_disabled(cli_off=no_det)
    lr_disabled = sl.is_disabled(cli_off=no_lr)

    # 1) 语料（两臂同吃）
    docs = sc.build_corpus()
    json.dump({"n_docs": len(docs), "docs": docs},
              open(CORPUS, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    print(f"[compare] 语料 {len(docs)} 文档")

    # 2/3) 两臂并行
    def _run_det():
        if det_disabled:
            return "disabled", 0, None
        t0 = time.time()
        rc = sd.main(["--corpus", CORPUS, "--out", DET_OUT])
        return "ran", rc, round(time.time() - t0, 1)

    def _run_lr():
        if lr_disabled:
            return "disabled", 0, None
        t0 = time.time()
        cmd = [DEFAULT_LR_PY, os.path.join(_HERE, "style_mine_lightrag.py"),
               "--corpus", CORPUS, "--out", LR_OUT]
        with open(LR_LOG, "w", encoding="utf-8") as lg:
            rc = subprocess.run(cmd, stdout=lg, stderr=subprocess.STDOUT).returncode
        return "ran", rc, round(time.time() - t0, 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_det = ex.submit(_run_det)
        f_lr = ex.submit(_run_lr)
        det_status, det_rc, det_el = f_det.result()
        lr_status, lr_rc, lr_el = f_lr.result()
    if det_status == "ran" and det_rc != 0:
        det_status = f"failed(rc={det_rc})"
    if lr_status == "ran" and lr_rc != 0:
        lr_status = f"failed(rc={lr_rc})"

    det_out = None
    lr_out = None
    if det_status.startswith("ran"):
        det_out = json.load(open(DET_OUT, encoding="utf-8"))
        det_status += f"（{det_el}s）"
    if lr_status.startswith("ran") and os.path.isfile(LR_OUT):
        lr_out = json.load(open(LR_OUT, encoding="utf-8"))
        lr_status += f"（{lr_el}s）"

    cmp = compare_outputs(det_out, lr_out, len(docs))
    md = render_report(cmp, det_status, lr_status, det_out, lr_out)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    json.dump(cmp, open(os.path.join(OUT_DIR, "compare.json"), "w", encoding="utf-8",
                        newline="\n"), ensure_ascii=False, indent=1, default=str)
    print(f"[compare] A={det_status} · B={lr_status} → {report_path}")

    # ③ 自动投喂（维护者令：涌现知识自动投入飞轮）——机器提案位：簇→draft，人闸后服务
    if sd.is_disabled() or sl.is_disabled():
        print("[compare] 有臂被开关关闭——跳过投喂（涌现面不完整，投了以偏概全）")
    else:
        import style_feed as sfd                  # 惰性导入（其模块层反向依赖本件）
        if sfd.is_disabled(cli_off=no_feed):
            print("[style-feed] 已关闭（开关 STYLE_FEED / --no-feed）——不投喂")
        else:
            sfd.main(["--det", DET_OUT, "--lr", LR_OUT, "--corpus", CORPUS])

    # ④ 双臂皆跑完 → 触发器快照顺延（下次到期从此刻起算）
    if det_status.startswith("ran") and lr_status.startswith("ran"):
        try:
            try:                       # 三段一体（反向飞轮→纠错环路→影响传播）：每轮跑，条件命中不靠引用边
                import neg_chain as _nc
                r_nc = _nc.scan()
                print(f"[neg-chain] 负例 {r_nc['negatives']} × 活件 {r_nc['live_scanned']} → "
                      f"命中 {len(r_nc['hits'])}（动作 {len(r_nc['acted'])}）")
            except Exception as _ex:   # noqa: BLE001 响亮不静默、不拦挖掘
                print(f"[neg-chain] 跳过（{type(_ex).__name__}: {_ex}）")
            try:                       # 影子环路（维护者令 20261008『开！』）：每轮复查、只记日志
                import auto_heal as _ah
                r_sh = _ah.shadow_scan()
                print(f"[shadow-loop] 已判错根 {r_sh['roots']} → 会下架 {len(r_sh['would_retract'])} 条"
                      f"（影子：不动手）")
            except Exception as _ex:   # noqa: BLE001 响亮不静默、不拦挖掘
                print(f"[shadow-loop] 跳过（{type(_ex).__name__}: {_ex}）")
            try:                       # 贝叶斯接线（20261009『全开全接线』；同日修孤岛空转）
                import auto_heal as _ah
                import bayes_shadow as _bs
                import edge_graph as _egx
                import premises as _pms
                from precedent_gov import PrecedentStore as _PS
                _ents = _PS.load(_ah.DEFAULT_STORE).entries
                _g = _egx.extract_graph(_ents)
                _adj = _egx._adjacency(_g)              # 与 propagate 同口径（含对称边）
                # 根型随根走（20261010 转正令）：人签错根=error（榜首可动作）；
                # 前提翻倒依赖=suspect（只打标）；两者不混——动作权限不同
                _cand = [(e["id"], "error") for e in _ah.wrong_roots(_ents)]
                for b in _pms.load().get("backfills", []):   # 前提翻倒依赖集=最该看传播的根
                    _cand += [(str(t.get("ref")), "suspect")
                              for t in b.get("targets", []) if t.get("ref")]
                _roots, _isl, _seen = [], 0, set()
                for _rid, _k in _cand:
                    if not _rid or _rid in _seen:
                        continue
                    _seen.add(_rid)
                    if _adj.get(_rid):
                        _roots.append((_rid, _k))
                    else:
                        _isl += 1      # 孤岛根跑出空榜=真空转（20261009 实测 n=0 ×3）——跳过不落账
                _e3 = [x for x in _roots if x[1] == "error"][:3]
                _s3 = [x for x in _roots if x[1] == "suspect"][:3]
                # 健康根影响面（维护者令 20261010『和错误根相辅相成』）：
                # approved/verified 且有下游，按邻接度降序取 3（稳定排序）——看信任根把权威扩散给谁
                _gov = {e["id"]: e.get("gov") for e in _ents}
                _healthy = sorted(
                    ((len(_adj[_id]), _id) for _id, _gv in _gov.items()
                     if _gv in ("approved", "verified") and _adj.get(_id)),
                    key=lambda x: (-x[0], x[1]))[:3]
                _acted_n = 0
                for _rid, _k in _e3 + _s3:
                    _r = _bs.run(_g, _rid, root_kind=_k)
                    if (_r.get("acted") or {}).get("acted"):
                        _acted_n += 1
                for _deg, _rid in _healthy:
                    _bs.run(_g, _rid, root_kind="healthy")     # 信任根只入账不动
                print(f"[bayes] 转正档（{_bs.DEFAULT_MODE}·榜首动作制）错误根 {len(_e3)} / "
                      f"翻倒依赖根 {len(_s3)}（候选 {len(_seen)}，孤岛 {_isl}）· "
                      f"健康侧 {len(_healthy)} 只入账——本轮动作 {_acted_n} 件（draft-only·可逆）")
            except Exception as _ex:   # noqa: BLE001 响亮不静默、不拦挖掘
                print(f"[bayes] 跳过（{type(_ex).__name__}: {_ex}）")
            import mine_trigger as mt
            mt.main(["mark"])
        except Exception as e:                          # 快照失败不拦对比（WARN 语义）
            print(f"[compare] mine-trigger 快照失败（不拦）：{e}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="双挖掘器并行编排 + 涌现对比报告")
    ap.add_argument("--no-det", action="store_true", help="关闭 A 臂（同 STYLE_MINE_DET=off）")
    ap.add_argument("--no-lr", action="store_true", help="关闭 B 臂（同 STYLE_MINE_LIGHTRAG=off）")
    ap.add_argument("--no-feed", action="store_true", help="关闭自动投喂（同 STYLE_FEED=off）")
    ap.add_argument("--report", default=DEFAULT_REPORT)
    a = ap.parse_args(argv)
    return run_all(a.no_det, a.no_lr, a.report, a.no_feed)


if __name__ == "__main__":
    sys.exit(main())
