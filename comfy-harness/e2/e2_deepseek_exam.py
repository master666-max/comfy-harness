# -*- coding: utf-8 -*-
"""e2_deepseek_exam.py — E-2 判官正式考 · A 案跨族常态对读版（20261007 · 引擎线转呈件落地）

A 案（工单回执·判卷域四件）：每次正式考双异族判官臂同图同判据互审——
  逐属性对拍（attr_divergences）→ 跨族分歧事件入回执 + 影子 J-4 台账逐读入账。
G5 谱系声明（判据件 v1.1 增补）：每臂回执带 judge_lineage（训练谱系 + 与生图/会话族关系）；
  两臂谱系同源时分歧信号降级为参考（本配置 deepseek×glm 异源，信号有效）。
盲协议不变（不知地面真值/不知 mapping）；机械锚随判据下发（v1-⑫）；
kill=输出不可解析 3 发终止。零生产写：结果落 e2_results.json，判例种子=draft 候人 promote。
API key 运行时读 provider_config，不入仓。
"""
import base64, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SANDBOX = os.path.join(ROOT, "调研-卷十二-C1站2-沙盒")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2_results.json")
SHADOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "field", "shadow_j4_ledger.jsonl")
SHADOW_SRC = "E2-" + time.strftime("%Y%m%d")
IMAGES = ["img_A.png", "img_B.png", "img_C.png", "img_D.png", "img_E2.png"]
# 机械锚读数(C2站2-G1/站4实测,PIL;参照引导 v1-⑫ 随判据下发)
ANCHORS = {
    "img_A.png":  {"S_mean": 100.03, "colorfulness": 112.39, "edge_energy": 5.95},
    "img_B.png":  {"S_mean": 100.05, "colorfulness": 111.52, "edge_energy": 2.50},
    "img_C.png":  {"S_mean": 100.05, "colorfulness": 107.77, "edge_energy": 2.02},
    "img_D.png":  {"S_mean": 0.00,   "colorfulness": 0.00,   "edge_energy": None},
    "img_E2.png": {"S_mean": 108.07, "colorfulness": 117.63, "edge_energy": None},
}
CHECKLIST_FWD = ["① 图像中存在红色立方体", "② 图像中存在木桌（构念声明：桌面物体在场即可，木质线索勉强可辨仍判满足；仅当桌面完全不可见时判不满足）",
                 "③ 图像中存在黄色橡皮鸭", "④ 图像呈现影棚光效"]
CHECKLIST_REV = list(reversed(CHECKLIST_FWD))

# G5 判官谱系声明（判据件 v1.1 增补）：每臂回执必带 judge_lineage
JUDGE_LINEAGE = {
    "deepseek": "DeepSeek-V4 系；与生图族(flux/klein)及 zcode 会话族(GLM)无训练谱系交集——自偏爱构造性豁免成立",
    "glm": "智谱 GLM 系(glm-4v-flash 视觉型)；与生图族(flux/klein)无谱系交集；与 zcode 会话族同源（会话族非被判对象，自偏爱不成立；对拍相对 deepseek 臂谱系异源，分歧信号有效）",
}


def load_families():
    """运行时读 provider_config 构建双族判官（key 不入仓）。
    注：glm 臂=glm-4v-flash 视觉型（4.5-flash 纯文本 400/4.5v 余额不足——probe 实录），
    max_tokens≤1024（该模上限，超限 400 code 1210）。"""
    cfg = json.load(open(os.path.expanduser(r"~/.zcode/v2/provider_config.json"), encoding="utf-8"))
    providers = {p.get("providerName"): p.get("config", {})
                 for p in cfg["config"]["providerConfigRules"]["providerRules"]}
    fams = {}
    for name, pname, model, max_tok in (("deepseek", "deepseek", "deepseek-v4-flash", 3000),
                                        ("glm", "智谱glm", "glm-4v-flash", 1024)):
        c = providers.get(pname) or {}
        base = (c.get("api") or {}).get("baseUrl", "").rstrip("/")
        key = ((c.get("access") or {}).get("apiKey"))
        if not (base and key):
            raise AssertionError(f"判官族 {name}（provider={pname}）缺 baseUrl/key")
        fams[name] = {"base": base, "key": key, "model": model, "max_tokens": max_tok,
                      "lineage": JUDGE_LINEAGE[name]}
    return fams


def attr_divergences(read_a: dict, read_b: dict) -> list:
    """A 案对拍纯函数：逐属性对答案（一句话理由不参与），缺属性=该属性缺判计分歧。"""
    attrs = sorted(set(list(read_a) + list(read_b)) - {"一句话理由"})
    return [a for a in attrs if read_a.get(a, "缺判") != read_b.get(a, "缺判")]


def anchors_text(anc):
    """机械锚文本（v1-⑫参照引导）。0.0 是实测值不是缺失——只对 None 缺项
    （P4-1 审计修复，A案重写时曾回归内联丢失，0607 复位并锁——test_p3fix AnchorZeroTests 护）。"""
    return (f"机械锚读数(程序实测,供参照): 饱和度均值={anc['S_mean']:.2f}, "
            f"colorfulness={anc['colorfulness']:.2f}"
            + (f", 边缘能量={anc['edge_energy']:.2f}" if anc["edge_energy"] is not None else ""))


def judge(img_name, checklist, arm, fam):
    b64 = base64.b64encode(open(os.path.join(SANDBOX, img_name), "rb").read()).decode()
    anc = ANCHORS[img_name]
    anchors_txt = anchors_text(anc)
    prompt = (
        "你是图像交付质检员。逐条核验以下验收判据,对每条独立给出 1(满足)或 0(不满足)。"
        "判定基准(G4 条款):以图内可见证据能否确证该判据所述属性为准;存在与可辨分开判,各条目按其构念声明处置。\n"
        + "\n".join(checklist) + "\n" + anchors_txt + "\n"
        "只输出一行 JSON:{\"红方块\":0或1,\"木桌\":0或1,\"黄鸭\":0或1,\"影棚光效\":0或1,\"一句话理由\":\"...\"}")
    body = {"model": fam["model"], "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
        "temperature": 0, "max_tokens": fam["max_tokens"]}
    req = urllib.request.Request(fam["base"] + "/chat/completions", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {fam['key']}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    msg = resp["choices"][0]["message"]
    txt = msg.get("content") or ""
    i, j = txt.find("{"), txt.rfind("}")
    parsed = json.loads(txt[i:j+1]) if (i >= 0 and j > i) else None
    return {"arm": arm, "image": img_name, "raw": txt[:300], "parsed": parsed,
            "finish_reason": resp["choices"][0].get("finish_reason"),
            "judge_lineage": fam["lineage"], "model": fam["model"],
            "latency_s": round(time.time()-t0, 1),
            "usage": resp.get("usage", {})}


def main():
    fams = load_families()
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "field"))
    from shadow_j4 import ShadowLedger
    ledger = ShadowLedger(SHADOW)

    R, unparseable, shadow_n = [], 0, 0
    per_img = {}
    for img in IMAGES:
        for fam_name, fam in fams.items():
            try:
                r = judge(img, CHECKLIST_FWD, fam_name, fam)
                R.append(r)
                if r["parsed"] is None:
                    unparseable += 1
                else:
                    ledger.record(judge=fam_name, target=img, verdict=r["parsed"],
                                  src=SHADOW_SRC)
                    shadow_n += 1
                per_img.setdefault(img, {})[fam_name] = r["parsed"]
            except Exception as e:
                unparseable += 1
                R.append({"arm": fam_name, "image": img, "error": str(e)[:200]})
                print(f"[NO] {img}×{fam_name}: {str(e)[:120]}")
            time.sleep(1)
        time.sleep(1)
    # 伪影三测·位置:img_C 双序对（deepseek 臂）
    try:
        r = judge("img_C.png", CHECKLIST_REV, "deepseek", fams["deepseek"])
        R.append(r)
        if r["parsed"] is None:
            unparseable += 1
        print(f"[OK] img_C 逆序(位置伪影对)")
    except Exception as e:
        unparseable += 1
        R.append({"arm": "deepseek", "image": "img_C.png", "error": str(e)[:200]})

    # A 案对拍：逐图逐属性跨族分歧
    divergences = []
    for img, reads in per_img.items():
        a, b = reads.get("deepseek"), reads.get("glm")
        if isinstance(a, dict) and isinstance(b, dict):
            for attr in attr_divergences(a, b):
                divergences.append({"image": img, "attr": attr,
                                    "deepseek": a.get(attr), "glm": b.get(attr)})
    for d in divergences:
        print(f"[分歧] {d['image']} × {d['attr']}: deepseek={d['deepseek']} glm={d['glm']}")

    R.append({"meta": {"judge_lineage": JUDGE_LINEAGE,
                       "divergences": divergences,
                       "shadow_records": shadow_n,
                       "shadow_ledger": os.path.relpath(SHADOW, ROOT)}})
    json.dump(R, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n结果 {len(R)} 臂 → {OUT}; 不可解析 {unparseable}/7 (kill线=3); "
          f"跨族分歧 {len(divergences)} 起; 影子账 +{shadow_n} 读")
    sys.exit(0 if unparseable < 3 else 2)


if __name__ == "__main__":
    main()
