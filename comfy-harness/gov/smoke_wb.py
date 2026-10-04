# -*- coding: utf-8 -*-
"""W-B 冒烟 · 判例治理条款启用验证（工单 W-B 验收判据）
冒烟 3 发：无签名 promote/tombstone/supersede 全拒（响亮拒绝，缺省不猜身份）；
签核正路：promote/deprecate→tombstone 两段式/supersede 闭环 + 检索过滤四断言
（墓碑不可召回/无主不可召回/approved 正常召回/deprecated 带旗）。
零生产写：全内存，零文件。
"""
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
from precedent_gov import PrecedentStore, GovernanceRefusal

R = {"pass": 0, "fail": 0}


def check(tag, ok, detail=""):
    R["pass" if ok else "fail"] += 1
    print(f"[{'OK' if ok else 'NO'}] {tag} {str(detail)[:120]}")


def mk(eid, text, owner=""):
    return {"id": eid, "type": "semantic", "importance": 2,
            "keywords": ["黄鸭", "裁剪", "验收"],
            "content": {"c": text, "a": "站2沙盒实测", "d": "适用裁剪去鸭场景"},
            "evidence": {"artifact": "调研-卷十二-C1站2-沙盒", "quote": text[:20], "recalc": "复跑 E2"},
            "owner": owner}


store = PrecedentStore()
store.add(mk("P-001", "裁剪框坐标系必须与图像实际尺寸一致,1024坐标用于512图会越界补黑边",
             owner="human:维护者"), actor="ai:卷十二线")
store.add(mk("P-002", "严格像素检测器阈值过严会漏暗黄鸭,机械断言给出假阴性地面真值",
             owner=""))  # 故意无主(防毒测试)

# ---- 冒烟 3 发:无签名全拒 ----
for i, (act, args) in enumerate([
    ("promote", ("P-001", "ai:卷十二线")),
    ("tombstone", ("P-002", "agent")),
    ("supersede", (mk("P-003", "新条", owner="human:维护者"), "P-001", "human-ish")),
], 1):
    refused, detail = False, ""
    try:
        getattr(store, act)(*args)
        detail = "竟然放行了=严重缺陷"
    except GovernanceRefusal as e:
        refused, detail = True, str(e)
    check(f"冒烟{i}.{act}-无签名", refused, detail)

# ---- 签核正路 ----
store.promote("P-001", actor="human:维护者")
check("签核.promote", store._get("P-001")["gov"] == "approved")
store.deprecate("P-002", actor="human:维护者", reason="无主防毒演练——先有主再看")
check("签核.deprecate", store._get("P-002").get("deprecated") is True)
tomb_refused = False
try:
    store.tombstone("P-001", actor="human:维护者")
except GovernanceRefusal:
    tomb_refused = True
check("两段式.approved直接墓碑拒", tomb_refused)
store.tombstone("P-002", actor="human:维护者", reason="演练墓碑")
check("签核.tombstone", store._get("P-002").get("tombstone") is True)
store.supersede(mk("P-004", "裁剪框坐标系必须先查图像实际尺寸再定裁剪框(修订P-001)",
                  owner="human:维护者"), "P-001", actor="human:维护者")
check("签核.supersede", store._get("P-001").get("tombstone") is True
      and store._get("P-004")["evidence"].get("supersedes") == "P-001")

# ---- 检索过滤四断言 ----
hits = store.recall("裁剪 坐标系 黄鸭")
ids = [e["id"] for _, e in hits]
check("检索.墓碑不可召回", "P-001" not in ids and "P-002" not in ids, str(ids))
check("检索.无主不可召回", "P-002" not in ids)
check("检索.修订闭环", "P-004" in ids, "新条P-004应可召回")
store.deprecate("P-004", actor="human:维护者", reason="演练旗标")
hits2 = store.recall("裁剪 坐标系 黄鸭")
flagged = [e for _, e in hits2 if e["id"] == "P-004"]
check("检索.deprecated带旗", bool(flagged) and flagged[0].get("_gov_flag") == "deprecated")
GOV_KINDS = {"promote", "deprecate", "tombstone", "supersede"}
gov_evs = [ev for ev in store.gov_events if ev["kind"] in GOV_KINDS]
check("治理事件流.append-only", len(store.gov_events) == 8
      and all(ev["actor"].startswith("human:") for ev in gov_evs),  # 拒绝零留痕+治理动效必人签;add 草稿允许 ai
      f"{len(store.gov_events)}事件,治理动效{len(gov_evs)}笔全human签")

print(f"\n冒烟总结: PASS {R['pass']} / FAIL {R['fail']}")
sys.exit(0 if R["fail"] == 0 else 1)
