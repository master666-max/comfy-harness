# -*- coding: utf-8 -*-
"""style_mine_lightrag.py — 风格挖掘器 B：LightRAG（LLM 实体/关系图谱 + 社区涌现）

必须用 LightRAG venv 跑（lightrag-hku==1.5.7 装在那；主环境无此依赖）：
  ~/.venvs/style-lightrag/Scripts/python.exe style_mine_lightrag.py
（compare 编排器以子进程方式拉起本件。）

链路：共用语料 corpus.json（与挖掘器 A 同一份）→ 每文档一条 insert（file_paths=src，
证据链可回源）→ LightRAG 建实体/关系图谱 → 实体图 Louvain 社区（seed=42 确定性）
→ 每社区 LLM 命名 → 候选风格 JSON（与 A 臂同构，对比器可直接对拍）。

模型面（20261008 实测裁定）：
  LLM=DeepSeek 云端点（deepseek-v4-flash；base/key 运行时读 ~/.zcode/v2/provider_config.json，
  key 绝不入仓、不打印）——本地候选实测录：hermes3.6-35B=思考失控（19.5tok/s 烧光预算
  不给正文）、prometheus-14B=在 LightRAG 长格式提示词上退化空转（单调用>600s）；
  嵌入=本地 LM Studio nomic-embed-text-v1.5（768 维，384MB 级零成本）。
  ⚠ 本地路径仍可用：显式给 --llm-base（如 http://127.0.0.1:8080/v1）即切回本地面。

开关（维护者令"两个都加个开关"）：STYLE_MINE_LIGHTRAG=off/0/false/no 或 --off
→ 关闭：退出 0、不产出、不报错。
环境：STYLE_LR_BASE/STYLE_LR_KEY/STYLE_LR_LLM（LLM 覆盖）·
STYLE_EMBED_BASE（默认 http://127.0.0.1:8080/v1）· STYLE_LR_EMBED（默认 nomic-embed）
· STYLE_LR_DIM（默认 768）。

用法：
  py_venv style_mine_lightrag.py [--selftest] [--corpus P] [--out P] [--wd P]
      [--resolution 1.5] [--min-cluster 3] [--keep-wd] [--off]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.join(_HERE, "style_mine_out", "corpus.json")
DEFAULT_OUT = os.path.join(_HERE, "style_mine_out", "lightrag_candidates.json")
DEFAULT_WD = os.path.join(_HERE, "style_mine_out", "lightrag_wd")

_ENV = "STYLE_MINE_LIGHTRAG"
_OFF = {"0", "off", "false", "no", "disable", "disabled"}
_SEP = "<SEP>"                      # lightrag.constants.GRAPH_FIELD_SEP（硬编码避免跨环境导入）
_PROVIDER_CONFIG = os.path.expanduser(r"~/.zcode/v2/provider_config.json")


def is_disabled(cli_off: bool = False, env: str | None = None) -> bool:
    if cli_off:
        return True
    v = (env if env is not None else os.environ.get(_ENV, "")).strip().lower()
    return v in _OFF


def _load_llm_cred() -> tuple:
    """读 provider_config 取 DeepSeek 端点的 (base, key)。key 只进内存——不打印、不入仓。"""
    cfg = json.load(open(_PROVIDER_CONFIG, encoding="utf-8"))
    providers = {p.get("providerName"): p.get("config", {})
                 for p in cfg["config"]["providerConfigRules"]["providerRules"]}
    c = providers.get("deepseek") or {}
    base = ((c.get("api") or {}).get("baseUrl") or "").rstrip("/")
    key = ((c.get("access") or {}).get("apiKey"))
    if not (base and key):
        raise AssertionError("deepseek 端点缺 baseUrl/key（provider_config.json）")
    return base, key


def resolve_endpoints(a) -> dict:
    """入口解析：LLM 与嵌入分开（LLM 默认云、嵌入默认本地；显式 --llm-base 可整体回本地面）。"""
    if a.llm_base:                      # 显式本地/自备端点
        llm = {"base": a.llm_base, "key": a.llm_key or "lm-studio",
               "name": a.llm or "style-llm"}
    else:
        base, key = _load_llm_cred()
        llm = {"base": base, "key": (a.llm_key or key),
               "name": a.llm or os.environ.get("STYLE_LR_LLM", "deepseek-v4-flash")}
    emb = {"base": a.embed_base, "name": a.embed, "dim": a.dim}
    return {"llm": llm, "emb": emb}


def _safe_id(src: str) -> str:
    # 净化会折叠中文（"正序"/"逆序"→同为 "-"）→ 撞 ID；补短哈希保唯一。
    # 证据回源不依赖 id——用 file_paths 的原 src（见 chunk→src 映射）。
    h = hashlib.sha1(src.encode("utf-8")).hexdigest()[:8]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", src) + "-" + h


async def _selftest(ep: dict) -> int:
    from lightrag.llm.openai import openai_complete_if_cache
    from openai import AsyncOpenAI
    llm, emb = ep["llm"], ep["emb"]
    t0 = time.time()
    txt = await openai_complete_if_cache(llm["name"], "只回复两个字：就位",
                                         api_key=llm["key"], base_url=llm["base"],
                                         max_tokens=32)
    # 直连嵌入端点：openai_embed 自带固定维度校验装饰层（误套会注入冲突），绕开它
    client = AsyncOpenAI(base_url=emb["base"], api_key="lm-studio", timeout=120)
    resp = await client.embeddings.create(model=emb["name"], input=["风格自检"])
    d = len(resp.data[0].embedding) if resp.data else 0
    ok = "就位" in str(txt)
    print(f"[style-lr] 自检：LLM({llm['name']})回复={str(txt).strip()[:20]!r}"
          f"（{'✓' if ok else '?'}） 嵌入维={d}（期望 {emb['dim']}，"
          f"{'✓' if d == emb['dim'] else '✗'}） 用时 {time.time()-t0:.1f}s")
    return 0 if (ok and d == emb["dim"]) else 1


async def mine_corpus(corpus_path: str, out_path: str, wd: str, ep: dict,
                      resolution: float, min_cluster: int) -> int:
    from lightrag import LightRAG
    from lightrag.llm.openai import openai_complete_if_cache
    from lightrag.utils import wrap_embedding_func_with_attrs
    from lightrag.kg.shared_storage import initialize_pipeline_status
    from openai import AsyncOpenAI
    import networkx as nx
    import numpy as np

    llm, emb = ep["llm"], ep["emb"]

    async def llm_func(prompt, system_prompt=None, history_messages=None, **kw):
        return await openai_complete_if_cache(
            llm["name"], prompt, system_prompt=system_prompt,
            history_messages=history_messages or [], api_key=llm["key"],
            base_url=llm["base"], **kw)

    @wrap_embedding_func_with_attrs(embedding_dim=emb["dim"], max_token_size=2048)
    async def embed_func(texts):
        # 直连嵌入端点：openai_embed 自带固定 1536 校验装饰层（双重装饰=注入冲突），绕开它
        client = AsyncOpenAI(base_url=emb["base"], api_key="lm-studio", timeout=120)
        resp = await client.embeddings.create(model=emb["name"], input=list(texts))
        return np.asarray([d.embedding for d in resp.data], dtype=np.float32)

    payload = json.load(open(corpus_path, encoding="utf-8"))
    docs = payload["docs"]

    rag = LightRAG(working_dir=wd, llm_model_func=llm_func, llm_model_name=llm["name"],
                   embedding_func=embed_func, llm_model_max_async=4,
                   embedding_func_max_async=2)
    await rag.initialize_storages()
    await initialize_pipeline_status()

    t0 = time.time()
    await rag.ainsert([d["text"] for d in docs],
                      ids=[_safe_id(d["src"]) for d in docs],
                      file_paths=[d["src"] for d in docs])
    try:
        await rag.finalize_storages()          # 冲刷落盘（旧版无此方法则忽略）
    except AttributeError:
        pass
    t_insert = time.time() - t0

    # ---- 图谱读取（GraphML）----
    graphml = os.path.join(wd, "graph_chunk_entity_relation.graphml")
    G = nx.read_graphml(graphml)

    def _deg(n):
        return G.degree(n)

    comms = [set(c) for c in nx.algorithms.community.louvain_communities(
        G, weight="weight", resolution=resolution, seed=42)]

    # ---- chunk→src 映射（证据链回源）----
    def _kv(path):
        if not os.path.isfile(path):
            return {}
        d = json.load(open(path, encoding="utf-8"))
        return d.get("_data", d) if isinstance(d, dict) else {}
    docs_kv = _kv(os.path.join(wd, "kv_store_full_docs.json"))
    chunks_kv = _kv(os.path.join(wd, "kv_store_text_chunks.json"))
    chunk_map = {}
    for cid, c in chunks_kv.items():
        did = (c or {}).get("full_doc_id")
        fp = (docs_kv.get(did) or {}).get("file_path")
        if fp:
            chunk_map[cid] = fp

    def evidence_of(comm) -> list:
        srcs = set()
        for ent in comm:
            node = G.nodes.get(ent) or {}
            for sid in str(node.get("source_id", "")).split(_SEP):
                sid = sid.strip()
                if sid in chunk_map:
                    srcs.add(chunk_map[sid])
        return sorted(srcs)

    async def name_comm(members) -> str:
        names = "、".join(sorted(members, key=lambda n: -_deg(n))[:24])
        descs = []
        for ent in sorted(members, key=lambda n: -_deg(n))[:8]:
            dsc = str((G.nodes.get(ent) or {}).get("description", "")).strip()
            if dsc:
                descs.append(dsc[:120])
        prompt = (f"以下是从图像生成提示词知识图谱中聚出的同一簇实体：{names}。\n"
                  f"部分实体描述：{'；'.join(descs[:6])}\n"
                  "请用不超过 12 个汉字给这个风格簇起一个名字（只输出名字本身，"
                  "不要引号、不要解释、不要标点）。")
        try:
            out = await llm_func(prompt, max_tokens=64, temperature=0.2)
            nm = re.sub(r"[\s\"'“”‘’。，,.：:]+", "", str(out))[:24]
            return nm or "·".join(sorted(members, key=lambda n: -_deg(n))[:3])
        except Exception:
            return "·".join(sorted(members, key=lambda n: -_deg(n))[:3])

    clusters, misc = [], []
    for comm in comms:
        members = sorted(comm, key=lambda n: (-_deg(n), n))
        if len(members) < min_cluster:
            misc.extend(members)
            continue
        w_in = []
        for u, v, d in G.edges(data=True):
            if u in comm and v in comm:
                try:
                    w_in.append(float(d.get("weight", 1.0)))
                except (TypeError, ValueError):
                    w_in.append(1.0)
        clusters.append({
            "name": await name_comm(comm),
            "size": len(members),
            "members": members,
            "cohesion": round(sum(w_in) / len(w_in), 2) if w_in else 0.0,
            "evidence": evidence_of(comm),
        })
    clusters.sort(key=lambda c: (-c["size"], c["name"]))
    misc.sort()

    out = {"method": "lightrag", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "corpus_n_docs": len(docs), "corpus_path": corpus_path,
           "params": {"llm": llm["name"], "llm_base": llm["base"], "embed": emb["name"],
                      "dim": emb["dim"], "resolution": resolution, "min_cluster": min_cluster},
           "clusters": clusters, "misc": misc,
           "stats": {"n_entities": G.number_of_nodes(), "n_relations": G.number_of_edges(),
                     "n_chunk_mapped": len(chunk_map), "n_docs_kv": len(docs_kv),
                     "insert_s": round(t_insert, 1)}}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    cov = len({s for c in clusters for s in c["evidence"]})
    print(f"[style-lr] {len(clusters)} 簇（实体 {out['stats']['n_entities']}"
          f"·关系 {out['stats']['n_relations']}·insert {out['stats']['insert_s']}s·"
          f"证据覆盖 {cov}/{len(docs)}） → {out_path}")
    for c in clusters:
        print(f"  {c['size']:3d} 实体 · {c['name']}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="风格挖掘器 B（LightRAG）")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--wd", default=DEFAULT_WD)
    ap.add_argument("--llm-base", default=os.environ.get("STYLE_LR_BASE"),
                    help="LLM 端点（缺省=provider_config 的 deepseek；给值即回本地面）")
    ap.add_argument("--llm-key", default=os.environ.get("STYLE_LR_KEY"))
    ap.add_argument("--llm", default=os.environ.get("STYLE_LR_LLM"))
    ap.add_argument("--embed-base", default=os.environ.get("STYLE_EMBED_BASE",
                                                           "http://127.0.0.1:8080/v1"))
    ap.add_argument("--embed", default=os.environ.get("STYLE_LR_EMBED", "nomic-embed"))
    ap.add_argument("--dim", type=int, default=int(os.environ.get("STYLE_LR_DIM", "768")))
    ap.add_argument("--resolution", type=float, default=1.5)
    ap.add_argument("--min-cluster", type=int, default=3)
    ap.add_argument("--keep-wd", action="store_true", help="保留上次图谱工作目录（默认清空重建）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--off", action="store_true", help="开关：关闭本挖掘器")
    a = ap.parse_args(argv)

    if is_disabled(a.off):
        print(f"[style-lr] 已关闭（开关 {_ENV} / --off）——不产出")
        return 0
    ep = resolve_endpoints(a)
    if a.selftest:
        return asyncio.run(_selftest(ep))
    if os.path.isdir(a.wd) and not a.keep_wd:
        shutil.rmtree(a.wd)
    return asyncio.run(mine_corpus(a.corpus, a.out, a.wd, ep, a.resolution, a.min_cluster))


if __name__ == "__main__":
    sys.exit(main())
