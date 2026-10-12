# -*- coding: utf-8 -*-
"""blind_judge.py — 盲测判卷器（维护者令 20261008：子代理/异族出题，机器对答案）

流程（结构性盲）：**先跑机器**（沙箱建库 → 影响面分档 → 传播分 → 贝叶斯序数），
**后对答案**（读取 case JSON 的 expected 字段）。产物=逐案结果 JSON + 汇总表。

id 归一化（**案例渲染步骤，已在报告注明**）：出题人的 id 多为 P-101/S-201 这类短形式，
`rsplit('-',1)[0]` 会把它们压成同一基底（s-…）而生成虚假 base-mate 边——
判卷前统一给 id 追加内容哈希后缀（`S-201-<hash6>`），使基底唯一化，测的才是语义判定而非 id 巧合。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import bayes_shadow as bs          # noqa: E402
import edge_graph as eg            # noqa: E402
from precedent_gov import PrecedentStore   # noqa: E402

TIER2LABEL = {"连坐候选": "high", "复核建议": "mid", "低（自证）": "low"}


def _norm_id(eid: str, content: str) -> str:
    h = hashlib.sha1(str(content).encode("utf-8")).hexdigest()[:6]
    return f"{eid}-{h}"


def _sandbox(case: dict, tmp: str) -> tuple[str, dict, dict]:
    """渲染入沙箱：①全表 id 归一化（防短 id 同基底假边）②**正文/证据里的引用文字同步改写**
    （初版漏了②→引用边全没建、全案判 none——判卷器自身的坑，实测抓出）。"""
    s = PrecedentStore([])
    recs = [case["root"]] + list(case["entries"])
    idmap = {r["id"]: _norm_id(r["id"], r.get("content", "")) for r in recs}

    def rewrite(text: str) -> str:
        out = str(text)
        for orig in sorted(idmap, key=len, reverse=True):     # 长 id 先替换，防前缀吃串
            out = out.replace(orig, idmap[orig])
        return out

    def mk(rec: dict) -> dict:
        return {"id": idmap[rec["id"]], "task": "t2i", "kind": "style", "level": "specialized",
                "type": "procedural", "importance": 3,
                "content": {"c": rewrite(rec.get("content", "")), "a": "", "d": ""},
                "keywords": [rewrite(k) for k in (rec.get("keywords") or [])],
                "evidence": {"artifact": rewrite(rec.get("evidence", ""))}}

    for r in recs:
        e = mk(r)
        s.add(e, actor="ai:blind-judge")
        s.promote(e["id"], actor="human:blind-judge")
    path = os.path.join(tmp, "blind_seed.json")
    s.save(path)
    return path, idmap, s


def judge(case_path: str) -> dict:
    case = json.load(open(case_path, encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="blind_") as tmp:
        seed, idmap, s = _sandbox(case, tmp)
        g = eg.extract_graph(s.entries)
        root_n = _norm_id(case["root"]["id"], case["root"].get("content", ""))
        rep = eg.impact(g, root_n, 2)
        prop = eg.propagate(g, root_n)
        rows = {r["node"]: r for r in rep["rows"]}
        bayes = [x["node"] for x in bs.posterior_ordinal(g, root_n)]

        # 先跑完机器，后读答案（结构性盲）
        gold = {_norm_id(e["id"], e.get("content", "")): e["expected"] for e in case["entries"]}
        out_rows, conf = [], {}
        for e in case["entries"]:
            nid = _norm_id(e["id"], e.get("content", ""))
            r = rows.get(nid)
            if r is None:
                got = "none"
            else:
                got = next((v for k, v in TIER2LABEL.items() if k in r["tier"]), "mid")
            conf[(gold[nid], got)] = conf.get((gold[nid], got), 0) + 1
            out_rows.append({"id": e["id"], "expected": gold[nid], "got": got,
                             "hop": (r or {}).get("hops"), "tier": (r or {}).get("tier"),
                             "prop_score": (r or {}).get("prop_score")})
        exp_high = [r for r in out_rows if r["expected"] == "high"]
        exp_low = [r for r in out_rows if r["expected"] == "low"]
        exp_none = [r for r in out_rows if r["expected"] == "none"]
        fn = [r["id"] for r in exp_high if r["got"] != "high"]
        act_fp = [r["id"] for r in exp_none if r["got"] in ("high", "mid")]
        tag_fp = [r["id"] for r in exp_none if r["got"] != "none"]
        low_hit = [r["id"] for r in exp_low if r["got"] == "low"]

        def _mx(rows_, k):
            v = [r[k] for r in rows_ if r.get(k) is not None]
            return max(v) if v else None

        def _mn(rows_, k):
            v = [r[k] for r in rows_ if r.get(k) is not None]
            return min(v) if v else None

        ordered = (_mn(exp_high, "prop_score") is not None
                   and (_mx(exp_low, "prop_score") is None
                        or _mn(exp_high, "prop_score") > _mx(exp_low, "prop_score")))
        bayes_order_ok = all(
            (bayes.index(_norm_id(h["id"], "")) if _norm_id(h["id"], "") in bayes else 10**6)
            < (bayes.index(_norm_id(y["id"], "")) if _norm_id(y["id"], "") in bayes else 10**6)
            for h in exp_high for y in exp_low + exp_none)
        res = {"case": case["case_name"], "provenance": case.get("provenance"),
               "n": len(out_rows), "rows": out_rows,
               "exact": sum(1 for r in out_rows if r["expected"] == r["got"]),
               "high_hit": f"{len(exp_high) - len(fn)}/{len(exp_high)}",
               "low_hit": f"{len(low_hit)}/{len(exp_low)}",
               "fn": fn, "action_fp": act_fp, "tag_fp": tag_fp,
               "prop_ordering_ok": ordered, "bayes_ordering_ok": bayes_order_ok,
               "confusion": {f"{a}->{b}": c for (a, b), c in sorted(conf.items())}}
        return res


def render(res: dict) -> str:
    L = [f"═══ 案：{res['case']}（{res['provenance']}）",
         f"  逐条：真值/判定/跳数/传播分"]
    for r in res["rows"]:
        mark = "✓" if r["expected"] == r["got"] else "✗"
        L.append(f"   {mark} {r['id']:9s} 真值={r['expected']:4s} 判定={r['got']:4s} "
                 f"hop={r['hop']} 传播分={r['prop_score']}")
    L.append(f"  命中 high {res['high_hit']} / low {res['low_hit']} / 精确 {res['exact']}/{res['n']}"
             f" | **漏报(FN)**={res['fn']} | **动作级误报**={res['action_fp']} | 标注级误报={res['tag_fp']}")
    L.append(f"  序数一致性：传播分排序={'✓' if res['prop_ordering_ok'] else '✗'} "
             f"贝叶斯序数={'✓' if res['bayes_ordering_ok'] else '✗'} | 混淆={res['confusion']}")
    return "\n".join(L)


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("用法: py blind_judge.py <case.json> [...]")
        return 2
    outs = []
    for p in argv:
        r = judge(p)
        print(render(r))
        op = os.path.join(os.path.dirname(p), "result_" + os.path.basename(p))
        json.dump(r, open(op, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        print(f"  结果落盘 {op}")
        outs.append(r)
    print("═══ 汇总：", [(r["case"][:18], r["exact"], r["n"], len(r["fn"]), len(r["action_fp"]),
                        len(r["tag_fp"])) for r in outs])
    return 0


if __name__ == "__main__":
    sys.exit(main())
