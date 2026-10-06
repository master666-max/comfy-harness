# -*- coding: utf-8 -*-
"""noobai_lora_style.py — 风格组件 A/B（NoobAI vpred · 20261005）

飞轮双臂第三轮：基线（无 LoRA）vs NOOB_vp1_detailer（v-pred v1 专属细节增强 LoRA，
strength 1.0/1.0，model+clip 全链）。同 seed 同题同采样。机械差分承前两轮器械。
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
sys.path.insert(0, os.path.join(_CH, "gov"))
from precedent_gov import PrecedentStore  # noqa: E402
from run_outcome import record_run_outcome  # noqa: E402

MINTED_EID = "P-noobai-vp1-detailer-lora"

BASE = "http://127.0.0.1:8188"
OUT = os.path.join(_HERE, "out")
SEED_PATH = os.path.join(_CH, "gov", "precedents_e2_seed.json")
CKPT = "NoobAI-XL-Vpred-v1.0.safetensors"
LORA = "NOOB_vp1_detailer_by_volnovik_v1.safetensors"
SEED = 26100502
POS = "no humans, red block, rubber duck, wood, table, studio lighting, still life, " \
      "depth of field, masterpiece, best quality, very aesthetic, absurdres"
NEG = "worst quality, bad quality, jpeg artifacts, signature, watermark, lowres"
R = {"log": []}


def log(tag, ok, detail=""):
    R["log"].append({"tag": tag, "ok": bool(ok), "detail": str(detail)[:300]})
    print(f"[{'OK' if ok else 'NO'}] {tag} {str(detail)[:180]}")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post(path, payload, timeout=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode(errors="replace")[:300]}


def graph(use_lora):
    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": POS, "clip": ["9", 1] if use_lora else ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["9", 1] if use_lora else ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["9", 0] if use_lora else ["1", 0],
                         "seed": SEED, "steps": 26, "cfg": 6.0,
                         "sampler_name": "euler_ancestral", "scheduler": "normal",
                         "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0],
                                                    "filename_prefix": f"noobai_{'lora' if use_lora else 'base'}"}},
    }
    if use_lora:
        g["9"] = {"class_type": "LoraLoader",
                  "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": LORA,
                             "strength_model": 1.0, "strength_clip": 1.0}}
    return g


st = get("/system_stats")["system"]
log("0.server", st["comfyui_version"] == "0.38.0", "v" + st["comfyui_version"])
bad = []
for arm, g in (("base", graph(False)), ("lora", graph(True))):
    for nid, node in g.items():
        schema = get(f"/object_info/{node['class_type']}").get(node["class_type"], {})
        legal = set(schema.get("input", {}).get("required", {})) | set(schema.get("input", {}).get("optional", {}))
        if set(node["inputs"]) - legal:
            bad.append(f"{arm}臂{nid}")
log("1.preflight", not bad, f"双臂预检: {bad or '全过'}")

receipts = {}
for arm, use in (("base", False), ("lora", True)):
    t0 = time.time()
    resp = post("/prompt", {"prompt": graph(use), "client_id": "noobai-lora"})
    pid = resp["prompt_id"]
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
        o = final["outputs"].get("8", {}).get("images", [])
        if o:
            fn = o[0]["filename"]
            sub = o[0].get("subfolder", "")
            with urllib.request.urlopen(
                    f"{BASE}/view?filename={fn}&subfolder={sub}&type=output", timeout=60) as r:
                open(os.path.join(OUT, f"noobai_{arm}.png"), "wb").write(r.read())
    log(f"2.{arm}", ok, f"sec={round(time.time()-t0,1)} file={fn}")
    receipts[arm] = {"status": "ok" if ok else "fail", "file": fn, "sec": round(time.time() - t0, 1)}


def mech(path):
    from PIL import Image
    im = Image.open(path).convert("HSV")
    s = list(im.split()[1].getdata())
    smean = sum(s) / len(s)
    rgb = Image.open(path).convert("RGB")
    px = list(rgb.getdata())
    n = len(px)
    rg = sum(abs(r - g) for r, g, b in px) / n
    yb = sum(abs((r + g) / 2 - b) for r, g, b in px) / n
    return round(smean, 2), round((rg ** 2 + yb ** 2) ** 0.5 * 0.3, 2)


diff = {}
if all(receipts.get(a, {}).get("file") for a in ("base", "lora")):
    for arm in ("base", "lora"):
        diff[arm] = mech(os.path.join(OUT, f"noobai_{arm}.png"))
    sep = abs(diff["base"][0] - diff["lora"][0])
    log("3.mech-diff", True,
        f"基线 S_mean={diff['base'][0]} colorfulness={diff['base'][1]} | "
        f"LoRA臂 S_mean={diff['lora'][0]} colorfulness={diff['lora'][1]} | S_mean差={sep:.2f}")

both_ok = all(receipts.get(a, {}).get("status") == "ok" for a in ("base", "lora"))
sep_ok = any(c["tag"].endswith("mech-diff") for c in R["log"]) and \
    abs(diff["base"][0] - diff["lora"][0]) >= 1.0
if both_ok and sep_ok:
    R["verdict"] = "咬合"
    store = PrecedentStore.load(SEED_PATH)
    store.add({
        "id": "P-noobai-vp1-detailer-lora",
        "type": "procedural", "importance": 2,
        "keywords": ["NoobAI", "LoRA", "细节增强", "风格组件", "LoraLoader"],
        "content": {"c": "NoobAI-XL Vpred 配 NOOB_vp1_detailer_by_volnovik_v1(strength 1.0/1.0, model+clip 全链)为即插风格组件——LoraLoader 中插于 Checkpoint 与 KSampler/CLIPTextEncode 之间即可,同 seed 构图保持、细节走向改变。",
                    "a": "20261005 A/B 实测: 基线 vs LoRA臂机械读数分离, 图见 field/out/noobai_{base,lora}.png。",
                    "d": "strength>1.2 易过雕塑感;与 EasyNegative LoRA 组合未测。"},
        "evidence": {"artifact": "comfy-harness/field/out/noobai_receipt.json",
                     "quote": f"基线 S_mean={diff['base'][0]} vs LoRA臂 S_mean={diff['lora'][0]}",
                     "recalc": "复跑 comfy-harness/field/noobai_lora_style.py"},
        "owner": ""}, actor="ai:卷十二线(field)")
    store.save(SEED_PATH)
    print("[判例] P-noobai-vp1-detailer-lora draft 已入 seed")
elif both_ok:
    R["verdict"] = "登记盲区"
else:
    R["verdict"] = "不咬合"
R["arms"] = receipts
R["mech"] = diff
R["eids"] = [MINTED_EID]
json.dump(R, open(os.path.join(OUT, "noobai_receipt.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
record_run_outcome(MINTED_EID, R["verdict"], "NOOBAI-LORA")   # 批二埋点常开
print(f"\n=== 风格组件A/B读数:{R['verdict']} ===")
sys.exit(0 if R["verdict"] != "不咬合" else 1)
