# -*- coding: utf-8 -*-
"""field_wiring_run.py — 飞轮断点A/C 实地补课（卷十二 · 20261005）

目的：操作→记录→提炼skill→复用 四环在真实生成上闭环一次。
复用：s1-flux2sched-v038-wiring 的 schema_facts（Flux2Scheduler=[steps,width,height]）
      先对活体 /object_info 断言命中，再布线——知情布线，非朴素先验。
布线源：节点 schema 全部来自活体 object_info 实测（20261005 预检记录），
        klein 蒸馏 4 步（承 20261002 桌面版成功运行史 4/4 it）。
零生产写：只写本沙盒 field/out/ 与 ComfyUI 自身 output/（工具正常行为）。
判例治理：新教训走 PrecedentStore.add（draft，owner 空，候人 promote）+ save 落盘。
"""
import json
import os
import random
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "comfy-harness", "gov"))
from precedent_gov import PrecedentStore  # noqa: E402
from run_outcome import record_run_outcome  # noqa: E402

MINTED_EID = "P-field-wiring-flux2-klein"

BASE = "http://127.0.0.1:8188"
DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "out")
SEED_PATH = os.path.join(_ROOT, "comfy-harness", "gov", "precedents_e2_seed.json")
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


# ---------- 0. 服务器身份 ----------
st = get("/system_stats")["system"]
log("0.server", st["comfyui_version"] == "0.38.0", "v" + st["comfyui_version"])

# ---------- 1. schema_facts 复用：活体验证 s1 判例 ----------
live = get("/object_info/Flux2Scheduler")["Flux2Scheduler"]["input"]["required"]
facts_hit = list(live) == ["steps", "width", "height"]
log("1.schema-facts-reuse", facts_hit,
    f"s1-flux2sched-v038-wiring 判例 [steps,width,height] 对活体逐字命中={facts_hit}")

# ---------- 2. 知情布线（全键来自活体 object_info 预检 20261005）----------
SEED = 20261005
GRAPH = {
    "1": {"class_type": "UNETLoader",
          "inputs": {"unet_name": "flux-2-klein-4b.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader",
          "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
    "4": {"class_type": "CLIPTextEncode",
          "inputs": {"clip": ["2", 0],
                     "text": "a red cube on a wooden desk beside a yellow rubber duck, studio lighting, product photo"}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
    "6": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 4.0}},
    "7": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": 1024, "height": 1024}},
    "8": {"class_type": "EmptyFlux2LatentImage",
          "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    "10": {"class_type": "SamplerCustom",
           "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": SEED, "cfg": 1.0,
                      "positive": ["6", 0], "negative": ["5", 0], "sampler": ["9", 0],
                      "sigmas": ["7", 0], "latent_image": ["8", 0]}},
    "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
    "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "field_wiring"}},
}

# ---------- 3. 预检：布线键 ⊆ 活体 required∪optional（s1 教训流程化）----------
bad = []
for nid, node in GRAPH.items():
    cls = node["class_type"]
    schema = get(f"/object_info/{cls}").get(cls, {})
    if not schema:
        bad.append(f"{nid}:{cls} 活体无此节点")
        continue
    legal = set(schema["input"]["required"]) | set(schema["input"].get("optional", {}))
    illegal = set(node["inputs"]) - legal
    if illegal:
        bad.append(f"{nid}:{cls} 非法输入 {sorted(illegal)}")
log("3.preflight-wiring", not bad, f"{len(GRAPH)} 节点×输入键对活体 schema 预检: {bad or '全过(朴素布线在 s1 场景会带 sched.model/sched.denoise 被拒——知情布线零非法键)'}")

# ---------- 4. 提交生成 + 轮询 ----------
t0 = time.time()
resp = post("/prompt", {"prompt": GRAPH, "client_id": "field-wiring"})
if "_http_error" in resp:
    log("4.submit", False, f"HTTP {resp['_http_error']}: {resp['_body']}")
    R["verdict"] = "不咬合"
    json.dump(R, open(os.path.join(OUT, "field_receipt.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(2)
pid = resp["prompt_id"]
final = None
for _ in range(600):                                   # ≤5 分钟（首跑含模型加载）
    h = get(f"/history/{pid}")
    if pid in h:
        e = h[pid]
        if e["status"].get("completed") or e["status"].get("status_str") == "error":
            final = e
            break
    time.sleep(0.5)
ok_run = bool(final) and final["status"]["status_str"] == "success"
log("4.generate", ok_run, f"prompt_id={pid[:8]}… status={final['status']['status_str'] if final else 'timeout'} "
                          f"sec={round(time.time()-t0,1)}")

# ---------- 5. 图像落盘 + 机械验证 ----------
img_name = None
if ok_run:
    outs = final["outputs"].get("12", {}).get("images", [])
    if outs:
        img_name = outs[0]["filename"]
        sub = outs[0].get("subfolder", "")
        url = f"/view?filename={img_name}&subfolder={sub}&type=output"
        with urllib.request.urlopen(BASE + url, timeout=60) as r:
            data = r.read()
        os.makedirs(OUT, exist_ok=True)
        local = os.path.join(OUT, "field_wiring_20261005.png")
        open(local, "wb").write(data)
        from PIL import Image
        import statistics as stat
        im = Image.open(local).convert("L")
        px = list(im.getdata())
        mean, std = stat.mean(px), stat.pstdev(px)
        log("5.image-verify", im.size == (1024, 1024) and std > 10,
            f"{img_name} 尺寸={im.size} 灰度mean={mean:.1f} std={std:.1f}({'>10=非空白' if std > 10 else '疑似空白'})")
        R["image"] = {"file": "comfy-harness/field/out/field_wiring_20261005.png", "size": list(im.size),
                      "mean": round(mean, 1), "std": round(std, 1)}

# ---------- 6. 读数三态 + 判例登记 ----------
bite = all(c["ok"] for c in R["log"])
R["verdict"] = "咬合" if bite else "不咬合"
R["prompt_id"] = pid
R["seed"] = SEED
R["eids"] = [MINTED_EID]
os.makedirs(OUT, exist_ok=True)
json.dump(R, open(os.path.join(OUT, "field_receipt.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

if bite:
    store = PrecedentStore.load(SEED_PATH) if os.path.exists(SEED_PATH) else PrecedentStore()
    store.add({
        "id": "P-field-wiring-flux2-klein",
        "type": "procedural", "importance": 3,
        "keywords": ["flux2", "klein", "布线", "field", "SamplerCustom", "sigmas"],
        "content": {"c": "flux2 klein 4B 的 API 直连知情布线=UNETLoader+CLIPLoader(type=flux2,qwen_3_4b)+VAELoader(flux2-vae)+CLIPTextEncode×2→FluxGuidance→Flux2Scheduler(steps,width,height)出sigmas→KSamplerSelect(euler)→SamplerCustom(cfg=1.0,sigmas接线)+EmptyFlux2LatentImage→VAEDecode→SaveImage;4步蒸馏,1024²,单卡12G可跑。",
                    "a": "20261005 field_wiring_run 实测:活体 schema 预检零非法键,POST 成功出图。",
                    "d": "适用 v0.38 flux2/klein;Flux2Scheduler 宽高直接传像素(非latent尺寸),steps=4 对应蒸馏版。"},
        "evidence": {"artifact": "comfy-harness/field/out/field_receipt.json",
                     "quote": "s1-flux2sched-v038-wiring 判例 [steps,width,height] 对活体逐字命中=True",
                     "recalc": "复跑 comfy-harness/field/field_wiring_run.py"},
        "owner": ""}, actor="ai:卷十二线(field)")
    store.save(SEED_PATH)
    print(f"\n[判例] P-field-wiring-flux2-klein 已追加 draft（owner 空，候人 promote）并原子落盘回 seed")

record_run_outcome(MINTED_EID, R["verdict"], "FIELD-WIRING")   # 批二埋点常开
print(f"\n=== 飞轮实地读数:{R['verdict']} ===")
sys.exit(0 if bite else 1)
