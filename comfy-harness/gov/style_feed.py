# -*- coding: utf-8 -*-
"""style_feed.py — 涌现→飞轮投喂器（机器提案位：簇→草稿判例）

（20261008 维护者令；工单-飞轮根治与向量化统合 P3/P4 增装：双子闸+聚合+出口）

链路：双挖掘器候选簇 →【N1 轮内合并】→【出口与闸】→ 铸 draft 判例入受治库。
draft 不供血（无主防毒缺省）；人签 promote 后才服务。

**P3/P4 四重防线（工单红线全载）**：
  ① 根凭据闸（Citogenesis 对策）：候选 evidence 必须回溯到 ≥1 个**根**（生成面文档 /
     已签 approved/verified 条目）；证据链全派生（草稿 id）→ 拒铸，转 process 出口。
  ② process 出口（C′）：成员命中流程词表（草稿 id 形态/挖掘措辞）≥2 → 不铸知识草稿，
     落 process_report.json（自食产物有正门可走，不回流）。
  ③ gen 代数上限（非放大红线）：候选代数 = 1 + 被引条目的代数；**gen≥2 禁铸**——
     合并不升信任级、更不升"谱系地位"。
  ④ 近重复闸（M/N9，cosine）：对既有条目嵌入缓存做 brute-force 余弦；≥dup_cos 不重铸，
     改记 recurrence（同簇跨轮重现=证据强化信号，只进人决策面——Provenance Laundering 红线）。
  （旧精确签名闸保留为第一道短路；cache_path=None 时 cosine 闸关闭=旧行为，仅测试用。）

轨道分流（按簇成分路由，不按挖掘器绑定）：governance > model > pipeline > postproc > style。
开关：STYLE_FEED=off/0/false/no 或 --off（compare 编排器透传 --no-feed）。
用法：
  py -X utf8 style_feed.py [--det P] [--lr P] [--corpus P] [--store P]
      [--min-size 4] [--dry-run] [--no-cosine] [--off]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # 工作区根（evocore 包所在）
import style_mine_compare as cmp_mod          # noqa: E402  （复用跨臂匹配器械）

DEFAULT_DET = os.path.join(_HERE, "style_mine_out", "det_candidates.json")
DEFAULT_LR = os.path.join(_HERE, "style_mine_out", "lightrag_candidates.json")
# 来源臂 → 证据文件（20261010：铸造证据指针从花括号模板改为真实路径，检定 R3 可核存）
_ARM_EVIDENCE_FILE = {"det": "style_mine_out/det_candidates.json",
                      "lightrag": "style_mine_out/lightrag_candidates.json"}
DEFAULT_CORPUS = os.path.join(_HERE, "style_mine_out", "corpus.json")
DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_REPORT = os.path.join(_HERE, "style_mine_out", "feed_report.json")
DEFAULT_PROCESS = os.path.join(_HERE, "style_mine_out", "process_report.json")
DEFAULT_RECURRENCE = os.path.join(_HERE, "style_mine_out", "recurrence.json")
DEFAULT_CACHE = os.path.join(_HERE, "style_mine_out", "embeddings.json")
DEFAULT_POOL = os.path.join(_HERE, "style_mine_out", "candidate_pool.json")
DEFAULT_ANTI = os.path.join(_HERE, "style_mine_out", "anti_shadow.jsonl")

_ENV = "STYLE_FEED"
_OFF = {"0", "off", "false", "no", "disable", "disabled"}

# 强标记词表（归一小写后子串/等值匹配；顺序=优先级）
_RULES = (
    ("governance", ("判例", "判据", "闸", "升格", "治理", "审计", "正式考", "verify",
                    "回执", "别名", "prereg", "supersede", "owner", "schema")),
    ("model", (".safetensors", ".gguf", "ckpt", "底模", "half-model", "noobai-xl",
               "anisor")),
    ("pipeline", ("ksampler", "steps", "denoise", "latent", "upscale", "hires", "重绘",
                  "loader", "scheduler", "cfg", "api", "布线", "节点", "pass", "契约",
                  "wiring", "venv", "trampoline", "cache", "/object_info", "combo",
                  "组合", "二段", "采样", "半模")),
    ("postproc", ("grain", "颗粒", "vignette", "暗角", "色散", "ca_", "detailer",
                  "面部二道", "手部", "film", "胶片", "第二道")),
)
# process 特征词（C′ 出口；草稿 id 形态+挖掘措辞——实测自食簇的组成词）
_PROCESS_PAT = re.compile(
    r"(?i)^[sp]-[a-z0-9-]+-[0-9a-f]{8}$|mining signature|machine proposal|candidate boundary|"
    r"observation flow|挖掘签名|观察签名|机器提案|观察流|style_mine|four-way|候选边界|"
    r"human gate|人闸|自食|loop")


def is_disabled(cli_off: bool = False, env: str | None = None) -> bool:
    if cli_off:
        return True
    v = (env if env is not None else os.environ.get(_ENV, "")).strip().lower()
    return v in _OFF


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def classify(members, hubs=frozenset()) -> str:
    """按成员成分分流 kind：计票制；model 轨须≥2 票（底模实体混入防护）；全零→style。"""
    ms = [_norm(m) for m in members if _norm(m) not in hubs]
    order = {kind: i for i, (kind, _) in enumerate(_RULES)}
    scores = {kind: 0 for kind, _ in _RULES}
    for m in ms:
        for kind, markers in _RULES:
            if len(m) >= 2 and (any(mk in m for mk in markers) or m in markers):
                scores[kind] += 1
                break
    best = max(scores, key=lambda k: (scores[k], -order[k]))
    need = 2 if best == "model" else 1
    return best if scores[best] >= need else "style"


def task_of(members) -> str:
    ms = " ".join(_norm(m) for m in members)
    if re.search(r"wan|video|帧|frame|anisor", ms):
        return "t2v"
    if re.search(r"i2v|图生视频", ms):
        return "i2v"
    return "t2i"


def model_family_of(evidence: list, corpus_docs: list) -> tuple:
    """沿证据回源生成文档的底模 → (族名, 样本文件≤3)；判例证据无底模信息→unknown。"""
    by_src = {d["src"]: (d.get("meta") or {}) for d in corpus_docs}
    fams, samples = set(), []
    for src in evidence:
        meta = by_src.get(src)
        if not meta:
            continue
        ck = str(meta.get("ckpt") or "")
        if ck:
            fam = re.sub(r"\.safetensors$", "", os.path.basename(ck))
            fams.add(fam)
            if len(samples) < 3:
                samples.append(os.path.basename(src).replace("generation:", ""))
    if not fams:
        return "unknown", samples
    if len(fams) == 1:
        return next(iter(fams)), samples
    return "mixed", samples


def sig_of(members) -> str:
    return hashlib.sha1(" ".join(sorted(_norm(m) for m in members))
                        .encode("utf-8")).hexdigest()[:8]


def candidate_text(name: str, members: list) -> str:
    """候选 → 嵌入文本（确定性：名称 + 前 20 成员）。"""
    return (str(name) + " " + " ".join(sorted(_norm(m) for m in members)[:20])).strip()


def is_process(name: str, members) -> int:
    """process 特征命中数（名称+成员逐词扫；≥2 判自食产物）。"""
    hits = sum(1 for m in members if _PROCESS_PAT.search(_norm(m)))
    if _PROCESS_PAT.search(_norm(name)):
        hits += 1
    return hits


def roots_of(store) -> set:
    """根凭据集：已签条目 id（approved/verified）——根凭据闸的锚。"""
    return {e["id"] for e in store.entries if e.get("gov") in ("approved", "verified")}


def gen_map(store) -> dict:
    """已铸条目的代数表（_mine_gen，缺省 0=非挖掘源）。"""
    return {e["id"]: int(e.get("_mine_gen") or 0) for e in store.entries}


def candidate_has_root(evidence: list, roots: set) -> bool:
    for s in evidence:
        if s.startswith("generation:"):
            return True
        if s.startswith("precedent:") and s.split(":", 1)[1] in roots:
            return True
    return False


def candidate_gen(evidence: list, gmap: dict) -> int:
    g = 0
    for s in evidence:
        if s.startswith("precedent:"):
            g = max(g, gmap.get(s.split(":", 1)[1], 0))
    return g + 1


def load_json(path: str, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)


def hubs_of(cands, ratio: float = 0.3, floor: int = 3) -> set:
    n = max(1, len(cands))
    cnt = {}
    for c in cands:
        for m in set(c["members"]):
            k = _norm(m)
            cnt[k] = cnt.get(k, 0) + 1
    return {m for m, k in cnt.items() if k > max(floor, ratio * n)}


def merge_batch_by_vec(cands: list, embed_fn, dup_cos: float) -> list:
    """N1 轮内合并：候选两两 cosine ≥ dup_cos → 并集合并（贪心，确定性顺序）。"""
    if not cands:
        return cands
    import numpy as _np
    vecs = embed_fn([candidate_text(c["name"], c["members"]) for c in cands])
    merged, used = [], [False] * len(cands)
    for i, c in enumerate(cands):
        if used[i]:
            continue
        cur = {"name": c["name"], "members": list(c["members"]),
               "arms": list(c["arms"]), "cohesion": c.get("cohesion", 0),
               "evidence": list(c.get("evidence", []))}
        for j in range(i + 1, len(cands)):
            if used[j]:
                continue
            a, b = vecs[i], vecs[j]
            na, nb = _np.linalg.norm(a), _np.linalg.norm(b)
            cos = float(a @ b / (na * nb)) if na and nb else 0.0
            if cos >= dup_cos:
                used[j] = True
                cur["members"] = sorted(set(cur["members"]) | set(cands[j]["members"]))
                cur["arms"] = sorted(set(cur["arms"]) | set(cands[j]["arms"]))
                cur["evidence"] = sorted(set(cur["evidence"]) | set(cands[j]["evidence"]))
        merged.append(cur)
    return merged


def merge_candidates(det: dict, lr: dict) -> list:
    """跨臂合并：配对簇→并集候选（arms 双记）；未配对各白过。"""
    pairing = cmp_mod.pair_clusters(det["clusters"], lr["clusters"])
    by_i = {p["det"]: p for p in pairing["pairs"]}
    out = []
    for i, dc in enumerate(det["clusters"]):
        p = by_i.get(i)
        if p:
            lc = lr["clusters"][p["lr"]]
            members = sorted({t["tag"] for t in dc.get("tags", [])}
                             | set(lc.get("members", [])))
            out.append({"name": dc["name"], "members": members,
                        "arms": ["det", "lightrag"],
                        "cohesion": round((dc.get("cohesion", 0)
                                           + lc.get("cohesion", 0)) / 2, 2),
                        "evidence": sorted(set(dc.get("evidence", []))
                                           | set(lc.get("evidence", [])))})
        else:
            out.append({"name": dc["name"],
                        "members": sorted({t["tag"] for t in dc.get("tags", [])}),
                        "arms": ["det"], "cohesion": dc.get("cohesion", 0),
                        "evidence": list(dc.get("evidence", []))})
    paired_lr = {p["lr"] for p in pairing["pairs"]}
    for j, lc in enumerate(lr["clusters"]):
        if j not in paired_lr:
            out.append({"name": lc["name"], "members": sorted(lc.get("members", [])),
                        "arms": ["lightrag"], "cohesion": lc.get("cohesion", 0),
                        "evidence": list(lc.get("evidence", []))})
    return out


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")
    return (s[:28] or "cluster").strip("-")


def members_of_minted(store, eid: str) -> list:
    """刚铸条的成员词（关键词+tags）——供反例通道对照标本用。"""
    try:
        e = store._get(eid)
    except Exception:                                          # noqa: BLE001
        return []
    f = e.get("facts") or {}
    return sorted(set([str(k) for k in (e.get("keywords") or [])]
                      + [str(x) for x in (f.get("tags") or [])]))


def feed(cands: list, store, corpus_docs: list, min_size: int = 4,
         dry: bool = False, hubs=None, cache_path: str | None = None,
         embed_fn=None, dup_cos: float = 0.90,
         recurrence_path: str = DEFAULT_RECURRENCE,
         pool_path: str | None = None, min_rounds: int = 2,
         anti_path: str | None = None, anti_mode: str | None = None) -> dict:
    """铸草稿（四重防线+成熟度闸+反例通道）。cache_path/pool_path/anti_path=None → 对应闸关闭
    （测试旧行为；生产由 main() 显式传路径——防测试误触生产件）。"""
    hubs = hubs if hubs is not None else hubs_of(cands)
    roots = roots_of(store)
    gmap = gen_map(store)

    went = 0
    if embed_fn is not None:
        before = len(cands)
        cands = merge_batch_by_vec(cands, embed_fn, dup_cos)     # N1 轮内合并
        went = before - len(cands)
    rounds = {}
    if pool_path:
        import candidate_pool as cp
        rounds = cp.observe(cands, pool_path)                    # N2：整批记一轮

    existing_text = " ".join(json.dumps(e.get("content", {}), ensure_ascii=False)
                             for e in store.entries)
    existing_sigs = {e.get("_mine_sig") for e in store.entries if e.get("_mine_sig")}
    existing_bases = {}                      # slug 基底表：同名=同概念（live 实证 2/9 组
    base_counts = {}                         # 跨代重铸 cos<0.90 溜过，基底相等直接判近重复）
    for e in store.entries:
        if str(e.get("id", "")).startswith("S-"):
            b = e["id"].rsplit("-", 1)[0].lower()
            existing_bases.setdefault(b, e["id"])          # 近重复闸：含下架件（防重铸已并概念）
            if not (e.get("tombstone") or e.get("machine_retracted")):
                base_counts[b] = base_counts.get(b, 0) + 1  # 族谱计数：只算在役（防灌大）
    cache = None                             # 近重复闸的两个 if cache_path 块共享此绑定（初值显式化）
    if cache_path:
        import embed_cache as ec
        cache = ec.load_cache(cache_path)
        if not cache.get("items"):
            raise RuntimeError(f"嵌入缓存为空/不存在（{cache_path}）——先跑 "
                               f"`py comfy-harness/gov/embed_cache.py`（近重复闸不降级）")
    recurrence = load_json(recurrence_path, {})
    minted, skipped, routed, process, recurred = [], [], {}, [], []
    for c in cands:
        if len(c["members"]) < min_size:
            skipped.append({"name": c["name"], "why": f"size<{min_size}"})
            continue
        sig = sig_of(c["members"])
        if sig in existing_sigs or f"挖掘签名 {sig}" in existing_text:
            skipped.append({"name": c["name"], "why": f"sig {sig} 已在库"})
            continue
        if is_process(c["name"], c["members"]) >= 2:             # ② process 出口（C′）
            process.append({"name": c["name"], "members": c["members"][:20],
                            "arms": c["arms"], "why": "process 特征≥2（自食产物走治理报告）"})
            continue
        gen = candidate_gen(c["evidence"], gmap)                 # ③ gen 上限（非放大红线）
        if gen >= 2:
            skipped.append({"name": c["name"], "why": f"gen={gen}≥2 禁铸（非放大红线）"})
            continue
        if not candidate_has_root(c["evidence"], roots):         # ① 根凭据闸（Citogenesis）
            process.append({"name": c["name"], "members": c["members"][:20],
                            "arms": c["arms"], "why": "证据全派生（无根凭据）→process"})
            continue
        base = f"s-{_slug(c['name']).lower()}"                      # ④a slug 基底闸（同名即重复）
        if base in existing_bases:
            hit_eid = existing_bases[base]
            rec = recurrence.setdefault(hit_eid, {"count": 0, "rounds": []})
            rec["count"] += 1
            rec["rounds"].append({"at": time.strftime("%Y-%m-%d"),
                                  "candidate": c["name"], "cos": None, "by": "slug-base"})
            skipped.append({"name": c["name"],
                            "why": f"近重复→recurrence({hit_eid[:36]}，同基底）"})
            recurred.append({"candidate": c["name"], "into": hit_eid, "cos": None})
            continue
        if pool_path:                                            # ⑤ 成熟度闸（N2·复现才铸）
            import candidate_pool as _cp
            rs = rounds.get(_cp.key_of(_cp.load_pool(pool_path), c), 1)
            if rs < min_rounds:
                skipped.append({"name": c["name"],
                                "why": f"成熟度闸：落池待复现（{rs}/{min_rounds} 轮）"})
                continue
        if cache_path:                                           # ④b 近重复闸（M/N9 cosine）
            import embed_cache as ec
            assert cache is not None, "近重复闸：cache 未载入（上方同条件块必先于本处执行）"
            txt = candidate_text(c["name"], c["members"])
            qv = embed_fn([txt])[0] if embed_fn else ec.embed_docs([txt])[0]
            top = ec.nearest(cache, qv, k=1)
            if top and top[0][0] >= dup_cos:
                hit_eid = top[0][1]
                rec = recurrence.setdefault(hit_eid, {"count": 0, "rounds": []})
                rec["count"] += 1
                rec["rounds"].append({"at": time.strftime("%Y-%m-%d"),
                                      "candidate": c["name"], "cos": round(top[0][0], 3)})
                skipped.append({"name": c["name"],
                                "why": f"近重复→recurrence({hit_eid[:36]}，cos={top[0][0]:.3f})"})
                recurred.append({"candidate": c["name"], "into": hit_eid,
                                 "cos": round(top[0][0], 3)})
                continue
        kind = classify(c["members"], hubs)
        task = task_of(c["members"])
        fam, samples = model_family_of(c["evidence"], corpus_docs)
        top = c["members"][:10]
        eid = f"S-{_slug(c['name'])}-{sig}"
        entry = {
            "id": eid, "type": "procedural", "importance": 3,
            "keywords": [t for t in c["members"][:6]],
            "task": task, "kind": kind, "level": "specialized",
            "_mine_sig": sig,                        # 机器标记（D′ 批：流程词出正文）
            "_mine_gen": gen,                        # 代数（工单 P4；非放大红线盯防）
            "content": {
                "c": f"风格簇「{c['name']}」：成员 {len(c['members'])} 项，代表 "
                     f"{'、'.join(top[:8])}；凝聚度 {c['cohesion']}；来源臂={'/'.join(c['arms'])}。",
                "a": f"双挖掘器共现簇：证据 {len(c['evidence'])} 文档可回源"
                     f"（style_mine_out/*_candidates.json）；底模归因={fam}；"
                     f"样本={samples or '（判例侧证据，无生成样本）'}。",
                "d": "边界：跨模型族词表实现可能不同（本地小模型实测不兼容风险在案）；存疑候人闸核验。",
            },
            "evidence": {
                # 20261010 检定器逮出：曾写死 "{det,lightrag}" 花括号模板——证据指针须可回源，
                # 按来源臂展开为真实文件（分号分隔；检定 R3 逐件核存）
                "artifact": ";".join(
                    _ARM_EVIDENCE_FILE.get(a, "style_mine_out/det_candidates.json")
                    for a in c["arms"]) or "style_mine_out/det_candidates.json",
                "quote": "；".join(top[:5]),
                "recalc": "py -X utf8 style_mine_compare.py && py -X utf8 style_feed.py --dry-run",
            },
        }
        facts = None
        if kind == "style":
            facts = {"tags": c["members"][:14], "cohesion": c["cohesion"],
                     "arms": c["arms"], "evidence_n": len(c["evidence"]),
                     "samples": samples, "sig": sig, "model_family": fam}
        if not dry:
            store.add(entry, actor="ai:style-feed", facts=facts)
        minted.append({"id": eid, "kind": kind, "task": task, "sig": sig,
                       "arms": c["arms"], "size": len(c["members"]), "gen": gen})
        routed[kind] = routed.get(kind, 0) + 1
        if pool_path:
            import candidate_pool as cp
            cp.mark_minted(pool_path, cp.key_of(cp.load_pool(pool_path), c), eid)
        existing_sigs.add(sig)
        existing_bases.setdefault(base, eid)                     # 同批内同名第二件即拦
        existing_text += json.dumps(entry["content"], ensure_ascii=False)
    if recurrence:
        save_json(recurrence_path, recurrence)
    fam = []
    for c in cands:
        b = "s-" + _slug(c["name"])          # 与铸造 id 约定一致：S-{slug}-{sig8}
        # 已有计数含既有件；本批候选撞上 n≥2 的基底=该概念将达第 3 件 → 族谱候选
        if b in existing_bases and base_counts.get(b, 0) >= 2:
            fam.append({"base": b, "n": base_counts[b], "canonical": existing_bases[b],
                        "candidate": c["name"],
                        "hint": f"族谱候选（N6）：概念「{b}」已有 {base_counts[b]} 件，"
                                f"本次再撞=第 {base_counts[b] + 1} 件——人签后可铸家族条"
                                f"并退场各代（N4 三件套）；机器只提案"})
    anti = None
    if anti_path:                                    # 反向飞轮（三态开关；on=标记进报告，拦截仍人闸）
        import embed_cache as _ec                    # 局部导入：ec 在上方仅于 cache_path 分支绑定
        import reverse_flywheel as rf
        anti = rf.run([{"name": m["id"], "members": members_of_minted(store, m["id"])}
                       for m in minted], store, anti_mode, anti_path,
                      cache_path or _ec.DEFAULT_CACHE, embed_fn, source="feed")
        if anti.get("injected") and anti.get("hits"):
            hit_ids = {h.get("candidate") for h in anti["hits"]}
            for m in minted:
                if m.get("id") in hit_ids:
                    m["anti_hit"] = True             # on 档：标本相似命中件在报告面标记（人闸复核入口）
    return {"minted": minted, "skipped": skipped, "routed": routed,
            "anti": anti, "family_candidates": fam,
            "process": process, "recurred": recurred, "n1_merged": went}


def main(argv=None):
    ap = argparse.ArgumentParser(description="涌现→飞轮投喂器（簇→草稿判例）")
    ap.add_argument("--det", default=DEFAULT_DET)
    ap.add_argument("--lr", default=DEFAULT_LR)
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--process-report", default=DEFAULT_PROCESS)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--min-size", type=int, default=4)
    ap.add_argument("--dup-cos", type=float, default=0.90)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-cosine", action="store_true", help="关闭近重复闸（调试用）")
    ap.add_argument("--pool", default=DEFAULT_POOL, help="候选静置池（生产缺省启用）")
    ap.add_argument("--no-pool", action="store_true", help="关闭成熟度闸（调试用）")
    ap.add_argument("--min-rounds", type=int, default=2)
    ap.add_argument("--anti", default=None,
                    help="反向飞轮三态 off|shadow|on（缺省读 ANTI_FLYWHEEL，再缺省 shadow）")
    ap.add_argument("--off", action="store_true", help="开关：关闭投喂")
    a = ap.parse_args(argv)
    if is_disabled(a.off):
        print(f"[style-feed] 已关闭（开关 {_ENV} / --off）——不投喂")
        return 0

    from precedent_gov import PrecedentStore
    import embed_cache as ec
    # 向量探针（20261009）：红线③向量层不降级——近重复闸/N1 需要嵌入；路不通就
    # 响亮拒铸本轮（不是静默跳闸自食），挖掘链其余段（neg_chain/影环/bayes）照跑
    embed_fn = None if a.no_cosine else ec.embed_docs
    if embed_fn is not None:
        try:
            embed_fn(["probe 向量路探针"])
        except Exception as ex:      # noqa: BLE001
            print(f"[style-feed] DENY:EMBED_UNAVAILABLE 向量路不可用"
                  f"（{type(ex).__name__}: {str(ex)[:80]}）——本轮不铸（红线③不降级）；"
                  f"恢复：lms load text-embedding-nomic-embed-text-v1.5 --identifier nomic-embed")
            return 3
    det = load_json(a.det, {"clusters": []})
    lr = load_json(a.lr, {"clusters": []})
    corpus = load_json(a.corpus, {"docs": []})["docs"]
    cands = merge_candidates(det, lr)
    store = PrecedentStore.load(a.store)
    res = feed(cands, store, corpus, a.min_size, a.dry_run,
               cache_path=None if a.no_cosine else a.cache,
               embed_fn=embed_fn,
               dup_cos=a.dup_cos,
               pool_path=None if a.no_pool else a.pool, min_rounds=a.min_rounds,
               anti_path=None if a.anti == "off" else DEFAULT_ANTI, anti_mode=a.anti)
    if not a.dry_run and res["minted"]:
        store.save(a.store)
    save_json(a.report, res)
    if res["process"]:
        save_json(a.process_report, {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "items": res["process"]})
    act = "dry-run" if a.dry_run else "minted"
    print(f"[style-feed] 候选 {len(cands)}（N1合并 {res['n1_merged']}）→ {act} "
          f"{len(res['minted'])} · 分流 {res['routed']} · 跳过 {len(res['skipped'])} · "
          f"process 出口 {len(res['process'])} · recurrence {len(res['recurred'])} · "
          f"族谱候选 {len(res.get('family_candidates') or [])} · "
          f"反例提示 {len((res.get('anti') or {}).get('hits') or [])}"
          f"{'（影子）' if (res.get('anti') or {}).get('mode') == 'shadow' else ''}"
          f"{'（不落库）' if a.dry_run else ' → ' + a.store}")
    for f_ in res.get("family_candidates") or []:
        print(f"  ★ {f_['hint']}")
    for m in res["minted"]:
        print(f"  S·{m['kind']:<10} {m['task']:<4} gen{m.get('gen', '?')} {m['id'][:52]}")
    for p in res["process"]:
        print(f"  ⇥process   {p['name'][:44]}（{p['why']}）")
    for r in res["recurred"]:
        print(f"  ↻recurrence {r['candidate'][:40]} → {r['into'][:36]}（{r['cos']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
