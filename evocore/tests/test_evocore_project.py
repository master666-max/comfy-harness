# -*- coding: utf-8 -*-
"""test_evocore_project.py — 事件流投影测试（S4/T1；`evocore/project.py`）

守的契约：
  ① entry_append 建条（**投影键=(entry_id, content_hash)**·R4-e 消歧，裁定索引 #31）；
  ② promotion → state=longterm（按 id 部分匹配，应用到该 id 的全部投影版本）；
  ③ retrieve_hit → last_used_at=**账本行 ts**（D7 登记项：持久化按语义实现）；
  ④ tombstone → tombstone=True（退出检索但原位保留——公理 F）；
  ⑤ 未知 kind / 指向不存在条目的事件 → 忽略（前向兼容，不崩）；
  ⑥ **形态词汇两认**（W2-N3）：`entry_append`/`retrieve_hit`（重装形态）与
     `memory_append`/`memory_retrieve_hit`（融合形态 + memsys 宿主桥）投影等价；
  ⑦ **R4-e 负向对照**：同 id 双内容必须**双可见**——此前按 id 单键投影，后者静默
     覆盖前者（"链上仍在、检索看不见"，第一定理同族）；
  ⑧ payload 无 content_hash（老库存量）→ 行序号兜底键，不炸、不串、不引包内件。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from evocore import project_entries, project_ids  # noqa: E402

TS1, TS2, TS3, TS4 = ("2026-09-23T10:00:00", "2026-09-23T11:00:00",
                      "2026-09-23T12:00:00", "2026-09-23T13:00:00")


def row(seq, kind, payload, ts):
    return (seq, ts, "llm:test", kind, __import__("json").dumps(payload, ensure_ascii=False), "p" * 64, "h" * 64)


def by_id(proj, eid):
    """id 维度取版本列表（消歧后一个 id 可挂多版本）。"""
    return [v for k, v in proj.items() if k[0] == eid]


class TestProject(unittest.TestCase):
    def test_append_creates_entry(self):
        """① 建条：投影键=(entry_id, content_hash)，id=entry_id 随行。"""
        proj = project_entries([row(1, "entry_append",
                                    {"entry_id": "e1", "content": "玻璃", "content_hash": "abc"}, TS1)])
        self.assertEqual(proj[("e1", "abc")]["id"], "e1")
        self.assertEqual(proj[("e1", "abc")]["content"], "玻璃")
        self.assertEqual(project_ids(proj), {"e1"})

    def test_created_at_stamped_from_ledger_ts(self):
        """①b S5/T1：payload 无 created_at → 盖账本行 ts（时间原点，老化机制的前提）。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1)])
        self.assertEqual(by_id(proj, "e1")[0]["created_at"], TS1)
        proj2 = project_entries([row(1, "entry_append",
                                      {"entry_id": "e2", "content": "x", "created_at": "2020-01-01T00:00:00"}, TS1)])
        self.assertEqual(by_id(proj2, "e2")[0]["created_at"], "2020-01-01T00:00:00")  # 显式值优先

    def test_promotion_sets_state(self):
        """② 晋升改态。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1),
                                row(2, "promotion", {"entry_id": "e1"}, TS2)])
        self.assertEqual(by_id(proj, "e1")[0]["state"], "longterm")

    def test_retrieve_hit_sets_last_used_from_ledger_ts(self):
        """③ 命中刷新 last_used=账本 ts（D7：持久化语义）。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1),
                                row(2, "retrieve_hit", {"entry_id": "e1", "query": "x"}, TS3)])
        self.assertEqual(by_id(proj, "e1")[0]["last_used_at"], TS3)

    def test_tombstone_marks_kept(self):
        """④ 墓碑：标记 True 且条目**仍在投影**（原位保留）。"""
        proj = project_entries([row(1, "entry_append", {"entry_id": "e1", "content": "x"}, TS1),
                                row(2, "tombstone", {"entry_id": "e1", "note": "n"}, TS4)])
        self.assertTrue(by_id(proj, "e1")[0]["tombstone"])
        self.assertEqual(project_ids(proj), {"e1"})

    def test_unknown_and_orphan_ignored(self):
        """⑤ 未知 kind 与孤儿事件（指向不存在条目）→ 忽略不崩。"""
        proj = project_entries([row(1, "host_extended_kind", {"whatever": 1}, TS1),
                                row(2, "promotion", {"entry_id": "ghost"}, TS2),
                                row(3, "retrieve_hit", {"entry_id": "ghost"}, TS3),
                                row(4, "tombstone", {"entry_id": "ghost"}, TS4)])
        self.assertEqual(proj, {})

    def test_cross_form_kind_vocabulary_equivalent(self):
        """⑥ W2-N3 跨形态对拍：重装形态词汇（entry_append/retrieve_hit）与融合形态·宿主桥
        词汇（memory_append/memory_retrieve_hit）投影结果**逐字段相同**。
        负向意义：改前把投影器指向 memory_* 账本会得到 {}——与"空账本"同形，无从察觉。"""
        payload = {"entry_id": "e1", "content": "玻璃", "content_hash": "abc"}
        heavy = project_entries([row(1, "entry_append", payload, TS1),
                                 row(2, "retrieve_hit", {"entry_id": "e1"}, TS3)])
        fused = project_entries([row(1, "memory_append", payload, TS1),
                                 row(2, "memory_retrieve_hit", {"entry_id": "e1"}, TS3)])
        self.assertEqual(heavy, fused)
        self.assertEqual(by_id(fused, "e1")[0]["last_used_at"], TS3)
        self.assertNotEqual(fused, {})            # 哨兵不裸：确认真的投出了东西

    def test_bridge_style_payload_projects(self):
        """⑥b 宿主桥真实 payload 形状（`bridge.record_append`：entry_id/content_hash/type/state，
        **无 content**）也能建条——否则指向 memsys 账本时静默投影为空。"""
        proj = project_entries([row(1, "memory_append", {
            "entry_id": "m1", "content_hash": "h" * 64,
            "type": "semantic", "state": "intermediate"}, TS1)])
        self.assertEqual(proj[("m1", "h" * 64)]["id"], "m1")
        self.assertEqual(proj[("m1", "h" * 64)]["state"], "intermediate")
        self.assertEqual(proj[("m1", "h" * 64)]["created_at"], TS1)

    # ---------- R4-e 消歧（统合 P1-3 · 裁定索引 #31） ----------

    def test_same_id_two_contents_both_visible(self):
        """⑦ 负向对照（裁定原文）：同 id 双内容必须**双可见**。"""
        proj = project_entries([
            row(1, "entry_append", {"entry_id": "e1", "content": "旧值", "content_hash": "aaa"}, TS1),
            row(2, "entry_append", {"entry_id": "e1", "content": "新值", "content_hash": "bbb"}, TS2)])
        self.assertEqual(len(proj), 2, "同 id 异内容被投影吞并——R4-e 缺口复现")
        self.assertEqual(project_ids(proj), {"e1"})
        self.assertEqual({e["content"] for e in proj.values()}, {"旧值", "新值"})

    def test_same_id_same_content_single_key(self):
        """⑦b 同 id 同内容（同指纹）→ 同键，幂等不重影。"""
        proj = project_entries([
            row(1, "entry_append", {"entry_id": "e1", "content": "x", "content_hash": "aaa"}, TS1),
            row(2, "entry_append", {"entry_id": "e1", "content": "x", "content_hash": "aaa"}, TS2)])
        self.assertEqual(len(proj), 1)

    def test_events_apply_to_all_versions_of_id(self):
        """②b/④b 事件载荷只带裸 entry_id → 按 id 部分匹配应用到该 id **全部版本**
        （载荷形状不变=不走 S2 重生成；语义=对"这个 id"的处置覆盖它的每个投影版本）。"""
        proj = project_entries([
            row(1, "entry_append", {"entry_id": "e1", "content": "旧", "content_hash": "aaa"}, TS1),
            row(2, "entry_append", {"entry_id": "e1", "content": "新", "content_hash": "bbb"}, TS2),
            row(3, "tombstone", {"entry_id": "e1", "note": "n"}, TS3),
            row(4, "retrieve_hit", {"entry_id": "e1", "query": "q"}, TS4)])
        vs = by_id(proj, "e1")
        self.assertEqual(len(vs), 2)
        self.assertTrue(all(v["tombstone"] for v in vs))
        self.assertTrue(all(v["last_used_at"] == TS4 for v in vs))

    def test_correction_marks_all_versions_of_id(self):
        """卷三-2 更正分录：memory_correction 按 entry_id 标注全部版本（原条目保留）。"""
        proj = project_entries([
            row(1, "entry_append", {"entry_id": "e1", "content": "旧", "content_hash": "aaa"}, TS1),
            row(2, "entry_append", {"entry_id": "e1", "content": "新", "content_hash": "bbb"}, TS2),
            row(3, "memory_correction", {"entry_id": "e1", "reason": "出处证伪", "by": "human:治理位"}, TS3)])
        vs = by_id(proj, "e1")
        self.assertEqual(len(vs), 2, "更正不得删原条目（公理 F）")
        self.assertTrue(all(v["corrected"] for v in vs))
        self.assertTrue(all("出处证伪" in v["correction_reason"] for v in vs))

    def test_correction_orphan_ignored(self):
        """卷三-2 孤儿更正（entry_id 无对应 append）→ 前向兼容忽略。"""
        proj = project_entries([
            row(1, "memory_correction", {"entry_id": "ghost", "reason": "r"}, TS1)])
        self.assertEqual(proj, {})

    def test_missing_content_hash_rowseq_fallback_not_colliding(self):
        """⑧ 老库存量（payload 无 content_hash）→ 键第二段=行序号兜底（不重算指纹、
        不引包内件——纯投影契约 S1v2 §2.3）；同 id 异内容仍不混，链上两条就投两条。"""
        proj = project_entries([
            row(1, "entry_append", {"entry_id": "e1", "content": "旧"}, TS1),
            row(2, "entry_append", {"entry_id": "e1", "content": "新"}, TS2)])
        self.assertEqual(len(proj), 2, "兜底键把同 id 异内容并成一键")
        self.assertEqual(project_ids(proj), {"e1"})
        self.assertTrue(all(k[1].startswith("*") for k in proj), "兜底键应带行序号标记")


if __name__ == "__main__":
    unittest.main(verbosity=2)
