# -*- coding: utf-8 -*-
"""evocore — 演化内核独立包（S1：自 memsys/engine 平移 · 一码四包的"码"源）

公开面 = SPEC §C Kernel Interface 中本包承担的部分（检索/生命周期/决策的纯函数）。
LedgerLike/ScannerLike 不在本包（归 audit-kit）——evocore 零依赖，不碰账本。

导出名注记：S1 设计件 §5 写的是概括名 `tokens`/`adjudicate`；实现实名为
`_tokens`（私有，按 S1"不改名"纪律不导出）与 `adjudicate_{conflict,merge,promote}`
（三 intent 各一函数）。本包按**实名**导出。
"""
__version__ = "0.6.2"
# 版本记录（S1v2 · 2026-09-23 · 总工单对齐轮 · 设计件《S1设计v2-evocore全量落地架构》）：
#   0.1.0  S1 平移版（自 memsys/engine，零语义变更）
#   0.1.1  S1v2 加固轮：T1 衰减映射单一化（tunables.decay_mult）· T2 常量命名化
#          （rationale_max/_SECONDS_PER_DAY）· T3 bad-ts 语义钉桩 · 契约测试与坏味基线。
#          **行为逐位不变**——证据：py -X utf8 tools/S1_verify_behavior.py（33 用例差异 0）。
#   0.2.0  S3/T1 加法式增补：新模块 entry.py（TYPES + validate_entry，宿主写入口构造校验）——
#          **不改动现有五件一字**；行为对拍仍 33 用例差异 0。
#   0.3.0  S4/T1 加法式增补：新模块 project.py（事件流→条目集投影，**单一投影器**：
#          kb CLI 与 L2 server 共用；另补 tombstone 回放）；行为对拍仍 33 用例差异 0。
#   0.5.0  P3/D7 统一（20260924 第三方接收）：content_hash 全宽 64 hex + created_at 入排除集（evocore-D7 关闭）
#   0.4.0  S8-4 加法式增补（20260923 开工批）：project.py 增 `project_overrides` /
#          `override_marks`（人侧终裁事件投影，与融合件 §7 `_overrides`/`_override_marks` 同语义）；
#          同批 W2-N3 使 `project_entries` **两认形态词汇**（entry_append/memory_append 等）。
#          原六件一字未动；行为对拍仍 33 用例差异 0。
#   0.5.5  件5 强幂等加固+P1-3 投影键消歧（20260928 缺陷五件批，版本线补记两次收口）：
#          同键重投 setdefault 只补缺；键=(entry_id, content_hash) 同 id 异内容双投影可见。
#   0.6.0  D11 投影族加法式增补（20260928 排期 4-6 走闸）：project.py 增投影族
#          `project_slim`/`project_human_view`/`project_agent_view`/`verify_view_mapping`
#          ＋嵌套段序 3 叶 Merkle（`seg_hash`/`content_hash_v3`/`verify_prefix_entry`）
#          ＋`SLIM_MARK_KIND` 事件形态——project_entries 既有语义一字未动（件 5 加固原样）。
#          配套登记：entry.content_hash 的 v3 写侧分发未随本闸（D11 §三配套增量，后批）。
#   0.6.1  v3 写侧分发（20260929 分支1·框架 排期配套，0.6.0 登记项清账）：entry.content_hash
#          按 content 形态分发——dict 嵌套段序→v3 三叶 Merkle（entry.content_hash_v3，与
#          project 同规，跨形态逐字节对拍钉死）；字符串→v2 全 body 哈希一字未动。
#          validate_entry 受理 dict content（c 必填非空）。导出 seg_hash/content_hash_v3。
#   0.6.2  supersede 事件接线（20260929 分支1·框架 排期件3）：project_entries 后续事件链
#          增 supersede 映射（{entry_id|node_id, reason} → status=superseded，按 id 部分匹配
#          全部版本）——R4 分支自 0.6.0 起不可达（无事件可置），自本版在账本流可达；
#          D6 关闭动词表的账本条目流语义落定（decision_tree 节点面语义不变）。
SPEC = "SPEC-内核接口与宿主契约-v1"

from .tunables import Tunables, DEFAULTS
from .retrieval import score, recall, retrieve
from .lifecycle import route, promote, attic, tombstone, touch, decay_multiplier
from .decision import adjudicate_conflict, adjudicate_merge, adjudicate_promote
from .entry import (TYPES, content_hash, content_hash_v3, seg_hash,
                     validate_entry)
from .project import (project_entries, project_ids, project_overrides, project_sources,
                     override_marks, OVERRIDE_KIND, SLIM_MARK_KIND,
                     project_slim, project_human_view, project_agent_view,
                     verify_view_mapping, verify_prefix_entry)
                     # content_hash_v3/seg_hash 单源导出=.entry 版（上方已导入）；
                     # project 版同规实现不经此处导出（F811 阴影废止，P1-P4-2）——
                     # 双实现同规由 test_entry_v3_dispatch 逐字节对拍钉死。
from . import (tunables as tunables, retrieval as retrieval, lifecycle as lifecycle,
               decision as decision, entry as entry, project as project)  # 子模块暴露（re-export 意图显式化——F401 批B-2清偿）

__all__ = [
    "__version__", "SPEC",
    # tunables
    "Tunables", "DEFAULTS",
    # retrieval
    "score", "recall", "retrieve",
    # lifecycle
    "route", "promote", "attic", "tombstone", "touch", "decay_multiplier",
    # decision
    "adjudicate_conflict", "adjudicate_merge", "adjudicate_promote",
    # entry（S3/T1）
    "TYPES", "validate_entry", "content_hash", "content_hash_v3", "seg_hash",
    # project（S4/T1；S8-4 增补终裁投影；0.6.0 增 D11 投影族）
    "project_entries", "project_ids", "project_overrides", "project_sources",
    "override_marks", "OVERRIDE_KIND",
    "SLIM_MARK_KIND", "project_slim", "project_human_view", "project_agent_view",
    "verify_view_mapping", "verify_prefix_entry",
]
