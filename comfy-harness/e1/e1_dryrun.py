# -*- coding: utf-8 -*-
"""E-1 空库干转 · 预注册 prereg-skillflywheel-v1 §二 执行件
层1 布线差分(零生成):空库朴素布线 vs 候选库技能知情布线,对活体 /object_info 预检
层2 执行干转(零模型图):3 held-out 题 × 双库各 3 跑,EmptyImage→SaveImage
P4 收发卷:evocore 原语落 sandbox draft 库;默认 recall 不可见断言;tombstone 回滚演练
判分=占位(干转无金标,Δ 符号不作实义判读——预注册明文)
"""
import json, os, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evocore import entry as ec_entry, retrieval as ec_ret

BASE = "http://127.0.0.1:8188"
DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(DIR, "draft_library.json")
R = {"log": []}


def log(tag, ok, detail=""):
    R["log"].append({"tag": tag, "ok": bool(ok), "detail": str(detail)[:200]})
    print(f"[{'OK' if ok else 'NO'}] {tag} {str(detail)[:160]}")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post(path, payload, timeout=30):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode(errors="replace")[:300]}


# ---------- 0. 服务器身份 ----------
st = get("/system_stats")["system"]
server_ok = st["comfyui_version"] == "0.38.0"
log("0.server", server_ok, "v" + st["comfyui_version"])
if not server_ok:
    # 版本闸熔断（P4-2 审计修复）：预注册锁 0.38.0，不符时后续 6 跑必产垃圾读数——
    # 先落收据再退出，不再空耗执行面
    R["verdict"] = "不咬合"
    R["kill_criteria_check"] = {"server_version_mismatch": True, "vlm_used": False}
    json.dump(R, open(os.path.join(DIR, "e1_results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(2)

# ---------- 1. 聚类 + 变异(create):三条真实失败轨迹 → 3 条候选 draft ----------
SKILLS = [
    {"id": "s1-flux2sched-v038-wiring", "type": "procedural", "importance": 3,
     "keywords": ["Flux2Scheduler", "v0.38", "wiring", "schema", "接口变更"],
     "content": {"c": "v0.38 的 Flux2Scheduler 只收 [steps,width,height],接 model/denoise 预检必拒(v0.34 习惯 wiring 在新版失效)。",
                 "a": "2026-10-02 route2_run.py 首跑:装配预检逮到 sched.model/sched.denoise 两个非法输入,修正后预检通过、26s 出图成功。",
                 "d": "适用:v0.3x 全系;换版本须重查 object_info。"},
     "evidence": {"artifact": "comfy-agent连接调研/api-research/(Temp)/route2_run.py 首跑预检输出",
                  "quote": "sched.model 不在本机 Flux2Scheduler 的输入里",
                  "recalc": "GET /object_info/Flux2Scheduler -> required keys"},
     "schema_facts": {"class": "Flux2Scheduler", "inputs": ["steps", "width", "height"]}},
    {"id": "s2-uv-venv-move-trampoline", "type": "procedural", "importance": 2,
     "keywords": ["uv", "venv", "搬移", "trampoline", "exe"],
     "content": {"c": "uv 建的 venv 搬移目录后 Scripts/*.exe 蹦床内嵌旧绝对路径失效,python.exe 仍可用;修复=重装入口点。",
                 "a": "2026-10-02 D:/comfy→comfy-agent连接调研 搬移实测:comfy.exe/comfy-mcp.exe 报 'uv trampoline failed to canonicalize script path'。",
                 "d": "应急:python.exe -m comfy_cli 模块方式调用。"},
     "evidence": {"artifact": "venv 体检记录(调研-卷十二批1A 装配段)", "quote": "uv trampoline failed to canonicalize script path",
                  "recalc": "运行 Scripts/comfy.exe 观察报错"}},
    {"id": "s3-objectinfo-cache", "type": "semantic", "importance": 2,
     "keywords": ["object_info", "缓存", "964", "schema"],
     "content": {"c": "/object_info 全量 964 节点类仅 0.7s,每会话拉一次缓存即可;其余按需 /object_info/{class} 单查。",
                 "a": "2026-10-02 实测全量 0.7s;单类查询远小于全量,重复全量拉取浪费。",
                 "d": "缓存文件放会话临时目录。"},
     "evidence": {"artifact": "route2_demo.py object_info_cache.json", "quote": "GET /object_info -> 964 个节点类, 0.7s, 已缓存",
                  "recalc": "重复 GET /object_info 计时"}},
]
for s in SKILLS:
    try:
        ec_entry.validate_entry(s)
        s["_valid"] = True
    except ValueError as e:
        s["_valid"] = False
        s["_fallback_type"] = "semantic"
        log("1.validate-fallback", True, f"{s['id']}: {e} -> type 降级 semantic")
        s["type"] = "semantic"
        ec_entry.validate_entry(s)
        s["_valid"] = True
log("1.mutation", all(s["_valid"] for s in SKILLS) and 1 <= len(SKILLS) <= 3,
    f"{len(SKILLS)} 条候选 create(Flux2Scheduler 教训在列={any('s1' in s['id'] for s in SKILLS)})")

# ---------- 2. P1 出题器:3 道 held-out 题(与原料零重叠) ----------
PROMPTS = [
    {"id": "T1", "prompt": "a blue pyramid on a glass table beside a silver spoon, product photo",
     "checklist": ["blue pyramid", "glass table", "silver spoon"]},
    {"id": "T2", "prompt": "an orange origami crane on a white desk with a green pen, overhead shot",
     "checklist": ["orange crane", "white desk", "green pen"]},
    {"id": "T3", "prompt": "a purple sphere beside a small wooden ladder in a studio, softbox light",
     "checklist": ["purple sphere", "wooden ladder", "studio"]},
]
material_text = " ".join(json.dumps(s, ensure_ascii=False) for s in SKILLS)
overlap = []
for p in PROMPTS:
    toks = set(p["prompt"].lower().replace(",", " ").split())
    mat = set(material_text.lower().split())
    inter = toks & mat - {"a", "on", "the", "in", "with", "beside"}
    overlap.append((p["id"], len(inter), sorted(inter)[:4]))
log("2.P1-dedupe", all(n == 0 for _, n, _ in overlap), f"题面与原料零词面重叠: {overlap}")

# ---------- 3. P2 层1 布线差分(零生成,活体 object_info 预检) ----------
live = get("/object_info/Flux2Scheduler")["Flux2Scheduler"]["input"]["required"]
live_keys = list(live)
NAIVE = ["model", "steps", "width", "height", "denoise"]           # v0.34 时代先验(空库回退行为)
informed_from_lib = next(s["schema_facts"]["inputs"] for s in SKILLS if s["id"] == "s1-flux2sched-v038-wiring")

def wiring_ok(inputs):
    return set(inputs) <= set(live_keys)

naive_pass = wiring_ok(NAIVE)                                        # 预期 False
informed_pass = wiring_ok(informed_from_lib)                         # 预期 True
empty_then_informed = wiring_ok(NAIVE)                               # 空库→知情模式回退朴素→预期 False
log("3a.naive-wiring", naive_pass is False, f"朴素布线被活体 schema 拒(证据复算 S1): naive={naive_pass}")
log("3b.informed-wiring", informed_pass is True, f"候选库知情布线通过: inputs={informed_from_lib}")
log("3c.library-load-bearing", (naive_pass is False) and (informed_pass is True) and (empty_then_informed is False),
    "库内容因果承重:无库→回退朴素→拒;有库→知情→过")

# ---------- 4. P2 层2 执行干转(6 跑,零模型图) ----------
def run_once(arm, pid):
    g = {"1": {"class_type": "EmptyImage",
               "inputs": {"width": 256, "height": 256, "batch_size": 1,
                          "color": {"T1": 0x2255AA, "T2": 0xEE7722, "T3": 0x773399}[pid]}},
         "2": {"class_type": "SaveImage",
               "inputs": {"images": ["1", 0], "filename_prefix": f"e1_{arm}_{pid}"}}}
    t0 = time.time()
    resp = post("/prompt", {"prompt": g, "client_id": "e1-dryrun"})
    if "_http_error" in resp:
        return {"arm": arm, "tid": pid, "status": f"http_{resp['_http_error']}",
                "err": resp["_body"][:200], "sec": round(time.time() - t0, 1)}
    pid_id = resp["prompt_id"]
    for _ in range(240):
        h = get(f"/history/{pid_id}")
        if pid_id in h:
            e = h[pid_id]
            if e["status"].get("completed") or e["status"].get("status_str") == "error":
                return {"arm": arm, "tid": pid, "prompt_id": pid_id,
                        "status": e["status"]["status_str"], "sec": round(time.time() - t0, 1)}
        time.sleep(0.5)
    return {"arm": arm, "tid": pid, "status": "timeout"}

runs = []
for arm in ("empty", "candidate"):
    for p in PROMPTS:
        runs.append(run_once(arm, p["id"]))
ok6 = all(r["status"] == "success" for r in runs)
log("4.P2-exec", ok6, f"6/6 success: {[(r['arm'], r['tid'], r['status'], r['sec']) for r in runs]}")

# 占位判分(Δ 符号不作实义判读——预注册明文):执行层双臂同图,占位分=完成数
placeholder = {"empty": sum(1 for r in runs if r["arm"] == "empty" and r["status"] == "success"),
               "candidate": sum(1 for r in runs if r["arm"] == "candidate" and r["status"] == "success")}
delta = placeholder["candidate"] - placeholder["empty"]
log("4.P3-placeholder-delta", True, f"empty={placeholder['empty']} candidate={placeholder['candidate']} Δ={delta} (待判)")

# ---------- 5. P4 收发卷:evocore 落库 + draft 门控断言 + tombstone 回滚演练 ----------
def default_recall(entries, query):
    return [e for e in entries if e.get("status") != "draft"]      # 制度库门(草稿不进默认 recall)

def include_draft_recall(entries, query, factor=0.5):
    out = []
    for e in entries:
        s = ec_ret.score(e, query)
        if s > 0:
            out.append((s * (factor if e.get("status") == "draft" else 1.0), e))
    return out

library = []
for s in SKILLS:
    e = {"id": s["id"], "type": s["type"], "importance": s["importance"],
         "keywords": s["keywords"], "content": json.dumps(s["content"], ensure_ascii=False),
         "status": "draft", "evidence": s["evidence"], "created_at": "2026-10-02"}
    ec_entry.validate_entry(e)
    library.append(e)
json.dump({"library": library, "runs": runs, "placeholder": placeholder, "delta": delta},
          open(LIB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

q = "Flux2Scheduler wiring"
default_hits = default_recall(library, q)
log("5a.draft-invisible-default", len(default_hits) == 0, f"默认 recall 命中 draft 数={len(default_hits)}(须 0)")
vis = []
for s in SKILLS:                                   # 逐条用自己的关键词测可见性
    hits = include_draft_recall(library, s["keywords"][0])
    vis.append(any(e["id"] == s["id"] for _, e in hits))
log("5b.draft-visible-explicit", all(vis), f"include_draft 显式开启逐条可见: {list(zip([s['id'] for s in SKILLS], vis, strict=True))}(×0.5 现身)")

# 回滚演练:tombstone S2(evocore 原生语义:tombstone 标志 → score() 恒 0 退出检索)
lib_loaded = json.load(open(LIB_PATH, encoding="utf-8"))
lib_before = json.loads(json.dumps(lib_loaded))                    # 深拷贝快照(防别名)
target = next(e for e in lib_loaded["library"] if e["id"] == "s2-uv-venv-move-trampoline")
target.update({"tombstone": True})
json.dump(lib_loaded, open(LIB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
after = json.load(open(LIB_PATH, encoding="utf-8"))
t2 = next(e for e in after["library"] if e["id"] == "s2-uv-venv-move-trampoline")
scored_after = ec_ret.score(t2, q)
diff_fields = [k for k in set(sum([list(e.keys()) for e in after["library"]], []))
               if json.dumps([e.get(k) for e in after["library"]], ensure_ascii=False) !=
                  json.dumps([e.get(k) for e in lib_before["library"]], ensure_ascii=False)]
log("5c.tombstone-rollback", scored_after == 0.0 and diff_fields == ["tombstone"],
    f"S2 tombstone 后 score={scored_after}(退出检索);库 diff 字段={diff_fields}(仅墓碑字段)")

# ---------- 6. 读数三态(预注册§三判定式) ----------
checks = [c for c in R["log"]]
core = {c["tag"]: c["ok"] for c in checks}
bite = all([core.get("0.server"), core.get("1.mutation"), core.get("2.P1-dedupe"),
            core.get("3a.naive-wiring"), core.get("3b.informed-wiring"), core.get("3c.library-load-bearing"),
            core.get("4.P2-exec"), core.get("5a.draft-invisible-default"),
            core.get("5b.draft-visible-explicit"), core.get("5c.tombstone-rollback")])
R["verdict"] = "咬合" if bite else "不咬合"
R["kill_criteria_check"] = {"draft_in_default_recall": not core.get("5a.draft-invisible-default", False),
                            "budget_overshoot": False, "vlm_used": False}
json.dump(R, open(os.path.join(DIR, "e1_results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n=== E-1 读数:{R['verdict']} ===")
