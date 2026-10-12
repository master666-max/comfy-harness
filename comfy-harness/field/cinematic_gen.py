# -*- coding: utf-8 -*-
"""cinematic_gen.py — 电影感两段式出图器（默认 4 抽 · 20261007 维护者令 · v2 加影调工艺）

标准管线（承 P-noobai-cinematic-recipe + P-noobai-facedetailer-pipeline 两判例）：
  一段组合 pass：质控组+题材词，cfg 4.5 / euler / normal / 28 步 / 832×1216
  面部二道：FaceDetailer guide 640 / denoise 0.6 / cfg 5.5 / euler+simple（眼词在正词里）
  影调工艺（v2 · 治 AI 蜡感）：胶片颗粒+微色散+暗角+轻对比——照后即处理，落盘即成品
默认 4 抽随机 seed；产出入 field/out/，文件名 <prefix>_<seed>.png。

用法：py cinematic_gen.py --prefix fireworks --pos "题材词..." [--seeds 4] [--start-seed N] [--no-grain]
"""
import argparse, json, os, random, shutil, time, urllib.request

BASE = "http://127.0.0.1:8188"
CKPT = "NoobAI-XL-Vpred-v1.0.safetensors"
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


def graph(seed, pos, neg, prefix, lora=None, lora_w=1.0, clip_skip=False,
          steps=32, cfg=4.8, hires_steps=15, hires_denoise=0.45, hires_scale=1.5,
          face_denoise=0.6, hand_denoise=0.55, face_steps=28, hand_steps=24,
          face_guide=640, hand_guide=512, grain=5.5,
          sampler="euler", scheduler="normal", force_inpaint=True,
          zsnr=True, ca_px=1, vignette=0.10, contrast=1.05,
          upscale_method="nearest-exact",
          cnet_model=None, cnet_image=None, cnet_strength=0.85, cnet_end=0.8):
    """v3 五段图：1段组合pass → hires放大重绘 → 面部二道 → 手部二道 → (落盘后影调工艺)

    lora：可选即插风格组件（P-noobai-vp1-detailer-lora 语义——LoraLoader 插于
    Checkpoint 与 KSampler/CLIPTextEncode 之间，model+clip 全链；缺省 None=零变化）。
    clip_skip：CLIPSetLastLayer(-2)——NAI 系社区标配（20261008 同种子 A/B 实证脸部
    成熟度/比例上调；official 配方档默认启用）。
    upscale_method：hires 潜放大插值——20261009 同种子 A/B（坏签 888784801）实锤
    nearest-exact 是色块像素化根源（潜单元 8px 整块复制+楼梯边，denoise 只洗六成）；
    bicubic/bislerp 均消块，bislerp 细节更锐。缺省 nearest-exact=历史可复现；
    主题键 upscale_method=bislerp 逐主题启用。
    （20261008 维护者裁：detailer-clean 实验已撤——干净链手修会把反射面重绘成直立
    伪影人影，管线还原；撤书记录见 obs 账本与 P-detailer-clean-chain 候退场。）
    """
    m0 = ["30", 0] if lora else ["1", 0]
    clip_src = ["30", 1] if lora else ["1", 1]
    c1 = clip_src  # clip_skip 的 CLIPSetLastLayers 在图后置挂节点26（20261010 修复）
    g = {
     "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
     "3": {"class_type": "ModelSamplingDiscrete", "inputs": {"sampling": "v_prediction", "zsnr": zsnr, "model": m0}},
     "4": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": c1}},
     "5": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": c1}},
     "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
     "7": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler,
                                                "scheduler": scheduler, "denoise": 1.0, "model": ["3", 0],
                                                "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0]}},
     "13": {"class_type": "LatentUpscale", "inputs": {"samples": ["7", 0],
                                                      "upscale_method": upscale_method,
                                                      "width": int(832 * hires_scale), "height": int(1216 * hires_scale), "crop": "disabled"}},
     "14": {"class_type": "KSampler", "inputs": {"seed": seed + 1, "steps": hires_steps, "cfg": cfg, "sampler_name": sampler,
                                                 "scheduler": scheduler, "denoise": hires_denoise, "model": ["3", 0],
                                                 "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["13", 0]}},
     "8": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["1", 2]}},
     "10": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face_yolov8m.pt"}},
     "15": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/hand_yolov8s.pt"}},
     "11": {"class_type": "FaceDetailer", "inputs": {
         "image": ["8", 0], "model": ["3", 0], "clip": c1, "vae": ["1", 2],
         "guide_size": face_guide, "guide_size_for": True, "max_size": 1024,
         "seed": seed, "steps": face_steps, "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple",
         "positive": ["4", 0], "negative": ["5", 0], "denoise": face_denoise, "feather": 5,
         "noise_mask": True, "force_inpaint": force_inpaint, "bbox_threshold": 0.5, "bbox_dilation": 10,
         "bbox_crop_factor": 3.0, "sam_detection_hint": "center-1", "sam_dilation": 0,
         "sam_threshold": 0.93, "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
         "sam_mask_hint_use_negative": "False", "drop_size": 10, "bbox_detector": ["10", 0],
         "wildcard": "", "cycle": 1}},
     "16": {"class_type": "FaceDetailer", "inputs": {
         "image": ["11", 0], "model": ["3", 0], "clip": c1, "vae": ["1", 2],
         "guide_size": hand_guide, "guide_size_for": True, "max_size": 1024,
         "seed": seed, "steps": hand_steps, "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple",
         "positive": ["4", 0], "negative": ["5", 0], "denoise": hand_denoise, "feather": 5,
         "noise_mask": True, "force_inpaint": force_inpaint, "bbox_threshold": 0.4, "bbox_dilation": 8,
         "bbox_crop_factor": 2.5, "sam_detection_hint": "center-1", "sam_dilation": 0,
         "sam_threshold": 0.93, "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
         "sam_mask_hint_use_negative": "False", "drop_size": 10, "bbox_detector": ["15", 0],
         "wildcard": "", "cycle": 1}},
     "9": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": prefix}},
    }
    if cnet_model and cnet_image:
        # ControlNet 硬控（20261010 接入）：guide 图（姿势骨架或原图）→ 条件注入
        g["20"] = {"class_type": "LoadImage", "inputs": {"image": os.path.basename(cnet_image)}}
        g["23"] = {"class_type": "ControlNetLoader",
                   "inputs": {"control_net_name": cnet_model}}
        guide_src = ["20", 0]
        if "openpose" in cnet_model:
            # 姿态骨架链：参考图 → SDPose 提取 → 骨架渲染（body+hands）
            g["25"] = {"class_type": "CheckpointLoaderSimple",
                       "inputs": {"ckpt_name": "sdpose_wholebody_fp16.safetensors"}}
            g["21"] = {"class_type": "SDPoseKeypointExtractor",
                       "inputs": {"model": ["25", 0], "vae": ["1", 2], "image": ["20", 0],
                                  "batch_size": 1}}
            g["22"] = {"class_type": "SDPoseDrawKeypoints",
                       "inputs": {"keypoints": ["21", 0], "draw_body": True,
                                  "draw_hands": True, "draw_face": True,
                                  "draw_feet": False, "stick_width": 4,
                                  "face_point_size": 3, "score_threshold": 0.3,
                                  "draw_head": True}}
            guide_src = ["22", 0]
        g["24"] = {"class_type": "ControlNetApplyAdvanced",
                   "inputs": {"positive": ["4", 0], "negative": ["5", 0],
                              "control_net": ["23", 0], "image": guide_src,
                              "strength": cnet_strength,
                              "start_percent": 0.0, "end_percent": cnet_end}}
        g["7"]["inputs"]["positive"] = ["24", 0]
        g["7"]["inputs"]["negative"] = ["24", 1]
    if lora:
        g["30"] = {"class_type": "LoraLoader",
                   "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": lora,
                              "strength_model": lora_w, "strength_clip": lora_w}}
    if clip_skip:
        # 20261010 双重潜伏 bug 修复：①clip_skip 引用的 CLIPSetLastLayers 节点从未建图
        # ②节点编号"0"在 ComfyUI 内部被真值过滤丢弃（0 号非法）——必须用安全编号
        g["26"] = {"class_type": "CLIPSetLastLayer",
                       "inputs": {"clip": ["1", 1], "stop_at_clip_layer": -2}}
        g["4"]["inputs"]["clip"] = ["26", 0]
        g["5"]["inputs"]["clip"] = ["26", 0]
    return g


def post(path, payload, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


THEMES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes.json")
RECIPE_BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "recipe_base.json")


def load_recipe_base():
    """版本化配方基座（20261010 基座继承制·裁决④）：主题卡默认继承，覆盖须 override_reason。

    文件损坏/形态非法=响亮拒启（fail-closed，不静默吞）；缺文件=无基座（退回签名缺省）。
    升版=人签（human_signed 字段在案）；premises 对 recipe_base_version 看门。"""
    if not os.path.isfile(RECIPE_BASE_PATH):
        return None
    try:
        b = json.load(open(RECIPE_BASE_PATH, encoding="utf-8"))
    except ValueError as ex:
        raise SystemExit(f"DENY:BAD_RECIPE_BASE {RECIPE_BASE_PATH} 解析失败：{ex}")
    if not isinstance(b.get("version"), int) or not isinstance(b.get("args"), dict):
        raise SystemExit("DENY:BAD_RECIPE_BASE version 须整数且 args 须对象")
    return b


def resolve_regime(th: dict, base_args: dict, no_zsnr: bool = False,
                   cli_upscale: str | None = None) -> tuple:
    """采样政权解析（优先级）：显式 CLI > 主题卡 > 配方基座 > 签名缺省。

    基座继承制下主题卡原则上不写政权值（拷贝=掉队根因，20261010 实锤 7 卡）；
    写了即视为故意覆盖——对照实验臂（ron 系）以此钉体制。返回 (zsnr, upscale_method)。"""
    if no_zsnr:
        zsnr = False
    elif "zsnr" in th:
        zsnr = bool(th["zsnr"])
    elif "zsnr" in base_args:
        zsnr = bool(base_args["zsnr"])
    else:
        zsnr = True
    if cli_upscale is not None:
        up = cli_upscale
    elif "upscale_method" in th:
        up = th["upscale_method"]
    elif "upscale_method" in base_args:
        up = base_args["upscale_method"]
    else:
        up = "nearest-exact"
    return zsnr, up

# ═══ NoobAI vpred 官方卡配方（civitai 833294 原文 · 20261008 并存裁定）═══
# 官方建议：vpred 版 masterpiece/best quality 放【负向】；正向用 score 系。
# 与 QUALITY 堆叠档并存（主题 recipe 字段二选一）——两种画风非高下。
OFFICIAL_POS = ('score_9, score_8_up, score_7_up, newest, rating:general, '
                'very aesthetic, absurdres')
OFFICIAL_NEG = ('nsfw, lowres, {bad}, error, fewer, extra, missing, worst quality, '
                'jpeg artifacts, bad quality, watermark, unfinished, displeasing, '
                'chromatic aberration, signature, extra digits, artistic error, '
                'username, scan, [abstract], masterpiece, best quality')


def capture_env() -> dict:
    """L1 环境指纹（20261009 vp1 冤案根治）：写入侧自动快照，不依赖记录者自觉。

    机器可读前提（zsnr/插值/采样器/底模…）在结论落账的同一刻被结构化登记——
    混杂防护的第一半：依赖登记由构造保证。前提的翻倒检测与依赖枚举见 gov/premises.py。
    """
    import datetime
    import hashlib
    import inspect
    sig = inspect.signature(graph).parameters
    th_sha = ""
    themes = {}
    if os.path.isfile(THEMES_PATH):
        raw = open(THEMES_PATH, "rb").read()
        th_sha = hashlib.sha256(raw).hexdigest()[:12]
        try:
            themes = json.loads(raw.decode("utf-8"))
        except ValueError:
            themes = {}
    # 配方基座版本（20261010 基座继承制）：升版即政权事件，premises 看门出票
    rb_sha, rb_ver = "", 0
    if os.path.isfile(RECIPE_BASE_PATH):
        raw_b = open(RECIPE_BASE_PATH, "rb").read()
        rb_sha = hashlib.sha256(raw_b).hexdigest()[:12]
        try:
            rb_ver = int(json.loads(raw_b.decode("utf-8")).get("version", 0))
        except (ValueError, TypeError):
            rb_ver = 0
    # 政权指纹（20261009 教训：zsnr 翻案发生在主题层覆盖，签名缺省全程未变——
    # 只抓声明值会漏掉真正的翻转）。布尔跃迁而非计数：首次出现才翻倒，不随加主题刷票
    reg = {
        "themes_n": len(themes),
        "themes_any_zsnr_false": any(t.get("zsnr") is False
                                     for t in themes.values()),
        "themes_any_bislerp": any(t.get("upscale_method") == "bislerp"
                                  for t in themes.values()),
        "themes_any_lora": any(bool(t.get("lora")) for t in themes.values()),
    }
    return {
        "ckpt": CKPT,
        "zsnr_default": sig["zsnr"].default,
        "upscale_method_default": sig["upscale_method"].default,
        "sampler_default": sig["sampler"].default,
        "scheduler_default": sig["scheduler"].default,
        "cfg_default": sig["cfg"].default,
        "steps_default": sig["steps"].default,
        "themes_sha": th_sha,                      # 词表时代指纹（只记不追踪翻倒）
        "recipe_base_version": rb_ver,             # 基座版本（watched：升版→翻倒出票）
        "recipe_base_sha": rb_sha,                 # 基座内容指纹（只记不追踪）
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
        **reg,
    }


def load_theme(name):
    """主题预设（20261008 注意力优化批：长命令税→--theme 一词；词表与判例 facts 同源）。"""
    themes = json.load(open(THEMES_PATH, encoding="utf-8"))
    if name not in themes:
        raise SystemExit(f"theme {name!r} 不在 {THEMES_PATH}（现有: {', '.join(sorted(themes))}）")
    return themes[name]


def resolve_args(args):
    """--theme 打底、显式旗覆盖 → (pos, neg, lora, lora_w, clip_skip)。

    recipe=stacked（默认）: QUALITY 堆叠打底，NEG_DEFAULT。
    recipe=official: OFFICIAL_POS 打底 + OFFICIAL_NEG（score 系，masterpiece 入负）
                     + 默认启用 clip_skip 2（官方秀风实测配置）。
    """
    th = load_theme(args.theme) if getattr(args, "theme", None) else {}
    recipe = th.get("recipe", "stacked")
    pos = args.pos or th.get("pos")
    if not pos:
        raise SystemExit("缺提示词：给 --pos 或 --theme")
    if recipe == "official":
        pos = f"{OFFICIAL_POS}, {pos}"
    else:
        # 质量词去重复（维护者 20261008 实测：主题 pos 自带质量串时会被再前置一遍=同一串出现两次，
        # 过权会把画面往"默认扁平审美"推）——pos 任何位置已含 masterpiece 就不再前置
        pos = pos if "masterpiece" in pos else f"{QUALITY}, {pos}"
    neg = getattr(args, "neg", None)
    if neg is None:
        # 20261009 修复：themes.json 的 neg 此前被静默无视（罗恩线 22 主题负词全程
        # 未生效，实际用的都是 NEG_DEFAULT）——优先级改为 CLI 旗 > 主题 > recipe 缺省
        th_neg = th.get("neg")
        neg = (th_neg if th_neg
               else (OFFICIAL_NEG if recipe == "official" else NEG_DEFAULT))
    lora = args.lora if args.lora is not None else th.get("lora")
    lora_w = args.lora_weight if args.lora_weight is not None else th.get("lora_weight", 1.0)
    clip_skip = bool(th.get("clip_skip", recipe == "official"))
    return pos, neg, lora, lora_w, clip_skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--pos", default=None)
    ap.add_argument("--theme", default=None, help="主题预设名（themes.json；显式旗可逐项覆盖）")
    ap.add_argument("--neg", default=None, help="负词（缺省随 recipe: 官方配方=OFFICIAL_NEG / 堆叠档=NEG_DEFAULT）")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--start-seed", type=int, default=None)
    ap.add_argument("--no-grain", action="store_true")
    ap.add_argument("--lora", default=None, help="可选即插风格组件（LoraLoader 全链插于 Checkpoint 与下游之间）")
    ap.add_argument("--lora-weight", type=float, default=None)
    ap.add_argument("--steps", type=int, default=None, help="主采样步数（缺省 32 / 随主题）")
    ap.add_argument("--cfg", type=float, default=None, help="CFG（缺省 4.8 / 随主题）")
    ap.add_argument("--hires-steps", type=int, default=None, help="hires 重绘步数（缺省 15）")
    ap.add_argument("--hires-denoise", type=float, default=None,
                    help="hires 重绘强度（缺省 0.45；上调=加细节，过高=改构图）")
    ap.add_argument("--hires-scale", type=float, default=None, help="hires 放大倍数（缺省 1.5）")
    ap.add_argument("--face-denoise", type=float, default=None, help="面部二道强度（缺省 0.6）")
    ap.add_argument("--hand-denoise", type=float, default=None, help="手部二道强度（缺省 0.55）")
    ap.add_argument("--face-steps", type=int, default=None, help="面部二道步数（缺省 28）")
    ap.add_argument("--hand-steps", type=int, default=None, help="手部二道步数（缺省 24）")
    ap.add_argument("--face-guide", type=int, default=None, help="面部二道 guide 尺寸（缺省 640）")
    ap.add_argument("--hand-guide", type=int, default=None, help="手部二道 guide 尺寸（缺省 512）")
    ap.add_argument("--grain", type=float, default=None, help="影调颗粒强度（缺省 5.5；调低=更清）")
    ap.add_argument("--sampler", default=None, help="主/hires 采样器（缺省 euler）")
    ap.add_argument("--scheduler", default=None, help="调度器（缺省 normal）")
    ap.add_argument("--no-force-inpaint", action="store_true",
                    help="二道强制重绘关闭（检测不到时不再整图软重绘——涂抹嫌疑参数）")
    ap.add_argument("--no-zsnr", action="store_true",
                    help="关闭 zsnr（v-pred 采样模式；默认 True）——软硬观感差异实测项")
    ap.add_argument("--ca-px", type=int, default=None,
                    help="后处理色差像素（缺省 1；0=关。红+1/蓝-1 通道位移=糊色块边界）")
    ap.add_argument("--vignette", type=float, default=None, help="后处理渐晕（缺省 0.10；0=关）")
    ap.add_argument("--contrast", type=float, default=None, help="后处理对比（缺省 1.05）")
    ap.add_argument("--upscale-method", default=None,
                    help="hires 潜放大插值（缺省 nearest-exact / 随主题；bislerp=消像素块）")
    ap.add_argument("--outdir", default=None,
                    help="批输出文件夹（缺省 out/<prefix>_<时间戳>/——每批独立，20261009 维护者令）")
    ap.add_argument("--cnet-model", default=None,
                    help="ControlNet 模型（openpose_pre/lineart_anime/depth——姿势硬控）")
    ap.add_argument("--cnet-image", default=None,
                    help="ControlNet guide 参考图（自动拷入 ComfyUI input）")
    ap.add_argument("--cnet-strength", type=float, default=0.85,
                    help="ControlNet 强度（缺省 0.85）")
    ap.add_argument("--cnet-end", type=float, default=0.8,
                    help="ControlNet 结束百分比（缺省 0.8）")
    ap.add_argument("--show-theme", action="store_true",
                    help="只解析并打印生效配置，不生成（主题/接线自检用）")
    args = ap.parse_args()
    pos, neg, lora, lora_w, clip_skip = resolve_args(args)
    th = load_theme(args.theme) if args.theme else {}
    steps = args.steps if args.steps is not None else int(th.get("steps", 32))
    cfg = args.cfg if args.cfg is not None else float(th.get("cfg", 4.8))
    hires_steps = (args.hires_steps if args.hires_steps is not None
                   else int(th.get("hires_steps", 15)))
    hires_denoise = (args.hires_denoise if args.hires_denoise is not None
                     else float(th.get("hires_denoise", 0.45)))
    hires_scale = (args.hires_scale if args.hires_scale is not None
                   else float(th.get("hires_scale", 1.5)))
    face_denoise = (args.face_denoise if args.face_denoise is not None
                    else float(th.get("face_denoise", 0.6)))
    hand_denoise = (args.hand_denoise if args.hand_denoise is not None
                    else float(th.get("hand_denoise", 0.55)))
    face_steps = (args.face_steps if args.face_steps is not None
                  else int(th.get("face_steps", 28)))
    hand_steps = (args.hand_steps if args.hand_steps is not None
                  else int(th.get("hand_steps", 24)))
    face_guide = (args.face_guide if args.face_guide is not None
                  else int(th.get("face_guide", 640)))
    hand_guide = (args.hand_guide if args.hand_guide is not None
                  else int(th.get("hand_guide", 512)))
    grain = (args.grain if args.grain is not None else float(th.get("grain", 5.5)))
    sampler = args.sampler or th.get("sampler", "euler")
    scheduler = args.scheduler or th.get("scheduler", "normal")
    force_inpaint = (False if args.no_force_inpaint
                     else bool(th.get("force_inpaint", True)))
    # 采样政权：基座继承制（20261010）——CLI > 主题卡 > 配方基座 > 签名缺省
    base = load_recipe_base() or {}
    zsnr, upscale_method = resolve_regime(th, base.get("args", {}),
                                          no_zsnr=args.no_zsnr,
                                          cli_upscale=args.upscale_method)
    ca_px = args.ca_px if args.ca_px is not None else int(th.get("ca_px", 1))
    vignette = (args.vignette if args.vignette is not None
                else float(th.get("vignette", 0.10)))
    contrast = (args.contrast if args.contrast is not None
                else float(th.get("contrast", 1.05)))
    if args.show_theme:
        print(json.dumps({"prefix": args.prefix, "pos": pos, "lora": lora,
                          "lora_weight": lora_w, "clip_skip": clip_skip,
                          "steps": steps, "cfg": cfg, "hires_steps": hires_steps,
                          "hires_denoise": hires_denoise, "hires_scale": hires_scale,
                          "sampler": sampler, "scheduler": scheduler,
                          "force_inpaint": force_inpaint,
                          "zsnr": zsnr, "upscale_method": upscale_method,
                          "recipe_base_version": base.get("version", 0),
                          "neg": neg}, ensure_ascii=False, indent=1))
        return 0
    # ControlNet 参考图拷入 ComfyUI input 目录（LoadImage 只读那里）
    cnet_image = args.cnet_image
    if cnet_image:
        dst = os.path.join(r"D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/ComfyUI/input",
                           os.path.basename(cnet_image))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(cnet_image, dst)
        cnet_image = os.path.basename(cnet_image)
    seeds = ([args.start_seed + i for i in range(args.seeds)] if args.start_seed
             else [random.randint(10**8, 10**9 - 1) for _ in range(args.seeds)])
    # 每批独立文件夹（20261009 维护者令）：out/ 根目录不再平铺堆叠
    outdir = args.outdir or f"out/{args.prefix}_{time.strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(outdir, exist_ok=True)
    print(f"两段式 {len(seeds)} 抽: {seeds}"
          + (f" · LoRA={lora}@{lora_w}" if lora else "")
          + f" → {outdir}/")
    for seed in seeds:
        t0 = time.time()
        pid = post("/prompt", {"prompt": graph(seed, pos, neg, f"{args.prefix}_{seed}",
                                                    lora, lora_w, clip_skip, steps, cfg,
                                                    hires_steps, hires_denoise, hires_scale,
                                                    face_denoise, hand_denoise, face_steps,
                                                    hand_steps, face_guide, hand_guide, grain,
                                                    sampler, scheduler, force_inpaint,
                                                    zsnr, ca_px, vignette, contrast,
                                                    upscale_method=upscale_method,
                                                    cnet_model=args.cnet_model,
                                                    cnet_image=cnet_image,
                                                    cnet_strength=args.cnet_strength,
                                                    cnet_end=args.cnet_end),
                               "client_id": "cinematic-gen"})["prompt_id"]
        e = None
        for _ in range(480):
            h = get(f"/history/{pid}")
            if pid in h and (h[pid]["status"].get("completed") or h[pid]["status"].get("status_str") == "error"):
                e = h[pid]; break
            time.sleep(1)
        ok = bool(e) and e["status"]["status_str"] == "success"
        if ok:
            o = e["outputs"]["9"]["images"][0]
            fname = f"{outdir}/{args.prefix}_{seed}.png"
            with urllib.request.urlopen(f"{BASE}/view?filename={o['filename']}&subfolder={o.get('subfolder','')}&type=output", timeout=60) as r:
                open(fname, "wb").write(r.read())
            if not args.no_grain:
                film_treat(fname, fname, grain=grain, ca_px=ca_px,
                           vignette=vignette, contrast=contrast)  # 影调工艺（参数可调）
            print(f"seed {seed}: OK {round(time.time()-t0,1)}s → {fname}")
        else:
            print(f"seed {seed}: FAIL")


if __name__ == "__main__":
    main()
