# -*- coding: utf-8 -*-
"""test_project_property.py — 投影器合并三律 property suite（件5 · D3 草案移植）

对象：evocore.project_entries。三条性质（VeriFx 对 CvRDT 收敛三前提：
幂等/交换/结合——arXiv:2207.02502 §2.2）：
  P1 重复律（幂等）  ：同流重放两次结果相同；同载荷新行号的重复 append 流尾重投
                       版本集不变（同 (id,hash) 不重影）。
  P2 空转律（幺元）  ：空段与孤儿事件不改变投影。
  P3 顺序律（交换）  ：(a) disjoint id 相邻对换序逐字段不变；
                       (b) 纯 append 流任意重排，补丁集不变。
每条性质配故意违例的 mutant（性质自己也要过负向对照，否则可能是永真式）：
  mutant-shadow    → 违 P1；mutant-phantom → 违 P2；mutant-id-keyed → 违 P3b。
件5 加固判（原 D3 残差探针，投影器加固后翻转为判）：
  流尾重投任一 **append** 行，逐字段不变（强幂等在 append 面成立）。
  注：非 append 事件（tombstone 等）按 id 匹配当前全部版本——后到版本继承标志
  是设计语义，重投时投影可变，不属残差（草案探针范围偏宽，移植时对准登记项原文
  "重复 append 行会复位已累积标志"）。
"""
import itertools
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from evocore import project_entries  # noqa: E402

TS1, TS2, TS3, TS4 = ("2026-09-28T10:00:00", "2026-09-28T11:00:00",
                      "2026-09-28T12:00:00", "2026-09-28T13:00:00")
APPEND_KINDS = ("entry_append", "memory_append")


def row(seq, kind, payload, ts, actor="llm:test"):
    return (seq, ts, actor, kind,
            json.dumps(payload, ensure_ascii=False), "p" * 64, "h" * 64)


def append(eid, chash, content, seq, ts):
    return row(seq, "entry_append",
               {"entry_id": eid, "content_hash": chash, "content": content}, ts)


def _payload(r):
    return json.loads(r[4])


def _entry_id(r):
    return _payload(r).get("entry_id")


def _patch_set(replay, rows):
    """补丁集：每个 append 行声明的 (id, content_hash) 投影后是否可恢复——
    从"声明的补丁"反查投影值，不遍历投影键（键的形状随实现变，值不骗人）。"""
    proj = replay(rows)
    vals = list(proj.values())
    out = []
    for r in rows:
        p = _payload(r)
        chash = p.get("content_hash")
        if chash and any(v.get("id") == p["entry_id"] and v.get("content_hash") == chash
                         for v in vals):
            out.append((p["entry_id"], chash))
    return sorted(out)


def prop_repeat(replay, rows):
    """P1 重复律：(a) 确定性；(b) 版本集幂等——同载荷新行号（真实重试形态）的
    重复 append 流尾重投，版本集不变。"""
    if replay(rows) != replay(rows):
        return False
    base_keys = set(replay(rows))
    top = max(r[0] for r in rows) + 1
    for i, r in enumerate(rows):
        if r[3] in APPEND_KINDS and _payload(r).get("content_hash"):
            dup = (top + i,) + r[1:]
            if set(replay(rows + [dup])) != base_keys:
                return False
    return True


def prop_neutral(replay, rows):
    """P2 空转律：空段不改变结果；孤儿事件也不改变结果。"""
    ghost = row(999, "tombstone", {"entry_id": "ghost"}, TS4)
    return (replay(rows + []) == replay(rows)
            and replay(rows + [ghost]) == replay(rows))


def prop_commute(replay, rows):
    """P3 顺序律：(a) disjoint id 相邻可交换对换序，逐字段不变；
    (b) 纯 append 流（≤5 条）任意重排，补丁集不变。"""
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if _entry_id(a) == _entry_id(b):
            continue
        swapped = rows[:i] + [b, a] + rows[i + 2:]
        if replay(swapped) != replay(rows):
            return False
    appends = [r for r in rows if r[3] in APPEND_KINDS]
    if 1 < len(appends) <= 5:
        base = _patch_set(replay, appends)
        for perm in itertools.permutations(appends):
            if _patch_set(replay, list(perm)) != base:
                return False
    return True


# ---- 负向对照（故意违例重放器）----

def replay_shadow(rows):
    """违 P1：append 键混入行号 (id, hash, seq)——重复投递重影第二版本。"""
    proj = {}
    for _seq, _ts, _actor, kind, payload, _ph, _sh in rows:
        p = json.loads(payload)
        if kind in APPEND_KINDS:
            k = (p["entry_id"], p.get("content_hash") or f"*{_seq}", _seq)  # ← 违例点
            proj[k] = {**p, "id": p["entry_id"]}
        elif kind == "tombstone":
            for k in [k for k in proj if k[0] == p.get("entry_id")]:
                proj[k]["tombstone"] = True
    return proj


def replay_phantom(rows):
    """违 P2：孤儿墓碑物化出幽灵条目。"""
    proj = {}
    for _seq, _ts, _actor, kind, payload, _ph, _sh in rows:
        p = json.loads(payload)
        if kind in APPEND_KINDS:
            proj[(p["entry_id"], p.get("content_hash") or f"*{_seq}")] = {
                **p, "id": p["entry_id"]}
        elif kind == "tombstone":
            hit = [k for k in proj if k[0] == p.get("entry_id")]
            if hit:
                for k in hit:
                    proj[k]["tombstone"] = True
            else:
                proj[(p["entry_id"], "*phantom")] = {"id": p["entry_id"],
                                                     "phantom": True}   # ← 违例点
    return proj


def replay_id_keyed(rows):
    """违 P3b：按 id 单键投影（R4-e 修复前旧病）——同 id 异值后者静默覆盖前者。"""
    proj = {}
    for _seq, _ts, _actor, kind, payload, _ph, _sh in rows:
        p = json.loads(payload)
        if kind in APPEND_KINDS:
            proj[p["entry_id"]] = {**p, "id": p["entry_id"]}   # ← 违例点
    return proj


def check_base_hash(rows):
    """base_hash 机检（协议件草案 §B 可执行版）：声明 base_hash 的 append 行，
    其 base 必须在更早行的 content_hash 集合里（合并基先于合并者入账）。"""
    seen, bad = set(), []
    for i, r in enumerate(rows):
        kind, payload = r[3], json.loads(r[4])
        if kind in APPEND_KINDS:
            bh = payload.get("base_hash")
            if bh is not None and bh not in seen:
                bad.append(i)              # 无锚写入
            if payload.get("content_hash"):
                seen.add(payload["content_hash"])
    return bad


def base_rows():
    return [
        append("e1", "aaa", "旧值", 1, TS1),
        append("e2", "bbb", "另一条", 2, TS2),
        row(3, "tombstone", {"entry_id": "e1", "note": "n"}, TS3),
        append("e1", "ccc", "新值（同 id 异值=discordant 候选）", 4, TS4),
    ]


class TestProjectProperty(unittest.TestCase):
    def test_p123_hold_on_real_projector(self):
        """三律在真实投影器上成立。"""
        rows = base_rows()
        self.assertTrue(prop_repeat(project_entries, rows), "P1 重复律破")
        self.assertTrue(prop_neutral(project_entries, rows), "P2 空转律破")
        self.assertTrue(prop_commute(project_entries, rows), "P3 顺序律破")

    def test_mutants_each_hit_own_property(self):
        """负向对照：每个 mutant 恰好打红自己声明的性质（性质非永真式）。"""
        rows = base_rows()
        for replay, target in ((replay_shadow, ["P1"]),
                               (replay_phantom, ["P2"]),
                               (replay_id_keyed, ["P3"])):
            hits = ([name for name, prop in (("P1", prop_repeat), ("P2", prop_neutral),
                                             ("P3", prop_commute))
                     if not prop(replay, rows)])
            self.assertEqual(hits, target, f"{replay.__name__} 命中 {hits}≠{target}")

    def test_base_hash_anchor_check(self):
        """base_hash 机检：有锚过、无锚红。"""
        def based(chash, base, seq, ts, content="新值"):
            head = append("e1", chash, content, seq, ts)[:4]
            tail = append("e1", chash, content, seq, ts)[5:]
            payload = json.dumps({"entry_id": "e1", "content_hash": chash,
                                  "content": content, "base_hash": base},
                                 ensure_ascii=False)
            return head + (payload,) + tail

        good = [append("e1", "aaa", "旧值", 1, TS1), based("ccc", "aaa", 2, TS2)]
        bad = [append("e1", "aaa", "旧值", 1, TS1), based("ccc", "zzz", 2, TS2)]
        self.assertEqual(check_base_hash(good), [], "有锚写入误报")
        self.assertEqual(check_base_hash(bad), [1], "无锚写入漏报")

    def test_strong_idempotence_append_tail_redelivery(self):
        """件5 加固判（原残差探针翻转）：流尾重投任一 append 行，逐字段不变——
        重复投递不得复位该版本已累积的 tombstone/corrected 标志。"""
        rows = base_rows()
        base = project_entries(rows)
        for r in rows:
            if r[3] not in APPEND_KINDS:
                continue
            self.assertEqual(project_entries(rows + [r]), base,
                             f"流尾重投 kind={r[3]} 改变投影（强幂等破）")
        # 同载荷新行号（真实重试形态）同样逐字段不变
        top = max(r[0] for r in rows) + 1
        for i, r in enumerate(rows):
            if r[3] not in APPEND_KINDS:
                continue
            dup = (top + i,) + r[1:]
            self.assertEqual(project_entries(rows + [dup]), base,
                             "同载荷新行号重投改变投影（强幂等破）")

    def test_stream_tail_reappend_keeps_flags(self):
        """件5 流尾重投专测：append→correction→tombstone→同键重投（新 seq）——
        corrected/tombstone 标志必须保持（旧病灶：重投复位，投影器覆盖旧字典）。"""
        rows = [
            append("e1", "aaa", "旧值", 1, TS1),
            row(2, "memory_correction", {"entry_id": "e1", "reason": "笔误", "by": "h"}, TS2),
            row(3, "tombstone", {"entry_id": "e1"}, TS3),
            append("e1", "aaa", "旧值", 4, TS4),   # 流尾重投同一内容（同键新 seq）
        ]
        proj = project_entries(rows)
        e = proj[("e1", "aaa")]
        self.assertTrue(e.get("corrected"), "重投复位 corrected（残差未修）")
        self.assertEqual(e.get("correction_reason"), "笔误")
        self.assertTrue(e.get("tombstone"), "重投复位 tombstone（残差未修）")

    def test_late_version_inherits_tombstone_by_design(self):
        """设计语义登记：非 append 事件按 id 匹配当前全部版本——尾部重投 tombstone
        命中后到版本属预期（不属件5 残差；草案探针范围偏宽的勘注）。"""
        rows = base_rows()
        tail_tomb = row(5, "tombstone", {"entry_id": "e1"}, TS4)
        proj = project_entries(rows + [tail_tomb])
        self.assertTrue(proj[("e1", "ccc")].get("tombstone"),
                        "后到版本应继承 tombstone（id 匹配全部当前版本）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
