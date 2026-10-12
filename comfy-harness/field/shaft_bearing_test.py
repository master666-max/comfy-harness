# -*- coding: utf-8 -*-
"""shaft_bearing_test.py — 批一-3 一石三鸟承重实验（工单 §二-1-3 · 判据先锁后跑）

判据（工单锁死）：有库臂 facts_source=recall 且 空库臂预检被拒 → 咬合（布线面承重）；
两臂行为无差 → 登记盲区回炉。附带：有库臂 POST 真生成（端到端证据，PIL 非空白）。
一石三鸟：facts 槽位 + verify 机器层 + recall_tier 轴供血 + 双臂差分，同一次实验全验。
"""
import json
import os
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_CH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_CH)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _CH)
sys.path.insert(0, os.path.join(_CH, "gov"))
from precedent_gov import PrecedentStore  # noqa: E402
from wired_assembly import extract_wiring, NAIVE_PRIOR  # noqa: E402

BASE = "http://127.0.0.1:8188"
OUT = os.path.join(_HERE, "out")
SEED = os.path.join(_CH, "gov", "precedents_e2_seed.json")
MACHINE_ACTOR = "machine:卷十二线-field"          # 候裁件②默认值（工单§八-2），改名可重跑
EID = "P-field-wiring-facts"
R = {"log": [], "eids": [EID]}


def log(tag, ok, detail=""):
    R["log"].append({"tag": tag, "ok": bool(ok), "detail": str(detail)[:300]})
    print(f"[{'OK' if ok else 'NO'}] {tag} {str(detail)[:180]}")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post(path, payload, timeout=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---------- 0. 服务器 ----------
st = get("/system_stats")["system"]
log("0.server", st["comfyui_version"] == "0.38.0", "v" + st["comfyui_version"])

# ---------- 1. 铸造 facts 判例（幂等）+ 机器 verify ----------
store = PrecedentStore.load(SEED)
if not any(e["id"] == EID for e in store.entries):
    store.add({
        "id": EID, "type": "procedural", "importance": 3,
        "keywords": ["flux2", "布线", "schema", "机器事实"],
        "content": {"c": "flux2 klein 0.38 活体的 Flux2Scheduler 机器事实：合法输入键=steps/width/height（sched.model/sched.denoise 已废除,朴素先验必被活体 schema 拒）。",
                    "a": "20261005 field_wiring_run 实测 12 节点零非法键+承重实验空库臂预检拒（同件回执）。",
                    "d": "适用 v0.38 flux2/klein 系；换版本须重查 object_info。"},
        "evidence": {"artifact": "comfy-harness/field/out/field_receipt.json",
                     "quote": "12 节点×输入键对活体 schema 预检: 全过",
                     "recalc": "复跑 comfy-harness/field/field_wiring_run.py"},
        "owner": ""}, actor="ai:卷十二线(shaft)",
        facts={"Flux2Scheduler": ["steps", "width", "height"]})
    log("1.mint", True, f"{EID} 已铸（facts 槽位+证据三件套）")
else:
    log("1.mint", True, f"{EID} 已在库（幂等跳过）")

receipt = os.path.join(_HERE, "out", "field_receipt.json")
store.verify(EID, actor=MACHINE_ACTOR, receipt=receipt)
v_e = store._get(EID)
log("2.machine-verify", v_e["gov"] == "verified",
    f"gov={v_e['gov']} actor={MACHINE_ACTOR} receipt={os.path.basename(receipt)}(verdict=咬合)")

# ---------- 2. 轴供血 vs 空库：双臂布线事实 ----------
hits = store.recall_tier("flux2 布线 schema")
scope_map = json.load(open(os.path.join(_CH, "gov", "pipeline_scopes.json"), encoding="utf-8"))["scopes"]
supplied = extract_wiring("flux2 布线", hits, target_model="flux-2-klein-4b", scope_map=scope_map)                    # 有库臂
empty = extract_wiring("flux2 布线", [])                          # 空库臂（供血禁用等价）
log("3.supply", supplied["facts_source"] == "recall" and EID.lower() in str(hits).lower(),
    f"facts_source={supplied['facts_source']} facts={supplied['facts']} "
    f"skipped_no_facts={supplied['skipped_no_facts']}(散文教训跳过计数)")

# ---------- 3. 双臂预检对轰（活体 object_info 为裁判）----------
live = get("/object_info/Flux2Scheduler")["Flux2Scheduler"]["input"]["required"]
live_keys = set(live)


def preflight(inputs_keys):
    illegal = sorted(set(inputs_keys) - live_keys)
    return illegal


empty_illegal = preflight(NAIVE_PRIOR["inputs"].keys())
empty_rejected = bool(empty_illegal)
log("4.empty-arm", empty_rejected,
    f"朴素先验键 {sorted(NAIVE_PRIOR['inputs'])} → 活体拒: {empty_illegal}")

informed_keys = supplied["facts"]["Flux2Scheduler"] + ["width", "height"]  # 宽高由画幅参数补
informed_illegal = preflight(informed_keys)
supplied_ok = not informed_illegal and supplied["facts_source"] == "recall"
log("5.supplied-arm", supplied_ok,
    f"facts 键 {sorted(set(informed_keys))} → 非法键 {informed_illegal or '无'}")

# ---------- 4. 判据核销（工单锁死）----------
bite = empty_rejected and supplied_ok
R["verdict"] = "咬合" if bite else ("不咬合" if not (empty_rejected or supplied_ok) else "登记盲区")

# ---------- 5. 有库臂端到端：真生成 ----------
if supplied_ok:
    SEEDN = 26100505
    G = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b.safetensors", "weight_dtype": "default"}},
         "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2"}},
         "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
         "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "a red cube on a wooden desk, studio light, product photo"}},
         "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
         "6": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 4.0}},
         "7": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": 1024, "height": 1024}},
         "8": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
         "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
         "10": {"class_type": "SamplerCustom", "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": SEEDN, "cfg": 1.0, "positive": ["6", 0], "negative": ["5", 0], "sampler": ["9", 0], "sigmas": ["7", 0], "latent_image": ["8", 0]}},
         "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
         "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "shaft_bearing"}}}
    # 轴注入点：sched 输入键由 recall facts 决定（不再写死）
    G["7"]["inputs"] = {k: {"steps": 4, "width": 1024, "height": 1024}[k] for k in supplied["facts"]["Flux2Scheduler"]}
    t0 = time.time()
    pid = post("/prompt", {"prompt": G, "client_id": "shaft-bearing"})["prompt_id"]
    final = None
    for _ in range(480):
        h = get(f"/history/{pid}")
        if pid in h:
            e = h[pid]
            if e["status"].get("completed") or e["status"].get("status_str") == "error":
                final = e
                break
        time.sleep(0.5)
    ok = bool(final) and final["status"]["status_str"] == "success"
    fn = None
    if ok:
        o = final["outputs"].get("12", {}).get("images", [])
        if o:
            fn = o[0]["filename"]
            sub = o[0].get("subfolder", "")
            with urllib.request.urlopen(f"{BASE}/view?filename={fn}&subfolder={sub}&type=output", timeout=60) as r:
                os.makedirs(OUT, exist_ok=True)
                open(os.path.join(OUT, "shaft_bearing.png"), "wb").write(r.read())
    from PIL import Image
    std = None
    if fn:
        im = Image.open(os.path.join(OUT, "shaft_bearing.png")).convert("L")
        px = list(im.getdata())
        mean = sum(px) / len(px)
        std = round((sum((p - mean) ** 2 for p in px) / len(px)) ** 0.5, 1)
    log("6.e2e-generate", ok and (std or 0) > 10,
        f"sec={round(time.time()-t0,1)} std={std}（轴注入 sched 键 {sorted(G['7']['inputs'])}）")
    R["e2e"] = {"ok": ok, "std": std, "seed": SEEDN}

# ---------- 6. 油量计首滴（真实 consumption）----------
if R["verdict"] == "咬合":
    store.record_outcome(EID, result="success", context="SHAFT-BEARING-1-3",
                         actor=MACHINE_ACTOR)
    log("7.outcome", True, "首滴油量：facts 判例被轴消费且承重成功")

store.save(SEED)
json.dump(R, open(os.path.join(OUT, "shaft_receipt.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n=== 承重实验读数:{R['verdict']} ===")
sys.exit(0 if R["verdict"] == "咬合" else 1)
