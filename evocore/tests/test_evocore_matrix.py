# -*- coding: utf-8 -*-
"""test_evocore_matrix.py — evocore 扩展测试矩阵（零依赖，标准库 unittest）
（S1 平移 · 源 memsys/tests/test_matrix_ms.py @ b19c9a4）
覆盖：retrieval 分词/权重/过滤/截断/平局、类型衰减曲线、lifecycle 三态边界、
decision 三方排序/恒 defer/批量晋升、tunables 构造期非法值全拒。
每个用例一句注释守一条不变量；只测契约不测实现细节。
"""
import sys, os, unittest, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # 仓根：含 evocore 包
from evocore import Tunables, DEFAULTS           # noqa: E402
from evocore import retrieval                      # noqa: E402
from evocore import lifecycle                      # noqa: E402
from evocore import decision                       # noqa: E402

NOW = datetime.datetime(2026, 9, 21, 12, 0, 0)
OLD_40D = "2026-08-12T12:00:00"          # NOW 前 40 天
OLD_200D = "2026-03-05T00:00:00"         # NOW 前 200 天
FRESH = "2026-09-21T12:00:00"            # 与 NOW 同刻（age=0）

def entry(**kw):
    base = {"id": "e1", "content": "偏好深色主题", "keywords": ["偏好"],
            "importance": 5, "created_at": "2026-09-20T00:00:00", "type": "semantic",
            "state": "intermediate"}
    base.update(kw); return base

class TestTokenizerAndScore(unittest.TestCase):
    def test_cjk_bigram_and_single_char(self):
        # 不变量：CJK 按 bigram 切分、单字保留（"记忆库"→["记忆","忆库"]，"深"→["深"]）
        self.assertEqual(retrieval._tokens("记忆库"), ["记忆", "忆库"])
        self.assertEqual(retrieval._tokens("深"), ["深"])
    def test_western_tokens_lowercased_and_mixed(self):
        # 不变量：西文 token 归一小写；空格分隔的西文与 CJK 混排各自成 token
        self.assertEqual(retrieval._tokens("API Token"), ["api", "token"])
        self.assertEqual(retrieval._tokens("Hello 世界"), ["hello", "世界"])
    def test_bigram_subword_query_hits_content(self):
        # 不变量：bigram 分词使子词查询可命中（查询"忆库"命中含"记忆库"的内容）
        e = entry(content="导出记忆库到文件", keywords=[])
        self.assertGreater(retrieval.score(e, "忆库", DEFAULTS, NOW), 0)
    def test_keyword_hit_outweighs_content_hit(self):
        # 不变量：单次 keywords 命中的边际分 = w_kw，单次 content 命中 = w_content，且 w_kw>w_content 实际生效
        t0 = Tunables(filter_zero=0)
        base = entry(keywords=[], content="无关内容")            # 零命中基线
        kw = entry(keywords=["偏好"], content="无关内容")         # 仅 keywords 命中
        ct = entry(keywords=[], content="偏好主题设定")           # 仅 content 命中
        b = retrieval.score(base, "偏好", t0, NOW)
        s_kw = retrieval.score(kw, "偏好", t0, NOW)
        s_ct = retrieval.score(ct, "偏好", t0, NOW)
        self.assertAlmostEqual(s_kw - b, DEFAULTS.w_kw, places=6)
        self.assertAlmostEqual(s_ct - b, DEFAULTS.w_content, places=6)
        self.assertGreater(s_kw, s_ct)
    def test_filter_zero_switch_semantics(self):
        # 不变量：filter_zero=1 零命中→0.0；=0 零命中仍保留 imp 分量（imp5-imp0 差 = w_imp*5）
        z5 = entry(keywords=[], content="毫无交集的内容", importance=5)
        z0 = entry(keywords=[], content="毫无交集的内容", importance=0)
        self.assertEqual(retrieval.score(z5, "偏好", DEFAULTS, NOW), 0.0)
        s5 = retrieval.score(z5, "偏好", Tunables(filter_zero=0), NOW)
        s0 = retrieval.score(z0, "偏好", Tunables(filter_zero=0), NOW)
        self.assertGreater(s5, 0)
        self.assertAlmostEqual(s5 - s0, DEFAULTS.w_imp * 5, places=6)

class TestRetrieve(unittest.TestCase):
    def test_k_truncates_and_orders_desc(self):
        # 不变量：retrieve 只返回前 k 条且按分数严格降序
        pool = [entry(id="p%d" % i, importance=i, keywords=["偏好"]) for i in range(1, 7)]
        got = retrieval.retrieve(pool, "偏好", k=3, now=NOW)
        self.assertEqual(len(got), 3)
        self.assertEqual([x[1]["id"] for x in got], ["p6", "p5", "p4"])
        self.assertTrue(got[0][0] > got[1][0] > got[2][0])
    def test_nonpositive_scores_excluded_even_if_k_overflows(self):
        # 不变量：k 超过池子大小时只返回正分条目（墓碑 0 分、纯 age 罚负分均不入列）
        pool = [entry(id="good1", keywords=["偏好"]), entry(id="good2", keywords=["偏好"]),
                entry(id="dead", tombstone=True, keywords=["偏好"]),
                entry(id="neg", keywords=[], content="毫无交集的内容", importance=0)]
        got = retrieval.retrieve(pool, "偏好", k=10,
                                 tunables=Tunables(filter_zero=0), now=NOW)
        self.assertEqual(sorted(x[1]["id"] for x in got), ["good1", "good2"])
    def test_tie_break_by_id_lexicographic(self):
        # 不变量：同分平局按 id 字典序破序，与传入顺序无关（确定性）
        a = entry(id="a_id"); b = entry(id="b_id")
        order1 = [x[1]["id"] for x in retrieval.retrieve([b, a], "偏好", k=5, now=NOW)]
        order2 = [x[1]["id"] for x in retrieval.retrieve([a, b], "偏好", k=5, now=NOW)]
        self.assertEqual(order1, ["a_id", "b_id"])
        self.assertEqual(order2, ["a_id", "b_id"])

class TestDecay(unittest.TestCase):
    def test_old_episodic_below_same_semantic(self):
        # 不变量：同内容同时间戳，老 episodic 分低于 semantic（快衰减）；age=0 时两者相等
        epi = retrieval.score(entry(created_at=OLD_40D, type="episodic"), "偏好", DEFAULTS, NOW)
        sem = retrieval.score(entry(created_at=OLD_40D, type="semantic"), "偏好", DEFAULTS, NOW)
        self.assertLess(epi, sem)
        self.assertEqual(retrieval.score(entry(created_at=FRESH, type="episodic"), "偏好", DEFAULTS, NOW),
                         retrieval.score(entry(created_at=FRESH, type="semantic"), "偏好", DEFAULTS, NOW))
    def test_decay_gap_matches_type_curve(self):
        # 不变量：episodic 与 semantic 分差 = w_age * age天数 * (mult_epi - mult_sem)（类型曲线公式生效）
        epi = retrieval.score(entry(created_at=OLD_40D, type="episodic"), "偏好", DEFAULTS, NOW)
        sem = retrieval.score(entry(created_at=OLD_40D, type="semantic"), "偏好", DEFAULTS, NOW)
        self.assertAlmostEqual(sem - epi,
                               DEFAULTS.w_age * 40 * (DEFAULTS.decay_mult_episodic
                                                      - DEFAULTS.decay_mult_semantic), places=6)
    def test_procedural_never_decays_200d(self):
        # 不变量：procedural 恒不衰减——200 天前条目与刚建条目得分相同
        self.assertEqual(retrieval.score(entry(created_at=OLD_200D, type="procedural"), "偏好", DEFAULTS, NOW),
                         retrieval.score(entry(created_at=FRESH, type="procedural"), "偏好", DEFAULTS, NOW))
    def test_touch_refresh_lifts_score(self):
        # 不变量：touch 刷新 last_used_at 后 age 从新刻起算，score 回升到"新近条目"水平
        t = entry(created_at="2026-06-01T00:00:00")
        before = retrieval.score(t, "偏好", DEFAULTS, NOW)
        lifecycle.touch(t, "2026-09-20T12:00:00")
        after = retrieval.score(t, "偏好", DEFAULTS, NOW)
        ref = retrieval.score(entry(created_at="2026-09-20T12:00:00"), "偏好", DEFAULTS, NOW)
        self.assertGreater(after, before)
        self.assertEqual(after, ref)
    def test_decay_multiplier_table_and_fallback(self):
        # 不变量：三类型乘数取 tunables 曲线值；未知类型回落标准 1.0
        self.assertEqual(lifecycle.decay_multiplier(entry(type="episodic")),
                         DEFAULTS.decay_mult_episodic)
        self.assertEqual(lifecycle.decay_multiplier(entry(type="semantic")),
                         DEFAULTS.decay_mult_semantic)
        self.assertEqual(lifecycle.decay_multiplier(entry(type="procedural")),
                         DEFAULTS.decay_mult_procedural)
        self.assertEqual(lifecycle.decay_multiplier(entry(type="unknown-kind")), 1.0)

class TestLifecycle(unittest.TestCase):
    def test_route_boundary_exact_threshold(self):
        # 不变量：route 阈值含边界——importance=7 恰好晋升，6 留 intermediate
        self.assertEqual(lifecycle.route(entry(importance=7)), "longterm")
        self.assertEqual(lifecycle.route(entry(importance=6)), "intermediate")
    def test_route_threshold_from_tunables(self):
        # 不变量：晋升阈值外置 tunables，非硬编码（min=3 时 imp=3 晋升）
        self.assertEqual(lifecycle.route(entry(importance=3),
                                         Tunables(promote_importance_min=3)), "longterm")
    def test_promote_attic_entry_raises(self):
        # 不变量：attic 条目不得直接晋升（公理 F：禁销毁式回退，须先人工恢复）
        with self.assertRaises(ValueError): lifecycle.promote(entry(state="attic"))
    def test_promote_sets_state_and_event(self):
        # 不变量：promote 落 state=longterm 并返回带 entry_id 的晋升留痕事件
        e = entry(); ev = lifecycle.promote(e)
        self.assertEqual(e["state"], "longterm")
        self.assertEqual(ev["kind"], "promotion"); self.assertEqual(ev["entry_id"], "e1")
    def test_attic_then_tombstone_legal(self):
        # 不变量：attic 后再 tombstone 是合法路径；content 原位保留（永不删除）
        e = entry(); ev1 = lifecycle.attic(e, "降权理由"); ev2 = lifecycle.tombstone(e)
        self.assertEqual(e["state"], "attic"); self.assertTrue(e["tombstone"])
        self.assertIn("content", e)
        self.assertEqual(ev1["kind"], "attic_nomination"); self.assertEqual(ev2["kind"], "tombstone")
    def test_tombstone_score_zero_under_any_tunables(self):
        # 不变量：墓碑条目 score 恒 0（任何 tunables、任何命中强度），且 retrieve 不返回
        t = entry(id="tomb", tombstone=True, keywords=["偏好"], importance=9)
        self.assertEqual(retrieval.score(t, "偏好", DEFAULTS, NOW), 0.0)
        self.assertEqual(retrieval.score(t, "偏好", Tunables(filter_zero=0), NOW), 0.0)
        got = retrieval.retrieve([t, entry(id="live")], "偏好", k=10, now=NOW)
        self.assertEqual([x[1]["id"] for x in got], ["live"])

class TestDecision(unittest.TestCase):
    def test_conflict_manual_dominates_three_way(self):
        # 不变量：三方冲突 manual 来源信任最高（即便 importance 最低、created_at 最旧），错判=irreversible
        m = entry(id="manual", source="manual", importance=1, created_at="2026-01-01T00:00:00")
        ag9 = entry(id="agent9", source="agent", importance=9, created_at="2026-09-21T00:00:00")
        ag5 = entry(id="agent5", source="agent", importance=5, created_at="2026-09-22T00:00:00")
        tr, win, lose = decision.adjudicate_conflict([ag5, ag9, m])
        self.assertEqual(win["id"], "manual")
        self.assertEqual([x["id"] for x in lose], ["agent9", "agent5"])
        self.assertEqual(tr["severity_if_wrong"], "irreversible")
    def test_conflict_importance_rank_same_source(self):
        # 不变量：同 source 按 importance 排序；无 manual 条目时错判严重度=redundant
        ag9 = entry(id="agent9", source="agent", importance=9, created_at="2026-09-21T00:00:00")
        ag5 = entry(id="agent5", source="agent", importance=5, created_at="2026-09-22T00:00:00")
        tr, win, _ = decision.adjudicate_conflict([ag5, ag9])
        self.assertEqual(win["id"], "agent9")
        self.assertEqual(tr["severity_if_wrong"], "redundant")
    def test_conflict_recency_breaks_same_rank_tie(self):
        # 不变量：同 source 同 importance 取 created_at 更新者
        old = entry(id="older", source="agent", importance=5, created_at="2026-09-01T00:00:00")
        new = entry(id="newer", source="agent", importance=5, created_at="2026-09-20T00:00:00")
        _, win, _ = decision.adjudicate_conflict([old, new])
        self.assertEqual(win["id"], "newer")
    def test_conflict_order_independent(self):
        # 不变量：conflict 判定与传入顺序无关（确定性）
        m = entry(id="manual", source="manual", importance=1, created_at="2026-01-01T00:00:00")
        ag9 = entry(id="agent9", source="agent", importance=9, created_at="2026-09-21T00:00:00")
        ag5 = entry(id="agent5", source="agent", importance=5, created_at="2026-09-22T00:00:00")
        n1 = entry(id="n1", source="agent", importance=5, created_at="2026-09-01T00:00:00")
        n2 = entry(id="n2", source="agent", importance=5, created_at="2026-09-20T00:00:00")
        _, win, lose = decision.adjudicate_conflict([n2, n1, ag9, m, ag5])
        self.assertEqual(win["id"], "manual")
        self.assertEqual([x["id"] for x in lose], ["agent9", "agent5", "n2", "n1"])
    def test_conflict_requires_two_entries(self):
        # 不变量：conflict 需 ≥2 条，单条构造即拒
        with self.assertRaises(ValueError): decision.adjudicate_conflict([entry()])
    def test_merge_always_defers(self):
        # 不变量：v1 规则对 merge 恒 defer（同义判断不可规则化），留痕含 intent/actor/kind
        # （<2 条现抛 ValueError——守卫与 conflict 对称，2026-09-23 修订）
        tr = decision.adjudicate_merge([entry(), entry(id="e2")])
        self.assertEqual(tr["decision"], "defer")
        self.assertEqual(tr["intent"], "merge")
        self.assertEqual(tr["actor"], "fallback:rule")
        self.assertEqual(tr["kind"], "memory_adjudicate")
        with self.assertRaises(ValueError):
            decision.adjudicate_merge([entry(id="solo")])   # 单条即拒（新契约）
    def test_promote_mixed_batch_with_boundary(self):
        # 不变量：批量晋升按 importance>=阈值逐条判定（7 恰好晋升），留痕决策串逐条可查
        es = [entry(id="a9", importance=9), entry(id="b7", importance=7),
              entry(id="c6", importance=6), entry(id="d3", importance=3)]
        tr, out = decision.adjudicate_promote(es)
        self.assertEqual([ok for _, ok in out], [True, True, False, False])
        self.assertEqual(tr["decision"], "a9:promote,b7:promote,c6:hold,d3:hold")

class TestTunablesRejects(unittest.TestCase):
    def _rejects(self, **kw):
        with self.assertRaises(ValueError): Tunables(**kw)
    def test_weight_fields_reject_nonpositive(self):
        # 不变量：四个检索权重必须 >0，0 与负值逐个构造即拒
        for kw in ({"w_kw": -1}, {"w_kw": 0}, {"w_content": -0.5}, {"w_content": 0},
                   {"w_imp": 0}, {"w_imp": -0.1}, {"w_age": -2}, {"w_age": 0}):
            self._rejects(**kw)
    def test_filter_zero_rejects_nonbinary(self):
        # 不变量：filter_zero 只许 0|1，越界与错型逐个构造即拒
        for v in (2, -1, "1", 0.5):
            self._rejects(filter_zero=v)
    def test_rates_reject_out_of_bounds(self):
        # 不变量：两决策比率必须 ∈(0,1) 开区间，0/1/越界/负值逐个构造即拒
        for v in (0, 1, 1.5, -0.1):
            self._rejects(decision_defer_rate_max=v)
            self._rejects(irreversible_error_rate_max=v)
    def test_decay_mult_and_promote_min_reject_invalid_but_keep_legal_bounds(self):
        # 不变量：三个衰减乘数必须 >=0（0 合法）、晋升阈值必须 >=0（0 合法）；合法边界值可构造
        for kw in ({"decay_mult_episodic": -1}, {"decay_mult_semantic": -0.1},
                   {"decay_mult_procedural": -5}, {"promote_importance_min": -1}):
            self._rejects(**kw)
        t = Tunables(decay_mult_procedural=0, promote_importance_min=0,
                     decision_defer_rate_max=0.99, irreversible_error_rate_max=0.01,
                     filter_zero=0)
        self.assertEqual(t.decay_mult_procedural, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
