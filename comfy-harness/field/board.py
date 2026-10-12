# -*- coding: utf-8 -*-
"""board.py — 批次预览板（分诊索引）。

定位（维护者裁 20261008，报告-AI注意力优化 #1）：**图视觉全量审看不省**——
板只负责把整批摆到一块让全量审看更聚焦（横向差异、疑点定位），终审仍逐张开原图。

用法：py -X utf8 board.py --prefix candid [--cols 2] [--tile 620] [--dir out]
产出：out/_board_<prefix>.png（网格拼图+文件名标注；已被 .gitignore 挡出库）。
"""
import argparse
import glob
import os
import sys

from PIL import Image, ImageDraw

_MARGIN = 8
_LABEL = 26


def build(prefix: str, directory: str = "out", cols: int = 2, tile: int = 620,
          out: str | None = None) -> tuple:
    # 递归匹配：20261009 起每批独立子文件夹（out/<prefix>_<ts>/），兼容旧平铺件
    files = sorted(f for f in glob.glob(os.path.join(directory, "**", f"{prefix}_*.png"),
                                        recursive=True)
                   if not os.path.basename(f).startswith(("_board", "_hand")))
    if not files:
        raise SystemExit(f"无匹配：{prefix}_*.png @ {directory}")
    imgs = []
    for f in files:
        src = Image.open(f)
        src.load()                       # 强制解码后即可释句柄（Windows 锁到 tmp 清理）
        im = src.convert("RGB").resize((tile, max(1, int(src.height * tile / src.width))))
        src.close()
        imgs.append((os.path.basename(f), im))
    rows = (len(imgs) + cols - 1) // cols
    row_h = [max(im.height for _, im in imgs[r * cols:(r + 1) * cols]) for r in range(rows)]
    W = cols * tile + (cols + 1) * _MARGIN
    H = sum(row_h) + rows * (_LABEL + _MARGIN) + _MARGIN
    board = Image.new("RGB", (W, H), (16, 16, 20))
    draw = ImageDraw.Draw(board)
    y = _MARGIN
    for r in range(rows):
        for c, (name, im) in enumerate(imgs[r * cols:(r + 1) * cols]):
            x = _MARGIN + c * (tile + _MARGIN)
            draw.text((x + 2, y + 4), name, fill=(240, 240, 240))
            board.paste(im, (x, y + _LABEL))
        y += row_h[r] + _LABEL + _MARGIN
    out = out or os.path.join(directory, f"_board_{prefix}.png")
    board.save(out)
    board.close()                        # Windows：落盘即释句柄（测试/后续读取要开它）
    return out, len(files)


def main(argv=None):
    ap = argparse.ArgumentParser(description="批次预览板（分诊索引，终审原图不省）")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--dir", default="out")
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--tile", type=int, default=620)
    a = ap.parse_args(argv)
    out, n = build(a.prefix, a.dir, a.cols, a.tile)
    print(f"[board] {n} 张 → {out}（分诊索引；终审逐张原图不省）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
