# comfy-harness

ComfyUI API 飞轮实验架 + 判例治理件：把「操作 → 记录 → 提炼 skill → 复用」四环
在真实生成上跑通，并用治理状态机防止错误经验固化成毒 skill。

## 它能干什么

| 模块 | 干什么 |
|---|---|
| `field/` | 对活体 ComfyUI 服务器（HTTP API）做知情布线真生成：先对 `/object_info` 预检输入键，再 POST `/prompt`，PIL 机械验证出图 |
| `e1/` | 干转实验：空库朴素布线 vs 判例库知情布线，对活体 schema 做差分断言 |
| `e2/` | 判官正式考：异族 VLM 判官（OpenAI 兼容接口）对图像交付做二元判读，含机械锚参照引导与位置伪影双序对 |
| `gov/` | 判例治理层：人签晋升（`human:*` 闸）/两段式退场（approved 须先 deprecate 再墓碑）/无主防毒（owner 空永不召回）/治理事件流 + 原子持久化（载入防毒再验证） |
| `evocore/` | 内嵌依赖：演化记忆引擎（条目校验/生命周期/检索评分），随包免安装 |

## 凭什么能通

- 知情布线实测：12 节点 Flux2 klein 工作流对活体 v0.38 schema 预检零非法键，42.7s 出图
  （见 `comfy-harness/field/out/`：回执 JSON + 1024² 样图）
- 离线测试全绿：`gov/smoke_wb.py` 13/13 + `gov/test_p3fix_audit.py` 10/10 +
  `evocore/tests/` 全套（纯内存，不需要 ComfyUI）

## 快速开始

```bash
# 0) 依赖：Python 3.10+，Pillow（field/e1 需要）；ComfyUI 本体自备
pip install Pillow

# 1) 离线测试（不需要 ComfyUI）
python comfy-harness/gov/smoke_wb.py
python -m pytest evocore/tests -q

# 2) 实地生成（需要本机 8188 端口有 ComfyUI 服务，模型名见 field_wiring_run.py 图谱）
python comfy-harness/field/field_wiring_run.py
```

E-2 判官考试复现说明：`e2_deepseek_exam.py` 运行时从 `~/.zcode/v2/provider_config.json`
读 DeepSeek 兼容端点配置（key 绝不入仓），考题图像需自备同尺寸沙盒图，机械锚读数
按你自己的图用 PIL 实测后替换 `ANCHORS` 表。

## 安全模型

- 治理动效（promote/deprecate/tombstone/supersede）一律强制 `human:*` 签名，AI 缺省拒绝；
- 持久化载入侧防毒：盘面 approved 必须有人签 promote 事件背书，否则降级 draft 并收回 owner；
- API key 运行时读取，仓库零密钥（CI 可扫）。

## 已知限制

- `e1/e2` 的判读题面与判例种子来自特定实验批次，换场景需自备题面；
- ComfyUI 节点 schema 随版本漂移，布线前预检（脚本已内置）失败时会响亮报错而非硬跑。

## License

MIT
