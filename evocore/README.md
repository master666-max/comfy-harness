# evocore · 演化内核独立包（v0.6.2）

> **定位**：演化内核（Evolution Core）——记忆域**演化机制的纯函数实现**：检索精排、
> 生命周期三态、决策判定。S1（2026-09-23）自 `memsys/engine/` 平移而来，
> 是"一码四包"装配体系的**唯一"码"源**（微内核 L1 融合 / 中库 L1 包内 / 共库 L2 服务
> 均由本包装配，见架构定版 v1.1 §9 交付序列）。
>
> **边界**：LedgerLike/ScannerLike **不在**本包（归 `audit-kit`）——evocore **零依赖**，
> 不碰账本、不引 audit-kit、不引 memsys（静态断言见 `tests/test_evocore_s1.py` 不变量③、
> 分层契约见 `tests/test_evocore_contract.py`）。
>
> **版本 0.3.0（S4/T1 增补 · 2026-09-23）**：在 0.1.1（S1v2 加固轮 · 总工单对齐：
> T1 衰减映射单一化 · T2 常量命名化（`rationale_max`/`_SECONDS_PER_DAY`）· T3 bad-ts
> 语义钉桩 · 契约测试与坏味基线）之上，**加法式**增补 `entry.py`（0.2.0）与
> `project.py`（0.3.0）两模块，原五件一字未动。**行为逐位不变**
> （`py -X utf8 tools/S1_verify_behavior.py`：33 用例差异 0）。逐版记录见 `__init__.py`
> 版本史；交付记录与验收原件：`../交付-S1v2-20260923/`。

## 公开 API（`__init__.py` 导出面 · 对照 SPEC §C）

| 模块 | 导出 |
|---|---|
| `tunables` | `Tunables`（frozen dataclass + 构造时校验）、`DEFAULTS` |
| `retrieval` | `score`、`recall`、`retrieve`（`_tokens` 私有，包内测试可用） |
| `lifecycle` | `route`、`promote`、`attic`、`tombstone`、`touch`、`decay_multiplier` |
| `decision` | `adjudicate_conflict`、`adjudicate_merge`、`adjudicate_promote` |
| `entry`（S3/T1 增补） | `TYPES`、`validate_entry`、`content_hash` |
| `project`（S4/T1 增补） | `project_entries`（**单一投影器**：中库 CLI 与 L2 服务件共用） |

> 名注记：S1 设计件 §5 的概括名 `tokens`/`adjudicate` 对应上表实名
> （`_tokens` 按私有约定不导出；三 intent 各一函数）。`__version__="0.6.2"`、
> `SPEC="SPEC-内核接口与宿主契约-v1"`。
> 导出面现含 S3/S4 增补两模块（`entry`/`project`）——见 `__init__.py` 版本史。

## 依赖形态（S1 后）

```
memsys.bridge → { audit-kit.(ledger, core),  evocore }      # 宿主侧
evocore       → ∅（仅标准库；包内相对导入）                  # 内核侧，零依赖
```

## 运行（无第三方依赖，标准库即可）

```bash
cd evocore/tests && py -X utf8 -m unittest        # 111 项（20261002 实跑读数；组分随批次生长，以 pytest 实跑为准）
```

## 已知分歧与债务登记（S1v2 §七 · "认知债"的反面）

| # | 项 | 说明 | 触发器 |
|---|---|---|---|
| **D1** | **bad-ts 跨形态分歧** | 坏时间戳：本包**降级** `age=0`（历史契约，读数钉死在 `test_evocore_s1.py::test_bad_ts_degrades_pinned`=5.541）；融合形态 evo-seat **抛 ValueError**（fail-closed）。SPEC §D 五硬条不覆盖该路径 | 出现需要跨形态逐位一致的宿主 → v0.2.0 语义变更流程（钉桩测试即安全网） |
| D2/D5 | 词面检索无向量层；`recall()` 现役=全量扫 | 能力边界（既定） | ≥100 分层实测掉带外 |
| D3 | 决策层 v1 规则版 | 挣得制待时 | 金标判据 §二 达标 |
| D4 | 分词无缓存 | 性能债（观测点：`tools/bench_evocore.py`） | 10k 库单查 >200 ms 或 100k >2 s |
| D6 | Tunables 无版本协商键 | SPEC §C 版本协商位 | 首次破坏性参数变更时补 |
| **D7**（跨件引用写 `evocore-D7`，DR-4 前缀化） | ~~content_hash 三形态口径分歧~~（W2-N4 钉桩登记 → **P3 统一关闭 · 20260924**） | ①本包 `entry.content_hash`=16 hex、排除 `state`/`last_used_at`、keywords 归一为有序词表（**声明的唯一来源**，SPEC §G「两个入口，一道门」）；②融合件 `evo_seat._content_hash`=16 hex、只排除 id 三件、**不归一**；③宿主桥 `bridge.record_append`=**64 hex**、全量 entry 无排除。⇒ 同一逻辑条目跨形态指纹不同，**迁移时幂等去重失效**。融合件原注释「与 bridge.content_hash 同口径」为**假**（bridge 无该函数、宽度亦不同），已更正 | **统一已执行（P3·20260924）**：全宽 64 hex+归一规则三处同规；**去重比较＝比较时重归一**——存量旧 16 hex 指纹不参与比较、永不回改（append-only 零破坏，优于原拟"meta 标记+读侧双认"，偏离已登记）；钉桩 `build/tests/test_content_hash_divergence.py` 已转正为「跨形态同指纹」正向断言 7 项（含判别力对照），**未删测试**；版本闸实测未触发（融合件改动落 §7，机制段未动） |

## S1 平移纪律与验收（存档）

- **改动白名单**（设计件 §3）：W1 `from tunables import DEFAULTS` → `from .tunables import DEFAULTS`
  （**恰 3 处**）；W2 各件 docstring **追加**一行溯源注记（**恰 4 处**：`源 memsys/... @ b19c9a4`）；
  其余逻辑行/注释行/常量行**逐字节一致**。
- **三层验收**（实跑命令与读数）：
  1. 源码逐行：`py -X utf8 tools/S1_verify_src.py` → 等价行 196 / W1=3 W2=4 / 违例 0 · **PASS**；
  2. 测试全绿：本包 56 项 + memsys 17 项 + audit-kit 49 项全绿；
     **（S1 时点值，本节为存档不改写；现值本包 111 项，见上「运行」节实跑读数）**
  3. 行为对拍：`py -X utf8 tools/S1_verify_behavior.py` → 33 用例（旧版 vs 本包同输入
     canonical JSON sha 比对）差异 0 / 空转对 0 · **PASS**（含 filter_zero 判力探针）。
- 被移出侧（`memsys/`）同步：README/docs 路径更新、`tests/test_bridge.py` 改引本包、
  `audit-kit/{tools_crosscheck.py,conformance.py}` 的宿主面断言随迁（`evocore` 入隔离禁用符号面）。

## 分层宪章 · 开放字段面（2026-10-05 · 候裁件④收口）

**宿主富字段，内核最小面。** facts / applicability / outcomes 类宿主层扩展字段
（precedent_gov 的 `facts` 槽位、blender 线 B1 `schema_facts`/B2 `applicability`）
**属宿主层约定，不进本包条目契约**：

- `validate_entry` 对未知字段**宽容**——这是宿主层富字段的存身前提，由
  `tests/test_entry_open_surface.py` 契约锁钉死（含"未知字段不得影响 content_hash"红线：
  内容寻址面只锚 content 的 c/a/d 三叶，宿主字段永不进哈希）；
- 给 `validate_entry` 加严格字段白名单 = 破坏分层宪章 = 该锁会响亮报红；
- 跨线窗口结论（候裁件④，维护者裁 2026-10-05）：两线各自在宿主层落地富字段
  （机制同源、各自落地），内核契约不动、冻结时钟互不污染。
