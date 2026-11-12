"""生成应用图标（.ico / PNG），不依赖外部素材。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def _draw_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256.0
    # 圆角底板
    d.rounded_rectangle([4 * s, 4 * s, 252 * s, 252 * s], radius=58 * s,
                        fill=(23, 25, 32, 255))
    # 青色计时环（留一段缺口，像倒计时）
    ring = [34 * s, 34 * s, 222 * s, 222 * s]
    d.arc(ring, start=100, end=380, fill=(79, 209, 197, 255), width=int(20 * s))
    # 人坐在椅子上的简笔
    teal = (79, 209, 197, 255)
    white = (236, 241, 245, 255)
    # 头
    d.ellipse([112 * s, 66 * s, 146 * s, 100 * s], fill=white)
    # 身体
    d.rounded_rectangle([100 * s, 104 * s, 158 * s, 158 * s], radius=18 * s, fill=white)
    # 椅子靠背
    d.rounded_rectangle([166 * s, 92 * s, 184 * s, 168 * s], radius=8 * s, fill=teal)
    # 椅子坐垫 + 椅腿
    d.rounded_rectangle([86 * s, 156 * s, 186 * s, 172 * s], radius=8 * s, fill=teal)
    d.rectangle([96 * s, 172 * s, 108 * s, 212 * s], fill=teal)
    d.rectangle([168 * s, 172 * s, 180 * s, 212 * s], fill=teal)
    # 桌板
    d.rounded_rectangle([58 * s, 136 * s, 118 * s, 148 * s], radius=6 * s, fill=white)
    d.rectangle([66 * s, 148 * s, 76 * s, 196 * s], fill=white)
    return img


def write_icons(out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ico = out_dir / "sitguard.ico"
    png = out_dir / "sitguard.png"
    base = _draw_icon(256)
    base.save(png)
    base.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico, png


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print(write_icons(here / "assets"))
