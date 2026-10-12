# -*- coding: utf-8 -*-
"""mine_diff.py — 对照重挖 diff（工单 P10 验收件）

**验收判据（工单原文）**："过程簇消失 / 真风格簇保留"。
本件把两批候选（旧=自食期 / 新=四重防线后）按同一口径分类计数：

- **过程簇** = is_process(name, members) ≥ 2 命中（style_feed 同源判据）——
  自食产物（提案流程词汇：Machine Proposal/Candidate Boundary/挖掘签名…）；
- **风格簇** = 非过程簇；
- 覆盖 = 每簇 size/evidence 汇总；
- 配对 = 名称归一化后新旧同名簇（"保留"的量化；过程簇同名对=消失失败）。

不代判：输出读数与配对表，终判归维护者。
用法：py comfy-harness/gov/mine_diff.py [--baseline DIR] [--new DIR] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import style_feed as sf                        # noqa: E402

BASE_DIR = os.path.join(_HERE, "style_mine_out", "remine_baseline")
NEW_DIR = os.path.join(_HERE, "style_mine_out")
ARMS = (("A 确定性", "det_candidates.json"), ("B LightRAG", "lightrag_candidates.json"))


def _load(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d


def _members(c):
    if isinstance(c.get("members"), list):
        return [str(m) for m in c["members"]]
    if isinstance(c.get("tags"), list):
        return [str(t.get("tag")) for t in c["tags"] if isinstance(t, dict) and t.get("tag")]
    return []


def classify(clusters: list) -> dict:
    proc, style = [], []
    for c in clusters:
        m = _members(c)
        hits = sf.is_process(str(c.get("name", "")), m)
        rec = {"name": str(c.get("name", "")), "size": int(c.get("size") or len(m)),
               "process_hits": hits}
        (proc if hits >= 2 else style).append(rec)
    return {"n": len(clusters), "process": proc, "style": style,
            "process_n": len(proc), "style_n": len(style),
            "process_cov": sum(r["size"] for r in proc),
            "style_cov": sum(r["size"] for r in style)}


def _key(name):
    return sf._norm(name)


def diff() -> dict:
    out = {"arms": {}}
    for label, fname in ARMS:
        old, new = _load(os.path.join(BASE_DIR, fname)), _load(os.path.join(NEW_DIR, fname))
        if old is None or new is None:
            out["arms"][label] = {"error": "缺旧或新候选件"}
            continue
        co, cn = classify(old["clusters"]), classify(new["clusters"])
        old_keys = {_key(c["name"]) for c in old["clusters"]}
        new_keys = {_key(c["name"]) for c in new["clusters"]}
        proc_keys_new = {_key(c["name"]) for c in cn["process"]}
        out["arms"][label] = {
            "corpus_old": old.get("corpus_n_docs"), "corpus_new": new.get("corpus_n_docs"),
            "old": co, "new": cn,
            "retained_names": sorted(old_keys & new_keys),
            "vanished_names": sorted(old_keys - new_keys),
            "added_names": sorted(new_keys - old_keys),
            "process_survived_names": sorted(proc_keys_new),
        }
    return out


def render(d: dict) -> str:
    L = ["# 对照重挖 diff（P10 验收件 · 过程簇消失/真风格簇保留）", ""]
    for label, r in d["arms"].items():
        L.append(f"## {label}")
        L.append("")
        if r.get("error"):
            L.append(f"- 不可比：{r['error']}")
            L.append("")
            continue
        L.append(f"- 语料：旧 {r['corpus_old']} → 新 {r['corpus_new']} 文档（E′身份闸后）")
        L.append(f"- 簇数：旧 {r['old']['n']} → 新 {r['new']['n']}")
        L.append(f"- **过程簇**：旧 {r['old']['process_n']}（覆盖 {r['old']['process_cov']} 成员）"
                 f" → 新 {r['new']['process_n']}（覆盖 {r['new']['process_cov']}）")
        L.append(f"- **风格簇**：旧 {r['old']['style_n']} → 新 {r['new']['style_n']}")
        if r["old"]["process"]:
            L.append(f"- 旧过程簇名（应消失）：{['%s(h%d)' % (x['name'][:40], x['process_hits']) for x in r['old']['process']]}")
        if r["new"]["process"]:
            L.append(f"- ⚠ 新仍存过程簇：{['%s(h%d)' % (x['name'][:40], x['process_hits']) for x in r['new']['process']]}")
        else:
            L.append("- 新过程簇：**零**（自食成分消失）")
        L.append(f"- 保留簇名（新旧同名）：{len(r['retained_names'])} 个；"
                 f"消失：{len(r['vanished_names'])}；新出现：{len(r['added_names'])}")
        L.append(f"  - 新出现：{r['added_names'][:12]}{'…' if len(r['added_names']) > 12 else ''}")
        L.append("")
    L.append("判读口径：过程簇按 style_feed.is_process≥2 判（与铸前闸同源）；"
             "同名=归一化后逐字相等（措辞漂移会使名字不全等，故另列新出现/消失供人看成分）。")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="对照重挖 diff")
    ap.add_argument("--baseline", default=BASE_DIR)
    ap.add_argument("--new", default=NEW_DIR)
    ap.add_argument("--out", default=os.path.join(NEW_DIR, "remine_diff.md"))
    a = ap.parse_args(argv)
    globals()["BASE_DIR"], globals()["NEW_DIR"] = a.baseline, a.new
    d = diff()
    text = render(d)
    print(text)
    open(a.out, "w", encoding="utf-8", newline="\n").write(text + "\n")
    json.dump(d, open(os.path.join(a.new, "remine_diff.json"), "w", encoding="utf-8",
                      newline="\n"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
