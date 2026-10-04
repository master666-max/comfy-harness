# -*- coding: utf-8 -*-
"""tunables.py — memsys 类型化常量（v4.3 §五）
（evocore 平移版 · S1 · 源 memsys/tunables.py @ b19c9a4）
B1 修正版：不用虚 Annotated（那是元数据，import 不崩）——用 frozen dataclass
+ __post_init__ 构造时校验，非法值在**构造时**抛错（P7 结构优先于检查）。
改参数 = 改此处 + PR + eval 门（v4.3 §十七 自由域）。
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Tunables:
    # 检索五参数（正典：与 v3.9 语义迁移对齐；W4 双跑门未过前标注"迁移语义"）
    w_kw: float = 3.0            # 关键词命中权重  (>0)
    w_content: float = 1.5       # 内容重合权重    (>0)
    w_imp: float = 0.2082        # 重要度权重      (>0, W-9 正典值)
    w_age: float = 0.1           # 年龄罚分系数    (>0; R2 起改 last_used 起算)
    filter_zero: int = 1         # 零命中过滤      (0|1; v3.10/M3 正典=1)
    # 生命周期
    promote_importance_min: int = 7   # 晋升阈值（v3.9 现行为 L996；R5 起改决策层）
    age_days_full_penalty: float = 40.0   # 病灶划界参数（X5 结论：40 天→−4 分）
    # 类型衰减（type 曲线：乘数，1.0=标准）
    decay_mult_episodic: float = 2.0    # 情景：快衰减
    decay_mult_semantic: float = 1.0    # 语义：标准
    decay_mult_procedural: float = 0.0  # 程序：零衰减
    # 决策层
    decision_defer_rate_max: float = 0.40   # defer 率超此触发复审（金标判据 §四）
    irreversible_error_rate_max: float = 0.05  # 接管判据（金标判据 §二）
    rationale_max: int = 200            # 留痕 rationale/reason 截断长（S1v2/T2：原双处魔法数收编）

    def __post_init__(self):
        errs = []
        for name in ("w_kw", "w_content", "w_imp", "w_age"):
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and v > 0):
                errs.append(f"{name}={v!r} 必须 >0")
        if self.filter_zero not in (0, 1): errs.append(f"filter_zero={self.filter_zero!r} 必须 0|1")
        if self.promote_importance_min < 0: errs.append("promote_importance_min 必须 ≥0")
        for name in ("decay_mult_episodic", "decay_mult_semantic", "decay_mult_procedural"):
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and v >= 0):
                errs.append(f"{name}={v!r} 必须 ≥0")
        for name in ("decision_defer_rate_max", "irreversible_error_rate_max"):
            v = getattr(self, name)
            if not (0 < v < 1): errs.append(f"{name}={v!r} 必须 ∈(0,1)")
        if self.rationale_max < 1: errs.append(f"rationale_max={self.rationale_max!r} 必须 ≥1")
        if errs:
            raise ValueError("Tunables 非法：" + "; ".join(errs))

DEFAULTS = Tunables()

def decay_mult(tunables, entry_type: str) -> float:
    """类型衰减乘数**唯一实现**（S1v2/T1 去重）：retrieval.score 与 lifecycle.decay_multiplier 共用。
    未知类型按 semantic 档（1.0）——与 v3.9 迁移语义逐位一致（行为对拍为证）。"""
    return {"episodic": tunables.decay_mult_episodic,
            "semantic": tunables.decay_mult_semantic,
            "procedural": tunables.decay_mult_procedural}.get(entry_type, 1.0)
