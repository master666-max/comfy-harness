# -*- coding: utf-8 -*-
"""ablation_shadow.py — 影子库消融实验（维护者令 20261010『为什么不全量克隆一个影子库』）

设计：生产库**全量克隆 ×2**（A=机制全开对照 / B=影子机制全关），同一输入流回放：
  输入流 = ①真实 obs 流（负例台账进料） ②当前 miku 主题配置（条件扫描靶）
           ③一条**历史缺陷配置**（pre-fix wreck：caustics+nearest-exact，验告警能力）
           ④前提环境史回放（旧政权→新政权，验翻倒检测）
消融维度（B 臂关闭）：neg_chain 条件告警 / auto_heal 影环 / 反飞轮雷达 / 贝叶斯影子 / premises 翻倒观察。
读数 = 每机制的捕获数（A 有 B 无 = 机制贡献；两臂同 = 机制在该维度无增益）。

红线：只读生产（clone 后一切写落沙箱）；沙箱内动作全在机器权限面（draft retract 可 relist）。
用法：py -X utf8 ablation_shadow.py [--rounds-note 供报告]（无生产写）
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

import auto_heal as ah          # noqa: E402
import bayes_shadow as bs       # noqa: E402
import edge_graph as eg         # noqa: E402
import neg_chain as nc          # noqa: E402
import premises as pms          # noqa: E402
import reverse_flywheel as rf   # noqa: E402
from precedent_gov import PrecedentStore  # noqa: E402

PROD_STORE = ah.DEFAULT_STORE
PROD_OBS = os.path.join(_HERE, "..", "field", "out")
PROD_PREMISES = os.path.join(_HERE, "style_mine_out", "premises.json")
PROD_BACKFILLS = pms.load(PROD_PREMISES).get("backfills", [])


def _clone(dst: str) -> str:
    """全量克隆：库 + obs 流（输入流两臂同源）。"""
    os.makedirs(os.path.join(dst, "out"), exist_ok=True)
    shutil.copy(PROD_STORE, os.path.join(dst, "seed.json"))
    for f in os.listdir(PROD_OBS):
        if f.endswith("_obs.jsonl"):
            shutil.copy(os.path.join(PROD_OBS, f),
                        os.path.join(dst, "out", f))
    return os.path.join(dst, "seed.json")


def _add_replay_config(store: PrecedentStore, eid: str, text: str, kw: list):
    """回放一条历史配置为沙箱草案（条件扫描的靶）。"""
    store.add({"id": eid, "task": "t2i", "kind": "style", "level": "specialized",
               "type": "procedural", "importance": 3,
               "content": {"c": text[:400], "a": "", "d": ""},
               "keywords": kw[:6], "evidence": {"artifact": "replay:history"}},
              actor="machine:ablation-replay")


def run_arm(on: bool, workdir: str) -> dict:
    """单臂：on=True 机制全开；on=False 影子机制全关（同输入流）。"""
    os.makedirs(workdir, exist_ok=True)
    store_path = _clone(workdir)
    obs_dir = os.path.join(workdir, "out")
    m = {"neg_registry": 0, "neg_warnings": 0, "auto_would": 0,
         "radar_hits": 0, "bayes_ranked": 0, "flips": 0, "tickets": 0}
    s = PrecedentStore.load(store_path)
    # 回放历史缺陷配置（pre-fix wreck：caustics + nearest-exact）
    _add_replay_config(s, "S-replay-wreck-prefix",
                       "wreck 内部构图 caustics 落脸光栅 upscale_method nearest-exact "
                       "hand_denoise 0.6 潜放大", ["caustics", "nearest-exact", "wreck"])
    s.save(store_path)

    if on:
        # ① neg_chain：台账进料 + 条件扫描（含历史靶）
        reg = nc.build_registry(store_path, obs_dir)
        m["neg_registry"] = len(reg)
        r_nc = nc.scan(store_path, obs_dir,
                       os.path.join(workdir, "neg_chain.jsonl"), mode="shadow")
        m["neg_warnings"] = len(r_nc.get("hits", []))
        # ② auto_heal 影环（只算不动手：沙箱内即便 on 也用 shadow 档，动作语义另行推演）
        r_ah = ah.shadow_scan(store_path=store_path,
                              log_path=os.path.join(workdir, "auto_heal.jsonl"),
                              mode="shadow")
        m["auto_would"] = len(r_ah.get("would_retract", []))
        # ③ 反飞轮雷达（候选=沙箱全部 draft；无嵌入→流程词判据）
        cands = [{"name": e["id"], "members": list(e.get("keywords") or [])}
                 for e in s.entries if e.get("gov") == "draft"]
        r_rf = rf.run(cands, s, mode="on",
                      shadow_path=os.path.join(workdir, "anti_shadow.jsonl"))
        m["radar_hits"] = len(r_rf.get("hits", []))
        # ④ 贝叶斯影子（纠错根∪前提依赖里有下游者）
        g = eg.extract_graph(s.entries)
        adj = eg._adjacency(g)
        cand = [e["id"] for e in ah.wrong_roots(s.entries)]
        cand += [str(t.get("ref")) for b in PROD_BACKFILLS
                 for t in b.get("targets", []) if t.get("ref")]
        ranked = 0
        for rid in dict.fromkeys(cand):
            if adj.get(rid):
                r_b = bs.run(g, rid, log_path=os.path.join(workdir, "bayes.jsonl"))
                ranked += r_b.get("checked", 0)
        m["bayes_ranked"] = ranked
        # ⑤ premises 翻倒观察（环境史回放：旧政权→新政权；沙箱预置回填依赖→翻倒出票可演示）
        pp = os.path.join(workdir, "premises.json")
        qp = os.path.join(workdir, "queue.json")
        pms.save({"watched": list(pms.DEFAULT_WATCHED), "states": {}, "flips": [],
                  "backfills": PROD_BACKFILLS}, pp)
        env_old = {"ckpt": "NoobAI-XL-Vpred-v1.0.safetensors", "zsnr_default": True,
                   "upscale_method_default": "nearest-exact", "sampler_default": "euler",
                   "scheduler_default": "normal", "themes_any_zsnr_false": False,
                   "themes_any_bislerp": False, "themes_any_lora": False}
        env_new = _capture_env()
        r_p1 = pms.observe_env(env_old, premises_path=pp, queue_path=qp,
                               store_path=store_path)
        r_p2 = pms.observe_env(env_new, premises_path=pp, queue_path=qp,
                               store_path=store_path)
        m["flips"] = len(r_p1["flips"]) + len(r_p2["flips"])
        q = pms.load_queue(qp)
        m["tickets"] = len(q["tickets"])
    return m


def _capture_env() -> dict:
    sys.path.insert(0, os.path.join(_HERE, "..", "field"))
    import cinematic_gen as cg
    return cg.capture_env()


def main(argv=None) -> int:
    base = tempfile.mkdtemp(prefix="ablation_shadow_")
    arm_on = run_arm(True, os.path.join(base, "A_full"))
    arm_off = run_arm(False, os.path.join(base, "B_off"))
    rows = [("neg_chain 台账+条件告警", "neg_registry", "neg_warnings"),
            ("auto_heal 影环(该下架)", "auto_would", "auto_would"),
            ("反飞轮雷达(标本同形/流程词)", "radar_hits", "radar_hits"),
            ("贝叶斯影子(序数后验覆盖)", "bayes_ranked", "bayes_ranked"),
            ("premises 翻倒检测", "flips", "flips"),
            ("翻倒出票", "tickets", "tickets")]
    print("── 影子库消融（同输入流：39 obs + 历史缺陷配置回放）──")
    print(f"{'机制':<28}{'A 全开':>8}{'B 全关':>8}  贡献")
    for label, k_on, k_off in rows:
        a, b = arm_on.get(k_on, 0), arm_off.get(k_off, 0)
        note = "机制贡献" if a > b else ("两臂同" if a == b else "?")
        print(f"{label:<30}{a:>6}{b:>8}  {note}")
    print(f"沙箱: {base}（A_full / B_off 全量克隆留存）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
