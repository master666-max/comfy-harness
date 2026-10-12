# -*- coding: utf-8 -*-
"""wired_assembly.py — 传动轴消费者（批一-2 · 工单-经验飞轮优化统合-20261005 §二-1-2）

把 PrecedentStore.recall_tier 的供血接到布线决策上：
  命中带 facts 槽位的判例 → 机器事实注入（facts_source="recall"）
  命中但无 facts       → 跳过并计数（skipped_no_facts，散文教训不可消费的活体注脚）
  零供血               → 朴素先验回退（facts_source="naive_fallback"，禁静默）
"""
from __future__ import annotations
import json

# 通用件词（消歧义主体判定停用表）：这些是组件/流程词，不是教训主体——
# 共享 "vae" 的 flux2 教训与 wan22 教训仍是跨主体（测试钉死）。
GENERIC_TERMS = frozenset({"vae", "布线", "验收", "schema", "qa", "视频", "风格"})

# v0.34 时代朴素先验（e1 NAIVE 同源）：sched.model/sched.denoise 在 0.38 活体不存在
NAIVE_PRIOR = {
    "suspect_keys": ["model", "denoise"],
    "inputs": {"model": None, "steps": 20, "width": 1024, "height": 1024, "denoise": 1.0},
}


def expand_query(query: str, alias_map: dict) -> str:
    """wiki 重定向页惯例：别名→扩展词追加进查询（词表漂移防线）。
    大小写不敏感匹配；已含扩展词与累计结果双重去重；无别名原样返回。"""
    tokens = query.split()
    seen = {t.lower() for t in tokens}
    extra = []
    for alias, terms in (alias_map or {}).items():
        if alias.lower() in seen:
            for t in terms:
                if t.lower() not in seen:
                    seen.add(t.lower())          # 累计去重: 多别名共词不再重复
                    extra.append(t)
    return query + (" " + " ".join(extra) if extra else "")


def disambiguation_hint(hits: list):
    """wiki 消歧义页惯例：同查询命中跨主体条目 → 域标提示。
    主体判定=关键词集去掉通用件词（GENERIC_TERMS）后是否相交——
    vae/布线/验收 是组件词不是主体词，共享组件词不算同域（测试钉死此语义）。"""
    kw_sets = [(set(e.get("keywords") or []) - GENERIC_TERMS) for _, e in hits]
    if len(kw_sets) < 2 or any(not k for k in kw_sets):
        return None                                    # 主体词被通用词掏空的条目不参与判定
    for i in range(len(kw_sets)):
        for j in range(i + 1, len(kw_sets)):
            if kw_sets[i] & kw_sets[j]:
                return None                            # 主体相交=同域，零提示
    domains = ["/".join(sorted(k)[:2]) for k in kw_sets]
    ids = [e.get("id") for _, e in hits]
    return (f"消歧义：本查询命中跨主体条目 {' vs '.join(ids)}（主体: {' vs '.join(domains)}）"
            "——建议加域前缀重查")


def load_alias_map(path: str) -> dict:
    """D-1 裁定：别名数据独立文件（数据与治理分离），缺席=空映射。"""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("aliases", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _scope_of(e: dict, scope_map: dict | None):
    """判例适用域解析：facts.applies_to.model 优先，注册表补位（已晋升件免改内容）。
    返回允许模型列表；无域信息 → None（老行为直供，向后兼容）。"""
    facts = e.get("facts") or {}
    ap = facts.get("applies_to")
    if isinstance(ap, dict) and ap.get("model"):
        return list(ap["model"])
    return (scope_map or {}).get(e.get("id"))


def extract_wiring(query: str, hits: list, target_model: str | None = None,
                   scope_map: dict | None = None) -> dict:
    """从 recall_tier 供血提取布线事实。hits=[(score, entry)]（evocore 原形状）。
    target_model 给定且判例有适用域时，域外件跳过并计数（skipped_out_of_scope）——
    管线专项闸（NoobAI 教训不注 flux 图）；无域信息件照旧供血（向后兼容）。"""
    facts: dict = {}
    skipped = 0
    out_of_scope = 0
    for _score, e in hits:
        if target_model is not None:
            scope = _scope_of(e, scope_map)
            if scope:
                t = str(target_model).lower()
                if not any(str(m).lower() in t or t in str(m).lower() for m in scope):
                    out_of_scope += 1              # 域外跳过+计数（禁静默）
                    continue
        f = e.get("facts")
        if isinstance(f, dict) and f:
            for k, v in f.items():
                if k != "applies_to":              # 域元数据不进布线面
                    facts[k] = v
        else:
            skipped += 1                        # 散文教训跳过并计数——披露不静默
    if facts:
        return {"query": query, "facts_source": "recall", "facts": facts,
                "skipped_no_facts": skipped, "skipped_out_of_scope": out_of_scope}
    return {"query": query, "facts_source": "naive_fallback", "facts": {},
            "skipped_no_facts": skipped, "skipped_out_of_scope": out_of_scope,
            "naive_prior": NAIVE_PRIOR}
