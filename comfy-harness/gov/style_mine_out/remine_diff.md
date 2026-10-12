# 对照重挖 diff（P10 验收件 · 过程簇消失/真风格簇保留）

## A 确定性

- 语料：旧 76 → 新 45 文档（E′身份闸后）
- 簇数：旧 13 → 新 9
- **过程簇**：旧 0（覆盖 0 成员） → 新 0（覆盖 0）
- **风格簇**：旧 13 → 新 9
- 新过程簇：**零**（自食成分消失）
- 保留簇名（新旧同名）：6 个；消失：7；新出现：3
  - 新出现：['cherry blossoms · dappled sunlight · falling petals', 'cinematic lighting · city lights · from side', 'highres · masterpiece · safe']

## B LightRAG

- 语料：旧 76 → 新 45 文档（E′身份闸后）
- 簇数：旧 31 → 新 23
- **过程簇**：旧 14（覆盖 542 成员） → 新 0（覆盖 0）
- **风格簇**：旧 17 → 新 23
- 旧过程簇名（应消失）：['S-explosive-fireworks-display-9a12ad89·s(h11)', 'Machine Proposal Style Cluster·Video Gen(h9)', 'Hires Upscale Redraw·P-noobai-v3-pipelin(h2)', 'Candidate Boundary·Human Gate·Mining Art(h11)', 'Absurdres · Best Quality · Masterpiece S(h5)', 'First-Flight Informed Wiring·AniSora V3.(h2)', 'Machine Proposal·Venv·Venv·E-1时代实测·P-uv-(h6)', 'Observation Flow Technique·Hands In Pock(h4)', 'Machine Proposal Style Cluster Height Wi(h4)', 'Observation Flow Technique (Gain)·FLUX.2(h6)', 'NoobAI Vpred Cinematic Recipe·Variation (h2)', '机器提案·风格簇「deepseek · e-2 · 异族判官」·样本·成员/阈值(h6)', '2026-10-08 Four-way A/B Test·Weight 0.7·(h2)', 'Bokeh · City Lights · Many People Walkin(h3)']
- 新过程簇：**零**（自食成分消失）
- 保留簇名（新旧同名）：0 个；消失：31；新出现：23
  - 新出现：['/object_info·p-objectinfo-cache·e-1 era', '1girl·1girl·1 girl', '20261007 v3 validation·v3test_26100731/732·71.4s steady state', 'anisora v3.2 gguf·anisora v3.2 gguf first flight wiring·ksampler', 'api direct-connection informed wiring·flux2scheduler·samplercustom', 'comfyui 0.38.0·modelsamplingdiscrete·v_prediction', 'face second pass·p-noobai-v3-detailer-postproc·hand second pass', 'img_c.png·deepseek-v4-flash·e-2 formal exam 2026-10-03', 'informed arm·naive arm·field_wiring_run', 'lora arm·20261005 a/b test·baseline', 'noob_vp1_detailer_by_volnovik_v1·same-seed same-parameter reproduction·loraloader', 'noobai vpred cinematic recipe·variant principle·self-mixed-body case']…

判读口径：过程簇按 style_feed.is_process≥2 判（与铸前闸同源）；同名=归一化后逐字相等（措辞漂移会使名字不全等，故另列新出现/消失供人看成分）。
