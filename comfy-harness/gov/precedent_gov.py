# -*- coding: utf-8 -*-
"""precedent_gov.py — 判例治理层

═══ 双轴关系声明（20261007 严查补记）═══
本库的信任态轴=gov（draft→verified→approved→deprecated→tombstone），**取代** evocore
lifecycle 的 state 轴（intermediate→longterm→attic）：判例不进 longterm 晋升路径，
approved 即终端信任态；state 字段在本库隐式全程 intermediate（未接线，非缺陷——
双轴并存会制造"同语义分叉"，故显式声明取代关系，禁后续误接）。（工单 W-B · 退场状态机三通道 + 人闸强制）

在 evocore 生命周期原语（promote/attic/tombstone/score）之上加治理卡点：
  - 治理动效（promote/deprecate/tombstone/supersede）一律强制 actor="human:*"，
    缺省身份响亮拒绝（沿仓宪法：执行无权自宣验收——治理位外置）；
  - 退场三通道：deprecate（标记不删，仍可召回但带旗）/ tombstone（退出检索，
    原位保留=审计窗口，evocore 内建 score→0）/ supersede（新条指向旧条+旧条盖墓碑）；
  - 无主防毒：owner 为空的判例永不召回（"WAL 能回滚现场，回滚不了被污染的检索"）；
  - gov_events：store 级 append-only 治理事件流（谁/何时/对谁/做了什么）。
**信任级单向棘轮（L5 裁定 A+C · 20261007）**：draft→verified→approved 只升不降，
无回退 API 且检查8 提交面禁反演——错知识由 `retract`（机器下架旗，退出供血）与人侧
deprecate/relist 处置，**信任经历永不被改写**（AI 不可抹除自身犯错痕迹）。
AI 可 append 草稿判例（add），但一切裁决动效必须人签——本模块只认字符串前缀，
不做身份认证（身份认证是部署层的事，此处守住的是"缺省不猜身份"）。
"""
from __future__ import annotations
import datetime
import glob
import json
import os
from evocore import entry as ec_entry
from evocore import retrieval as ec_ret


class GovernanceRefusal(PermissionError):
    """治理动效缺 human:* 签署时响亮拒绝。消息带 DENY:* 机读前缀（借鉴批）。"""


class StaleWriteError(RuntimeError):
    """写并发冲突（借鉴批 · 引擎线 fencing 语义的 JSON 快照对解）：
    本会话基于 rev=N 读入，磁盘已是 rev>N——拒写防静默覆盖（DENY:STALE_SAVE）。"""


# 状态机合法迁移表（单一事实源——seed_gov_gate 检查8 引用同源，禁双实现漂移，F5）
GOV_TRANSITIONS = {
    "draft": {"verified", "approved"},
    "verified": {"approved"},
    "approved": set(),
}

# ═══ v2 分类分面（20261007 维护者三问后铺齐 · 调研-经验库分类体系件设计）═══
TASKS = ("t2i", "i2v", "t2v", "i2i", "upscale", "audio", "3d", "general")
KINDS = ("prompt", "pipeline", "model", "postproc", "governance")
LEVELS = ("general", "specialized")     # general=域级通用（跨模型族服务）


def _check_taxonomy(entry: dict) -> None:
    """三字段词表校验（在位才检——向后兼容；kind 允许列表=混体双面）。"""
    t = entry.get("task")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        bad_t = [x for x in ts if x not in TASKS]
        if bad_t:
            raise ValueError(f"task 值域外：{bad_t}（∈{TASKS}）")
    kk = entry.get("kind")
    if kk is not None:
        ks = kk if isinstance(kk, list) else [kk]
        bad = [k for k in ks if k not in KINDS]
        if bad:
            raise ValueError(f"kind 值域外：{bad}（∈{KINDS}）")
    lv = entry.get("level")
    if lv is not None and lv not in LEVELS:
        raise ValueError(f"level 值域外：{lv!r}（∈{LEVELS}）")


# severity_if_wrong=判错危害等级（20261007 严肃盘查自纠：原表系引擎 decision.py 语义误抄——
# 引擎值是危害等级(irreversible/redundant)，我误写成"退场路径"且多数路径不存在。现值=实况：
# irreversible_ratchet(信任级单向) / exitable_via_deprecate(可退服务) / terminal_flag(旗不可恢复)
# / audit_preserved(审计窗口)。批三自动降旗按此配阈值。
SEVERITY = {
    "promote": "irreversible_ratchet",      # 人签棘轮单向——错签仅可缓退旗+墓碑，信任级不回滚
    "verify": "exitable_via_deprecate",     # 错验可缓退旗退出服务；信任级同样不回滚
    "deprecate": "terminal_flag",           # 不可恢复（无 restore API 且检查8 禁回退）——单向
    "tombstone": "audit_preserved",         # 检索退出，原位保留=审计窗口
    "supersede": "audit_preserved",
    "amend": "re_amendable",                # 元数据可反向再修（amend 双向）
    "retract": "relistable",                # 机器下架可被人复架（L5 裁定 A+C）
    "relist": "re_retractable",
}


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _require_human(actor: str, action: str, eid: str) -> None:
    if not (isinstance(actor, str) and actor.startswith("human:") and len(actor) > len("human:")):
        raise GovernanceRefusal(
            f"DENY:NO_HUMAN_SIG {action}({eid}) 拒绝：治理动效须 human:名字 签署，收到 {actor!r}——"
            f"AI 执行无权自宣验收（治理位外置，缺省不猜身份）")


def _require_machine(actor: str, action: str, eid: str) -> None:
    if not (isinstance(actor, str) and actor.startswith("machine:") and len(actor) > len("machine:")):
        raise GovernanceRefusal(
            f"DENY:NO_MACHINE_SIG {action}({eid}) 拒绝：下架权仅 machine:* 命名空间"
            f"（人侧退场走 deprecate/relist），收到 {actor!r}")


# ═══ facts 单面规则（20261007 机械化批）：消费面登记表=单一事实源 ═══
# 每条目 facts 键必须同属一个消费面（prompt/pipeline/postproc/model/governance）；
# 跨面知识须拆条（机器数据各归其面）；未知键构造即拒（新键须在此登记=显式注册制）。
FACTS_PLANES = {
    "prompt": {"quality_tags", "negative_guard", "scene_motion_sample",
               "official_prefix_add", "official_negative", "note", "eye_tags"},
    "pipeline": {"cfg", "sampler", "scheduler", "steps", "seed", "portrait_size",
                 "Flux2Scheduler", "UnetLoaderGGUF", "CLIPLoader.wan",
                 "Wan22ImageToVideoLatent", "hires"},
    "postproc": {"face_detailer", "detector_path_note", "hand_detailer", "film_treat"},
    "model": set(),
    "governance": set(),
}


def facts_plane_problems(facts: dict | None) -> list:
    """facts 键面检查 → 问题列表（空=合规）。未知键 + 跨面混键均报。"""
    if not isinstance(facts, dict) or not facts:
        return []
    owner = {}
    unknown = []
    for k in facts:
        hit = [p for p, keys in FACTS_PLANES.items() if k in keys]
        if not hit:
            unknown.append(k)
        else:
            owner[k] = hit[0]
    out = []
    if unknown:
        out.append(f"DENY:PLANE_UNKNOWN 未登记面的键 {sorted(unknown)}（新键须在 FACTS_PLANES 登记面）")
    planes = sorted(set(owner.values()))
    if len(planes) > 1:
        detail = {p: sorted(k for k, v in owner.items() if v == p) for p in planes}
        out.append(f"DENY:PLANE_MIX facts 跨面混键 {detail}——跨面知识须拆条（机器数据各归其面）")
    return out


class PrecedentStore:
    """判例库治理面。entries=evocore 兼容条目；治理字段：owner/gov/deprecated/superseded_by。"""

    def __init__(self, entries: list[dict] | None = None):
        self.entries: list[dict] = list(entries or [])
        self.gov_events: list[dict] = []

    # ---- 写入侧 ----
    def add(self, entry: dict, actor: str = "ai:unknown", facts: dict | None = None) -> dict:
        """追加草稿判例。AI 可写（draft 性质），不进人闸；validate 用 evocore。
        facts=机器可执行槽位（可选）：必须可 JSON 化的 dict——散文教训不可程序消费。"""
        if facts is not None:
            if not isinstance(facts, dict):
                raise ValueError(f"facts 须为 dict，收到 {type(facts).__name__}")
            try:
                json.dumps(facts)
            except (TypeError, ValueError) as err:
                raise ValueError(f"facts 不可 JSON 化（{err}）") from err
            _pp = facts_plane_problems(facts)
            if _pp:
                raise ValueError("；".join(_pp))
            entry["facts"] = facts
        _check_taxonomy(entry)
        ec_entry.validate_entry(entry)
        if any(x.get("id") == entry.get("id") for x in self.entries):
            raise ValueError(f"DENY:DUP_ID 条目 {entry.get('id')!r} 已存在——同 ID 双条会令"
                             f"治理动效二义（promote/退场只命中先入者；改铸新 ID 或先退场旧条）")
        _ch = ec_entry.content_hash(entry)      # L2：内容幂等键（引擎同源宪法级幂等键）
        for x in self.entries:
            if ec_entry.content_hash(x) == _ch:
                raise ValueError(
                    f"DENY:DUP_CONTENT 条目 {entry.get('id')!r} 与既有 {x.get('id')!r} 内容逐字相同"
                    f"（content_hash={_ch[:12]}…）——重铸教训须内容有实质差异；"
                    f"确系同案请用既有件（amend 改元数据 / supersede 出新版）")
        entry.setdefault("owner", "")          # 无主=默认不可召回（防毒缺省）
        entry.setdefault("gov", "draft")
        entry["_added_by"] = actor
        entry["_added_at"] = _now()
        self.entries.append(entry)
        self.gov_events.append({"kind": "add", "id": entry["id"], "actor": actor, "at": entry["_added_at"]})
        return entry

    # ---- 治理动效（全 human:* 闸）----
    def promote(self, eid: str, actor: str, prereg: str | None = None) -> dict:
        """prereg=判据指针（`文件@版本` 或 None——读账即知本决策当时有无判据可依，借鉴批）。"""
        _require_human(actor, "promote", eid)
        e = self._get(eid)
        if e.get("deprecated") or e.get("tombstone"):
            raise GovernanceRefusal(
                f"DENY:BAD_STATE promote({eid}) 拒绝：退场件不可晋升（deprecated={bool(e.get('deprecated'))} "
                f"tombstone={bool(e.get('tombstone'))}）——棘轮单向，须另铸新条走完整生命周期")
        e["gov"] = "approved"
        if not e.get("owner"):
            e["owner"] = actor   # 无主件晋升即落签署人名下（recall 防毒闸看 owner——
                                 # 只改 gov 不落 owner 会让"promote后进召回"永不兑现）
        ev = {"kind": "promote", "id": eid, "actor": actor, "prereg": prereg,
              "severity_if_wrong": SEVERITY["promote"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    # ---- 机器层（批一：draft→verified 机器通道，verified 可被 recall_tier 供血）----
    @staticmethod
    def _default_whitelist() -> list[str]:
        """回执白名单目录：comfy-harness/ 全域 + 工作区调研卷沙盒目录。"""
        gov_dir = os.path.dirname(os.path.abspath(__file__))
        ch = os.path.dirname(gov_dir)
        ws = os.path.dirname(ch)
        return [ch] + sorted(glob.glob(os.path.join(ws, "调研-卷十二-*")))

    def verify(self, eid: str, actor: str, receipt: str,
               whitelist: list[str] | None = None, prereg: str | None = None) -> dict:
        """draft→verified 机器通道（非对称写权的机器侧升格）。
        准入判据硬编码：actor 限 machine:* 命名空间；回执路径归一化后必须落于白名单
        目录内、文件在盘、JSON 内 verdict=咬合——缺一响亮拒绝（伪回执/仓外路径防伪）。"""
        if not (isinstance(actor, str) and actor.startswith("machine:") and len(actor) > len("machine:")):
            raise GovernanceRefusal(
                f"DENY:BAD_ACTOR verify({eid}) 拒绝：机器层只认 machine:* 命名空间，收到 {actor!r}"
                f"——human 走 promote 闸，machine 冒名与越权同罪")
        e = self._get(eid)
        if e.get("gov") != "draft":
            raise GovernanceRefusal(
                f"DENY:BAD_STATE verify({eid}) 拒绝：仅 draft 可机器验证，当前 gov={e.get('gov')!r}")
        rp = os.path.realpath(receipt)
        wl = [os.path.realpath(w) for w in (whitelist if whitelist is not None
                                            else self._default_whitelist())]
        contained = False
        for w in wl:
            try:
                if os.path.commonpath([rp, w]) == w:
                    contained = True
                    break
            except ValueError:
                continue
        if not contained:
            raise ValueError(f"DENY:FAKE_RECEIPT verify({eid}) 拒绝：回执 {rp} 不在白名单目录内（防仓外伪证）")
        if not os.path.isfile(rp):
            raise ValueError(f"DENY:FAKE_RECEIPT verify({eid}) 拒绝：回执文件不在盘 {rp}")
        try:
            with open(rp, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as err:
            raise ValueError(f"DENY:FAKE_RECEIPT verify({eid}) 拒绝：回执不可读（{err}）") from err
        if not (isinstance(data, dict) and data.get("verdict") == "咬合"):
            raise ValueError(f"DENY:FAKE_RECEIPT verify({eid}) 拒绝：回执 verdict≠咬合（机器升格只认承重实证）")
        _artifact = str((e.get("evidence") or {}).get("artifact", ""))
        if os.path.basename(rp) not in _artifact:
            raise ValueError(
                f"DENY:UNBOUND_RECEIPT verify({eid}) 拒绝：回执 {os.path.basename(rp)} 不在条目自述"
                f"证据 artifact 内（{_artifact[:60]!r}）——机器升格的回执必须绑本条目证据"
                f"（20261007 严肃盘查 L3：无绑定则任意咬合回执可验证任意条目）")
        e["gov"] = "verified"
        try:    # 回执路径存仓内相对形式（F4 教训：绝对路径泄本机拓扑且不可移植）
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            receipt_rec = os.path.relpath(rp, _root).replace("\\", "/")
        except ValueError:
            receipt_rec = rp
        ev = {"kind": "verify", "id": eid, "actor": actor, "receipt": receipt_rec,
              "prereg": prereg, "severity_if_wrong": SEVERITY["verify"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    def recall_tier(self, query: str, k: int = 5, now=None, task: str | None = None,
                    kind: str | None = None, level: str | None = None) -> list[dict]:
        """传动轴供血面：verified+approved 双层召回（tier 标注入，approved 优先）。
        与 recall() 的差别：不受 owner 闸（机器 verified 件 owner 天然空——防毒由
        verify 硬判据承担），draft 永不供血。消费侧对无 facts 条目跳过并计数。
        检索解剖修复（0607）：先全池精排再分区再截 k——防 approved 被高名次 verified
        挤出 top-k（原实现 k 先截断后分区，结构性丢件）。"""
        pool = [e for e in self.entries
                if not e.get("tombstone") and not e.get("machine_retracted")
                and e.get("gov") in ("approved", "verified")]
        self.last_filtered = {"excluded_unlabeled": 0}
        if task is not None or kind is not None or level is not None:
            def _match(e):
                if task is not None:
                    et = e.get("task")
                    ets = et if isinstance(et, list) else [et]
                    if task not in ets and "general" not in ets:
                        return False
                if kind is not None:
                    kk = e.get("kind")
                    ks = kk if isinstance(kk, list) else [kk]
                    if kind not in ks:
                        return False
                if level is not None and e.get("level") != level:
                    return False
                return True
            kept = []
            for e in pool:
                needs = {"task": task, "kind": kind, "level": level}
                if any(v is not None and e.get(k) is None for k, v in needs.items()):
                    self.last_filtered["excluded_unlabeled"] += 1   # 无字段件排除+计数（禁静默）
                    continue
                if _match(e):
                    kept.append(e)
            pool = kept
        ranked = ec_ret.retrieve(pool, query, k=len(pool), now=now)    # 全池精排
        approved = [(s, e) for s, e in ranked if e.get("gov") == "approved"]
        verified = [(s, e) for s, e in ranked if e.get("gov") == "verified"]
        out = []
        for s, e in (approved + verified)[:k]:
            e["_tier"] = e["gov"]
            if e.get("deprecated"):
                e["_gov_flag"] = "deprecated"
            out.append((s, e))
        return out

    def pending_matches(self, query: str, now=None) -> dict:
        """草稿匹配披露（0607 检索解剖）：匹配的未晋升件计数+id——查询命中草稿时
        供血面静默为零是盲区，"有可晋升的经验在候"须被看见（人闸推动器）。"""
        drafts = [e for e in self.entries
                  if e.get("gov") == "draft" and not e.get("tombstone")]
        ranked = ec_ret.retrieve(drafts, query, k=len(drafts), now=now)
        return {"count": len(ranked), "ids": [e["id"] for _, e in ranked]}

# 可修元数据面（L6）：内容/证据/id 不可修（知识本体走 supersede；身份不可变）
    AMENDABLE = ("task", "kind", "level", "facts", "importance", "keywords")

    def amend(self, eid: str, fields: dict, reason: str,
              actor: str = "ai:unknown") -> dict:
        """元数据变更入账（L6 · 20261007）：分类三轴/facts/重要度/关键词可修，
        每次修改产 amend 事件带 old→new 全 diff——元数据生命周期从此有审计痕迹。
        content/evidence/id 不可修（DENY:AMEND_FIELD——知识本体变更走 supersede）。"""
        e = self._get(eid)
        bad = [k for k in fields if k not in self.AMENDABLE]
        if bad:
            raise ValueError(
                f"DENY:AMEND_FIELD amend({eid}) 拒绝：不可修字段 {sorted(bad)}"
                f"（可修={list(self.AMENDABLE)}；content/evidence/id 变更走 supersede）")
        if "facts" in fields:
            f = fields["facts"]
            if not isinstance(f, dict):
                raise ValueError(f"amend facts 须 dict，得 {type(f).__name__}")
            try:
                json.dumps(f)
            except (TypeError, ValueError) as err:
                raise ValueError(f"amend facts 不可 JSON 化（{err}）") from err
            _pp = facts_plane_problems(f)
            if _pp:
                raise ValueError("；".join(_pp))
        if "importance" in fields and not isinstance(fields["importance"], int):
            raise ValueError(f"amend importance 须 int，得 {fields['importance']!r}")
        if "keywords" in fields and not isinstance(fields["keywords"], list):
            raise ValueError(f"amend keywords 须 list，得 {fields['keywords']!r}")
        merged = {**e, **fields}
        _check_taxonomy(merged)
        old_vals = {k: e.get(k) for k in fields}
        e.update(fields)
        ev = {"kind": "amend", "id": eid, "actor": actor,
              "reason": str(reason)[:200], "changed": sorted(fields),
              "old": old_vals, "new": {k: fields[k] for k in fields},
              "severity_if_wrong": SEVERITY["amend"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    # ── L5 裁定 A+C：机器下架权（退出供血 ≠ 回退信任；棘轮不破）──
    def retract(self, eid: str, actor: str, reason: str = "", evidence: str = "") -> dict:
        """机器下架：置 machine_retracted 旗——立即退出供血面，gov 主值一字不动。
        触发（批三）：outcome 连败 or 独立复验失败。人需恢复走 relist。"""
        _require_machine(actor, "retract", eid)
        e = self._get(eid)
        if e.get("tombstone"):
            raise GovernanceRefusal(f"DENY:BAD_STATE retract({eid})：墓碑件已退出检索，无需下架")
        e["machine_retracted"] = True
        ev = {"kind": "retract", "id": eid, "actor": actor, "reason": str(reason)[:200],
              "evidence": str(evidence)[:200],
              "severity_if_wrong": SEVERITY["retract"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    def relist(self, eid: str, actor: str, reason: str = "") -> dict:
        """人侧复架：清 machine_retracted 旗（误撤复核后恢复）——仅 human:*。"""
        _require_human(actor, "relist", eid)
        e = self._get(eid)
        if not e.get("machine_retracted"):
            raise GovernanceRefusal(f"DENY:BAD_STATE relist({eid})：非机器下架件，无架可复")
        e["machine_retracted"] = False
        ev = {"kind": "relist", "id": eid, "actor": actor, "reason": str(reason)[:200],
              "severity_if_wrong": SEVERITY["relist"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    def record_outcome(self, eid: str, result: str, context: str,
                       actor: str = "machine:unknown") -> dict:
        """油量计：成败战绩追加到条目内 outcomes（append-only，权威轴不动）。
        域归纳燃料（批四）与自动降旗触发器（批三）的数据源。"""
        if result not in ("success", "failure"):
            raise ValueError(f"result 须为 success|failure，收到 {result!r}")
        e = self._get(eid)
        rec = {"result": result, "context": str(context)[:200], "actor": actor, "at": _now()}
        e.setdefault("outcomes", []).append(rec)
        return rec

    def deprecate(self, eid: str, actor: str, reason: str = "") -> dict:
        """退场通道①：标记不删——仍可召回但检索结果带 deprecated 旗。"""
        _require_human(actor, "deprecate", eid)
        e = self._get(eid)
        e["deprecated"] = True
        ev = {"kind": "deprecate", "id": eid, "actor": actor, "reason": reason[:200],
              "severity_if_wrong": SEVERITY["deprecate"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    def tombstone(self, eid: str, actor: str, reason: str = "") -> dict:
        """退场通道②：退出检索，原位保留（evocore 内建 score→0=审计窗口）。"""
        _require_human(actor, "tombstone", eid)
        e = self._get(eid)
        if e.get("gov") == "approved" and not e.get("deprecated"):
            raise GovernanceRefusal(
                f"DENY:TWO_STAGE tombstone({eid}) 拒绝：approved 判例须先 deprecate 再墓碑（两段式退场，防误删现役知识）")
        from evocore.lifecycle import tombstone as ec_tomb
        ev = ec_tomb(e)
        ev.update({"actor": actor, "reason": reason[:200],
                   "severity_if_wrong": SEVERITY["tombstone"], "at": _now()})
        self.gov_events.append(ev)
        return ev

    def supersede(self, new_entry: dict, old_eid: str, actor: str) -> dict:
        """退场通道③：新条指向旧条 + 旧条盖墓碑（修订闭环，全人签）。"""
        _require_human(actor, "supersede", old_eid)
        old = self._get(old_eid)
        ec_entry.validate_entry(new_entry)
        new_entry["superseded_by"] = None
        new_entry["evidence"] = {**new_entry.get("evidence", {}), "supersedes": old_eid}
        self.add(new_entry, actor=actor)
        old["tombstone"] = True
        ev = {"kind": "supersede", "new_id": new_entry["id"], "old_id": old_eid,
              "actor": actor, "severity_if_wrong": SEVERITY["supersede"], "at": _now()}
        self.gov_events.append(ev)
        return ev

    # ---- 读出侧 ----
    def recall(self, query: str, k: int = 5, now=None) -> list[dict]:
        """治理过滤先行：墓碑/无主不可召回；deprecated 可召回但带旗。
        返回 [(score, entry)]（evocore retrieve 原形状），entry 侧附 _gov_flag。"""
        pool = [e for e in self.entries
                if not e.get("tombstone") and (e.get("owner") or "").startswith("human:")]
        ranked = ec_ret.retrieve(pool, query, k=k, now=now)
        out = []
        for s, e in ranked:
            if e.get("deprecated"):
                e["_gov_flag"] = "deprecated"
            out.append((s, e))
        return out

    def _get(self, eid: str) -> dict:
        for e in self.entries:
            if e.get("id") == eid:
                return e
        raise KeyError(f"判例不存在: {eid}")

    # ---- 持久化（P3-1 审计修复：晋升态/退场态/gov_events 落盘可累积）----
    def save(self, path: str) -> None:
        """全量快照落盘（tmp+os.replace 原子写）+ **CAS 并发保护**（借鉴批）：
        读入时记 _meta.rev；写前校验磁盘 rev 未变，变了=他会话已写——拒写（DENY:STALE_SAVE）
        提示重载，禁静默覆盖（三线并行 JSON 快照的 fencing 对解）。"""
        disk_rev = 0
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    disk_rev = int(json.load(fh).get("_meta", {}).get("rev", 0))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                disk_rev = 0
        if disk_rev != getattr(self, "_rev", 0):
            raise StaleWriteError(
                f"DENY:STALE_SAVE 本会话基于 rev={getattr(self, '_rev', 0)} 读入，"
                f"磁盘已是 rev={disk_rev}——他会话已写，拒覆盖；请重载后重做本次变更")
        clean = [{k: v for k, v in e.items() if k not in ("_tier", "_gov_flag")}
                 for e in self.entries]           # 持久化边界剥离检索瞬时标注（0607 取证发现）
        payload = {"_meta": {"saved_at": _now(), "schema": "precedent-store/1",
                             "rev": getattr(self, "_rev", 0) + 1},
                   "entries": clean, "gov_events": self.gov_events}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        self._rev = getattr(self, "_rev", 0) + 1

    @classmethod
    def load(cls, path: str) -> "PrecedentStore":
        """载入并防毒再验证（盘面不是信任源，fail-closed）：
        - approved 必须有 human 签 promote 事件背书，否则降回 draft+收回 owner（伪造核准不可召回）；
        - tombstone/deprecated 无事件背书→保守态保留（禁销毁式回退）+ 异常响亮留痕；
        - 条目不合 evocore 契约→响亮拒绝整次载入（零静默吞坏）。"""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        store = cls()
        try:
            store._rev = int(data.get("_meta", {}).get("rev", 0))
        except (TypeError, ValueError):
            store._rev = 0
        events = data.get("gov_events", [])
        promoted = {ev.get("id") for ev in events
                    if ev.get("kind") == "promote" and str(ev.get("actor", "")).startswith("human:")}
        human_added = {ev.get("id") for ev in events
                       if ev.get("kind") == "add" and str(ev.get("actor", "")).startswith("human:")}
        human_superseded = {ev.get("new_id") for ev in events
                            if ev.get("kind") == "supersede" and str(ev.get("actor", "")).startswith("human:")}
        human_backed = promoted | human_added | human_superseded   # owner 人属主张的最低背书
        deprecated = {ev.get("id") for ev in events if ev.get("kind") == "deprecate"}
        tombstoned = ({ev.get("id") for ev in events if ev.get("kind") == "tombstone"}
                      | {ev.get("old_id") for ev in events if ev.get("kind") == "supersede"})
        for e in data.get("entries", []):
            for _k in ("_tier", "_gov_flag"):
                e.pop(_k, None)                    # 历史污染件剥离（旧版 save 曾落盘瞬时标注）
            try:
                ec_entry.validate_entry(e)
            except ValueError as err:
                raise ValueError(f"load({path}) 拒绝：条目 {e.get('id')!r} 不合 evocore 契约（{err}）") from err
            e.setdefault("owner", "")     # 与 add() 同款缺省归一（盘面缺字段≠可信任）
            e.setdefault("gov", "draft")
            if e["gov"] == "approved" and e["id"] not in promoted:
                e["gov"] = "draft"
                if str(e["owner"]).startswith("human:"):
                    e["owner"] = ""
                store.gov_events.append({"kind": "load_anomaly", "id": e["id"], "at": _now(),
                                         "note": "盘面 approved 无 human promote 事件背书→降级 draft+收回 owner"})
            elif str(e["owner"]).startswith("human:") and e["id"] not in human_backed:
                e["owner"] = ""
                store.gov_events.append({"kind": "load_anomaly", "id": e["id"], "at": _now(),
                                         "note": "盘面 owner 人属主张无人签事件背书→收回（无主防毒）"})
            elif e.get("tombstone") and e["id"] not in tombstoned:
                store.gov_events.append({"kind": "load_anomaly", "id": e["id"], "at": _now(),
                                         "note": "盘面墓碑无 tombstone/supersede 事件背书→保守保留（禁销毁式回退）"})
            elif e.get("deprecated") and e["id"] not in deprecated:
                store.gov_events.append({"kind": "load_anomaly", "id": e["id"], "at": _now(),
                                         "note": "盘面 deprecated 无 deprecate 事件背书→保守保留"})
            store.entries.append(e)
        store.gov_events.extend(events)
        return store
