# -*- coding: utf-8 -*-
"""style_corpus.py — 风格挖掘共用语料构建器（双挖掘器同吃一份语料，对比才公平）

用途（维护者令·20261008）：风格簇挖掘（确定性）与 LightRAG 挖掘（LLM 图谱）
并行实验的**唯一输入面**——两边读同一份 corpus.json，输出同构的候选风格 JSON，
再由 style_mine_compare.py 对比"自动涌现"。

语料两路（均只读、不改任何源）：
  A. 判例种子 gov/precedents_e2_seed.json——判例 content/facts/keywords；
  B. ComfyUI 服务端原始产物 output/*.png 的嵌入元数据（tEXt 'prompt' 块）——
     注意 field/out 的成图经 film_treat 用 PIL 重存，元数据已被剥；**必须读服务端原件**。

统一文档（corpus doc）：
  {"src": "precedent:P-xxx" | "generation:<file>", "type": "precedent|generation",
   "text": "...", "tags": [...], "meta": {...}}

零外部依赖（stdlib + Pillow 读 PNG 文本块）；开关态由各挖掘器自理，本件恒可用。

用法：py -X utf8 style_corpus.py [--comfy-out DIR] [--out PATH] [--seed PATH]
默认输出 gov/style_mine_out/corpus.json（目录自动建）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SEED = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_OUT = os.path.join(_HERE, "style_mine_out", "corpus.json")
# ComfyUI 服务端产物目录（本机实测路径；他机用 --comfy-out / COMFY_OUTPUT_DIR 覆盖）
DEFAULT_COMFY_OUT = os.environ.get(
    "COMFY_OUTPUT_DIR", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\output")

# 权重包裹：(tag:1.2) / (tag) / ((tag)) —— 取内层词、弃权重
_RE_WEIGHT = re.compile(r"^\(+([^():]+?)(?::[\d.]+)?\)+$")
# 负词识别启发（ComfyUI 通用惯例：negative 多含 worst quality/low quality）
_RE_NEG = re.compile(r"worst quality|low quality|lowres", re.IGNORECASE)
_TAG_MAXLEN = 60          # 超长串（路径/句子）不当 tag 参与共现


def norm_tag(t: str) -> str:
    """单 tag 归一：去权重包裹、小写、收空白。空串/超长返回 ""（由调用方丢弃）。"""
    t = t.strip()
    m = _RE_WEIGHT.match(t)
    if m:
        t = m.group(1).strip()
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    if not t or len(t) > _TAG_MAXLEN:
        return ""
    return t


def norm_tags(text: str) -> list:
    """逗号分隔词表 → 去重保序 tag 列表（落盘用 sorted 稳定）。"""
    seen, out = set(), []
    for raw in text.split(","):
        t = norm_tag(raw)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _tags_from_facts(facts: dict) -> list:
    """判例 facts 里的词表类值 → tags（字符串全值按逗号拆；数字/布尔丢）。"""
    out = []
    def walk(v):
        if isinstance(v, str):
            out.extend(norm_tags(v))
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(facts)
    return out


def doc_from_precedent(e: dict) -> dict:
    c = e.get("content") or {}
    if isinstance(c, str):
        c = {"c": c}
    text = " ".join(str(x) for x in (c.get("c"), c.get("a"), c.get("d")) if x)
    tags = []
    for kw in (e.get("keywords") or []):
        t = norm_tag(str(kw))
        if t:
            tags.append(t)
    tags.extend(_tags_from_facts(e.get("facts") or {}))
    seen, dedup = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return {"src": f"precedent:{e.get('id')}", "type": "precedent",
            "text": f"[{e.get('id')}] {text}",
            "tags": sorted(dedup),
            "meta": {"eid": e.get("id"), "gov": e.get("gov"),
                     "kind": e.get("kind"), "task": e.get("task"), "level": e.get("level")}}


def doc_from_png(path: str) -> dict | None:
    """读 ComfyUI 原件的 'prompt' tEXt 块 → 生成类文档；无元数据返回 None。"""
    from PIL import Image
    try:
        info = Image.open(path).info
    except Exception:
        return None
    raw = info.get("prompt")
    if not raw:
        return None
    try:
        g = json.loads(raw)
    except ValueError:
        return None
    pos, neg = [], []
    meta = {"file": os.path.basename(path)}
    for node in g.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        ins = node.get("inputs") or {}
        if ct == "CLIPTextEncode" and isinstance(ins.get("text"), str):
            (neg if _RE_NEG.search(ins["text"]) else pos).append(ins["text"])
        elif ct == "KSampler":
            for k in ("steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if k in ins and not isinstance(ins[k], list):
                    meta.setdefault(k, ins[k])
        elif ct == "CheckpointLoaderSimple":
            meta.setdefault("ckpt", ins.get("ckpt_name"))
        elif ct == "LoraLoader":
            meta.setdefault("lora", ins.get("lora_name"))
            meta.setdefault("lora_w", ins.get("strength_model"))
        elif ct == "EmptyLatentImage":
            meta.setdefault("base_size", [ins.get("width"), ins.get("height")])
    if not pos:
        return None
    text = " ; ".join(pos)
    return {"src": f"generation:{meta['file']}", "type": "generation",
            "text": text, "tags": sorted(norm_tags(text)), "meta": meta}


def build_corpus(seed_path: str = DEFAULT_SEED, comfy_out: str = DEFAULT_COMFY_OUT) -> list:
    docs = []
    n_skipped_draft = 0
    if os.path.isfile(seed_path):
        d = json.load(open(seed_path, encoding="utf-8"))
        for e in d.get("entries", []):
            # 闸双面（工单 P3 · Biba no-write-up 血统）：未批准不入挖掘基质——
            # 挖掘只读 生成面 + 观察面 + approved/verified；draft 是回声（其证据
            # 正是挖掘产物），进池=自食复利。原'全收'版实录见报告 v1.1 §10.2。
            if e.get("gov") not in ("approved", "verified"):
                n_skipped_draft += 1
                continue
            docs.append(doc_from_precedent(e))
    print(f"[corpus] 身份闸：判例面只收 approved/verified（跳过 draft/其他 {n_skipped_draft} 条——闸双面·不入挖掘基质）")
    n_png = n_skip = 0
    if os.path.isdir(comfy_out):
        for name in sorted(os.listdir(comfy_out)):
            if not name.lower().endswith(".png"):
                continue
            doc = doc_from_png(os.path.join(comfy_out, name))
            if doc:
                docs.append(doc)
                n_png += 1
            else:
                n_skip += 1
    return docs


def main(argv=None):
    ap = argparse.ArgumentParser(description="风格挖掘共用语料构建器")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--comfy-out", default=DEFAULT_COMFY_OUT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)

    docs = build_corpus(a.seed, a.comfy_out)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    payload = {"seed_path": a.seed, "comfy_out": a.comfy_out,
               "n_docs": len(docs), "docs": docs}
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    n_pre = sum(1 for d in docs if d["type"] == "precedent")
    n_gen = sum(1 for d in docs if d["type"] == "generation")
    all_tags = {t for d in docs for t in d["tags"]}
    print(f"[corpus] 文档 {len(docs)}（判例 {n_pre} + 生成 {n_gen}）· 独立 tag {len(all_tags)}")
    print(f"[corpus] 落盘 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
