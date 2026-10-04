# -*- coding: utf-8 -*-
"""P3-2-1 契约锁（清账令工单 A1）：e1 判例库时间戳字段必须对齐 evocore 检索契约 created_at。

根因：e1_dryrun.py 写判例用 "created"，evocore/retrieval._age_days 只认
last_used_at / created_at——字段不命中落入"缺失→0.0（无年龄项）"分支，
时间衰减静默失效（P3 报告 P2-1，20261003 审计；清账令 20261004 修复）。
"""
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_ROOT))

from evocore.retrieval import _age_days  # noqa: E402
import datetime  # noqa: E402


def _library_entries():
    data = json.loads((_HERE / "draft_library.json").read_text(encoding="utf-8"))
    return data["library"] if isinstance(data, dict) else data


def test_library_entries_carry_created_at():
    """存量数据面：每条判例必须带 created_at（ISO 日期），不允许旧字段 created。"""
    entries = _library_entries()
    assert entries, "判例库为空，契约测试无对象"
    for e in entries:
        assert "created" not in e, f"{e.get('id')} 仍带旧字段 created（evocore 契约=created_at）"
        assert "created_at" in e, f"{e.get('id')} 缺 created_at——age 衰减将静默失效"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e["created_at"])), (
            f"{e.get('id')} created_at 非 ISO 日期: {e['created_at']}"
        )


def test_writer_source_uses_created_at():
    """写面锁：e1_dryrun.py 落判例的字段名必须是 created_at（防回归）。"""
    src = (_HERE / "e1_dryrun.py").read_text(encoding="utf-8")
    assert '"created_at"' in src, "e1_dryrun.py 未用 created_at 写判例"
    assert not re.search(r'"created"\s*:', src), "e1_dryrun.py 仍存在 \"created\": 写法（漂移复发）"


def test_created_at_feeds_evocore_age():
    """行为面：created_at 形态必须被 evocore _age_days 读出非零年龄（契约咬合）。"""
    now = datetime.datetime(2026, 10, 4)
    entry = {"created_at": "2026-10-02"}
    age = _age_days(entry, now)
    assert age == 2.0, f"created_at 未进 age 计算（got {age}）——契约断裂"


def test_missing_timestamp_semantics_unchanged():
    """语义面：缺失时间戳=0.0（无年龄项，P2-2 统一批语义）——修复不得改坏该分支。"""
    now = datetime.datetime(2026, 10, 4)
    assert _age_days({}, now) == 0.0
    assert _age_days({"created": "2026-10-02"}, now) == 0.0  # 旧字段=缺失（契约外字段不认）
