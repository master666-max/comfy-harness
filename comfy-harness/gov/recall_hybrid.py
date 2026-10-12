# -*- coding: utf-8 -*-
"""recall_hybrid.py — 混合召回（工单 P7 · V2）：词法 ∪ 向量，RRF 融合

背景（实弹）：纯词法召回在跨语言/口语化/意图化查询上失效率 43%（"胶片颗粒质感"/
"怎么让手指不糊"零命中）。本件在**同一供血池**上加一路向量排序，RRF 并入：

  lexical = evocore.retrieve（现役五参数精排，保留其行为与年龄/命中项）
  vector  = embed_cache.nearest（nomic 嵌入 cosine，brute-force）
  fused   = RRF: score(d) = Σ_i 1/(K + rank_i(d))，K=60（标准配参）

**边界（工单红线）**：
  - 只服务传进来的池（判例库侧=approved/verified 双池，draft 照旧不供血）；
  - 读侧可用性优先：嵌入缓存/端点在查询时不可用 → **响亮告警 + 词法兜底**（与写侧
    "不降级"区别：写侧拒写防污染，读侧兜底保可用——差异在 AGENTS 原则注记）；
  - 结果形状 (score, entry) 元组与 evocore 一致，治理层三调用点零形状改造。

用法：rank(pool, query, k, now=None, cache_path=DEFAULT_CACHE) -> [(rrf_score, entry)]
"""
from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import embed_cache as ec                          # noqa: E402
from evocore import retrieval as ec_ret           # noqa: E402

RRF_K = 60                                        # RRF 标准常数
VEC_DOWN_WINDOW = 60.0                            # 向量路熔断窗口（秒）：失败一次，窗口内不再重试
_VEC_DOWN_UNTIL = 0.0                             # 熔断截止时刻（0=未熔断）


def _lexical(pool, query, now):
    return ec_ret.retrieve(pool, query, k=len(pool), now=now)


def rank(pool, query, k=5, now=None, cache_path: str | None = None,
         embed_fn=None) -> list:
    """RRF 融合排序。向量路不可用 → 响亮告警 + 词法兜底（读侧可用性）。

    向量排名=**池内相对位次**（实测教训：全缓存 81 条排名的噪声件——cosine 0.44
    档——会借"第 12 名"混进 RRF，把词法真命中挤出 top；池内重排后噪声件只能压
    池内其它噪声件）。"""
    lex = _lexical(pool, query, now)
    lex_rank = {e["id"]: i for i, (_s, e) in enumerate(lex)}
    for e in pool:
        lex_rank.setdefault(e["id"], len(pool) + 1)          # 词法零分件=末档（不丢）
    vec_rank = {}
    cache_path = cache_path or ec.DEFAULT_CACHE
    global _VEC_DOWN_UNTIL
    use_live = embed_fn is None          # 熔断只针对 **live 端点**；注入式 embed_fn（测试/自备编码器）不受影响
    if use_live and time.time() < _VEC_DOWN_UNTIL:
        pass                                # 熔断窗口内：跳过失败尝试（仍词法兜底；进窗时已告警）
    else:
        try:
            cache = ec.load_cache(cache_path)
            if cache.get("items"):
                fn = embed_fn or ec.embed_query
                qv = fn([query])[0]
                pool_ids = {e["id"] for e in pool}
                hits = [(s, eid) for s, eid in ec.nearest(cache, qv, k=len(cache["items"]))
                        if eid in pool_ids]                 # 池外件不入 RRF（防噪声借名次）
                for i, (_s, eid) in enumerate(hits):
                    vec_rank[eid] = i
        except Exception as ex:                               # noqa: BLE001 —— 响亮不静默
            if use_live:
                _VEC_DOWN_UNTIL = time.time() + VEC_DOWN_WINDOW   # 熔断：窗口内不再重试（自愈式）
            print(f"[recall_hybrid] 向量路不可用（{type(ex).__name__}: {ex}）——"
                  f"词法兜底；{int(VEC_DOWN_WINDOW)}s 熔断窗口内不再重试（读侧可用性优先）",
                  file=sys.stderr)
    fused = []
    by_id = {e["id"]: e for e in pool}
    for eid, e in by_id.items():
        s = 0.0
        if eid in lex_rank:
            s += 1.0 / (RRF_K + lex_rank[eid] + 1)
        if eid in vec_rank:
            s += 1.0 / (RRF_K + vec_rank[eid] + 1)
        if s > 0:
            fused.append((s, e))
    fused.sort(key=lambda x: (-x[0], str(x[1].get("id"))))
    return fused[:k]
