# -*- coding: utf-8 -*-
"""premises.py — 前提依赖登记·翻倒传播·重审队列（20261009 vp1 冤案根治 · L2+L3+lint）

**根缺口**：全图只建模 记录→记录 的引用关系（cites/merged-from/cluster-mate），
从未建模 结论→前提 的依赖关系——前提是散文不是节点，翻倒只是又一条记录，
回溯失效传播无从谈起（实测：zsnr 翻案条目在边图里 0 条边全图孤岛）。

**本件三机制**：
  ① 依赖登记：obs/条目写入时自动盖环境指纹（capture_env，field 侧），premise=key=value；
     存量无指纹件走 backfill 显式回填（可审计，不重写历史）。
  ② 翻倒传播：前提值变化 = 翻倒事件（auto：observe_env 发现 watched key 值变；
     manual：flip 命令；backfill：补登历史翻倒）——翻倒自动枚举依赖集、生成重审票。
  ③ 重审队列：票不撤不判（人闸裁决原则），状态机 pending→retried→closed-confirm/
     closed-overturn/dismissed；batch 搭车臂（L3）按 match 关键词自动补对照销票。

**lint 闸**：教义句（论断模式）出现在 AGENTS/themes note 时必须挂证据指针
  （条目 id / obs 账本 / premises 票号）——治理面外不得自带结论（P-e 的机械化）。

CLI：
  py gov/premises.py status [--store P] [--premises P] [--queue P]
  py gov/premises.py scan   [--env-json S]                 # observe_env：翻倒检测+出票
  py gov/premises.py flip <key> <new> --ref R [--reason S] # 人工/实证翻倒
  py gov/premises.py backfill <key> <oldvalue> --targets id1,id2 --ref R [--note S]
  py gov/premises.py retrials [--status pending]
  py gov/premises.py close <T-id> --verdict overturn|confirm|dismiss --artifact S [--note S]
  py gov/premises.py lint                                  # 教义句挂指针检查
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

ROOT = os.path.dirname(os.path.dirname(_HERE))            # 仓根
FIELD = os.path.join(ROOT, "comfy-harness", "field")
OBS_DIRS = [os.path.join(FIELD, "out"), os.path.join(_HERE, "style_mine_out")]
DEFAULT_PREMISES = os.path.join(_HERE, "style_mine_out", "premises.json")
DEFAULT_QUEUE = os.path.join(_HERE, "style_mine_out", "retrial_queue.json")
DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")

# 追踪翻倒的 watched key（可 watch/unwatch 扩展；themes_sha 只记不追踪——每次改词表都翻会淹死队列）
DEFAULT_WATCHED = ["ckpt", "sampler_default", "scheduler_default",
                   "upscale_method_default", "zsnr_default",
                   "themes_any_zsnr_false", "themes_any_bislerp",
                   "themes_any_lora",
                   "recipe_base_version"]   # 配方基座版本（20261010 基座继承制：升版=政权事件→出票）

ACTOR = "machine:premises"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def load(path: str = DEFAULT_PREMISES) -> dict:
    if os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    return {"watched": list(DEFAULT_WATCHED), "states": {}, "flips": [],
            "backfills": []}


def save(reg: dict, path: str = DEFAULT_PREMISES) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(reg, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _pid(key: str, value) -> str:
    return f"{key}={value}"


# ── 依赖枚举：谁建立在这个前提上 ────────────────────────────────────────────
def _iter_obs_lines():
    for d in OBS_DIRS:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith("_obs.jsonl"):
                continue
            for i, ln in enumerate(open(os.path.join(d, fname),
                                        encoding="utf-8"), 1):
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except ValueError:
                    continue
                yield {"kind": "obs", "ref": f"{fname}:{i}", "rec": o}


def _iter_store_entries(store_path: str):
    if not os.path.isfile(store_path):
        return
    store = json.load(open(store_path, encoding="utf-8"))
    for e in store.get("entries", []):
        yield {"kind": "entry", "ref": e.get("id", "?"), "rec": e}


def _env_of(rec: dict) -> dict | None:
    env = rec.get("env")
    if isinstance(env, dict):
        return env
    f = rec.get("facts") or {}
    if isinstance(f.get("env"), dict):
        return f["env"]
    return None


def dependents(key: str, value, reg: dict | None = None,
               store_path: str = DEFAULT_STORE) -> list:
    """依赖枚举：live 指纹匹配 + backfill 登记匹配（不重写历史，两路并查）。"""
    reg = reg or load()
    want = _pid(key, value)
    out = []
    for it in _iter_obs_lines():
        env = _env_of(it["rec"])
        if env and str(env.get(key)) == str(value):
            out.append({"kind": "obs", "ref": it["ref"],
                        "claim": str(it["rec"].get("现象", ""))[:200]})
    for it in _iter_store_entries(store_path):
        env = _env_of(it["rec"])
        if env and str(env.get(key)) == str(value):
            c = (it["rec"].get("content") or {})
            out.append({"kind": "entry", "ref": it["ref"],
                        "claim": str(c.get("c", ""))[:200]})
    for b in reg.get("backfills", []):
        if b.get("premise") == want:
            for t in b.get("targets", []):
                out.append({"kind": t.get("kind", "entry"), "ref": t.get("ref"),
                            "backfilled": True})
    # 去重（backfill 与 live 可能同指一件）
    seen, uniq = set(), []
    for d in out:
        k = (d["kind"], d["ref"])
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


# ── 重审队列 ────────────────────────────────────────────────────────────────
def load_queue(path: str = DEFAULT_QUEUE) -> dict:
    if os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    return {"tickets": [], "next": 1}


def save_queue(q: dict, path: str = DEFAULT_QUEUE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(q, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _ticket_id(q: dict) -> str:
    tid = f"T-{q['next']:03d}"
    q["next"] += 1
    return tid


def enqueue(q: dict, target: dict, premise_pid: str, now_pid: str,
            claim: str = "", suspect: dict | None = None,
            match: list | None = None, dedupe: bool = True) -> dict | None:
    """出票（去重键=target+premise；不撤不判，人闸裁决）。"""
    if dedupe:
        for t in q["tickets"]:
            if (t["target"] == target and t["premise"] == premise_pid
                    and t["status"] == "pending"):
                return None
    t = {"id": _ticket_id(q), "target": target, "premise": premise_pid,
         "now": now_pid, "claim": claim[:200], "suspect": suspect or {},
         "match": match or [], "status": "pending", "created_at": _now(),
         "created_by": "machine:flip"}
    q["tickets"].append(t)
    return t


def close(q: dict, tid: str, verdict: str, artifact: str = "",
          note: str = "") -> dict:
    for t in q["tickets"]:
        if t["id"] == tid:
            assert t["status"] in ("pending", "retried"), f"{tid} 状态={t['status']} 不可close"
            assert verdict in ("confirm", "overturn", "dismiss"), verdict
            t["status"] = f"closed-{verdict}"
            t["closed_at"] = _now()
            t["artifact"] = artifact
            t["note"] = note[:300]
            return t
    raise SystemExit(f"close: 票 {tid} 不存在")


def _claim_of(dep: dict) -> str:
    return str(dep.get("claim", ""))[:200]


# ── 翻倒检测与传播 ──────────────────────────────────────────────────────────
def observe_env(env: dict, reg: dict | None = None, q: dict | None = None,
                premises_path: str = DEFAULT_PREMISES,
                queue_path: str = DEFAULT_QUEUE,
                store_path: str = DEFAULT_STORE,
                how: str = "auto") -> dict:
    """写入侧接线：每个新 env 快照过一遍 watched key——值变 = 翻倒 = 出票。"""
    reg = reg if reg is not None else load(premises_path)
    q = q if q is not None else load_queue(queue_path)
    watched = [k for k in reg.get("watched", DEFAULT_WATCHED) if k in env]
    flips = []
    for k in watched:
        new = env[k]
        last = reg["states"].get(f"last:{k}")
        pid_new = _pid(k, new)
        if last is not None and str(last.get("value")) != str(new):
            pid_old = _pid(k, last["value"])
            flip = {"key": k, "from": str(last["value"]), "to": str(new),
                    "at": _now(), "ref": f"env:{_now()}", "how": how}
            reg["flips"].append(flip)
            flips.append(flip)
            reg["states"][pid_old] = {"status": "flipped", "flipped_to": pid_new,
                                      "at": flip["at"]}
            # 传播：旧前提下成立的每个依赖 → 出重审票
            for dep in dependents(k, last["value"], reg, store_path):
                tgt = {"kind": dep["kind"], "ref": dep["ref"]}
                enqueue(q, tgt, pid_old, pid_new, claim=_claim_of(dep))
        reg["states"][f"last:{k}"] = {"value": new, "at": _now()}
        reg["states"].setdefault(pid_new, {"status": "live", "since": _now()})
    save(reg, premises_path)
    save_queue(q, queue_path)
    return {"flips": flips, "tickets": len(q["tickets"])}


def declare_flip(key: str, old, new: str, ref: str, reg: dict | None = None,
                 q: dict | None = None, premises_path: str = DEFAULT_PREMISES,
                 queue_path: str = DEFAULT_QUEUE,
                 store_path: str = DEFAULT_STORE,
                 how: str = "manual") -> dict:
    """实证翻倒（人签/obs 铁证）：直接声明 from→to 并传播出票。"""
    reg = reg if reg is not None else load(premises_path)
    q = q if q is not None else load_queue(queue_path)
    pid_old, pid_new = _pid(key, old), _pid(key, new)
    reg["flips"].append({"key": key, "from": str(old), "to": str(new),
                         "at": _now(), "ref": ref, "how": how})
    reg["states"][pid_old] = {"status": "flipped", "flipped_to": pid_new,
                              "at": _now()}
    reg["states"][pid_new] = {"status": "live", "since": _now()}
    reg["states"][f"last:{key}"] = {"value": new, "at": _now()}
    deps = dependents(key, old, reg, store_path)
    for dep in deps:
        tgt = {"kind": dep["kind"], "ref": dep["ref"]}
        enqueue(q, tgt, pid_old, pid_new, claim=_claim_of(dep))
    save(reg, premises_path)
    save_queue(q, queue_path)
    return {"flip": reg["flips"][-1], "dependents": deps, "tickets": len(q["tickets"])}


def backfill(key: str, value, targets: list, ref: str, note: str = "",
             reg: dict | None = None, q: dict | None = None,
             premises_path: str = DEFAULT_PREMISES,
             queue_path: str = DEFAULT_QUEUE,
             store_path: str = DEFAULT_STORE) -> dict:
    """存量回填：无指纹时代的历史条目显式登记前提依赖（可审计，不改历史行）。

    若该前提已登记为 flipped（或随后被翻倒），回填即触发对这批 target 的出票。
    """
    reg = reg if reg is not None else load(premises_path)
    q = q if q is not None else load_queue(queue_path)
    pid = _pid(key, value)
    ent = {"premise": pid, "targets": [{"kind": k, "ref": r} for k, r in targets],
           "ref": ref, "note": note[:200], "at": _now()}
    reg.setdefault("backfills", []).append(ent)
    save(reg, premises_path)
    created = []
    st = reg["states"].get(pid, {})
    if st.get("status") == "flipped":                    # 该前提已翻倒 → 立即出票
        for t in ent["targets"]:
            tk = enqueue(q, t, pid, st["flipped_to"],
                         claim=f"backfill: {note}")
            if tk:
                created.append(tk["id"])
        save_queue(q, queue_path)
    return {"backfill": ent, "tickets_created": created}


# ── 机会主义重审（L3 搭车匹配）────────────────────────────────────────────
def piggyback_matches(context: str, q: dict | None = None,
                      queue_path: str = DEFAULT_QUEUE) -> list:
    """给定当前批次上下文（theme 名+pos+lora 串），返回可搭车的 pending 票。"""
    q = q if q is not None else load_queue(queue_path)
    out = []
    for t in q["tickets"]:
        if t["status"] != "pending" or not t.get("match"):
            continue
        if any(str(kw).lower() in context.lower() for kw in t["match"]):
            out.append(t)
    return out


def mark_retried(q: dict | None = None, queue_path: str = DEFAULT_QUEUE,
                 tid: str = "", artifact: str = "", seed=None) -> dict:
    q = q if q is not None else load_queue(queue_path)
    for t in q["tickets"]:
        if t["id"] == tid:
            t["status"] = "retried"
            t["retrial"] = {"at": _now(), "artifact": artifact, "seed": seed}
            save_queue(q, queue_path)
            return t
    raise SystemExit(f"mark_retried: {tid} 不存在")


# ── lint 闸：教义句必须挂证据指针（P-e 机械化）────────────────────────────
CLAIM_PAT = re.compile(
    r"(实测|实证|致糊|导致|会造成|会引起|根因|真凶|根源|必须|禁止|不要|一律|"
    r"定稿|胜出|平反|推翻|结论|教义)")
POINTER_PAT = re.compile(
    r"(P-[A-Za-z0-9\-]{6,}|S-[A-Za-z0-9\-]{6,}|T-\d{3}|F-\d{3}|"
    r"[\w/\\.-]+_obs\.jsonl|out/[\w.\-]+\.png|sha256=[0-9a-f]{8}|"
    r"DENY:[A-Z_]+|test_\w+\.py)")


def lint_file(path: str, text: str | None = None) -> list:
    """返回无指针的论断句列表（file, 句）。themes.json 传 note 字段聚合文本。"""
    if text is None:
        text = open(path, encoding="utf-8").read()
    bad = []
    for raw in re.split(r"[。；;\n]", text):
        s = raw.strip()
        if s and CLAIM_PAT.search(s) and not POINTER_PAT.search(s):
            bad.append({"file": path, "claim": s[:120]})
    return bad


def lint() -> list:
    """AGENTS.md（harness 线）+ themes.json 全部 note 字段过闸。"""
    bad = []
    ag = os.path.join(ROOT, "comfy-harness", "AGENTS.md")
    if os.path.isfile(ag):
        bad += lint_file(ag)
    tp = os.path.join(FIELD, "themes.json")
    if os.path.isfile(tp):
        themes = json.load(open(tp, encoding="utf-8"))
        for name, th in themes.items():
            note = str(th.get("note", ""))
            if not note:
                continue
            for b in lint_file(f"{tp}#{name}", note):
                bad.append(b)
    return bad


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="前提依赖登记·翻倒传播·重审队列")
    ap.add_argument("verb", choices=("status", "scan", "flip", "backfill",
                                     "retrials", "close", "lint", "watch",
                                     "enqueue"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--ref", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--targets", default="")
    ap.add_argument("--verdict", default=None,
                    choices=(None, "confirm", "overturn", "dismiss"))
    ap.add_argument("--artifact", default="")
    ap.add_argument("--from", dest="from_val", default=None,
                    help="flip 显式旧值（无 last-seen 的种子回填场景必填）")
    ap.add_argument("--kind", default="entry")
    ap.add_argument("--premise-old", default="")
    ap.add_argument("--premise-new", default="")
    ap.add_argument("--claim", default="")
    ap.add_argument("--match", default="", help="搭车关键词，逗号分隔")
    ap.add_argument("--suspect-lora", default="")
    ap.add_argument("--suspect-weight", type=float, default=0.7)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--premises", default=DEFAULT_PREMISES)
    ap.add_argument("--queue", default=DEFAULT_QUEUE)
    a = ap.parse_args(argv)

    if a.verb == "lint":
        bad = lint()
        for b in bad:
            print(f"[lint] 无指针论断：{b['file']}\n       └ {b['claim']}")
        print(f"[lint] {len(bad)} 处违规" + ("——教义句必须挂条目id/obs账本/票号" if bad else "（全过）"))
        return 1 if bad else 0

    if a.verb == "status":
        reg, q = load(a.premises), load_queue(a.queue)
        live = {k: v for k, v in reg["states"].items() if not k.startswith("last:")}
        print(f"watched: {reg['watched']}")
        print(f"前提状态: live={sum(1 for v in live.values() if v['status']=='live')} "
              f"flipped={sum(1 for v in live.values() if v['status']=='flipped')} "
              f"flips={len(reg['flips'])} backfills={len(reg.get('backfills', []))}")
        print(f"重审队列: {len(q['tickets'])} 票 "
              f"(pending={sum(1 for t in q['tickets'] if t['status']=='pending')})")
        for f in reg["flips"][-5:]:
            print(f"  flip {f['key']}: {f['from']}→{f['to']} ({f['how']}, {f['at']})")
        return 0

    if a.verb == "scan":
        sys.path.insert(0, FIELD)
        import cinematic_gen as cg
        env = (json.loads(a.args[0]) if a.args else cg.capture_env())
        r = observe_env(env, store_path=a.store, premises_path=a.premises,
                        queue_path=a.queue)
        print(f"[scan] 翻倒 {len(r['flips'])} 起，队列 {r['tickets']} 票")
        for f in r["flips"]:
            print(f"  ⚠ {f['key']}: {f['from']}→{f['to']}")
        return 0

    if a.verb == "flip":
        if len(a.args) < 2 or not a.ref:
            raise SystemExit("flip <key> <new> --ref R 必填（种子场景加 --from 旧值）")
        key, new = a.args[0], a.args[1]
        reg = load(a.premises)
        last = (str(a.from_val) if a.from_val is not None
                else reg["states"].get(f"last:{key}", {}).get("value"))
        if last is None:
            raise SystemExit(f"flip: {key} 无 last-seen 且未给 --from——拒绝盲翻")
        r = declare_flip(key, last, new, a.ref, store_path=a.store,
                         premises_path=a.premises, queue_path=a.queue)
        print(f"[flip] {key}: {last}→{new}，依赖 {len(r['dependents'])} 件，"
              f"队列 {r['tickets']} 票")
        return 0

    if a.verb == "backfill":
        if len(a.args) < 2 or not a.targets or not a.ref:
            raise SystemExit("backfill <key> <oldvalue> --targets id1,id2 --ref R 必填")
        tgts = [("entry", t.strip()) for t in a.targets.split(",") if t.strip()]
        r = backfill(a.args[0], a.args[1], tgts, a.ref, a.note,
                     store_path=a.store, premises_path=a.premises,
                     queue_path=a.queue)
        print(f"[backfill] {r['backfill']['premise']} ← {len(tgts)} 件，"
              f"出票 {r['tickets_created']}")
        return 0

    if a.verb == "retrials":
        q = load_queue(a.queue)
        st = a.args[0] if a.args else "pending"
        for t in q["tickets"]:
            if st in ("all", t["status"]):
                print(f"{t['id']} [{t['status']}] {t['premise']} → {t['target']['ref'][:40]}"
                      f" | {t['claim'][:50]}")
        return 0

    if a.verb == "close":
        if not a.args or a.verdict is None:
            raise SystemExit("close <T-id> --verdict confirm|overturn|dismiss [--artifact S] [--note S]")
        q = load_queue(a.queue)
        t = close(q, a.args[0], a.verdict, a.artifact, a.note)
        save_queue(q, a.queue)
        print(f"[close] {t['id']} → {t['status']}")
        return 0

    if a.verb == "enqueue":
        if not a.premise_old or not a.premise_new or not a.ref:
            raise SystemExit("enqueue --premise-old X --premise-new Y --ref R 必填")
        q = load_queue(a.queue)
        sus = ({"lora": a.suspect_lora, "lora_weight": a.suspect_weight}
               if a.suspect_lora else {})
        t = enqueue(q, {"kind": a.kind, "ref": a.ref},
                    a.premise_old, a.premise_new, claim=a.claim,
                    suspect=sus,
                    match=[m.strip() for m in a.match.split(",") if m.strip()])
        save_queue(q, a.queue)
        print(f"[enqueue] {t['id'] if t else '去重未出'} | {a.ref[:40]}")
        return 0

    if a.verb == "watch":
        reg = load(a.premises)
        if a.args[0] not in reg["watched"]:
            reg["watched"].append(a.args[0])
            save(reg, a.premises)
        print(f"[watch] {reg['watched']}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
