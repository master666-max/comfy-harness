# -*- coding: utf-8 -*-
"""cinematic_gen.py — 电影感两段式出图器（默认 4 抽 · 20261007 维护者令 · v2 加影调工艺）

标准管线（承 P-noobai-cinematic-recipe + P-noobai-facedetailer-pipeline 两判例）：
  一段组合 pass：质控组+题材词，cfg 4.5 / euler / normal / 28 步 / 832×1216
  面部二道：FaceDetailer guide 640 / denoise 0.6 / cfg 5.5 / euler+simple（眼词在正词里）
  影调工艺（v2 · 治 AI 蜡感）：胶片颗粒+微色散+暗角+轻对比——照后即处理，落盘即成品
默认 4 抽随机 seed；产出入 field/out/，文件名 <prefix>_<seed>.png。

用法：py cinematic_gen.py --prefix fireworks --pos "题材词..." [--seeds 4] [--start-seed N] [--no-grain]
"""
import argparse, json, random, time, urllib.request

BASE = "http://127.0.0.1:8188"
# v3（20261007 · 官方模型卡逐字对齐）：质控组补 highres/safe；负词换官方全表
QUALITY = "masterpiece, best quality, newest, absurdres, very awa, highres, safe"
NEG_DEFAULT = ("nsfw, worst quality, old, early, low quality, lowres, signature, username, "
               "logo, bad hands, mutated hands, mammal, anthro, furry, ambiguous form, "
               "feral, semi-anthro, empty background, sparse, plain background")


def film_treat(src, dst, grain=5.5, ca_px=1, vignette=0.10, contrast=1.05):
    """影调工艺（v2）：拆数码蜡感。numpy+PIL 纯本地，零模型成本。"""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    import numpy as np
    im = Image.open(src).convert("RGB")
    arr = np.asarray(im).astype(np.float32)
    if grain > 0:
        arr += np.random.normal(0, grain, arr.shape)
    arr = 255.0 * ((arr / 255.0 - 0.5) * contrast + 0.5)
    im2 = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if ca_px > 0:
        r, g, b = im2.split()
        im2 = Image.merge("RGB", (ImageChops.offset(r, ca_px, 0), g,
                                  ImageChops.offset(b, -ca_px, 0)))
    if vignette > 0:
        w, h = im2.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).ellipse((-int(w*0.25), -int(h*0.25), int(w*1.25), int(h*1.25)), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.18)))
        im2 = Image.composite(im2, Image.blend(im2, Image.new("RGB", (w, h), (0, 0, 0)), vignette), mask)
    im2.save(dst)


def graph(seed, pos, neg, prefix):
    """v3 五段图：1段组合pass → hires放大重绘 → 面部二道 → 手部二道 → (落盘后影调工艺)"""
    return {
     "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "NoobAI-XL-Vpred-v1.0.safetensors"}},
     "3": {"class_type": "ModelSamplingDiscrete", "inputs": {"sampling": "v_prediction", "zsnr": True, "model": ["1", 0]}},
     "4": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["1", 1]}},
     "5": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
     "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
     "7": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 32, "cfg": 4.8, "sampler_name": "euler",
                                                "scheduler": "normal", "denoise": 1.0, "model": ["3", 0],
                                                "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0]}},
     "13": {"class_type": "LatentUpscale", "inputs": {"samples": ["7", 0], "upscale_method": "nearest-exact",
                                                      "width": 1248, "height": 1824, "crop": "disabled"}},
     "14": {"class_type": "KSampler", "inputs": {"seed": seed + 1, "steps": 15, "cfg": 4.8, "sampler_name": "euler",
                                                 "scheduler": "normal", "denoise": 0.45, "model": ["3", 0],
                                                 "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["13", 0]}},
     "8": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["1", 2]}},
     "10": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face_yolov8m.pt"}},
     "15": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/hand_yolov8s.pt"}},
     "11": {"class_type": "FaceDetailer", "inputs": {
         "image": ["8", 0], "model": ["3", 0], "clip": ["1", 1], "vae": ["1", 2],
         "guide_size": 640, "guide_size_for": True, "max_size": 1024,
         "seed": seed, "steps": 28, "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple",
         "positive": ["4", 0], "negative": ["5", 0], "denoise": 0.6, "feather": 5,
         "noise_mask": True, "force_inpaint": True, "bbox_threshold": 0.5, "bbox_dilation": 10,
         "bbox_crop_factor": 3.0, "sam_detection_hint": "center-1", "sam_dilation": 0,
         "sam_threshold": 0.93, "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
         "sam_mask_hint_use_negative": "False", "drop_size": 10, "bbox_detector": ["10", 0],
         "wildcard": "", "cycle": 1}},
     "16": {"class_type": "FaceDetailer", "inputs": {
         "image": ["11", 0], "model": ["3", 0], "clip": ["1", 1], "vae": ["1", 2],
         "guide_size": 512, "guide_size_for": True, "max_size": 1024,
         "seed": seed, "steps": 24, "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple",
         "positive": ["4", 0], "negative": ["5", 0], "denoise": 0.55, "feather": 5,
         "noise_mask": True, "force_inpaint": True, "bbox_threshold": 0.4, "bbox_dilation": 8,
         "bbox_crop_factor": 2.5, "sam_detection_hint": "center-1", "sam_dilation": 0,
         "sam_threshold": 0.93, "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
         "sam_mask_hint_use_negative": "False", "drop_size": 10, "bbox_detector": ["15", 0],
         "wildcard": "", "cycle": 1}},
     "9": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": prefix}},
    }


def post(path, payload, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--pos", required=True)
    ap.add_argument("--neg", default=NEG_DEFAULT)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--start-seed", type=int, default=None)
    ap.add_argument("--no-grain", action="store_true")
    args = ap.parse_args()
    pos = args.pos if args.pos.startswith("masterpiece") else f"{QUALITY}, {args.pos}"
    seeds = ([args.start_seed + i for i in range(args.seeds)] if args.start_seed
             else [random.randint(10**8, 10**9 - 1) for _ in range(args.seeds)])
    print(f"两段式 {len(seeds)} 抽: {seeds}")
    for seed in seeds:
        t0 = time.time()
        pid = post("/prompt", {"prompt": graph(seed, pos, args.neg, f"{args.prefix}_{seed}"),
                               "client_id": "cinematic-gen"})["prompt_id"]
        e = None
        for _ in range(480):
            h = get(f"/history/{pid}")
            if pid in h and (h[pid]["status"].get("completed") or h[pid]["status"].get("status_str") == "error"):
                e = h[pid]; break
            time.sleep(1)
        ok = bool(e) and e["status"]["status_str"] == "success"
        fname = None
        if ok:
            o = e["outputs"]["9"]["images"][0]
            fname = f"out/{args.prefix}_{seed}.png"
            with urllib.request.urlopen(f"{BASE}/view?filename={o['filename']}&subfolder={o.get('subfolder','')}&type=output", timeout=60) as r:
                open(fname, "wb").write(r.read())
            if not args.no_grain:
                film_treat(fname, fname)               # v2 影调工艺照后即处理
        print(f"seed {seed}: {'OK ' + str(round(time.time()-t0,1)) + 's → ' + fname if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
