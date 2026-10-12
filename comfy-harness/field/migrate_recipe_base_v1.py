# -*- coding: utf-8 -*-
"""migrate_recipe_base_v1.py — 一次性迁移：主题卡政权值 → 基座继承制（20261010 裁决④）

背景：政权值（zsnr/upscale_method）在 24 张卡里逐卡拷贝——有拷贝必有掉队，实锤 7 卡
停留在"马赛克元凶 nearest + 已裁定该关的 zsnr=True"。本迁移把卡收敛到基座继承：

  动作表（幂等，可复跑；每卡动作明示）：
    skip     backend=klein（flux_gen 独立管线，vpred 政权不适用）；
    pin      ron_fem* 对照实验臂——钉当前生效体制 + override_reason（行为零变化，
             实验可比性保命）；已有同值钉 = 幂等跳过；
    drop     显式值 == 基座值的拷贝键 → 删除（继承，行为零变化）；
    keep     显式值 ≠ 基座值（意料外）→ 保留 + override_reason（安全网，响示人）；
    inherit  无键卡 → 继承基座（**行为变更**：nearest→bislerp / zsnr True→False，
             这是本次迁移的目的——7 卡掉队根治）。

  顺带：premises.json 的 watched 列表补 recipe_base_version（存量状态文件自带 watched，
  只改 DEFAULT_WATCHED 不生效）。

用法：py -X utf8 field/migrate_recipe_base_v1.py [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
THEMES = os.path.join(_HERE, "themes.json")
BASE = os.path.join(_HERE, "recipe_base.json")
PREMISES = os.path.join(os.path.dirname(_HERE), "gov", "style_mine_out",
                        "premises.json")
RON_PREFIX = "ron_fem"
REASON_PIN = "对照实验臂锁体制（20261010 基座继承制迁移；行为零变化，禁基座覆盖）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    base = json.load(open(BASE, encoding="utf-8"))
    bargs = base.get("args", {})
    themes = json.load(open(THEMES, encoding="utf-8"))
    changed, rows = False, []
    for name, card in sorted(themes.items()):
        if card.get("backend") == "klein":
            rows.append((name, "skip", "非vpred管线（flux_gen）"))
            continue
        if name.startswith(RON_PREFIX):
            cur = (bool(card.get("zsnr", True)),
                   card.get("upscale_method", "nearest-exact"))
            if card.get("override_reason") == REASON_PIN:
                rows.append((name, "pin·幂等", f"zsnr={cur[0]} up={cur[1]}"))
                continue
            card["zsnr"] = cur[0]
            card["upscale_method"] = cur[1]
            card["override_reason"] = REASON_PIN
            changed = True
            rows.append((name, "pin", f"zsnr={cur[0]} up={cur[1]}（行为零变化）"))
            continue
        acted = []
        for k in ("zsnr", "upscale_method"):
            if k not in card:
                continue
            if str(card[k]).lower() == str(bargs.get(k)).lower():
                del card[k]                       # 拷贝==基座 → 删（继承，值不变）
                acted.append(f"drop {k}")
            else:
                card.setdefault("override_reason",
                                f"{k} 与基座 v{base.get('version')} 不同——故意覆盖待核"
                                "（20261010 迁移安全网）")
                acted.append(f"keep {k}={card[k]}（≠基座）")
        if acted:
            changed = True
            rows.append((name, "copy", "；".join(acted)))
        else:
            eff_z, eff_u = "zsnr" in card, "upscale_method" in card
            rows.append((name, "inherit",
                         f"继承基座 v{base.get('version')}"
                         f"（zsnr→{bargs.get('zsnr')} upscale→{bargs.get('upscale_method')}）"
                         + ("【行为变更】" if not (eff_z or eff_u) else "")))
    for name, act, det in rows:
        print(f"  {act:10s} {name:24s} {det}")
    if a.dry:
        print("[迁移] dry-run：未落盘")
        return 0
    if changed:
        json.dump(themes, open(THEMES, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"[迁移] themes.json 已写（{len(rows)} 卡）")
    else:
        print("[迁移] 无变更（已迁移过？）")
    # premises watched 补键（存量状态文件自带 watched 列表，只改代码缺省不生效）
    if os.path.isfile(PREMISES):
        p = json.load(open(PREMISES, encoding="utf-8"))
        w = p.get("watched") or []
        if "recipe_base_version" not in w:
            w.append("recipe_base_version")
            p["watched"] = w
            json.dump(p, open(PREMISES, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print("[迁移] premises.json watched + recipe_base_version")
        else:
            print("[迁移] premises.json watched 已含 recipe_base_version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
