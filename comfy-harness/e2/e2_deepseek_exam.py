# -*- coding: utf-8 -*-
"""E-2 判官正式考 · DeepSeek 异族判官（工单 W-C · 2026-10-03）
判官=deepseek-v4-flash（异族:≠GLM会话族,≠klein生图族→自偏爱构造性豁免）
判读口径=判据件v1.0正式件:逐条目二元+关系满足矩阵;盲协议(不知地面真值/不知mapping);
机械锚读数随判据下发(v1-⑫参照引导);伪影三测:位置=双序对(实跑),冗长=n/a(格式绑定,H1已证),自偏爱=n/a(构造性豁免);
kill=输出不可解析3发终止。零生产写:结果落 e2_results.json,判例种子=draft(owner空,候人promote)。
API key 运行时读 provider_config,不入仓。
"""
import base64, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(ROOT, "调研-卷十二-C1站2-沙盒")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2_results.json")
IMAGES = ["img_A.png", "img_B.png", "img_C.png", "img_D.png", "img_E2.png"]
# 机械锚读数(C2站2-G1/站4实测,PIL;参照引导 v1-⑫ 随判据下发)
ANCHORS = {
    "img_A.png":  {"S_mean": 100.03, "colorfulness": 112.39, "edge_energy": 5.95},
    "img_B.png":  {"S_mean": 100.05, "colorfulness": 111.52, "edge_energy": 2.50},
    "img_C.png":  {"S_mean": 100.05, "colorfulness": 107.77, "edge_energy": 2.02},
    "img_D.png":  {"S_mean": 0.00,   "colorfulness": 0.00,   "edge_energy": None},
    "img_E2.png": {"S_mean": 108.07, "colorfulness": 117.63, "edge_energy": None},
}
CHECKLIST_FWD = ["① 图像中存在红色立方体", "② 图像中存在木桌", "③ 图像中存在黄色橡皮鸭", "④ 图像呈现影棚光效"]
CHECKLIST_REV = list(reversed(CHECKLIST_FWD))
KEY = None
for p in json.load(open(os.path.expanduser(r"~/.zcode/v2/provider_config.json"), encoding="utf-8"))["config"]["providerConfigRules"]["providerRules"]:
    if p.get("providerName", "").lower() == "deepseek":
        KEY = p["config"]["access"]["apiKey"]
        BASE = p["config"]["api"]["baseUrl"].rstrip("/")
assert KEY, "deepseek provider 未配置"


def anchors_text(anc):
    """机械锚文本（v1-⑫参照引导）。0.0 是实测值不是缺失——只对 None 缺项
    （P4-1 审计修复：原 if anc['edge_energy'] 把 0.0 当缺失静默吞掉）。"""
    return (f"机械锚读数(程序实测,供参照): 饱和度均值={anc['S_mean']:.2f}, "
            f"colorfulness={anc['colorfulness']:.2f}"
            + (f", 边缘能量={anc['edge_energy']:.2f}" if anc["edge_energy"] is not None else ""))


def judge(img_name, checklist, arm):
    b64 = base64.b64encode(open(os.path.join(SANDBOX, img_name), "rb").read()).decode()
    anc = ANCHORS[img_name]
    anchors_txt = anchors_text(anc)
    prompt = (
        "你是图像交付质检员。逐条核验以下验收判据,对每条独立给出 1(满足)或 0(不满足)。"
        "判定基准:以图内可见证据能否确证该判据所述属性为准;存在与可辨分开判——对象存在但属性不可辨时,该属性判 0。\n"
        + "\n".join(checklist) + "\n" + anchors_txt + "\n"
        "只输出一行 JSON:{\"红方块\":0或1,\"木桌\":0或1,\"黄鸭\":0或1,\"影棚光效\":0或1,\"一句话理由\":\"...\"}")
    body = {"model": "deepseek-v4-flash", "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
        "temperature": 0, "max_tokens": 3000}  # v4-flash推理型:img_C构念难题reasoning超1500(length截断),3000留足
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
    return {"arm": arm, "image": img_name, "raw": txt[:300], "parsed": parsed,
            "finish_reason": resp["choices"][0].get("finish_reason"),
            "reasoning_head": (msg.get("reasoning_content") or "")[:120],
            "latency_s": round(time.time()-t0, 1),
            "usage": resp.get("usage", {})}


def main():
    R, unparseable = [], 0
    for img in IMAGES:
        try:
            r = judge(img, CHECKLIST_FWD, "正序")
            R.append(r)
            if r["parsed"] is None:
                unparseable += 1  # 解析失败计入kill(首跑bug:只数API异常漏了空content)
            print(f"[{'OK' if r['parsed'] else 'NP'}] {img} 正序")
        except Exception as e:
            unparseable += 1
            R.append({"arm": "正序", "image": img, "error": str(e)[:200]})
            print(f"[NO] {img}: {str(e)[:120]}")
        time.sleep(1)
    # 伪影三测·位置:img_C 双序对
    try:
        r = judge("img_C.png", CHECKLIST_REV, "逆序")
        R.append(r)
        if r["parsed"] is None:
            unparseable += 1
        print(f"[{'OK' if r['parsed'] else 'NP'}] img_C 逆序(位置伪影对)")
    except Exception as e:
        unparseable += 1
        R.append({"arm": "逆序", "image": "img_C.png", "error": str(e)[:200]})
        print(f"[NO] img_C 逆序: {str(e)[:120]}")
    json.dump(R, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n结果 {len(R)} 臂 → {OUT}; 不可解析 {unparseable}/6 (kill线=3)")
    sys.exit(0 if unparseable < 3 else 2)


if __name__ == "__main__":
    main()
