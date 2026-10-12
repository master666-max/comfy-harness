# -*- coding: utf-8 -*-
"""entry.py — 条目形状规范（S3/T1 加法式增补：宿主写入口的构造校验面）

设计依据：《S3设计-中库规范件全量落地架构》§2.4/§四 T1——"条目构造校验"按切刀原则
（对**任意条目集合**成立）属演化内核域，故进 evocore；**本模块为纯加法**——不改动本包
现有五件一字。`STATES` 自 `.lifecycle` 引入（lifecycle 为定义处，本件为使用处，单一事实源）。
"""
from __future__ import annotations

import hashlib
import json

from .lifecycle import STATES

TYPES = ("episodic", "semantic", "procedural")


def validate_entry(e: dict) -> None:
    """条目构造校验（非法条目建不出来，P7）。非法即 raise ValueError（fail-closed）。

    规则与融合形态（evo-seat §1 `validate_entry`）**同语义**：id/content 非空 ·
    type ∈ TYPES（默认 semantic）· state ∈ STATES（默认 intermediate）· importance 非负整数。
    实现为**单一来源**（融合件与中库 CLI 共用同一套规则文本，不复制）。
    **v3 增补（20260929 排期 2-3b 配套 · D11 写侧分发）**：content 可为 **dict 嵌套段序**
    {"c","a","d"}（c 结论段必填非空；a 论证/d 细节可选字符串）——此时 content_hash 走
    v3 三叶 Merkle（见 content_hash）。"""
    for k in ("id", "content"):
        if not str(e.get(k, "")).strip():
            raise ValueError(f"条目缺 {k}")
    content = e.get("content")
    if isinstance(content, dict):
        c = content.get("c", "")
        if not isinstance(c, str) or not c.strip():
            raise ValueError("v3 条目结论段 c 必填且非空")
        for seg in ("a", "d"):
            if not isinstance(content.get(seg, ""), str):
                raise ValueError(f"v3 段 {seg} 须字符串或缺省：{content.get(seg)!r}")
    if e.get("type", "semantic") not in TYPES:
        raise ValueError(f"type 非法：{e.get('type')!r}")
    if e.get("state", "intermediate") not in STATES:
        raise ValueError(f"state 非法：{e.get('state')!r}")
    imp = e.get("importance", 0)
    if not isinstance(imp, int) or imp < 0:
        raise ValueError(f"importance 须非负整数：{imp!r}")


def _seg_canon(v) -> str:
    """段归一（**与 project.py `_seg_canon` 同规**：ensure_ascii=False, sort_keys=True,
    紧凑分隔符）。同规两处实现系架构约束——分层契约禁止 entry←project 互引；
    一致性由 `test_entry_v3_dispatch.py` 跨形态逐字节对拍钉死（不靠注释声称）。"""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def seg_hash(v) -> str:
    """段哈希 h_x = sha256(canonical(x))，64 hex（D11 §二②；与 project.seg_hash 同规）。"""
    return hashlib.sha256(_seg_canon(v).encode("utf-8")).hexdigest()


def content_hash_v3(content: dict) -> str:
    """v3 嵌套段序 3 叶 Merkle：sha256("v3|"+h_c+"|"+h_a+"|"+h_d)，64 hex（D11 §二②；
    **与 project.content_hash_v3 同规**，跨形态对拍钉死）。content 须 dict {"c","a","d"}
    （c 必填非空）。前缀视图只携 {c, h_a, h_d} 即可离线验证本承诺（project.verify_prefix_entry）。
    """
    if not isinstance(content, dict):
        raise ValueError(f"content_hash_v3 只受理 dict 形态（v3），得 {type(content).__name__}")
    c = content.get("c", "")
    if not isinstance(c, str) or not c.strip():
        raise ValueError("v3 条目结论段 c 必填且非空")
    for seg in ("a", "d"):
        if not isinstance(content.get(seg, ""), str):
            raise ValueError(f"v3 段 {seg} 须字符串或缺省：{content.get(seg)!r}")
    return seg_hash("v3|" + seg_hash(c) + "|" + seg_hash(content.get("a", ""))
                    + "|" + seg_hash(content.get("d", "")))


def content_hash(e: dict) -> str:
    """条目内容指纹（幂等键，**64 hex**）——P3/D7 统一（20260924）。

    归一规则（**跨写入口 + 跨形态唯一来源**，SPEC §G"两个入口，一道门"）：
    排除表示形态/投影字段（id/entry_id/content_hash/state/last_used_at/**created_at**；
    state 由 importance 经 route 确定、created_at/last_used_at 由投影补齐——皆非内容），
    keywords 字符串↔词表归一为有序词表，canonical JSON 后取 sha256 全宽。
    **v3 写侧分发（20260929 · D11 排期配套，0.6.0 版本记录登记的"未随本闸"项）**：
    content 为 **dict 嵌套段序** {"c","a","d"} 时 → 走 v3 三叶 Merkle（content_hash_v3）——
    前缀视图 {c, h_a, h_d} 即可离线验证（人读视图密码学绑定，账本零改动）；
    content 为字符串（v2 存量与默认形态）→ 走既有 v2 全 body 哈希，一字未动
    （老库不迁移、跨写入口归一不变——`test_content_hash_divergence.py` 保持绿）。
    **去重比较＝比较时重归一**：对既有条目的投影重算本指纹再比——老库存储的旧 16 hex
    指纹不参与比较、也永不回改（append-only），故无破坏性、无迁移。
    历史：v1=16 hex 截断（S3-S4/T1 起跨写入口归一）；v2=本版（全宽+created_at 入排除集，
    关闭 `evocore-D7`）；v3=嵌套段序分发（D11）。
    """
    content = e.get("content")
    if isinstance(content, dict):
        return content_hash_v3(content)
    body = {k: v for k, v in e.items()
            if k not in ("id", "entry_id", "content_hash", "state", "last_used_at",
                         "created_at")}
    if isinstance(body.get("keywords"), str):
        body["keywords"] = sorted(body["keywords"].split())
    elif isinstance(body.get("keywords"), list):
        body["keywords"] = sorted(body["keywords"])
    canon = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
