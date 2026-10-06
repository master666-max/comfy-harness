# -*- coding: utf-8 -*-
"""e2_v11_acceptance.py — 判据件 v1.1 验收实验 · DSK 臂（修订单§三预注册管辖 · 2026-10-05）

命题：② 宽松构念声明落定后，img_C×② 跨族分歧应闭合。
盲协议：不知地面真值/不知裁决内容/不知既往判读。判据锁死于修订单§三，本脚本无裁量权。
"""
import base64, json, os, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SANDBOX = os.path.join(ROOT, "调研-卷十二-C1站2-沙盒")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2_v11_acceptance.json")
IMG = "img_C.png"
CHECKLIST = [
    "① 图像中存在红色立方体",
    "② 图像中存在木桌（构念声明：桌面物体在场即可，木质线索勉强可辨仍判满足；仅当桌面完全不可见时判不满足）",
    "③ 图像中存在黄色橡皮鸭",
    "④ 图像呈现影棚光效",
]
KEY = None
for p in json.load(open(os.path.expanduser(r"~/.zcode/v2/provider_config.json"), encoding="utf-8"))["config"]["providerConfigRules"]["providerRules"]:
    if p.get("providerName", "").lower() == "deepseek":
        KEY = p["config"]["access"]["apiKey"]
        BASE = p["config"]["api"]["baseUrl"].rstrip("/")
assert KEY, "deepseek provider 未配置"

b64 = base64.b64encode(open(os.path.join(SANDBOX, IMG), "rb").read()).decode()
prompt = (
    "你是图像交付质检员。逐条核验以下验收判据,对每条独立给出 1(满足)或 0(不满足)。"
    "判定基准(G4 条款):以图内可见证据能否确证为准;存在与可辨分开判,各条目按其构念声明处置。\n"
    + "\n".join(CHECKLIST) + "\n"
    "只输出一行 JSON:{\"红方块\":0或1,\"木桌\":0或1,\"黄鸭\":0或1,\"影棚光效\":0或1,\"一句话理由\":\"...\"}")
body = {"model": "deepseek-v4-flash", "messages": [
    {"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
    "temperature": 0, "max_tokens": 3000}
req = urllib.request.Request(BASE + "/chat/completions", method="POST",
                             data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=120) as r:
    resp = json.load(r)
msg = resp["choices"][0]["message"]
txt = msg.get("content") or ""
i, j = txt.find("{"), txt.rfind("}")
parsed = json.loads(txt[i:j+1]) if (i >= 0 and j > i) else None
rec = {"arm": "v1.1验收-DSK", "image": IMG, "raw": txt[:300], "parsed": parsed,
       "finish_reason": resp["choices"][0].get("finish_reason"),
       "latency_s": round(time.time() - t0, 1), "usage": resp.get("usage", {})}
json.dump([rec], open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"parsed": parsed, "latency_s": rec["latency_s"]}, ensure_ascii=False))
