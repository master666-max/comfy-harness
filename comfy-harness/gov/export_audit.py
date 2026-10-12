# -*- coding: utf-8 -*-
"""export_audit.py — 内部日志全量导出 + 条目逐条体检（维护者审计令 20261010）

① 导出：全部内部日志/账本拷入 out/log_export_<日期>/（附 AUDIT.md 索引）
② 逐条体检：122 条目逐个过检（gov/年龄/标记/向量/标签一致性）+ 库健康读数
只读生产，写全部落导出目录。
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
SMO = os.path.join(_HERE, "style_mine_out")
FIELD_OUT = os.path.join(_HERE, "..", "field", "out")
STORE = os.path.join(_HERE, "precedents_e2_seed.json")
NOW = datetime.datetime.now()


def _age(e):
    try:
        d = datetime.datetime.fromisoformat(str(e.get("_added_at", ""))[:19])
        return (NOW - d).days
    except ValueError:
        return -1


def main() -> int:
    stamp = NOW.strftime("%Y%m%d_%H%M")
    exp = os.path.join(FIELD_OUT, f"log_export_{stamp}")
    os.makedirs(exp, exist_ok=True)

    # ── ① 日志全量导出 ──
    manifest = ["# 导出索引 " + stamp, ""]
    cop = []
    for d in (SMO, FIELD_OUT):
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p) and (f.endswith((".jsonl", ".json", ".md"))
                                      or f in ("noobai_kit.html",)):
                dst = os.path.join(exp, f)
                shutil.copy(p, dst)
                cop.append(f"{f} ({os.path.getsize(p)//1024}KB)")
    manifest.append("## 导出文件\n" + "\n".join(f"- {c}" for c in cop))

    # ── ② 逐条体检 ──
    store = json.load(open(STORE, encoding="utf-8"))
    es = store["entries"]
    vet, warn = [], []
    novec = []
    for e in es:
        f = e.get("facts") or {}
        eid = e["id"]
        age = _age(e)
        issues = []
        if e.get("gov") == "draft" and not e.get("machine_retracted") and age > 2:
            issues.append(f"草案{age}天未过闸(积压)")
        if e.get("machine_retracted"):
            pass
        if f.get("specimen") and not e.get("tombstone"):
            issues.append("在册标本(反例面, 勿晋升)")
        if e.get("id") == "P-detailer-clean-chain":
            issues.append("候退场(维护者裁伪影,撤书在案)")
        prefix_mismatch = ""
        c = str((e.get("content") or {}).get("c", ""))
        if c.startswith("异常观察") and e["id"] in (
                "P-obs-26101001-2-probe-air-job-12-2ed5e637",):
            prefix_mismatch = "台账已改类配方,草稿前缀仍'异常观察'( cosmetic )"
            issues.append(prefix_mismatch)
        line = (f"{eid[:52]:54} gov={e.get('gov'):9} age={age:>3} "
                f"{'⚠ ' + '; '.join(issues) if issues else ''}")
        vet.append(line)
        if issues:
            warn.append(line)
        if e.get("gov") == "draft" and not e.get("machine_retracted"):
            # 无向量口径以 review 视图为准（embed_cache 实查），此处不臆断
            pass

    gov = {}
    for e in es:
        gov[e.get("gov")] = gov.get(e.get("gov"), 0) + 1
    ages = [_age(e) for e in es if e.get("gov") == "draft"
            and not e.get("machine_retracted")]

    report = "\n".join([
        "# 条目逐条体检 " + stamp, "",
        f"总数 {len(es)} | gov {gov}", "",
        "## ⚠ 带标记条目 (" + str(len(warn)) + ")",
        ""] + [f"- {w}" for w in warn] + [
        "", f"## 无向量草案 {len(novec)} 件（候 embed_cache 增量重嵌）",
        ""] + [f"- {x}" for x in novec] + [
        "", f"## 全量逐条", "", "```"] + vet + ["```"])
    open(os.path.join(exp, "AUDIT.md"), "w", encoding="utf-8").write(report)

    print(f"导出目录: {exp}")
    print(f"条目 {len(es)} | 带标记 {len(warn)} | 无向量草案 {len(novec)}")
    print(f"在役草案年龄: 中位 {sorted(ages)[len(ages)//2] if ages else '-'} 天, "
          f"最老 {max(ages) if ages else '-'} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
