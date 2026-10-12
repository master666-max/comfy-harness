# -*- coding: utf-8 -*-
"""engine/retrieval.py — memsys 检索层（五参数精排内核 + 召回接口）
（evocore 平移版 · S1 · 源 memsys/engine/retrieval.py @ b19c9a4）
v3.9 `_rank_entries` 的语义迁移（纯函数，独立可测）；
W4 双跑门未过前，与 v3.9 输出的逐位对齐是待验收标注（README 构建状态）。
召回接口 recall() 预留向量层挂载点（触发器：≥100 分层实测掉带外才装）。
"""
from __future__ import annotations
import datetime
import re
from .tunables import DEFAULTS, decay_mult

_TOKEN = re.compile(r"[\w\u4e00-\u9fff]+")
_SECONDS_PER_DAY = 86400.0   # S1v2/T2：原裸值收编（单位换算常量，非可调机制参数）

def _tokens(text):
    # CJK bigram + 西文单词（与 v3.9 CJK-bigram 分词语义对齐；逐位对齐待 W4 双跑门）
    out = []
    for w in _TOKEN.findall(text or ""):
        if re.fullmatch(r"[\u4e00-\u9fff]+", w):
            if len(w) == 1: out.append(w)
            else: out += [w[i:i+2] for i in range(len(w)-1)]
        else:
            out.append(w.lower())
    return out

def _age_days(entry, now):
    created = entry.get("last_used_at") or entry.get("created_at")
    if not created:
        return 0.0   # 无时间戳=无年龄项（缺失≠损坏；与融合形态 evo_seat 同语义——P2-2 统一批补齐）
    try:
        import datetime
        t = datetime.datetime.fromisoformat(str(created).replace("Z", "+00:00").replace("+00:00", ""))
        return max(0.0, (now - t).total_seconds() / _SECONDS_PER_DAY)
    except Exception:
        return 36500.0   # bad-ts 按 100 年龄降权（P2-2：坏时间戳不得置顶；v3.9 置顶语义废止）

def score(entry, query, tunables=DEFAULTS, now=None) -> float:
    """五参数线性打分（v3.9 语义）。now=None 用当前时间（naive datetime）。"""
    if now is None: now = datetime.datetime.now()
    q = set(_tokens(query))
    c = set(_tokens(str(entry.get("content", ""))))
    kw = set(_tokens(" ".join(entry.get("keywords", []) or [])))
    kw_hit = len(q & kw)
    content_hit = len(q & c)
    if tunables.filter_zero and kw_hit == 0 and content_hit == 0:
        return 0.0
    s = tunables.w_kw * kw_hit + tunables.w_content * content_hit
    s += tunables.w_imp * float(entry.get("importance", 0) or 0)
    age_d = _age_days(entry, now)
    mult = decay_mult(tunables, entry.get("type", "semantic"))   # S1v2/T1：单一实现（原内联 dict 去重）
    s -= tunables.w_age * age_d * mult   # 类型曲线无条件生效（procedural=0 → age 项恒 0）
    if entry.get("tombstone"): s = 0.0   # 墓碑退出检索（公理保留）
    return round(s, 4)

def recall(entries, query, tunables=DEFAULTS, now=None):
    """召回接口：现役=词面全量扫（entries 可迭代）；向量层=触发器后挂此处。"""
    return list(entries)   # 现役：词面全量；向量召回按触发器（≥100 分层实测）后才装配

def retrieve(entries, query, k=5, tunables=DEFAULTS, now=None, recall_fn=recall):
    """retrieve = recall(召回) → score(五参数精排) → 确定性平局破序（W-5 语义）。"""
    cands = recall_fn(entries, query, tunables=tunables, now=now)
    scored = [(score(e, query, tunables, now), e) for e in cands]
    scored = [x for x in scored if x[0] > 0]
    ranked = sorted(scored, key=lambda kv: (-kv[0], kv[1].get("id", "")))
    return ranked[:k]
