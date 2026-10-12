# -*- coding: utf-8 -*-
"""draft_consolidate.py — 草稿更迭与衰减（工单 P5 · N4 + N8）

**N4 机器更迭三件套**（全在机器权限面内——权限矩阵实测：retract=machine:*，amend=无闸）：
  ① 铸造合并条：并集 members/evidence → 新 draft（sig 重算，gen=max(被并)——
     **非放大红线：合并只并证据，不升代数、不升信任级**）；
  ② retract 被并旧条（machine:*，reason 指向新条 id，audit-preserved 可人签 relist）；
  ③ amend 合并条 facts 补 `merged_from` 链（old→new 全 diff 入账）。

**N8 衰减出清**：≥max_age_days 天无复现（recurrence.json 无记录）且与任何 approved/
verified 条目无关键词关联（≥2 词重叠）的孤儿草案 → machine retract(stale)。
有关联者豁免（可能是待转正候选）；recurrence 命中者豁免（复现中）。

用法：
  py -X utf8 draft_consolidate.py merge <旧id> <旧id>… [--name N] [--dry-run]
  py -X utf8 draft_consolidate.py decay [--max-age-days 3] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))
import style_feed as sf            # noqa: E402  （sig_of/_slug 复用）

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_RECURRENCE = os.path.join(_HERE, "style_mine_out", "recurrence.json")
ACTOR = "machine:flywheel-consolidate"


def _members_of(e: dict) -> list:
    kw = [str(k) for k in (e.get("keywords") or [])]
    facts = e.get("facts") or {}
    tags = [str(t) for t in (facts.get("tags") or [])]
    return sorted(set(kw + tags))


def merge(store, old_ids: list, name: str | None = None, dry: bool = False,
          recurrence: dict | None = None) -> dict:
    """N4 三件套。**影子权重**（维护者令 20261008）：merged facts 记
    shadow_weight = (被并件数-1) + Σ 各被并件在 recurrence.json 的被拦重铸次数
    ——"这件事重复出现过几次"的量化。用途后置：正向=复现加权（人决策面打分），
    负向=自食雷达（高影重+零证据=凝结核嫌疑）。**非放大：仅数值标注，不升信任级。**"""
    olds = []
    for eid in old_ids:
        e = store._get(eid)
        if e.get("gov") != "draft" or e.get("tombstone"):
            raise SystemExit(f"merge: {eid} 非可并草案（gov={e.get('gov')} "
                             f"tombstone={bool(e.get('tombstone'))}）")
        olds.append(e)
    members = sorted({m for e in olds for m in _members_of(e)})
    if not members:
        raise SystemExit("merge: 被并件全无成员，拒绝空并")
    sig = sf.sig_of(members)
    nm = name or (olds[0].get("id") or "merged")
    # id 约定：canonical 名常自带 S- 前缀 → 先剥再套，防双 S（S-S-…）
    # ——双 S 会让基底比对失配：未来同概念重铸件的基底≠合并条基底，近重复闸漏拦（维护者令批次实弹抓出）
    _base = str(nm)[2:] if str(nm).upper().startswith("S-") else str(nm)
    eid = f"S-{sf._slug(_base)}-{sig}"
    gmax = max(int(e.get("_mine_gen") or 1) for e in olds)      # 非放大：代数取max不+1
    fams = {((e.get("facts") or {}).get("model_family")) for e in olds} - {None}
    facts = {"tags": members[:14], "cohesion": round(sum(
        float((e.get("facts") or {}).get("cohesion") or 0) for e in olds) / len(olds), 2),
        "arms": sorted({a for e in olds for a in ((e.get("facts") or {}).get("arms") or [])}),
        "evidence_n": sum(int((e.get("facts") or {}).get("evidence_n") or 0) for e in olds),
        "samples": sorted({s for e in olds for s in ((e.get("facts") or {}).get("samples") or [])})[:3],
        "sig": sig, "model_family": (next(iter(fams)) if len(fams) == 1 else "mixed"),
        "recurrence": {e["id"]: json_len(e) for e in olds},
        "merged_from": list(old_ids),
        "shadow_weight": _shadow_weight(olds, old_ids, recurrence)}
    entry = {"id": eid, "type": "procedural", "importance": max(
        int(e.get("importance") or 3) for e in olds),
        "keywords": members[:6], "task": olds[0].get("task") or "t2i",
        "kind": olds[0].get("kind") or "style", "level": olds[0].get("level") or "specialized",
        "_mine_sig": sig, "_mine_gen": gmax,
        "content": {
            "c": f"合并风格束「{nm}」：由 {len(olds)} 条同类草案并集（"
                 f"{'、'.join(o['id'][:40] for o in olds)}）；成员 {len(members)} 项。",
            "a": "N4 机器更迭：并集成员/证据；被并件已机器下架（audit-preserved，可人签 relist）；"
                 "血缘见 facts.merged_from。",
            "d": "边界：合并只并证据不升信任级（仍 draft，候人闸 promote）；被并件数字见 merged_from。",
        },
        "evidence": dict((olds[0].get("evidence") or {}))}
    res = {"new": eid, "merged_from": list(old_ids), "gen": gmax, "dry": dry,
           "shadow_weight": facts["shadow_weight"]}
    if dry:
        return res
    store.add(entry, actor=ACTOR, facts=facts)                  # ① 铸合并条
    events = []
    for o in olds:                                              # ② retract 旧条
        events.append(store.retract(o["id"], actor=ACTOR,
                                    reason=f"consolidated into {eid}",
                                    evidence="工单P5·N4机器更迭"))
    store.amend(eid, {"facts": facts}, reason=              # ③ amend 补链（全 diff 入账）
                 f"N4 三件套：merged_from={','.join(old_ids)}", actor=ACTOR)
    res["retracted"] = [e["id"] for e in events]
    return res


def _shadow_weight(olds: list, old_ids: list, recurrence: dict | None) -> int:
    """影子权重 = 同代被并重复数 + 跨轮被拦重铸数（缺账本则只计前者，不猜）。"""
    rec = recurrence or {}
    blocked = sum(int(((rec.get(i) or {}).get("count")) or 0) for i in old_ids)
    return (len(olds) - 1) + blocked


def json_len(e: dict) -> int:
    """被并件的 recurrence 读数（facts 里的，缺省 0）。"""
    r = (e.get("facts") or {}).get("recurrence")
    if isinstance(r, dict):
        return int(r.get("count") or 0)
    return 0


def decay(store, recurrence: dict, max_age_days: float = 3.0, dry: bool = False) -> dict:
    """N8 衰减：孤儿草案出清（有关联/复现者豁免）。"""
    now = datetime.datetime.now()
    related_kw = set()
    for e in store.entries:
        if e.get("gov") in ("approved", "verified"):
            related_kw |= {str(k).lower() for k in (e.get("keywords") or [])}
    stale, exempt = [], []
    for e in store.entries:
        if e.get("gov") != "draft" or e.get("tombstone") or e.get("machine_retracted"):
            continue
        if e["id"] in recurrence:                               # 复现中：豁免
            exempt.append(e["id"])
            continue
        kw = {str(k).lower() for k in (e.get("keywords") or [])}
        if len(kw & related_kw) >= 2:                           # 与已签条目关联：豁免
            exempt.append(e["id"])
            continue
        try:
            created = datetime.datetime.fromisoformat(str(e.get("_added_at") or ""))
        except ValueError:
            created = now
        if (now - created).days >= max_age_days:
            stale.append(e["id"])
    res = {"stale": stale, "exempt": len(exempt), "dry": dry}
    if not dry:
        for eid in stale:
            store.retract(eid, actor=ACTOR,
                          reason=f"stale（≥{max_age_days}天无复现且无已签关联——N8 衰减出清）",
                          evidence="工单P5·N8")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="草稿更迭三件套(N4)与衰减出清(N8)")
    ap.add_argument("mode", choices=("merge", "decay"))
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--name", default=None)
    ap.add_argument("--max-age-days", type=float, default=3.0)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--recurrence", default=DEFAULT_RECURRENCE)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(a.store)
    if a.mode == "merge":
        if len(a.ids) < 2:
            raise SystemExit("merge: 至少两个旧 id")
        r = merge(store, a.ids, a.name, a.dry_run, sf.load_json(a.recurrence, {}))
        if not a.dry_run:
            store.save(a.store)
        print(f"[consolidate] 合并条 {r['new']}（gen{r['gen']}，"
              f"影子权重{r.get('shadow_weight', '?')}）← {r['merged_from']}"
              f"{'（dry）' if r['dry'] else '（旧条已 retract，amend 链在账）'}")
        return 0
    r = decay(store, sf.load_json(a.recurrence, {}), a.max_age_days, a.dry_run)
    if not a.dry_run and r["stale"]:
        store.save(a.store)
    print(f"[decay] 清出 {len(r['stale'])} 条孤儿草案（豁免 {r['exempt']}）"
          f"{'（dry）' if r['dry'] else ' → 已机器 retract(stale)'}")
    for eid in r["stale"]:
        print(f"  ↓stale {eid[:56]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
