# -*- coding: utf-8 -*-
"""precedent_gov.py — 判例治理层（工单 W-B · 退场状态机三通道 + 人闸强制）

在 evocore 生命周期原语（promote/attic/tombstone/score）之上加治理卡点：
  - 治理动效（promote/deprecate/tombstone/supersede）一律强制 actor="human:*"，
    缺省身份响亮拒绝（沿仓宪法：执行无权自宣验收——治理位外置）；
  - 退场三通道：deprecate（标记不删，仍可召回但带旗）/ tombstone（退出检索，
    原位保留=审计窗口，evocore 内建 score→0）/ supersede（新条指向旧条+旧条盖墓碑）；
  - 无主防毒：owner 为空的判例永不召回（"WAL 能回滚现场，回滚不了被污染的检索"）；
  - gov_events：store 级 append-only 治理事件流（谁/何时/对谁/做了什么）。
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
    """治理动效缺 human:* 签署时响亮拒绝。"""


# 状态机合法迁移表（单一事实源——seed_gov_gate 检查8 引用同源，禁双实现漂移，F5）
GOV_TRANSITIONS = {
    "draft": {"verified", "approved"},
    "verified": {"approved"},
    "approved": set(),
}


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _require_human(actor: str, action: str, eid: str) -> None:
    if not (isinstance(actor, str) and actor.startswith("human:") and len(actor) > len("human:")):
        raise GovernanceRefusal(
            f"{action}({eid}) 拒绝：治理动效须 human:名字 签署，收到 {actor!r}——"
            f"AI 执行无权自宣验收（治理位外置，缺省不猜身份）")


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
            entry["facts"] = facts
        ec_entry.validate_entry(entry)
        entry.setdefault("owner", "")          # 无主=默认不可召回（防毒缺省）
        entry.setdefault("gov", "draft")
        entry["_added_by"] = actor
        entry["_added_at"] = _now()
        self.entries.append(entry)
        self.gov_events.append({"kind": "add", "id": entry["id"], "actor": actor, "at": entry["_added_at"]})
        return entry

    # ---- 治理动效（全 human:* 闸）----
    def promote(self, eid: str, actor: str) -> dict:
        _require_human(actor, "promote", eid)
        e = self._get(eid)
        e["gov"] = "approved"
        if not e.get("owner"):
            e["owner"] = actor   # 无主件晋升即落签署人名下（recall 防毒闸看 owner——
                                 # 只改 gov 不落 owner 会让"promote后进召回"永不兑现）
        ev = {"kind": "promote", "id": eid, "actor": actor, "at": _now()}
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
               whitelist: list[str] | None = None) -> dict:
        """draft→verified 机器通道（非对称写权的机器侧升格）。
        准入判据硬编码：actor 限 machine:* 命名空间；回执路径归一化后必须落于白名单
        目录内、文件在盘、JSON 内 verdict=咬合——缺一响亮拒绝（伪回执/仓外路径防伪）。"""
        if not (isinstance(actor, str) and actor.startswith("machine:") and len(actor) > len("machine:")):
            raise GovernanceRefusal(
                f"verify({eid}) 拒绝：机器层只认 machine:* 命名空间，收到 {actor!r}"
                f"——human 走 promote 闸，machine 冒名与越权同罪")
        e = self._get(eid)
        if e.get("gov") != "draft":
            raise GovernanceRefusal(
                f"verify({eid}) 拒绝：仅 draft 可机器验证，当前 gov={e.get('gov')!r}")
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
            raise ValueError(f"verify({eid}) 拒绝：回执 {rp} 不在白名单目录内（防仓外伪证）")
        if not os.path.isfile(rp):
            raise ValueError(f"verify({eid}) 拒绝：回执文件不在盘 {rp}")
        try:
            with open(rp, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as err:
            raise ValueError(f"verify({eid}) 拒绝：回执不可读（{err}）") from err
        if not (isinstance(data, dict) and data.get("verdict") == "咬合"):
            raise ValueError(f"verify({eid}) 拒绝：回执 verdict≠咬合（机器升格只认承重实证）")
        e["gov"] = "verified"
        try:    # 回执路径存仓内相对形式（F4 教训：绝对路径泄本机拓扑且不可移植）
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            receipt_rec = os.path.relpath(rp, _root).replace("\\", "/")
        except ValueError:
            receipt_rec = rp
        ev = {"kind": "verify", "id": eid, "actor": actor, "receipt": receipt_rec, "at": _now()}
        self.gov_events.append(ev)
        return ev

    def recall_tier(self, query: str, k: int = 5, now=None) -> list[dict]:
        """传动轴供血面：verified+approved 双层召回（tier 标注入，approved 优先）。
        与 recall() 的差别：不受 owner 闸（机器 verified 件 owner 天然空——防毒由
        verify 硬判据承担），draft 永不供血。消费侧对无 facts 条目跳过并计数。"""
        pool = [e for e in self.entries
                if not e.get("tombstone") and e.get("gov") in ("approved", "verified")]
        ranked = ec_ret.retrieve(pool, query, k=k, now=now)
        approved = [(s, e) for s, e in ranked if e.get("gov") == "approved"]
        verified = [(s, e) for s, e in ranked if e.get("gov") == "verified"]
        out = []
        for s, e in approved + verified:
            e["_tier"] = e["gov"]
            if e.get("deprecated"):
                e["_gov_flag"] = "deprecated"
            out.append((s, e))
        return out

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
        ev = {"kind": "deprecate", "id": eid, "actor": actor, "reason": reason[:200], "at": _now()}
        self.gov_events.append(ev)
        return ev

    def tombstone(self, eid: str, actor: str, reason: str = "") -> dict:
        """退场通道②：退出检索，原位保留（evocore 内建 score→0=审计窗口）。"""
        _require_human(actor, "tombstone", eid)
        e = self._get(eid)
        if e.get("gov") == "approved" and not e.get("deprecated"):
            raise GovernanceRefusal(
                f"tombstone({eid}) 拒绝：approved 判例须先 deprecate 再墓碑（两段式退场，防误删现役知识）")
        from evocore.lifecycle import tombstone as ec_tomb
        ev = ec_tomb(e)
        ev.update({"actor": actor, "reason": reason[:200], "at": _now()})
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
              "actor": actor, "at": _now()}
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
        """全量快照落盘（tmp+os.replace 原子写）。快照≠信任源：载入侧再验证。"""
        payload = {"_meta": {"saved_at": _now(), "schema": "precedent-store/1"},
                   "entries": self.entries, "gov_events": self.gov_events}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str) -> "PrecedentStore":
        """载入并防毒再验证（盘面不是信任源，fail-closed）：
        - approved 必须有 human 签 promote 事件背书，否则降回 draft+收回 owner（伪造核准不可召回）；
        - tombstone/deprecated 无事件背书→保守态保留（禁销毁式回退）+ 异常响亮留痕；
        - 条目不合 evocore 契约→响亮拒绝整次载入（零静默吞坏）。"""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        store = cls()
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
