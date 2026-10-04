# -*- coding: utf-8 -*-
"""E-2 盲对照臂 · img_D 撤锚单发（议题二对照证据，探索性——候用户裁决语境）

背景：E-2 正考 img_D 臂的 prompt 含机械锚「饱和度均值=0.00」，判官 reasoning 明文引用——
①=0/③=0 属锚 assisted，视觉独立检出未证。本臂对 img_D 撤锚重判：
  - 仍 [0,1,0,1] → 视觉独立检出坐实，D 判例升级证据；
  - 翻案 → v1-⑫ 参照引导依赖度被定量。
零生产写：结果落 e2_blind_control.json。单发，kill 线不适用（探索臂）。
"""
import base64, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(ROOT, "调研-卷十二-C1站2-沙盒")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2_blind_control.json")
IMG = "img_D.png"
CHECKLIST = ["① 图像中存在红色立方体", "② 图像中存在木桌", "③ 图像中存在黄色橡皮鸭", "④ 图像呈现影棚光效"]

KEY = None
for p in json.load(open(os.path.expanduser(r"~/.zcode/v2/provider_config.json"), encoding="utf-8"))["config"]["providerConfigRules"]["providerRules"]:
    if p.get("providerName", "").lower() == "deepseek":
        KEY = p["config"]["access"]["apiKey"]
        BASE = p["config"]["api"]["baseUrl"].rstrip("/")
assert KEY, "deepseek provider 未配置"

b64 = base64.b64encode(open(os.path.join(SANDBOX, IMG), "rb").read()).decode()
prompt = (
    "你是图像交付质检员。逐条核验以下验收判据,对每条独立给出 1(满足)或 0(不满足)。"
    "判定基准:以图内可见证据能否确证该判据所述属性为准;存在与可辨分开判——对象存在但属性不可辨时,该属性判 0。\n"
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
rec = {"arm": "盲对照(撤锚)", "image": IMG, "raw": txt[:300], "parsed": parsed,
       "finish_reason": resp["choices"][0].get("finish_reason"),
       "reasoning_head": (msg.get("reasoning_content") or "")[:200],
       "latency_s": round(time.time() - t0, 1), "usage": resp.get("usage", {})}
json.dump([rec], open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"parsed": parsed, "latency_s": rec["latency_s"],
                  "finish": rec["finish_reason"]}, ensure_ascii=False))
