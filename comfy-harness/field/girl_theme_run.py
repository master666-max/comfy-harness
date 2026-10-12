# -*- coding: utf-8 -*-
"""girl_theme_run.py — 白毛美少女双臂（用户点题 · 20261005）

复用 noobai_lora_style.py 骨架：基线 vs NOOB_vp1_detailer LoRA，同 seed 同题。
纯出图件：预检+双臂+落盘+非空白验证，无判别门（点题件非实验件）。
"""
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CKPT = "NoobAI-XL-Vpred-v1.0.safetensors"
LORA = "NOOB_vp1_detailer_by_volnovik_v1.safetensors"
SEED = 26100503
POS = ("1girl, solo, white hair, long hair, hair between eyes, blue eyes, hair ornament, "
       "frills, white dress, looking at viewer, upper body, outdoors, night, starry sky, moonlight, "
       "masterpiece, best quality, very aesthetic, absurdres")
NEG = "lowres, worst quality, bad quality, jpeg artifacts, signature, watermark, username, text"
ok_all = True


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post(path, payload, timeout=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


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
                                                    "filename_prefix": f"girl_{'lora' if use_lora else 'base'}"}},
    }
    if use_lora:
        g["9"] = {"class_type": "LoraLoader",
                  "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": LORA,
                             "strength_model": 1.0, "strength_clip": 1.0}}
    return g


schema = get("/object_info/CheckpointLoaderSimple")["CheckpointLoaderSimple"]
legal = set(schema["input"]["required"]) | set(schema["input"].get("optional", {}))
assert set(graph(False)["1"]["inputs"]) <= legal

R = {"seed": SEED, "pos": POS, "arms": {}}
for arm, use in (("base", False), ("lora", True)):
    t0 = time.time()
    pid = post("/prompt", {"prompt": graph(use), "client_id": "girl-theme"})["prompt_id"]
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
    ok_all = ok_all and ok
    fn = None
    if ok:
        o = final["outputs"].get("8", {}).get("images", [])
        if o:
            fn = o[0]["filename"]
            sub = o[0].get("subfolder", "")
            with urllib.request.urlopen(
                    f"{BASE}/view?filename={fn}&subfolder={sub}&type=output", timeout=60) as r:
                open(os.path.join(OUT, f"girl_{arm}.png"), "wb").write(r.read())
    from PIL import Image
    std = None
    if fn:
        im = Image.open(os.path.join(OUT, f"girl_{arm}.png")).convert("L")
        px = list(im.getdata())
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        std = round(var ** 0.5, 1)
    print(f"[{'OK' if ok and (std or 0) > 10 else 'NO'}] {arm} sec={round(time.time()-t0,1)} "
          f"file=girl_{arm}.png std={std}")
    R["arms"][arm] = {"status": "ok" if ok else "fail", "sec": round(time.time() - t0, 1)}

json.dump(R, open(os.path.join(OUT, "girl_receipt.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("完成" if ok_all else "有失败臂")
