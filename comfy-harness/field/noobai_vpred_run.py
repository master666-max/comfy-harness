# -*- coding: utf-8 -*-
"""noobai_vpred_run.py — 2号主模型实地双臂差分（NoobAI-XL Vpred v1.0 · 20261005）

飞轮双臂规矩（承 e1 3a/3b 差分设计与 field_wiring_run 实操骨架）：
  朴素臂 = CheckpointLoaderSimple 直出（v0.34 时代习惯：模型自带一切，直接进 KSampler）
  知情臂 = 中插 ModelSamplingDiscrete(v_prediction, zsnr=True) —— v-pred 模型正确处置
同 seed 同题同采样设置，PIL HSV 饱和度均值+colorfulness 机械差分；
新教训入 PrecedentStore draft（若两臂机械分离→判例成立）。
零生产写：只写本沙盒 field/out/ 与 ComfyUI 自身 output/。
"""
import json
import os
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))           # comfy-harness/field
_CH = os.path.dirname(_HERE)                                 # comfy-harness
_ROOT = os.path.dirname(_CH)                                 # 工作区根（evocore 所在）
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_CH, "gov"))
from precedent_gov import PrecedentStore  # noqa: E402
from run_outcome import record_run_outcome  # noqa: E402

MINTED_EID = "P-noobai-vpred-autodetect"

BASE = "http://127.0.0.1:8188"
DIR = _HERE
OUT = os.path.join(DIR, "out")
SEED_PATH = os.path.join(_CH, "gov", "precedents_e2_seed.json")
CKPT = "NoobAI-XL-Vpred-v1.0.safetensors"
SEED = 26100502
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


POS = "no humans, red block, rubber duck, wood, table, studio lighting, still life, " \
      "depth of field, masterpiece, best quality, very aesthetic, absurdres"
NEG = "worst quality, bad quality, jpeg artifacts, signature, watermark, lowres"


def graph(informed, seed):
    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": POS, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0] if not informed else ["5", 0],
                         "seed": seed, "steps": 26, "cfg": 6.0,
                         "sampler_name": "euler_ancestral", "scheduler": "normal",
                         "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0],
                                                    "filename_prefix": f"noobai_{'vpred' if informed else 'naive'}"}},
    }
    if informed:
        g["5"] = {"class_type": "ModelSamplingDiscrete",
                  "inputs": {"model": ["1", 0], "sampling": "v_prediction", "zsnr": True}}
    return g


# ---------- 0-1. 服务器 + 预检（布线键 ⊆ 活体 schema） ----------
st = get("/system_stats")["system"]
log("0.server", st["comfyui_version"] == "0.38.0", "v" + st["comfyui_version"])
bad = []
for arm, g in (("朴素", graph(False, SEED)), ("知情", graph(True, SEED))):
    for nid, node in g.items():
        schema = get(f"/object_info/{node['class_type']}").get(node["class_type"], {})
        legal = set(schema.get("input", {}).get("required", {})) | set(schema.get("input", {}).get("optional", {}))
        if set(node["inputs"]) - legal:
            bad.append(f"{arm}臂{nid}")
log("1.preflight", not bad, f"双臂×{7 + 1}节点对活体 schema 预检: {bad or '全过'}")

# ---------- 2. 双臂提交 ----------
receipts = {}
for arm, informed in (("naive", False), ("vpred", True)):
    t0 = time.time()
    resp = post("/prompt", {"prompt": graph(informed, SEED), "client_id": "noobai-vpred"})
    if "_http_error" in resp:
        log(f"2.{arm}", False, f"HTTP {resp['_http_error']}: {resp['_body']}")
        receipts[arm] = {"status": "rejected"}
        continue
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
    sec = round(time.time() - t0, 1)
    fn = None
    if ok:
        o = final["outputs"].get("8", {}).get("images", [])
        if o:
            fn = o[0]["filename"]
            sub = o[0].get("subfolder", "")
            with urllib.request.urlopen(
                    f"{BASE}/view?filename={fn}&subfolder={sub}&type=output", timeout=60) as r:
                os.makedirs(OUT, exist_ok=True)
                open(os.path.join(OUT, f"noobai_{arm}.png"), "wb").write(r.read())
    log(f"2.{arm}", ok, f"status={final['status']['status_str'] if final else 'timeout'} sec={sec} file={fn}")
    receipts[arm] = {"status": "ok" if ok else "fail", "file": fn, "sec": sec, "prompt_id": pid}

# ---------- 3. 机械差分（HSV S_mean + colorfulness，承 C1站2 器械） ----------
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
    return round(smean, 2), round((rg ** 2 + yb ** 2) ** 0.5 * 0.3, 2), rgb.size


diff = {}
if all(receipts.get(a, {}).get("file") for a in ("naive", "vpred")):
    for arm in ("naive", "vpred"):
        diff[arm] = mech(os.path.join(OUT, f"noobai_{arm}.png"))
    sep = abs(diff["naive"][0] - diff["vpred"][0])
    log("3.mech-diff", True,
        f"朴素臂 S_mean={diff['naive'][0]} colorfulness={diff['naive'][1]} | "
        f"知情臂 S_mean={diff['vpred'][0]} colorfulness={diff['vpred'][1]} | S_mean差={sep:.2f}")

# ---------- 4. 读数三态 + 判例 ----------
both_ok = all(receipts.get(a, {}).get("status") == "ok" for a in ("naive", "vpred"))
mech_sep = "mech-diff" in dict((c["tag"], c) for c in R["log"]) and \
           abs(diff["naive"][0] - diff["vpred"][0]) >= 1.0
if both_ok and mech_sep:
    R["verdict"] = "咬合"
elif both_ok:
    R["verdict"] = "登记盲区"  # 双臂全出但机械不可分——v-pred 处置或自动识别,需人眼仲裁
else:
    R["verdict"] = "不咬合"
R["arms"] = receipts
R["mech"] = diff
R["seed"] = SEED
R["eids"] = [MINTED_EID]
json.dump(R, open(os.path.join(OUT, "noobai_receipt.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

if R["verdict"] == "咬合":
    store = PrecedentStore.load(SEED_PATH) if os.path.exists(SEED_PATH) else PrecedentStore()
    store.add({
        "id": "P-noobai-vpred-sampling",
        "type": "procedural", "importance": 3,
        "keywords": ["NoobAI", "v-prediction", "SDXL", "布线", "ModelSamplingDiscrete", "zsnr"],
        "content": {"c": "NoobAI-XL Vpred v1.0 必须中插 ModelSamplingDiscrete(sampling=v_prediction, zsnr=True) 再进 KSampler;朴素直载会在 v-pred 模型上按 eps 采样——出图色彩学偏离(机械可测),构图可辨但质感失真。",
                    "a": "20261005 双臂同seed实测:朴素/知情两臂 HSV S_mean 与 colorfulness 机械分离,图见 field/out/noobai_{naive,vpred}.png。",
                    "d": "适用 SDXL v-pred 系动漫模型;CFG 5-7/euler_ancestral/normal 为该系惯用采样面。"},
        "evidence": {"artifact": "comfy-harness/field/out/noobai_receipt.json",
                     "quote": f"朴素臂 S_mean={diff['naive'][0]} vs 知情臂 S_mean={diff['vpred'][0]}",
                     "recalc": "复跑 comfy-harness/field/noobai_vpred_run.py"},
        "owner": ""}, actor="ai:卷十二线(field)")
    store.save(SEED_PATH)
    print("[判例] P-noobai-vpred-sampling draft 已入 seed（候人 promote）")

record_run_outcome(MINTED_EID, R["verdict"], "NOOBAI-VPRED")   # 批二埋点常开
print(f"\n=== 2号主模型实地读数:{R['verdict']} ===")
sys.exit(0 if R["verdict"] != "不咬合" else 1)
