# -*- coding: utf-8 -*-
"""obs_to_draft.py — 观察流账本→飞轮铸判（机械化兑现端；skill:image-review 的下半程）

上半程=评审时把观察落账（`field/out/<prefix>_obs.jsonl`，一行一条，见 skill:image-review）；
本件=下半程：扫全部账本 → **够格条目自动铸技巧草稿**（治理位人闸后服务召回）。

账本行 schema：
  {"类":"增益|减损|异常|复现线索|无", "现象":"…", "条件":"…", "证据":"f1+f2",
   "对照":true/false, "可复算":"命令或说明", "minted":"P-…"(由本件写回)}

够格=类∉{无} 且 对照=true 且 可复算非空 且 尚未铸（行内 minted / 库内"观察签名"）。
  20261010 维护者审计修正：原类白名单 {增益,减损} 过窄——"异常=机制未明不铸"的真门
  本就是证据闸（对照+可复算：机制未明就没有对照实验）；类拦截使构图 bug 修复记录
  （异常/配方/复审/伪影 11 条）零注入（实锤）。现仅排除"无"（空转）。
  minted 哨兵：'0'/空串=未铸（历史 --minted=0 误用 11 行，'0' 为 truthy 会伪装已铸）。

幂等双闸：行内 minted 字段 + 库内"观察签名 <sig>" 查重。
开关：OBS_FEED=off/0/false/no 或 --off；--dry-run 只报不铸不写回。
用法：py -X utf8 obs_to_draft.py [--dir field/out] [--store P] [--dry-run] [--off]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # 工作区根（evocore）
import style_feed as sf                                        # noqa: E402  （classify/_slug 复用）

DEFAULT_DIR = os.path.join(_HERE, "..", "field", "out")
DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")

_ENV = "OBS_FEED"
_OFF = {"0", "off", "false", "no", "disable", "disabled"}
# 20261010 扩容（维护者审计「修构图bug是注入的吗」→ 实锤零注入）：仅排除"无"（空转）；
# 真门=证据闸（对照+可复算），类白名单是冗余且过窄的一道
_MINTABLE = {"增益", "减损", "异常", "配方", "复审", "伪影", "复现线索"}
_MINTED_SENTINEL = {"", "0"}


def _minted_id(rec: dict):
    """已铸 id；'0'/空串=未铸哨兵（--minted=0 历史误用，'0' 为 truthy 会伪装已铸）。"""
    v = rec.get("minted")
    return None if str(v).strip() in _MINTED_SENTINEL else v


def is_disabled(cli_off: bool = False, env: str | None = None) -> bool:
    if cli_off:
        return True
    v = (env if env is not None else os.environ.get(_ENV, "")).strip().lower()
    return v in _OFF


def _sig(phenomenon: str) -> str:
    return hashlib.sha1(" ".join(_norm_word for _norm_word in
                                 re.sub(r"\s+", " ", phenomenon).strip().lower().split())
                        .encode("utf-8")).hexdigest()[:8]


def load_ledgers(directory: str) -> list:
    """读目录下全部 *_obs.jsonl → [{path, line_no, rec}]（坏行跳过并计数）。"""
    rows, bad = [], 0
    if not os.path.isdir(directory):
        return rows
    for name in sorted(os.listdir(directory)):
        if not name.endswith("_obs.jsonl"):
            continue
        p = os.path.join(directory, name)
        for i, line in enumerate(open(p, encoding="utf-8"), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(rec, dict):
                rows.append({"path": p, "line_no": i, "rec": rec})
    if bad:
        print(f"[obs] 坏行 {bad}（跳过，不静默）")
    return rows


def mint(rows: list, store, dry: bool = False) -> dict:
    existing = " ".join(json.dumps(e.get("content", {}), ensure_ascii=False)
                        for e in store.entries)
    existing_sigs = {e.get("_mine_sig") for e in store.entries if e.get("_mine_sig")}
    minted, skipped = [], []
    for row in rows:
        rec = row["rec"]
        cls = rec.get("类", "")
        phen = str(rec.get("现象", "")).strip()
        if cls not in _MINTABLE or not phen:
            continue
        sig = _sig(phen)
        if _minted_id(rec) or sig in existing_sigs or f"观察签名 {sig}" in existing:
            skipped.append({"现象": phen[:40], "why": "已铸"})
            continue
        if not (rec.get("对照") and str(rec.get("可复算", "")).strip()):
            skipped.append({"现象": phen[:40], "why": "不够格（缺对照/可复算）"})
            continue
        kind = sf.classify([phen, str(rec.get("条件", ""))])
        eid = f"P-obs-{sf._slug(phen)}-{sig}"
        ev = rec.get("证据", "")
        if isinstance(ev, dict):                    # 20261010 证据分离：files 可机核
            fl = ev.get("files") or []
            art = ";".join(str(f.get("path") or f.get("name") or "") for f in fl) \
                or row["path"]
            ev_text = "；".join(str(f.get("name") or "") for f in fl)
            if ev.get("note"):
                ev_text += f"（注：{ev['note']}）"
            ev_extra = {"files": [{"name": f.get("name"), "sha256": f.get("sha256")}
                                  for f in fl]}
        else:
            art = str(ev or "") or row["path"]
            ev_text = str(ev or "")
            ev_extra = {}
        entry = {
            "id": eid, "type": "procedural", "importance": 4,
            "keywords": [w for w in re.split(r"[\s，,、]+", phen) if w][:6],
            "task": "t2i", "kind": kind, "level": "specialized",
            "_mine_sig": sig,                       # 机器标记（D′ 批：流程词出正文）
            "content": {
                "c": f"{cls}观察：{phen}。",
                "a": f"条件：{rec.get('条件', '')}；对照实验在场；复算：{rec.get('可复算', '')}。"
                     f"证据：{ev_text}（大体积图证不入库，路径+本地留存）。",
                "d": "边界：来自观察流单条，推广前须复算；机制解释若后续推翻以 amend 修订。",
            },
            "evidence": {
                "artifact": art,
                "quote": phen,
                "recalc": rec.get("可复算", ""),
                **ev_extra,
            },
        }
        if not dry:
            facts = {}
            if isinstance(rec.get("env"), dict):
                facts["env"] = rec["env"]       # L1 前提依赖随行入账（翻倒可枚举）
            store.add(entry, actor="ai:obs-feed", **({"facts": facts} if facts else {}))
            existing += json.dumps(entry["content"], ensure_ascii=False)
            row["_dirty"] = True                  # 本轮铸的行才写回
        existing_sigs.add(sig)
        rec["minted"] = eid
        minted.append({"id": eid, "kind": kind, "类": cls, "现象": phen[:40]})
    return {"minted": minted, "skipped": skipped}


def writeback(rows: list) -> int:
    """把 minted 写回账本（按 path 分组重写；仅动有变化的行）。"""
    by_path = {}
    for row in rows:
        by_path.setdefault(row["path"], []).append(row)
    n = 0
    for path, grp in by_path.items():
        if not any(r.get("_dirty") for r in grp):
            continue
        lines = open(path, encoding="utf-8").read().splitlines()
        for r in grp:
            if r.get("_dirty"):
                lines[r["line_no"] - 1] = json.dumps(r["rec"], ensure_ascii=False)
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="观察流账本→飞轮铸判")
    ap.add_argument("--dir", default=os.path.normpath(DEFAULT_DIR))
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--off", action="store_true", help="开关：关闭投喂")
    a = ap.parse_args(argv)
    if is_disabled(a.off):
        print(f"[obs] 已关闭（开关 {_ENV} / --off）——不投喂")
        return 0

    from precedent_gov import PrecedentStore
    rows = load_ledgers(a.dir)
    store = PrecedentStore.load(a.store)
    res = mint(rows, store, a.dry_run)
    if not a.dry_run and res["minted"]:
        store.save(a.store)
        writeback(rows)
    os.makedirs(os.path.join(_HERE, "style_mine_out"), exist_ok=True)
    json.dump(res, open(os.path.join(_HERE, "style_mine_out", "obs_feed_report.json"),
                        "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    print(f"[obs] 账本行 {len(rows)} → {'dry-run' if a.dry_run else 'minted'} "
          f"{len(res['minted'])} · 跳过 {len(res['skipped'])}")
    for m in res["minted"]:
        print(f"  {m['kind']:<10} {m['id'][:56]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
