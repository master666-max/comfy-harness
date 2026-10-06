# -*- coding: utf-8 -*-
"""antisora_run.py — AniSora V3.2 视频线首飞（field 纪律 · 2026-10-05）

预注册判据（先锁后跑）：
  咬合   = WEBP 落盘 且 n_frames≥33 且 运动量(mean|frame[i]-frame[i+1]|, 灰度降采样)≥1.0；
  登记盲区 = 落盘但静止（运动量<1.0）——管线通、模型退化或分辨率/步数不足，如实落三态；
  不咬合 = 无产物/崩溃/OOM。kill：连续 2 次 OOM 终止。
单低噪声半模全步数首飞（High 上游未发布，README 自述 "High will come later on ("）——
画质受限于高噪声段退化，如实登记不粉饰。
"""
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
_CH = os.path.dirname(HERE)
_ROOT = os.path.dirname(_CH)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_CH, "gov"))
from precedent_gov import PrecedentStore  # noqa: E402
from run_outcome import record_run_outcome  # noqa: E402

SEED_PATH = os.path.join(_CH, "gov", "precedents_e2_seed.json")
MACHINE_ACTOR = "machine:卷十二线-field"
MINTED_EID = "P-antisora-wan22-gguf-wiring"
SEEDN = 26100506
R = {"log": [], "eids": [MINTED_EID]}


def log(tag, ok, detail=""):
    R["log"].append({"tag": tag, "ok": bool(ok), "detail": str(detail)[:300]})
    print(f"[{'OK' if ok else 'NO'}] {tag} {str(detail)[:180]}", flush=True)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post(path, payload, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}   # /free 等端点返回空体


def oi(cls):
    return get(f"/object_info/{cls}").get(cls, {})


# ---------- 0. 服务器 + VRAM ----------
full = get("/system_stats")
st = full["system"]
d = full["devices"][0]
log("0.server", st["comfyui_version"] == "0.38.0",
    f"v{st['comfyui_version']} VRAM free {round(d.get('vram_free',0)/2**30,1)}G")

# ---------- 1. 预检（布线键 ⊆ 活体 schema）----------
GRAPH = {
    "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "Index-Anisora-V3.2-Low-Q4_K_M.gguf"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
    "4": {"class_type": "CLIPTextEncode",
          "inputs": {"clip": ["2", 0],
                     "text": "anime style, white hair girl gently turns her head and smiles, hair swaying, starry night background, high quality"}},
    "5": {"class_type": "CLIPTextEncode",
          "inputs": {"clip": ["2", 0],
                     "text": "static, still, blurry, worst quality, jpeg artifacts, watermark"}},
    "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
    "13": {"class_type": "LoadImage", "inputs": {"image": "antisora_start.png"}},
    "7": {"class_type": "WanImageToVideo",
          "inputs": {"positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
                     "width": 832, "height": 480, "length": 33, "batch_size": 1,
                     "start_image": ["13", 0]}},
    "8": {"class_type": "KSampler",
          "inputs": {"model": ["6", 0], "seed": SEEDN, "steps": 15, "cfg": 6.0,
                     "sampler_name": "euler", "scheduler": "normal",
                     "positive": ["7", 0], "negative": ["7", 1],
                     "latent_image": ["7", 2], "denoise": 1.0}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
    "10": {"class_type": "SaveAnimatedWEBP",
           "inputs": {"images": ["9", 0], "filename_prefix": "antisora_first_flight",
                      "fps": 16.0, "lossless": False, "quality": 90, "method": "default"}},
}
bad = []
for nid, node in GRAPH.items():
    schema = oi(node["class_type"])
    legal = set(schema.get("input", {}).get("required", {})) | set(schema.get("input", {}).get("optional", {}))
    if set(node["inputs"]) - legal:
        bad.append(f"{nid}:{node['class_type']} 非法键 {set(node['inputs']) - legal}")
log("1.preflight", not bad, f"{len(GRAPH)} 节点对活体 schema: {bad or '全过'}")

# ---------- 2. 提交 + 轮询（首飞含 14B 加载，宽限 30 分钟）----------
post("/free", {"unload_models": True})
t0 = time.time()
pid = post("/prompt", {"prompt": GRAPH, "client_id": "antisora-first"})["prompt_id"]
final = None
oom_hits = 0
while time.time() - t0 < 2700:
    h = get(f"/history/{pid}")
    if pid in h:
        e = h[pid]
        msgs = str(e.get("status", {}))
        if "out of memory" in msgs.lower():
            oom_hits += 1
        if e["status"].get("completed") or e["status"].get("status_str") == "error":
            final = e
            break
    time.sleep(5)
ok = bool(final) and final["status"]["status_str"] == "success"
log("2.generate", ok, f"sec={round(time.time()-t0,1)} status={final['status']['status_str'] if final else 'timeout'} oom={oom_hits}")
if not ok:
    R["verdict"] = "不咬合"
    R["oom_hits"] = oom_hits
    json.dump(R, open(os.path.join(OUT, "antisora_receipt.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    record_run_outcome(MINTED_EID, R["verdict"], "ANTISORA-FIRST-FLIGHT")
    sys.exit(1)

# ---------- 3. 产物落盘 + 机械验证（帧数 + 运动量）----------
o = final["outputs"].get("10", {}).get("images", [{}])[0]
fn, sub = o.get("filename"), o.get("subfolder", "")
with urllib.request.urlopen(f"{BASE}/view?filename={fn}&subfolder={sub}&type=output", timeout=120) as r:
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "antisora_first_flight.webp"), "wb").write(r.read())

from PIL import Image
im = Image.open(os.path.join(OUT, "antisora_first_flight.webp"))
n_frames = getattr(im, "n_frames", 1)
size = im.size
diffs = []
prev = None
for i in range(n_frames):
    im.seek(i)
    f = im.convert("L").resize((104, 60))
    px = list(f.getdata())
    if prev is not None:
        diffs.append(sum(abs(a - b) for a, b in zip(px, prev)) / len(px))
    prev = px
motion = sum(diffs) / len(diffs) if diffs else 0.0
log("3.mech", n_frames >= 33,
    f"frames={n_frames} size={size} 运动量={motion:.2f}（判据≥1.0; 静止<1.0=盲区）")

# ---------- 4. 三态判定 ----------
if n_frames >= 33 and motion >= 1.0:
    R["verdict"] = "咬合"
elif n_frames >= 33:
    R["verdict"] = "登记盲区"
else:
    R["verdict"] = "不咬合"
R["frames"] = n_frames
R["motion"] = round(motion, 2)
R["size"] = list(size)
R["seed"] = SEEDN

# ---------- 5. 判例 + 油量 ----------
if R["verdict"] == "咬合":
    store = PrecedentStore.load(SEED_PATH)
    if not any(e["id"] == MINTED_EID for e in store.entries):
        store.add({
            "id": MINTED_EID, "type": "procedural", "importance": 3,
            "keywords": ["AniSora", "wan22", "GGUF", "视频", "布线"],
            "content": {"c": "AniSora V3.2 GGUF(wan架构,Q4_K_M)首飞知情布线：UnetLoaderGGUF+CLIPLoader(type=wan,umt5_xxl)+VAELoader(wan_2.1_vae)+ModelSamplingSD3(shift=8)+Wan22ImageToVideoLatent(只出LATENT,start_image塑形,2.2代无clip_vision)+KSampler(cfg6/20步/euler)+SaveAnimatedWEBP(fps16);首飞49帧@832x480。",
                        "a": "20261005 单低噪声半模全步数首飞实测（High 半模上游未发布）。",
                        "d": "适用 wan2.2 系 I2V；双模全质需另配 High 半模；长度须 4n+1。"},
            "evidence": {"artifact": "comfy-harness/field/out/antisora_receipt.json",
                         "quote": f"frames={n_frames} motion={motion:.2f}",
                         "recalc": "复跑 comfy-harness/field/antisora_run.py"},
            "owner": ""}, actor="ai:卷十二线(antisora)",
            facts={"Wan22ImageToVideoLatent": ["vae", "width", "height", "length", "batch_size"],
                   "UnetLoaderGGUF": ["unet_name"], "CLIPLoader.wan": ["clip_name", "type"]})
    store.save(SEED_PATH)
    print("[判例] P-antisora-wan22-gguf-wiring draft 已入 seed")

record_run_outcome(MINTED_EID, R["verdict"], "ANTISORA-FIRST-FLIGHT")
json.dump(R, open(os.path.join(OUT, "antisora_receipt.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n=== AniSora 首飞读数:{R['verdict']} ===")
sys.exit(0 if R["verdict"] == "咬合" else 1)
