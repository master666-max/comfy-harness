# -*- coding: utf-8 -*-
"""project.py — 事件流→条目集投影（S4/T1 加法式增补：**单一投影器**）

设计依据：《S4设计-L2-0服务件全量落地架构》§2.3 裁定①——server 与 kb CLI 必须共用
同一投影器（"两个投影器必然漂移"属 D7/D8 同类隐患，事前处置）。本模块为纯加法：
不改动本包其余模块一字。

投影语义（S5/T1 对齐：与融合件 §7 `_load_entries` **同语义**——形态分离、语义对齐）：
  entry_append → 建条（含 content_hash；id=entry_id；**created_at=payload 显式值，否则账本行 ts**）
  promotion    → state=longterm
  retrieve_hit → last_used_at=账本行 ts（**D7 登记项**：中库/服务形态按语义实现持久化；
                 融合件 evo-seat 的 touch 仅内存态——触发器=融合件版本周期对齐）
  tombstone    → tombstone=True（退出检索，原位保留——公理 F）
"""
from __future__ import annotations

import hashlib
import json

# 形态词汇**两认**（W2-N3 · 20260923 开工批）：同一语义在两种形态里有两套 kind 名——
#   融合形态（`evo_seat.py` §7 `_load_entries`）与 memsys 宿主桥（`bridge.record_append`）
#     写 `memory_append` / `memory_retrieve_hit`；
#   重装形态（中库 `kb.py` CLI / L2 `server.py`）写 `entry_append` / `retrieve_hit`。
# 只认一套的后果：把投影器指向另一套写出的账本时**静默投影为空**——而"未知 kind 忽略"
# 本是前向兼容特性，于是「没投出东西」与「账本本来就空」在输出上同形（第一定理）。
# 两认不新增任何行为：语义同一，只是不再因形态词汇差异而丢账。
APPEND_KINDS = ("entry_append", "memory_append")
HIT_KINDS = ("retrieve_hit", "memory_retrieve_hit")


def project_entries(rows) -> dict:
    """把账本行序列投影为条目集 {(entry_id, content_hash): entry}。

    **投影键=(id, content_hash) 显式消歧（R4-e · 裁定索引 #31 · 统合 P1-3）**：
    同 id 异内容双双入链时**双投影可见**（负向对照=必须双可见，见 evocore/tests）——
    此前按 id 单键投影，后者静默覆盖前者（"链上仍在、检索看不见"，第一定理同族）。

    payload 缺 content_hash（老库存量）→ 键的第二段以 `*<seq>` 兜底（行序号，永不碰撞）：
    不重算指纹、不引包内件（保住纯投影契约 S1v2 §2.3），链上两条就投两条——身份以账为准。

    后续事件（promotion/retrieve_hit/tombstone）载荷只带裸 entry_id——按 **id 部分匹配**
    应用到该 id 的**全部**投影版本（消歧后一个 id 可挂多版本；载荷形状不变=不走 S2 重生成）。

    rows 形态=账本 `.rows()` 的产出：
      (seq, ts, actor, kind, payload, prev_hash, self_hash)
    未知 kind 忽略（前向兼容：账本可含宿主扩展 kind）。
    """
    proj = {}
    for _seq, ts, _actor, kind, payload, _ph, _sh in rows:
        p = json.loads(payload)
        if kind in APPEND_KINDS:
            key = (p["entry_id"], p.get("content_hash") or f"*{_seq}")
            if key in proj:
                # 件5 强幂等加固：同键重投（同 id+同指纹=同一内容重复投递，典型=
                # 流尾重叠/重试重放）不得复位已累积标志（corrected/tombstone/
                # state/last_used_at）——首见字段为准，setdefault 只补缺不覆盖。
                e = proj[key]
                for bk, bv in p.items():
                    if bk != "entry_id":
                        e.setdefault(bk, bv)
                continue        # created_at 首见已定（显式值优先，否则首发行 ts）
            e = {**p, "id": p["entry_id"]}
            if not e.get("created_at"):
                e["created_at"] = ts      # S5/T1：时间原点=账本行 ts（payload 显式值优先）
            proj[key] = e
        elif kind == "memory_correction":
            # 卷三-2 更正分录（复式记账更正传统）：语义化撤销——原条目不删（公理 F），
            # 打 corrected 标记供读侧拒绝/降权；payload {entry_id, reason, by}；
            # 按 entry_id 匹配全部投影版本（同 id 多版本一并标注）；孤儿前向兼容忽略。
            for k in [k for k in proj if k[0] == p.get("entry_id")]:
                proj[k]["corrected"] = True
                proj[k]["correction_reason"] = p.get("reason", "")
        elif kind == "promotion" or kind in HIT_KINDS or kind == "tombstone":
            for k in [k for k in proj if k[0] == p.get("entry_id")]:
                if kind == "promotion":
                    proj[k]["state"] = "longterm"
                elif kind in HIT_KINDS:
                    proj[k]["last_used_at"] = ts
                else:
                    proj[k]["tombstone"] = True
        elif kind == "supersede":
            # supersede 事件接线（20260929 分支1·框架 · 排期件3 · 主线"已知未接线"清账）：
            # R4 的 status=="superseded" 分支此前无事件可置（不可达死代码）——本映射使其
            # 在账本流可达：{entry_id|node_id, reason, by?} 按 id 部分匹配全部投影版本。
            # 语义=D6 关闭动词表：supersede 作用于**账本条目流**（decision_tree.supersede
            # 作用于树节点——两套语义，本映射只管前者）；下游 R4 收缩（slim/human 视图
            # 出列）由此自动生效。
            pid = p.get("entry_id") or p.get("node_id")
            for k in [k for k in proj if k[0] == pid]:
                proj[k]["status"] = "superseded"
                proj[k]["supersede_reason"] = p.get("reason", "")
    return proj


def project_ids(proj) -> set:
    """id 维度视图（R4-e 下游配套）：存在性检查/按 id 取条目用——投影键消歧后，
    「条目在不在」这类问题问的是 id 维度，不再等价于 `id in proj`。"""
    return {k[0] for k in proj}


OVERRIDE_KIND = "human_override"


def project_overrides(rows) -> list:
    """人侧终裁事件投影（S8-4 · 20260923 开工批）：`[(自身 seq, payload)]`。

    与融合形态 `evo_seat.py` §7 `_overrides` **同语义**（形态分离、语义对齐）。
    终裁不删历史——被终裁的判定事件仍在账；本函数只把终裁取出来供读侧标注。
    payload 冻结（S8工单 S8-4）：`{target_seq?, decision, rationale, cap_ref?}`。
    """
    out = []
    for seq, _ts, _actor, kind, payload, _ph, _sh in rows:
        if kind == OVERRIDE_KIND:
            out.append((seq, json.loads(payload)))
    return out


def project_sources(rows) -> dict:
    """来源视图投影（S8-6 最小版）：`{actor: {events, by_kind, last_ts}}`。

    只回答一个问题——「**谁的 Agent 在喂什么**」：按 actor 聚合事件数、按 kind 的分布、
    最近一次时间。**不判可信度、不计算被采纳率/污染率**（那属完整版，归 L2-2；
    见 `裁定索引.md` §一 第 13 行）。

    **与工单字面的一处偏离（登记在此）**：S8工单 S8-6 写的是「按 `actor` 前缀聚合」，
    本实现按**完整 actor** 聚合。理由：L2 的 actor 规约是 `llm:<平台>:<grant_id>`，
    截第一段会把 `llm:alpha:g1` 与 `llm:beta:g2` 并进同一个 `llm` 桶——
    而那恰恰是本视图唯一要区分的东西（本批实跑服务件时抓到：两身份各写 1 条，
    截前缀后显示成"llm 2 条"，视图形同失效）。要家族级汇总，对键再切一次即可。
    与融合形态 `evo_seat.py` §7 `_source_stats` 同语义（跨形态一致性由
    `build/tests/test_sources_view.py` 钉，不靠注释声称）。
    """
    out: dict = {}
    for _seq, ts, actor, kind, _payload, _ph, _sh in rows:
        key = actor or "(空 actor)"
        s = out.setdefault(key, {"events": 0, "by_kind": {}, "last_ts": ""})
        s["events"] += 1
        s["by_kind"][kind] = s["by_kind"].get(kind, 0) + 1
        if ts > s["last_ts"]:
            s["last_ts"] = ts
    return out


def override_marks(rows) -> dict:
    """把终裁回溯到条目：`payload.target_seq` → 该 seq 的判定留痕里的 `entries[]`。

    返回 `{entry_id: [(终裁自身 seq, 被终裁的判定 seq, decision, rationale)]}`；
    无 `target_seq` 的方针性终裁不入此表。与融合件 `_override_marks` 同语义。
    """
    materialized = [(seq, ts, actor, kind, payload, ph, sh)
                    for seq, ts, actor, kind, payload, ph, sh in rows]
    adj = {}
    for seq, _ts, _actor, kind, payload, _ph, _sh in materialized:
        if kind == "memory_adjudicate":
            adj[seq] = json.loads(payload).get("entries", [])
    marks = {}
    for ov_seq, p in project_overrides(materialized):
        tgt = p.get("target_seq")
        if tgt is None:
            continue
        try:
            tseq = int(tgt)
        except (TypeError, ValueError):
            continue   # 畸形 target_seq：跳过而非中断整表
        for eid in adj.get(tseq, []):
            marks.setdefault(eid, []).append((ov_seq, tseq, p.get("decision"), p.get("rationale")))
    return marks


# ═══ 投影族（D11 · 排期 4-6 · 20260928 走闸） ═══
# 同一事件流的多个确定性视图：slim 标记管"谁进人读集"，嵌套段序管"每条目读到多深"
# （D11 §〇一行结论）。三件全部由既有哈希链与投影机器导出，账本 schema 零破坏；
# 视图=投影不是第二真相源（公理 A2）：可从账本重放、不可写、投影键三视图逐字相同。
# 装配登记：本段为纯加法——project_entries 既有语义一字未动（件 5 强幂等加固原样保留）。
# import 偏离登记：任务书"不新增 import"，本段新增 `import hashlib`（标准库，分层契约
# 白名单内——3 叶 Merkle 必须算 sha256，这是契约矩阵保持绿的唯一实现路径）。
SLIM_MARK_KIND = "slim_mark"
# 新账本事件 kind。payload 冻结（D11 §三）：{node_id, subset, action: "mark"|"unmark", by, reason}
# slim 是账本事件不是节点字段——条目 append-only 永不回改（公理 A2）；
# 投影按 (node_id, subset) 末次事件定去留（R3 增长只走人：新节点永不自动入 slim）。
SLIM_DEFAULT_SUBSET = "human_default"


def _seg_canon(v) -> str:
    """段归一：与 entry.content_hash 同一归一规则（ensure_ascii=False, sort_keys=True,
    紧凑分隔符——D11 §二②）。entry 不引包内件（契约：project.py 零包内依赖），
    规则同源由跨形态指纹测试盯防。"""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def seg_hash(v) -> str:
    """段哈希 h_x = sha256(canonical(x))，64 hex（D11 §二②）。"""
    return hashlib.sha256(_seg_canon(v).encode("utf-8")).hexdigest()


def content_hash_v3(content) -> str:
    """v3 嵌套段序 3 叶 Merkle（段序即规范序）：sha256("v3|"+h_c+"|"+h_a+"|"+h_d)，
    64 hex 与 v2 输出同形。content 须为 dict 形态 {"c","a","d"}（c 结论段必填非空，
    a 论证段/d 细节段缺省 ""，空段哈希=sha256(canon(""))）。
    配套登记：entry.content_hash 的 v3 分发（D11 §三"配套增量"）未随本闸实装——
    写侧仍在后批；本函数是投影侧的同一规范（验证两步的 ② 用）。"""
    if not isinstance(content, dict):
        raise ValueError(f"content_hash_v3 只受理 dict 形态（v3），得 {type(content).__name__}")
    c = content.get("c", "")
    if not isinstance(c, str) or not c.strip():
        raise ValueError("v3 条目结论段 c 必填且非空（结论一句话强制存在——Q1 E2 对药）")
    for k in ("a", "d"):
        if not isinstance(content.get(k, ""), str):
            raise ValueError(f"v3 段 {k} 须字符串或缺省，得 {type(content.get(k)).__name__}")
    return seg_hash("v3|" + seg_hash(c) + "|" + seg_hash(content.get("a", ""))
                    + "|" + seg_hash(content.get("d", "")))


def _prefix_entry(e: dict) -> dict:
    """depth=1 前缀视图单条目（D11 §二②）：{id, content_hash, c, h_a, h_d, v3}——
    **不携带 h_c**（验证者自己算）与 a/d 明文（h_a/h_d 只是承诺）。
    v3=dict 形态（v2 存量扁平字符串永不回改：h_a/h_d=None，密码学前缀绑定是 v3 专属）。
    content_hash 取**账本 payload 承诺值**（不重算——S1v2 §2.3 纯投影契约）；
    payload 缺 content_hash 的老库条目（*seq 兜底键）无承诺可绑 → None。"""
    content = e.get("content")
    if isinstance(content, dict):
        c = content.get("c", "")
        if not isinstance(c, str) or not c.strip():
            raise ValueError(f"v3 条目 {e.get('id')!r} 结论段 c 必填且非空（投影侧 fail-closed）")
        return {"id": e.get("id"), "content_hash": e.get("content_hash"),
                "c": c, "h_a": seg_hash(content.get("a", "")),
                "h_d": seg_hash(content.get("d", "")), "v3": True}
    return {"id": e.get("id"), "content_hash": e.get("content_hash"),
            "c": content if isinstance(content, str) else "",
            "h_a": None, "h_d": None, "v3": False}


def verify_prefix_entry(pv: dict) -> str | None:
    """前缀视图离线验证两步（D11 §二②）：①sha256(canonical(c))==h_c（派生）；
    ②sha256("v3|"+h_c+"|"+h_a+"|"+h_d)==content_hash（绑定）。两步全过 ⟹ c 确是账本
    承诺条目的真结论段，且 a/d 内容未披露（3 叶 Merkle 包含证明）。
    返回 None=过；违例理由串（调用方聚合为 V4 清单）。v2 条目（v3=False）只查 c 非空。"""
    if not pv.get("v3"):
        if not str(pv.get("c", "")).strip():
            return f"V4 前缀绑定：{pv.get('id')!r} 结论段为空（条目至少有一层被读）"
        return None
    if not pv.get("content_hash"):
        return f"V4 前缀绑定：{pv.get('id')!r} 无账本承诺值（payload 缺 content_hash）"
    h_c = seg_hash(pv.get("c", ""))
    rebound = seg_hash("v3|" + h_c + "|" + pv.get("h_a", "") + "|" + pv.get("h_d", ""))
    if rebound != pv["content_hash"]:
        return (f"V4 前缀绑定：{pv.get('id')!r} 人读文本不绑定账本承诺"
                f"（重算 {rebound[:12]}… ≠ 承诺 {pv['content_hash'][:12]}…）")
    return None


def project_slim(rows, subset: str = SLIM_DEFAULT_SUBSET) -> set:
    """slim 视图（D11 §三）：指定子集的 {(entry_id, content_hash)} 键集。
    slim_mark 末次事件定去留（R3）；superseded/tombstoned/corrected 投影时自动出列
    （R4，GO 做不到的免费收缩——D6 关闭动词：tombstone/correct=条目级标志，
    supersede=节点级 status）。R1 子集性：slim 节点必须是投影既有节点，标记不加新内容。
    纯函数：同 rows 同 subset 同输出——slim 永不过期。"""
    proj = project_entries(rows)
    marks: dict = {}
    for _seq, _ts, _actor, kind, payload, _ph, _sh in rows:
        if kind != SLIM_MARK_KIND:
            continue
        p = json.loads(payload)
        if p.get("action") == "mark":
            marks[(p.get("node_id"), p.get("subset"))] = True
        elif p.get("action") == "unmark":
            marks[(p.get("node_id"), p.get("subset"))] = False   # 末次事件定去留
    out = set()
    for key, e in proj.items():
        if not marks.get((key[0], subset), False):
            continue                        # R3：从未标记/末次为 unmark → 不入人读集
        if e.get("tombstone") or e.get("corrected") or e.get("status") == "superseded":
            continue                        # R4：关闭动词自动出列（带病节点不留人读视图）
        out.add(key)
    return out


def _seq_head(rows) -> dict:
    """视图输出头（V1 同源检查用）：所吃账本区间 {seq_start, seq_end}（空流=0/0）。"""
    return {"seq_start": rows[0][0] if rows else 0, "seq_end": rows[-1][0] if rows else 0}


def project_human_view(rows, subset: str = SLIM_DEFAULT_SUBSET, depth: int = 1) -> dict:
    """人读视图（D11 §三）：project_slim × 嵌套段序截断。
    返回 {"seq_start":…, "seq_end":…, "entries": {键: 前缀视图+corrected+last_used_at}}，
    depth=1 只导出 c 段（②草案；其余档位未定义即拒——fail-closed）。
    R4 收缩在 project_slim 内生效：corrected 条目不以干净形态出现（V5 的机械前提）。
    纯函数：同 rows 同 subset 同输出——视图可从账本重放（公理 A2，PM 纪律）。"""
    if depth != 1:
        raise ValueError(f"人读视图仅实装 depth=1（D11 §二②单档），得 depth={depth}")
    materialized = list(rows)
    head = _seq_head(materialized)
    slim = project_slim(materialized, subset)
    proj = project_entries(materialized)
    entries = {}
    for key in sorted(slim):
        e = proj[key]
        pv = _prefix_entry(e)
        pv["corrected"] = bool(e.get("corrected"))
        pv["last_used_at"] = e.get("last_used_at")
        entries[key] = pv
    return {**head, "entries": entries}


def project_agent_view(rows) -> dict:
    """AI 视图（D11 §三）：= project_entries(rows) 直通（全量条目集，不另写投影）。
    显式存在的意义：把"投影族"立为家族名目——agent-view 不是第二种投影，是投影本身；
    与 human-view 的差集=slim 策展，交集=映射校验对象（V1–V5）。"""
    materialized = list(rows)
    return {**_seq_head(materialized), "entries": project_entries(materialized)}


def verify_view_mapping(rows, human: dict, agent: dict) -> list:
    """V1–V5 五检查点（D11 §二③），返回违规清单（空=全过；退出码 0/1/2 语义与
    claim_gates 一致，由调用方映射：0 全过/1 有违例/2 装置错=输入形态不合法）。
    挂会话收尾——"人只读清单不读全量"。"""
    bad: list = []
    try:
        h_ent, a_ent = human["entries"], agent["entries"]
    except (TypeError, KeyError) as ex:
        return [f"V0 装置错：视图缺 entries 头（{ex!r}）——先对装置再谈映射"]
    if (human.get("seq_start"), human.get("seq_end")) != (agent.get("seq_start"),
                                                          agent.get("seq_end")):
        bad.append(f"V1 同源：两视图 seq 区间不等"
                   f"（human={human.get('seq_start')}..{human.get('seq_end')}, "
                   f"agent={agent.get('seq_start')}..{agent.get('seq_end')}）——先对账再谈视图")
        return bad                       # 异源输入上后续检查无意义（D11 §二③ V1）
    # V2 子集性：human 键集 ⊆ agent 键集（键=(id, content_hash) 精确相等）——抓幽灵条目
    for k in sorted(set(h_ent) - set(a_ent)):
        bad.append(f"V2 子集性：human 键 {k} 不在 agent 视图（幽灵条目）")
    # V3 slim 存在性：slim 键必在 agent 视图且无关闭标志（R4 收缩生效证明）
    for k in sorted(project_slim(rows)):
        e = a_ent.get(k)
        if e is None:
            bad.append(f"V3 slim 存在性：slim 键 {k} 不在 agent 视图")
        elif e.get("tombstone") or e.get("corrected") or e.get("status") == "superseded":
            bad.append(f"V3 slim 存在性：slim 键 {k} 带关闭标志仍在集（R4 收缩失灵）")
    # V4 前缀绑定：human 每条目过两步验证 + 越层泄漏（human 文本不得出现在 a/d 段——ISAD(G) 2.2）
    for k in sorted(h_ent):
        msg = verify_prefix_entry(h_ent[k])
        if msg:
            bad.append(msg)
        content = a_ent.get(k, {}).get("content")
        if isinstance(content, dict):
            leaked = [seg for seg in ("a", "d")
                      if content.get(seg) and content.get(seg) == h_ent[k].get("c")]
            if leaked:
                bad.append(f"V4 越层泄漏：{k[0]} 的 c 段与 {'/'.join(leaked)} 段全同"
                           "（粗层复制细层——ISAD(G) 2.2/2.4 红旗）")
    # V5 更正同步：corrected 条目不得以干净形态出现在 human 视图；两视图标志必须同真
    for k in sorted(set(a_ent) & set(h_ent)):
        if a_ent[k].get("corrected") and not h_ent[k].get("corrected"):
            bad.append(f"V5 更正同步：corrected 键 {k} 在 human 视图以干净形态出现")
        if h_ent[k].get("corrected") and not a_ent[k].get("corrected"):
            bad.append(f"V5 更正同步：human 键 {k} 的 corrected 标在 agent 视图缺失")
    return bad
