# -*- coding: utf-8 -*-
"""mine_trigger.py — 挖掘到期触发器（20261008 维护者令：累计阈值→提醒主控）。

背景：风格双挖掘器"休假"事故——矿机不会自己上线，需要机械提醒。
设计：以"自上次挖掘以来的新语料量"为唯一读数（新生成文档数 + 观察流新增行数），
累计破阈值即报"挖掘到期"。提醒通道=Stop-hook（会话收尾对账时注入 additionalContext，
复用其 6h 冷却与去重键基建）；状态=style_mine_out/mine_state.json。

语义：
  check（默认）: 读数 vs 上次 mark 快照；Δ ≥ 阈值 → 打印提醒 + exit 1（到期）。
                首次运行（无状态）→ 静默建初始快照（宽限：从此刻开始计数，不空报）。
  mark          : 以当前读数记快照（挖掘跑完调用；compare 编排器已自动接线）。
  --threshold N : 覆盖阈值（默认随状态文件，初始 8）。
环境：Z_REPO（测试）/ COMFY_OUTPUT_DIR（生成面目录，同 style_corpus）。
"""
import argparse
import glob
import json
import os
import sys
import time

REPO = os.environ.get("Z_REPO") or os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # gov→comfy-harness→仓根（少剥一层曾致读数全0）
_GOV = os.path.join(REPO, "comfy-harness", "gov")
STATE = os.path.join(_GOV, "style_mine_out", "mine_state.json")
OBS_DIR = os.path.join(REPO, "comfy-harness", "field", "out")
SEED = os.path.join(_GOV, "precedents_e2_seed.json")
DEFAULT_COMFY_OUT = os.environ.get(
    "COMFY_OUTPUT_DIR", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\output")
DEFAULT_THRESHOLD = 8


def measure() -> dict:
    """当前读数：生成文档数（ComfyUI 产物 png）+ 观察流行数 + 库存条目数。"""
    gen = 0
    if os.path.isdir(DEFAULT_COMFY_OUT):
        gen = len(glob.glob(os.path.join(DEFAULT_COMFY_OUT, "*.png")))
    obs = 0
    for f in glob.glob(os.path.join(OBS_DIR, "*_obs.jsonl")):
        try:
            with open(f, encoding="utf-8") as fh:
                obs += sum(1 for l in fh if l.strip())
        except OSError:
            pass
    entries = 0
    try:
        entries = len(json.load(open(SEED, encoding="utf-8")).get("entries", []))
    except (OSError, ValueError):
        pass
    return {"gen_docs": gen, "obs_lines": obs, "entries": entries}


def load_state() -> dict | None:
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_state(cur: dict, threshold: int) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"last_mine_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "snapshot": cur, "threshold": threshold},
              open(STATE, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)


def delta(cur: dict, snap: dict) -> dict:
    """增量（负数按 0 计——产物被清/库被裁不算负数债）。"""
    return {k: max(0, cur.get(k, 0) - snap.get(k, 0))
            for k in ("gen_docs", "obs_lines", "entries")}


def health_lines() -> list:
    """到期提醒附带健康度（P9 T-a/T-b 常设哨兵；读数失败响亮降级不拦提醒）。"""
    try:
        import health
        r = health.readings(gen_docs=None)
        p, rf = r.get("probe") or {}, r.get("reforge") or {}
        ta = (f"不可用（{p['error'][:60]}）" if p.get("error")
              else f"{len(p['misses'])}/{p['probes']}={round(p['zero_hit_rate'] * 100, 1)}%"
                   + ("⚠" if p.get("over_threshold") else ""))
        tb = (f"{rf.get('twin_groups', 0)}/{rf.get('drafts', 0)}="
              f"{round((rf.get('rate') or 0) * 100, 1)}%"
              + ("⚠" if rf.get("over_threshold") else ""))
        e = r["entry"]
        return [f"（健康度 P9：raw:ratified:draft={e['ratio']}"
                f" · approved率={round((e['approved_rate'] or 0) * 100, 1)}%"
                f" · T-a语义失效率={ta} · T-b重铸率={tb}）"]
    except Exception as ex:                                    # noqa: BLE001 响亮不静默
        return [f"（健康度读数不可用：{type(ex).__name__}: {ex}）"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="挖掘到期触发器")
    ap.add_argument("mode", nargs="?", default="check", choices=("check", "mark"))
    ap.add_argument("--threshold", type=int, default=None)
    a = ap.parse_args(argv)
    cur = measure()
    st = load_state()
    threshold = a.threshold or (st or {}).get("threshold", DEFAULT_THRESHOLD)

    if a.mode == "mark" or st is None:
        save_state(cur, threshold)
        if a.mode == "mark":
            print(f"[mine-trigger] 快照已记：{cur}（阈值 {threshold}）")
        else:
            print(f"[mine-trigger] 初始快照建立（宽限）：{cur}（阈值 {threshold}）")
        return 0

    d = delta(cur, st.get("snapshot", {}))
    score = d["gen_docs"] + d["obs_lines"]
    if a.mode == "check" and score >= threshold:
        print(f"【挖掘到期】自上次挖掘（{st.get('last_mine_at', '?')}）以来新增 "
              f"生成 {d['gen_docs']} 张 / 观察 {d['obs_lines']} 行 / 条目 {d['entries']} "
              f"（阈值 {threshold}）——建议：py z.py mine（或 z.py due --mark 顺延）")
        for ln in health_lines():
            print(ln)
        return 1
    print(f"[mine-trigger] 未到期：Δ={d}（score {score}/{threshold}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
