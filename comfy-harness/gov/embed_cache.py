# -*- coding: utf-8 -*-
"""embed_cache.py — 条目嵌入缓存（工单 P2 · V1 向量化）

**派生投影纪律**（工单红线③）：真相永远是条目内容（content/keywords）；
本缓存 = {id, model, dim, hash, vec} 的派生投影，**可全量重建**。
文本组装确定性化（`text_of`）——hash 失配即增量重嵌，条目删除即缓存清除。

**模型钉版**：默认 `nomic-embed`（text-embedding-nomic-embed-text-v1.5，dim=768）。
缓存头记录 model+dim：换模型调用 → 拒绝混用并指示 `--rebuild`（半新半旧=向量漂移）。

**离线响亮报错**：嵌入端点（LM Studio）不在线 → RuntimeError 带指引，绝不静默降级
（与 style_mine_lightrag 同环境变量：STYLE_EMBED_BASE / STYLE_LR_EMBED / STYLE_LR_DIM）。

用法：
  py -X utf8 embed_cache.py [--check] [--rebuild] [--store P] [--cache P]
  from embed_cache import refresh, load_cache, text_of, cosine, nearest
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.request

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # 仓根（evocore 包所在）

DEFAULT_STORE = os.path.join(_HERE, "precedents_e2_seed.json")
DEFAULT_CACHE = os.path.join(_HERE, "style_mine_out", "embeddings.json")
DEFAULT_BASE = os.environ.get("STYLE_EMBED_BASE", "http://127.0.0.1:8080/v1")
DEFAULT_MODEL = os.environ.get("STYLE_LR_EMBED", "nomic-embed")
DEFAULT_DIM = int(os.environ.get("STYLE_LR_DIM", "768"))

# nomic-embed-text-v1.5 官方任务前缀（非对称检索：文档/查询分路编码）。
# 不带前缀时相似度刻度浑浊（实测噪声底 0.48~0.58 与真命中 0.57~0.70 重叠）。
# 前缀方案名入 content_hash：换方案 = 全量重嵌，杜绝半新半旧向量漂移。
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
PREFIX_SCHEME = "nomic-task-v1"


def text_of(entry: dict) -> str:
    """条目 → 嵌入文本（确定性组装：keywords + content 三段；顺序钉死）。"""
    parts = [" ".join(entry.get("keywords") or [])]
    c = entry.get("content")
    if isinstance(c, dict):
        parts += [str(c.get(k, "")) for k in ("c", "a", "d")]
    else:
        parts.append(str(c or ""))
    return " ".join(p for p in parts if p).strip()


def _hash(text: str) -> str:
    return hashlib.sha1((PREFIX_SCHEME + "|" + text).encode("utf-8")).hexdigest()[:16]


def embed_query(queries: list, base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL,
                dim: int = DEFAULT_DIM) -> np.ndarray:
    """查询侧编码（search_query 前缀）；与文档侧 refresh 分路对称。"""
    return embed_texts([QUERY_PREFIX + q for q in queries], base=base, model=model, dim=dim)


def embed_docs(texts: list, base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL,
               dim: int = DEFAULT_DIM) -> np.ndarray:
    """文档侧编码（search_document 前缀）——候选文本与缓存条目比较时必用此路，
    否则文档 vs 查询前缀不对称，cosine 刻度漂移（近重复闸 0.90 判据失真）。"""
    return embed_texts([DOC_PREFIX + t for t in texts], base=base, model=model, dim=dim)


def embed_texts(texts: list, base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL,
                dim: int = DEFAULT_DIM) -> np.ndarray:
    """调 LM Studio OpenAI 兼容端点。离线/维错 → 响亮 RuntimeError（不静默）。"""
    body = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/embeddings", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                                  # noqa: BLE001 —— 响亮不静默
        raise RuntimeError(
            f"嵌入端点不可用（{base}，{type(e).__name__}: {e}）——"
            f"请 `lms load text-embedding-nomic-embed-text-v1.5 --identifier nomic-embed`"
            f" 后重试；向量层不降级（工单红线③）") from e
    vecs = np.asarray([d["embedding"] for d in data["data"]], dtype=np.float32)
    if vecs.shape != (len(texts), dim):
        raise RuntimeError(f"嵌入维不符：得 {vecs.shape}，期望 ({len(texts)}, {dim})——"
                           f"模型钉版校验失败，勿混用（检查 STYLE_LR_DIM/模型）")
    return vecs


def _b64(v: np.ndarray) -> str:
    return base64.b64encode(v.tobytes()).decode("ascii")


def _unb64(s: str, dim: int) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype=np.float32).copy()


def load_cache(path: str = DEFAULT_CACHE) -> dict:
    """返回 {model, dim, updated_at, items: {id: {hash, vec(b64)}}}；缺文件=空壳。"""
    if not os.path.isfile(path):
        return {"model": None, "dim": None, "updated_at": None, "items": {}}
    return json.load(open(path, encoding="utf-8"))


def _save_cache(path: str, cache: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cache["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(cache, open(path, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False)


def refresh(store_path: str = DEFAULT_STORE, cache_path: str = DEFAULT_CACHE,
            base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL, dim: int = DEFAULT_DIM,
            rebuild: bool = False, check: bool = False,
            embed_fn=embed_texts) -> dict:
    """增量刷新缓存。check=True 只报差不动盘。返回报告 dict。"""
    from precedent_gov import PrecedentStore
    store = PrecedentStore.load(store_path)
    # 标本件即使退场也保向量（退场↔反向飞轮接口：雷达相似度臂靠它比对；
    # 退场件不进召回池，故无供血面泄漏）
    entries = [e for e in store.entries
               if not e.get("tombstone") or (e.get("facts") or {}).get("specimen")]
    old = load_cache(cache_path)
    model_mismatch = bool(old.get("model")) and (old.get("model") != model or old.get("dim") != dim)
    if model_mismatch and not rebuild and not check:
        raise RuntimeError(
            f"缓存模型={old.get('model')}/{old.get('dim')} 与请求 {model}/{dim} 不符——"
            f"半新半旧=向量漂移，拒绝混用；请 `--rebuild` 全量重嵌（工单红线③）")
    kept = {} if (rebuild or model_mismatch) else dict(old.get("items") or {})
    todo, hashes = [], {}
    for e in entries:
        h = _hash(text_of(e))
        hashes[e["id"]] = h
        if kept.get(e["id"], {}).get("hash") == h:
            continue
        todo.append(e)
    removed = [i for i in kept if i not in hashes]
    report = {"model": model, "dim": dim, "n_entries": len(entries),
              "to_embed": len(todo), "reused": len(entries) - len(todo),
              "removed": len(removed), "model_mismatch": model_mismatch, "check": check,
              "prefix_scheme": PREFIX_SCHEME}
    if check or not todo and not removed:
        return report
    vecs = embed_fn([DOC_PREFIX + text_of(e) for e in todo], base=base, model=model, dim=dim) \
        if todo else np.zeros((0, dim), dtype=np.float32)
    for e, v in zip(todo, vecs, strict=False):
        kept[e["id"]] = {"hash": hashes[e["id"]], "vec": _b64(v)}
    for i in removed:
        kept.pop(i, None)
    _save_cache(cache_path, {"model": model, "dim": dim, "prefix_scheme": PREFIX_SCHEME,
                             "items": kept})
    return report


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def nearest(cache: dict, query_vec: np.ndarray, k: int = 5, exclude: set | None = None) -> list:
    """brute-force 余弦 top-k（工单：无向量库必要，全库条数级毫秒）。"""
    dim = cache.get("dim") or len(query_vec)
    scored = []
    for eid, it in (cache.get("items") or {}).items():
        if exclude and eid in exclude:
            continue
        scored.append((cosine(query_vec, _unb64(it["vec"], dim)), eid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:k]


def main(argv=None):
    ap = argparse.ArgumentParser(description="条目嵌入缓存（派生投影·模型钉版）")
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dim", type=int, default=DEFAULT_DIM)
    ap.add_argument("--check", action="store_true", help="只报差不动盘")
    ap.add_argument("--rebuild", action="store_true", help="全量重嵌（换模型后必用）")
    a = ap.parse_args(argv)
    r = refresh(a.store, a.cache, a.base, a.model, a.dim, a.rebuild, a.check)
    print(f"[embed] entries={r['n_entries']} to_embed={r['to_embed']} "
          f"reused={r['reused']} removed={r['removed']} "
          f"{'CHECK ' if r['check'] else ''}model={r['model']}/{r['dim']}"
          f"{'（模型失配，--rebuild 全量）' if r['model_mismatch'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
