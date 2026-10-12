# -*- coding: utf-8 -*-
"""flux_gen.py — FLUX.2 Klein 4B 直出器（第二后端 · 自然语言/官方原文提示词）。

与 cinematic_gen（NoobAI v3 五段）并立的第二后端：BFL 新架构，写实/电影/自然比例
上限（20261008 原封上限测试实证）。提示词=自然语言（Qwen3-4B 文本塔），tag 体系不通用。
图谱克隆自 field_wiring_run 已验证布线（4 步蒸馏 cfg 1.0，SamplerCustom+Flux2Scheduler）。

用法：py -X utf8 flux_gen.py --prefix bfl_coast [--pos …] [--seeds 4] [--start-seed N]
      [--width 1024] [--height 1024] [--guidance 4.0]
产物：out/<prefix>_<seed>.png（.gitignore 图证政策内）。
"""
import argparse
import json
import random
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8188"


def graph(seed, pos, width, height, guidance, steps, prefix):
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "flux-2-klein-4b.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": pos}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": guidance}},
        "7": {"class_type": "Flux2Scheduler", "inputs": {"steps": steps, "width": width, "height": height}},
        "8": {"class_type": "EmptyFlux2LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "SamplerCustom",
               "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": seed, "cfg": 1.0,
                          "positive": ["6", 0], "negative": ["5", 0], "sampler": ["9", 0],
                          "sigmas": ["7", 0], "latent_image": ["8", 0]}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "12": {"class_type": "SaveImage",
               "inputs": {"images": ["11", 0], "filename_prefix": f"{prefix}_{seed}"}},
    }


def post(path, payload, timeout=300):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description="FLUX.2 Klein 直出器（第二后端）")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--pos", required=True, help="自然语言提示词（原封官方原文/自撰皆可）")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=1024)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--start-seed", type=int, default=None)
    ap.add_argument("--guidance", type=float, default=4.0)
    ap.add_argument("--steps", type=int, default=4)
    a = ap.parse_args()
    seeds = ([a.start_seed + i for i in range(a.seeds)] if a.start_seed is not None
             else [random.randint(10**8, 10**9 - 1) for _ in range(a.seeds)])
    print(f"Klein {len(seeds)} 抽: {seeds} · {a.width}x{a.height} · g{a.guidance}/{a.steps}步")
    for seed in seeds:
        t0 = time.time()
        pid = post("/prompt", {"prompt": graph(seed, a.pos, a.width, a.height, a.guidance, a.steps, a.prefix),
                               "client_id": "flux-gen"})["prompt_id"]
        e = None
        for _ in range(600):
            h = get(f"/history/{pid}")
            if pid in h and (h[pid]["status"].get("completed")
                             or h[pid]["status"].get("status_str") == "error"):
                e = h[pid]
                break
            time.sleep(0.5)
        ok = bool(e) and e["status"]["status_str"] == "success"
        if ok:
            o = e["outputs"]["12"]["images"][0]
            with urllib.request.urlopen(f"{BASE}/view?filename={o['filename']}"
                                        f"&subfolder={o.get('subfolder','')}&type=output",
                                        timeout=60) as r:
                data = r.read()
            fn = f"out/{a.prefix}_{seed}.png"
            open(fn, "wb").write(data)
            print(f"seed {seed}: OK {time.time()-t0:.1f}s → {fn}")
        else:
            print(f"seed {seed}: FAIL {str(e.get('status',{}))[:150] if e else 'timeout'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
