#!/usr/bin/env python3
"""五套主题色卡：从 system.css 读 .theme-* 的 paper/ink/accent，拼成一张横向色卡图。

    python tools/swatch.py            # → out/themes.png (1800×640)
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H, GAP = 340, 560, 25
LABEL_H = 96


def parse_themes():
    css = (ROOT / "templates" / "system.css").read_text(encoding="utf-8")
    themes = []
    for m in re.finditer(r"\.theme-([\w-]+)\s*\{([^}]*)\}", css):
        name, body = m.group(1), m.group(2)

        def var(k):
            mm = re.search(rf"--{k}:\s*(#[0-9a-fA-F]{{3,6}})", body)
            return mm.group(1) if mm else "#000000"

        note = re.search(r"/\*\s*(.+?)\s*\*/", body)
        themes.append({"name": name, "paper": var("paper"), "ink": var("ink"),
                       "accent": var("accent"), "note": note.group(1) if note else ""})
    return themes


def font(size, ink):
    p = ROOT / "assets" / "NotoSansSC-VF.ttf"
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def card(t, f_serif, f_mono):
    im = Image.new("RGB", (W, H), hexrgb(t["paper"]))
    d = ImageDraw.Draw(im)
    ink, accent = hexrgb(t["ink"]), hexrgb(t["accent"])

    d.rectangle([24, 64, 88, 68], fill=accent)                       # 顶部短强调条
    d.text((24, 96), t["name"], font=f_serif, fill=ink)              # 主题名
    d.text((24, 176), t["note"], font=f_mono, fill=ink)              # 中文说明
    # 三色样：纸 / 墨 / 强调
    for i, (label, col) in enumerate([("paper", t["paper"]), ("ink", t["ink"]), ("accent", t["accent"])]):
        y = 240 + i * 84
        d.rectangle([24, y, 104, y + 56], fill=hexrgb(col), outline=ink if label != "accent" else None)
        d.text((124, y + 6), label, font=f_mono, fill=ink)
        d.text((124, y + 30), col, font=f_mono, fill=ink)
    # 反白块示例
    d.rectangle([24, 486, 208, 528], fill=accent)
    d.text((34, 494), "==反白==", font=f_serif, fill=hexrgb(t["paper"]))
    return im


def main():
    themes = parse_themes()
    if not themes:
        raise SystemExit("system.css 里没有 .theme-*")
    f_serif = font(34, None)
    f_mono = font(15, None)
    total_w = len(themes) * W + (len(themes) - 1) * GAP + GAP * 2
    sheet = Image.new("RGB", (total_w, H + LABEL_H + GAP * 2), "#e8e6e0")
    dd = ImageDraw.Draw(sheet)
    dd.text((GAP, 18), "YXL / 1212  ·  THEME SWATCHES  ·  templates/system.css", font=f_mono, fill="#55524a")
    for i, t in enumerate(themes):
        x = GAP + i * (W + GAP)
        sheet.paste(card(t, f_serif, f_mono), (x, LABEL_H + GAP))
    out = ROOT / "out" / "themes.png"
    out.parent.mkdir(exist_ok=True)
    sheet.save(out)
    print(f"  themes.png  {sheet.size[0]}x{sheet.size[1]}  {len(themes)} themes  → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
