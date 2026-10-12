# 风格挖掘对比报告 · 2026-10-10 17:50:45

语料：161 文档（两臂同吃 corpus.json）

## 〇-0 健康度读数（P9 · 占比记账/签名面/回声簇率/T 哨兵）

```
健康度读数（P9）：raw:ratified:draft = 161:19:84（生成面 161 / 已签 19 / 草案 84）
  ①approved 率 = 18/19 = 94.7%；②签名覆盖率 = 19/127 = 15.0%
  T-a 语义失效率 = 1/7 = 14.3%（探针固化集，离线）
  ③回声簇率 = 对已签 1/51 = 2.0%；对全库（含草案·自食度量）= 3/51 = 5.9%（阈值 cos≥0.9）
     近义样本：Scripts/*.exe·uv trampoline failed to canonicali → 已签 P-uv-venv-trampoline cos=0.947 / 全库 P-uv-venv-trampoline cos=0.947
     近义样本：AniSora V3.2 GGUF·Video Generation Frame Count C → 已签 P-antisora-wan22-gguf-wiring cos=0.849 / 全库 S-AniSora-V3-2-GGUF-KSampler-W cos=0.909
     近义样本：20261005 Dual-Arm Same-Seed Test·ComfyUI 0.38.0· → 已签 P-noobai-vpred-autodetect cos=0.877 / 全库 S-ComfyUI-0-38-0-Informed-Arm- cos=0.902
  T-b 重铸率 = 1 双胞组/84 草案 = 1.2%
  T-c 反例雷达（反向飞轮·影子）= 扫描 7 轮 / 命中 14；命中率 12.8%
  T-d 有向环 = 0 个（非同名声循环引用=自食铁证）｜经验图边数 55
```

## 〇 运行面

- **A 臂（确定性共现+社区检测）**：ran（0.5s） · 参数 {'min_support': 2, 'min_edge': 2, 'min_cluster': 3, 'stopword_ratio': 0.7, 'min_jaccard': 0.5, 'resolution': 1.5} · modularity · 耗时 0.44s
- **B 臂（LightRAG 图谱）**：ran（1587.9s） · LLM=deepseek-v4-flash · 嵌入=nomic-embed · insert 1561.7s

## 一 规模与覆盖（读数）

| 指标 | A 确定性 | B LightRAG |
|---|---|---|
| 簇数 | 26 | 25 |
| 最大簇 | 44 | 88 |
| 平均簇大小 | 9.4 | 27.8 |
| 证据覆盖（可回源文档数） | 154 | 69 |
| 实体/关系规模 | tag 面 256/379，边 1870 | 实体 716，关系 1175 |

## 二 跨臂配对（同一风格，两边都看到了吗）

| A 簇（确定性） | B 簇（LightRAG） | 匹配词 | 相似度 |
|---|---|---|---|
| aqua eyes · aqua hair · collared shirt（44） | Grey Shirt·Detailed Clothes Folds·Visible Seams（7） | 6 | 0.86 |
| ahoge · big grin · black wizard robe（30） | Fem Ron Weasley·Hogwarts Uniform·Gryffindor Colors（43） | 23 | 0.77 |
| cherry blossoms · dappled sunlight · falling petals（19） | Image·Outdoors·Wind（21） | 10 | 0.53 |
| anime illustration · crisp clean line art · gentle open smile（17） | Japanese High School Girl·Anime Key Visual·Anime Illustration（23） | 13 | 0.76 |
| after rain · blurry background · blurry foreground（13） | Girl·1Girl·Wet Road（33） | 6 | 0.46 |
| cinematic lighting · city lights · light rays（11） | Girl·1Girl·Wet Road（33） | 10 | 0.91 |
| arms slightly out · curled up · from above（8） | Hatsune Miku·Cel Shading·Layered Clothing（87） | 7 | 0.88 |
| broken columns · fish school · looking into distance（8） | Sunken Ruins·Fish School·Broken Columns（5） | 5 | 1.0 |
| bbox/face_yolov8m.pt · simple · 面部二道（7） | Official Full Table·Combination Pass·Hires Upscale Redraw（73） | 3 | 0.43 |
| broken wooden beams · inside shipwreck · light through broken planks（7） | Shipwreck·Broken Planks·Ship Interior（8） | 6 | 0.86 |
| dynamic pose · head tilted · musical note（7） | Hatsune Miku·Cel Shading·Layered Clothing（87） | 7 | 1.0 |
| fingers near mouth · freckles · hand near face（7） | Close-Up Portrait·Photo (Medium)·Quality Control Group（24） | 2 | 0.29 |
| 1990s anime style · film grain · oldschool（6） | Hatsune Miku·Cel Shading·Layered Clothing（87） | 6 | 1.0 |
| bioluminescence · blue glow · glowing particles（6） | Underwater·Dramatic Lighting·Deep Sea（28） | 6 | 1.0 |
| gold stripes · knit trim · red and yellow striped necktie（6） | Fem Ron Weasley·Hogwarts Uniform·Gryffindor Colors（43） | 2 | 0.33 |
| above the ocean surface · blue sky · clouds（5） | Image·Outdoors·Wind（21） | 4 | 0.8 |
| back view · hands barely visible · looking back（5） | Hatsune Miku·Cel Shading·Layered Clothing（87） | 5 | 1.0 |
| deep open water · distant whale · giant whale silhouette（5） | Underwater·Dramatic Lighting·Deep Sea（28） | 3 | 0.6 |
| deepseek · e-2 · 异族判官（5） | DeepSeek-V4-Flash·img_C.png·Deepseek-V4-Flash（88） | 4 | 0.8 |
| detailed shading · gradient shading · dark background（5） | Fem Ron Weasley·Hogwarts Uniform·Gryffindor Colors（43） | 3 | 0.6 |
| a single vintage car with headlights on · cliffs on one side · soft golden rim light ;（4） | Ultra-Wide Cinematic Shot·Fog-Drenched Coastal Highway·Vintage Car（9） | 4 | 1.0 |
| height · width · 布线（4） | API Direct Informed Wiring·Flux2Scheduler·SamplerCustom（53） | 3 | 0.75 |
| rating:general · score_7_up · score_8_up（4） | Girl·1Girl·Wet Road（33） | 1 | 0.25 |
| fabric texture · knit texture · bright red and gold striped necktie（3） | Fem Ron Weasley·Hogwarts Uniform·Gryffindor Colors（43） | 2 | 0.67 |
| red background · simple background · solid background（3） | Fem Ron Weasley·Hogwarts Uniform·Gryffindor Colors（43） | 3 | 1.0 |

**A 独有**（确定性聚出、LightRAG 未成簇/未对上）：['against light · arms slightly raised · backlit']

**B 独有**（LightRAG 聚出、确定性未成簇/未对上）：['AniSora V3.2 GGUF·Video Generation Frame Count Contract·Informed Wiring', 'FaceDetailer·FaceDetailer v2 (0.6/640 + Eye Prompts)·Eye-Specific Prompts', 'NoobAI Vpred Cinematic Recipe·Variant Principle·Scene and Motion Words', 'P-objectinfo-cache·/object_info·Single Class Query', 'Scripts/*.exe·uv trampoline failed to canonicalize script path·venv', '20261005 Dual-Arm Same-Seed Test·ComfyUI 0.38.0·Naive Direct Loading', 'P-Noobai-Cinematic-Prompt·NoobAI Vpred·Prompt Face', 'Sweeping Panning Shot·Sentient Tree·Spectral Sentinel', 'ComfyUI 0.38+·Cross-Version Revalidation·Manual V-Pred Handling', 'Seed·Detail Direction·Composition', 'Traditional Media·Watercolor·Paper Texture']

## 三 判读素材（工具不代判）

- 确定性：A 臂同输入必同输出；B 臂 LLM 抽取/命名含温度扰动（社区切分本身固定 seed）。
- 证据链：两臂 evidence 均可回源（A=文档 src；B=chunk→文档映射）。
- 粒度/命名质量/独有发现见上两节；终判归维护者。

### A 臂全簇
- 44 tag · cohesion 0.78 · aqua eyes · aqua hair · collared shirt
- 30 tag · cohesion 0.8 · ahoge · big grin · black wizard robe
- 19 tag · cohesion 0.8 · cherry blossoms · dappled sunlight · falling petals
- 17 tag · cohesion 0.76 · anime illustration · crisp clean line art · gentle open smile
- 13 tag · cohesion 0.91 · after rain · blurry background · blurry foreground
- 11 tag · cohesion 0.94 · cinematic lighting · city lights · light rays
- 8 tag · cohesion 0.81 · arms slightly out · curled up · from above
- 8 tag · cohesion 1.0 · broken columns · fish school · looking into distance
- 7 tag · cohesion 0.67 · bbox/face_yolov8m.pt · simple · 面部二道
- 7 tag · cohesion 1.0 · broken wooden beams · inside shipwreck · light through broken planks
- 7 tag · cohesion 0.78 · dynamic pose · head tilted · musical note
- 7 tag · cohesion 0.94 · fingers near mouth · freckles · hand near face
- 6 tag · cohesion 1.0 · 1990s anime style · film grain · oldschool
- 6 tag · cohesion 1.0 · bioluminescence · blue glow · glowing particles
- 6 tag · cohesion 0.79 · gold stripes · knit trim · red and yellow striped necktie
- 5 tag · cohesion 0.8 · above the ocean surface · blue sky · clouds
- 5 tag · cohesion 1.0 · against light · arms slightly raised · backlit
- 5 tag · cohesion 0.85 · back view · hands barely visible · looking back
- 5 tag · cohesion 1.0 · deep open water · distant whale · giant whale silhouette
- 5 tag · cohesion 0.93 · deepseek · e-2 · 异族判官
- 5 tag · cohesion 0.73 · detailed shading · gradient shading · dark background
- 4 tag · cohesion 1.0 · a single vintage car with headlights on · cliffs on one side · soft golden rim light ;
- 4 tag · cohesion 0.75 · height · width · 布线
- 4 tag · cohesion 1.0 · rating:general · score_7_up · score_8_up
- 3 tag · cohesion 0.87 · fabric texture · knit texture · bright red and gold striped necktie
- 3 tag · cohesion 1.0 · red background · simple background · solid background

### B 臂全簇
- 88 实体 · cohesion 1.11 · DeepSeek-V4-Flash·img_C.png·Deepseek-V4-Flash
- 87 实体 · cohesion 6.08 · Hatsune Miku·Cel Shading·Layered Clothing
- 73 实体 · cohesion 1.02 · Official Full Table·Combination Pass·Hires Upscale Redraw
- 53 实体 · cohesion 1.0 · API Direct Informed Wiring·Flux2Scheduler·SamplerCustom
- 53 实体 · cohesion 1.0 · AniSora V3.2 GGUF·Video Generation Frame Count Contract·Informed Wiring
- 43 实体 · cohesion 3.39 · Fem Ron Weasley·Hogwarts Uniform·Gryffindor Colors
- 40 实体 · cohesion 1.0 · FaceDetailer·FaceDetailer v2 (0.6/640 + Eye Prompts)·Eye-Specific Prompts
- 33 实体 · cohesion 1.68 · Girl·1Girl·Wet Road
- 28 实体 · cohesion 5.16 · Underwater·Dramatic Lighting·Deep Sea
- 27 实体 · cohesion 1.02 · NoobAI Vpred Cinematic Recipe·Variant Principle·Scene and Motion Words
- 24 实体 · cohesion 1.17 · Close-Up Portrait·Photo (Medium)·Quality Control Group
- 23 实体 · cohesion 1.46 · Japanese High School Girl·Anime Key Visual·Anime Illustration
- 21 实体 · cohesion 1.68 · Image·Outdoors·Wind
- 15 实体 · cohesion 1.0 · P-objectinfo-cache·/object_info·Single Class Query
- 15 实体 · cohesion 1.0 · Scripts/*.exe·uv trampoline failed to canonicalize script path·venv
- 12 实体 · cohesion 1.0 · 20261005 Dual-Arm Same-Seed Test·ComfyUI 0.38.0·Naive Direct Loading
- 10 实体 · cohesion 1.0 · P-Noobai-Cinematic-Prompt·NoobAI Vpred·Prompt Face
- 9 实体 · cohesion 1.0 · Ultra-Wide Cinematic Shot·Fog-Drenched Coastal Highway·Vintage Car
- 8 实体 · cohesion 1.62 · Shipwreck·Broken Planks·Ship Interior
- 8 实体 · cohesion 1.0 · Sweeping Panning Shot·Sentient Tree·Spectral Sentinel
- 7 实体 · cohesion 1.0 · ComfyUI 0.38+·Cross-Version Revalidation·Manual V-Pred Handling
- 7 实体 · cohesion 6.38 · Grey Shirt·Detailed Clothes Folds·Visible Seams
- 5 实体 · cohesion 1.0 · Sunken Ruins·Fish School·Broken Columns
- 3 实体 · cohesion 1.0 · Seed·Detail Direction·Composition
- 3 实体 · cohesion 1.0 · Traditional Media·Watercolor·Paper Texture
