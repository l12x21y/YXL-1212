#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YXL/1212 渲染器
  文字内容 (JSON)  →  3:4 纸面版式 (HTML)  →  PNG 图

用法:
    python render.py content/demo.json
    python render.py content/demo.json --only 1,3
    python render.py content/demo.json --html-only

不出图时只生成 HTML，用浏览器可直接看/手改。
"""
import html
import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
HTML_DIR = OUT / "html"

W, H = 1800, 2400           # 与 system.css 的 --W / --H 一致

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


# ────────────────────────── 小工具 ──────────────────────────
def e(s):
    return html.escape(str(s), quote=False)


def _span_end(html, i):
    """从 i 开始找与已开的 <span> 配对的那个 </span> 的结束位置。"""
    depth, n = 1, i
    while n < len(html):
        m = re.compile(r"<span\b|</span>").search(html, n)
        if not m:
            return -1
        depth += -1 if m.group(0) == "</span>" else 1
        if depth == 0:
            return m.end()
        n = m.end()
    return -1


def _indent_tail(html):
    """提行落在段首时，后面的文字空两格，和提行的左端对齐。"""
    head = '<span class="line">'
    if not html.startswith(head):
        return html
    end = _span_end(html, len(head))
    if end <= 0 or end >= len(html):
        return html
    return html[:end] + f'<span class="ind">{html[end:]}</span>'


def lines(v):
    """字符串数组 → <br> 分行（标题手动断行，比自动折行可控）
    文本里用 *字* 包裹的字符会染上强调色；
    字符串里的 \\n 表示硬换行，换行后的那一行空两格。"""
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        segs = x.split("\n")
        html = _indent_tail(accentize(segs[0]))
        for s in segs[1:]:
            # 大字句自己带左缩进，别再套 .ind，否则缩进叠成两倍
            if s.startswith("@@"):
                html += "<br>" + accentize(s)
            else:
                html += "<br>" + (f'<span class="ind">{accentize(s)}</span>' if s else "")
        out.append(html)
    return "<br>".join(out)


def accentize(s):
    """行内强调，四档由轻到重：
       *字*   → 染强调色（不改字号）
       ^^句^^  → 放大字号
       !!!句!!!→ 加重（500，慎用，破坏细体基调）
       ==句==  → 反白色块
       [[句]]  → 单独占一行（关键句独立成行）
       @@句@@  → 大字句：独立成行、100px、换色，前后留白最大
       <~句~> → 压灰（ink-2），"这句是自嘲/旁白，别当真"
    """
    # <~ ~> 先抽成占位符，再 escape —— 否则尖括号会被 html.escape 变成 &lt;~，
    # 后面的正则就再也匹配不到（实测踩过一次）
    dims = []
    s = re.sub(r"<~(.+?)~>",
               lambda m: dims.append(m.group(1)) or f"\x00DIM{len(dims) - 1}\x00", s)
    s = e(s)
    for k, txt in enumerate(dims):
        s = s.replace(f"\x00DIM{k}\x00", f'<span class="dim">{e(txt)}</span>')
    # 整行首尾的破折号做"悬挂"：开头的挪到上一行尾，结尾的收进行内，避免行首出标点
    s = re.sub(r"@@([—－]{2})(.+?)@@", r"\1@@\2@@", s)
    s = re.sub(r"@@(.+?)@@", r'<span class="pull">\1</span>', s)
    s = re.sub(r"\[\[([—－]{2})(.+?)\]\]", r'\1<span class="line">\2</span>', s)
    s = re.sub(r"\[\[(.+?)\]\]([—－]{2})", r"[[\1\2]]", s)
    s = re.sub(r"\[\[(.+?)\]\]", r'<span class="line">\1</span>', s)
    s = re.sub(r"!!(.+?)!!", r'<b class="wt">\1</b>', s)
    s = re.sub(r"\*(.+?)\*", r'<em class="ac">\1</em>', s)
    s = re.sub(r"\^\^(.+?)\^\^", r'<span class="big">\1</span>', s)
    # 块里套了放大字时，块要加高一档，否则大字上方贴着边框（见 .inv-big）
    s = re.sub(r"==(.+?)==",
               lambda m: (f'<span class="inv inv-big">{m.group(1)}</span>'
                          if 'class="big"' in m.group(1)
                          else f'<span class="inv">{m.group(1)}</span>'), s)
    return s


def folio(i):
    return f"{i:02d}"


def colophon(p, i, meta):
    items = p.get("colophon") or [
        f'{meta.get("series", "YXL / 1212")} · {meta.get("issue", "")}'.strip(" ·"),
        meta.get("date", ""),
        f"P.{folio(i)}",
    ]
    spans = "".join(f"<span>{e(x)}</span>" for x in items)
    return f'<div class="colophon meta">{spans}</div>'


def topbar(p, meta):
    left = p.get("kicker") or meta.get("series", "YXL / 1212")
    right = p.get("running_head", "")          # 不再默认输出期号，要就显式写
    r = f"<span>{e(right)}</span>" if right else ""
    return f'<div class="meta meta-top"><span>{e(left)}</span>{r}</div>'


# ────────────────────────── 七种版式 ──────────────────────────
def _plain(s):
    """去掉行内标记，只留字，用来算标题该放多大"""
    return re.sub(r"==|\*\*|\*|!!|\^\^|\[\[|\]\]", "", s)


def l_cover(p, i, meta):
    inner = ""
    if p.get("subtitle"):
        inner += f'<p class="t-lead">{lines(p["subtitle"])}</p>'
    if p.get("subtitle_en"):
        inner += f'<p class="t-small latin" style="margin-top:26px">{lines(p["subtitle_en"])}</p>'
    sub = f'<div class="sub"><span class="bar"></span><div>{inner}</div></div>' if inner else ""
    rule = "rule-accent" if p.get("rule") == "accent" else "rule-ink"
    # 标题太长时按最长一行自动降字号，别让 8 个字折成 5+3
    tt = p.get("title", "")
    tt = tt if isinstance(tt, list) else [tt]
    maxlen = max((len(_plain(x)) for x in tt), default=0)
    fs = 180
    if maxlen:
        fs = max(96, min(180, int(1420 / (maxlen * 1.02))))
    style = f' style="font-size:{fs}px"' if fs < 180 else ""
    return f'''<div class="frame">
      {topbar(p, meta)}
      <div class="title-wrap">
        <div class="{rule}"></div>
        <h1 class="t-display"{style}>{lines(p.get("title", ""))}</h1>{sub}
      </div>
      {colophon(p, i, meta)}
    </div>'''


def l_statement(p, i, meta):
    """竖排：每列一个 <p>，由 vertical-rl 的块方向从右往左堆叠。
    text 给字符串 → 自动分列并算字号；给数组 → 数组即列（手控）。"""
    t = p.get("text", "")
    if isinstance(t, list):
        parts, fs = t, 132
    else:
        MAXCOL, MAXH, ADV = 12, 1760, 0.93   # 每列字数上限 / 可用列高 / 单字前进量(em，实测)
        n = len(t)
        cols = max(1, min(3, -(-n // MAXCOL)))
        per = -(-n // cols)
        fs = min(150, int(MAXH / (per * ADV)))
        parts = [t[k * per:(k + 1) * per] for k in range(cols)]
    vertical = "".join(f"<p>{accentize(x)}</p>" for x in parts if x)
    # 横排前缀：竖排里的拉丁字母会被 text-orientation:mixed 侧倒成一小条
    # （"AI" 倒过来只有 0.7em 宽，和旁边的汉字完全不成比例）。提出来横排放。
    pre = p.get("pre", "")
    pre_html = f'<div class="pre">{accentize(pre)}</div>' if pre else ""
    note = p.get("note", "")
    note_html = f'<p class="t-micro">{lines(note)}</p>' if note else ""
    aside = f'<div class="aside"><div class="dot-accent"></div>{note_html}</div>' if note else ""
    return f'''<div class="frame">
      {topbar(p, meta)}
      {pre_html}<div class="vertical" style="font-size:{fs}px">{vertical}</div>{aside}
      {colophon(p, i, meta)}
    </div>'''


def l_quote(p, i, meta):
    sign = p.get("sign", "")
    sign_html = (f'<div class="sign"><span class="line"></span>'
                 f'<span class="t-small">{e(sign)}</span></div>') if sign else ""
    # 没有署名时，下方空出来的一大片交给 quote-body 自己吸收，
    # 否则 margin-top:auto 会把大字一路顶到底、贴住版权行
    body_cls = "quote-body" if sign else "quote-body no-sign"
    # 文字里已经有反白色块时，左侧红条就成了多余的第二重点，去掉
    raw = p.get("text", "")
    raw = raw if isinstance(raw, str) else "".join(raw)
    bar = '' if "==" in raw else '<div class="bar-accent"></div>'
    return f'''<div class="frame">
      {topbar(p, meta)}
      <div class="{body_cls}">
        {bar}
        <blockquote class="t-d2">{lines(p.get("text", ""))}</blockquote>
      </div>{sign_html}
      {colophon(p, i, meta)}
    </div>'''


def l_list(p, i, meta):
    head_bits = []
    if p.get("lead"):
        head_bits.append(f'<p class="t-small">{lines(p["lead"])}</p>')
    items = ""
    for k, it in enumerate(p.get("items", []), 1):
        d = f'<p class="t-small">{lines(it.get("d", ""))}</p>' if it.get("d") else ""
        items += (f'<div class="item"><div class="n">{k:02d}</div>'
                  f'<div><h2 class="t-h2">{e(it.get("t", ""))}</h2>{d}</div></div>')
    return f'''<div class="frame">
      {topbar(p, meta)}
      <div class="head">
        <h1 class="t-h1">{lines(p.get("title", ""))}</h1>{''.join(head_bits)}
      </div>
      <div class="items">{items}</div>
      {colophon(p, i, meta)}
    </div>'''


def l_essay(p, i, meta):
    body = "".join(f'<p class="t-body">{lines(x)}</p>' for x in p.get("paragraphs", []))
    sign = p.get("sign", "")
    sign_html = f'<div class="sign"><p class="t-small">{e(sign)}</p></div>' if sign else ""
    return f'''<div class="frame">
      {topbar(p, meta)}
      <div class="main">
        <div class="head">
          <p class="label">{e(p.get("label", ""))}</p>
          <h1 class="t-h1">{lines(p.get("title", ""))}</h1>
        </div>
        <div class="body">{body}</div>
      </div>
      {sign_html}
      {colophon(p, i, meta)}
    </div>'''


def l_index(p, i, meta):
    rows = ""
    for k, it in enumerate(p.get("items", []), 1):
        rows += (f'<div class="row"><span class="n">{k:02d}</span>'
                 f'<span class="t">{e(it.get("t", ""))}</span>'
                 f'<span class="pg">{e(it.get("pg", ""))}</span></div>')
    note = f'<p class="t-micro">{lines(p["note"])}</p>' if p.get("note") else ""
    return f'''<div class="frame">
      {topbar(p, meta)}
      <div class="head">
        <div><h1 class="t-h1">{lines(p.get("title", ""))}</h1></div>{note}
      </div>
      <div class="rows">{rows}</div>
      {colophon(p, i, meta)}
    </div>'''


def l_split(p, i, meta):
    fig = p.get("figure", "")
    fig_html = f'<div class="figure">{lines(fig)}</div>' if fig else "<div></div>"
    lead = f'<p class="t-lead">{lines(p["lead"])}</p>' if p.get("lead") else ""
    body = "".join(f'<p class="t-body">{lines(x)}</p>' for x in p.get("paragraphs", []))
    return f'''<div class="frame">
      <div class="top">
        <div class="meta meta-top"><span>{e(p.get("kicker", ""))}</span><span>{e(p.get("side", ""))}</span></div>
        {fig_html}
        <div class="meta">{e(p.get("figure_caption", ""))}</div>
      </div>
      <div class="bottom">
        <div class="main">
          <h1 class="t-h1">{lines(p.get("title", ""))}</h1>{lead}{body}
        </div>
        {colophon(p, i, meta)}
      </div>
    </div>'''


LAYOUTS = {
    "cover": l_cover, "statement": l_statement, "quote": l_quote, "list": l_list,
    "essay": l_essay, "index": l_index, "split": l_split,
}


# ────────────────────────── 组页 ──────────────────────────
def build(p, i, meta, css_href):
    lay = p.get("layout", "cover")
    if lay not in LAYOUTS:
        raise SystemExit(f"未知版式: {lay}（可选 {', '.join(LAYOUTS)}）")
    theme = p.get("theme") or meta.get("theme", "ivory")
    body = LAYOUTS[lay](p, i, meta)
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<title>{e(meta.get('series','YXL / 1212'))} · {folio(i)}</title>
<link rel="stylesheet" href="{css_href}">
</head>
<body>
<section class="plate theme-{theme} layout-{lay}">
  <div class="folio">{folio(i)}</div>
  {body}
</section>
</body></html>'''


def find_chrome():
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    raise SystemExit("找不到 Chrome / Edge")


def png_size(p):
    with open(p, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def shoot(chrome, src, dst):
    prof = Path(tempfile.gettempdir()) / "yxl-chrome"
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-first-run", "--no-default-browser-check", "--allow-file-access-from-files",
           "--force-device-scale-factor=1", f"--user-data-dir={prof}",
           f"--window-size={W},{H}", "--virtual-time-budget=8000",
           f"--screenshot={dst}", src.as_uri()]
    r = subprocess.run(cmd, capture_output=True)
    if not Path(dst).exists():
        raise SystemExit(f"截图失败:\n{r.stderr.decode('utf-8', 'ignore')[:800]}")


CONTENT = ROOT / "content"

LAYOUT_CN = {"cover": "封面", "statement": "竖排宣言", "quote": "引文", "list": "条目",
             "essay": "正文", "index": "目录", "split": "封底"}

THEME_SKIN = {
    "ivory": ("#f2efe7", "#17160f", "#1b2ac6"),
    "bone":  ("#efeeea", "#14161a", "#d93b22"),
    "kraft": ("#e7dcc7", "#2b2113", "#bf4218"),
    "slate": ("#e8e9e5", "#101216", "#c3216b"),
    "night": ("#15150f", "#edeae1", "#e4543a"),
}


def dest_for(src):
    """out/ 镜像 content/ 的层级：content/A/B.json → out/A/B/"""
    try:
        rel = src.resolve().relative_to(CONTENT.resolve())
        return OUT / rel.parent / src.stem
    except ValueError:
        return OUT / src.stem


INDEX_TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title} · {series}</title>
<style>
  :root{{--paper:{paper};--ink:{ink};--ink2:{ink}99;--ink3:{ink}55;--hair:{ink}26;--accent:{accent};
    --serif:"Noto Serif SC","Songti SC",SimSun,Georgia,serif;--mono:Consolas,monospace}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:var(--paper);color:var(--ink);font-family:var(--serif);font-weight:300;
    padding:72px 60px 88px;-webkit-font-smoothing:antialiased}}
  header{{border-bottom:1px solid var(--hair);padding-bottom:34px;margin-bottom:54px;
    display:flex;justify-content:space-between;align-items:flex-end;gap:40px}}
  .kicker{{font-family:var(--mono);font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:var(--ink3)}}
  h1{{font-size:50px;font-weight:200;line-height:1.3;margin-top:18px;letter-spacing:.01em}}
  .lede{{font-size:16px;line-height:1.9;color:var(--ink2);margin-top:15px;max-width:720px;letter-spacing:.02em}}
  .tally{{font-family:var(--mono);font-size:12px;letter-spacing:.18em;color:var(--ink3);text-align:right;white-space:nowrap;line-height:2}}
  .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:38px 30px}}
  figure img{{width:100%;display:block;border:1px solid var(--hair)}}
  figcaption{{margin-top:12px;display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
  .name{{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase}}
  .n{{color:var(--ink3);margin-right:8px}}
  .use{{font-size:12.5px;color:var(--ink3);letter-spacing:.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  footer{{margin-top:60px;padding-top:22px;border-top:1px solid var(--hair);display:flex;
    justify-content:space-between;font-family:var(--mono);font-size:11.5px;letter-spacing:.18em;
    text-transform:uppercase;color:var(--ink3)}}
</style></head><body>
<header>
  <div>
    <div class="kicker">{series} · {chapter}</div>
    <h1>{title}</h1>
    {lede_html}
  </div>
  <div class="tally">{count} PLATES<br>1800 × 2400</div>
</header>
<div class="grid">
{figures}</div>
<footer><span>{series}</span><span>Noto Serif SC · 200 / 300</span><span>{date}</span></footer>
</body></html>
"""


def write_index(dest, shots, meta, chapter=""):
    """自动生成该章的总览页（同目录 index.html）。"""
    paper, ink, accent = THEME_SKIN.get(meta.get("theme", "ivory"), THEME_SKIN["ivory"])
    figs = ""
    for name, lay, cap in shots:
        figs += (f'  <figure><img src="{name}.png" alt="{name}">\n'
                 f'    <figcaption><span class="name"><span class="n">{name[:2]}</span>'
                 f'{lay.upper()}</span><span class="use">{e(cap)}</span></figcaption></figure>\n')
    lede = meta.get("lede", "")
    (dest / "index.html").write_text(INDEX_TPL.format(
        title=e(meta.get("title") or meta.get("series", "YXL / 1212")),
        lede_html=f'<p class="lede">{e(lede)}</p>' if lede else "",
        series=e(meta.get("series", "YXL / 1212")),
        chapter=e(chapter or meta.get("chapter", "")),
        date=e(meta.get("date", "")),
        paper=paper, ink=ink, accent=accent,
        count=len(shots), figures=figs), encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    src = Path(args[0] if args else ROOT / "content" / "demo.json")
    doc = json.loads(src.read_text(encoding="utf-8"))
    meta = doc.get("meta", {})
    pages = doc["pages"]

    # 一章一个文件夹：output 目录镜像 content/ 的层级
    dest = dest_for(src)
    html_dir = dest / "html"

    only = None
    if "--only" in sys.argv:
        k = sys.argv.index("--only")
        if k + 1 >= len(sys.argv):
            raise SystemExit("--only 后面要跟页码，例如 --only 1,3")
        only = {int(x) for x in sys.argv[k + 1].replace(",", " ").split()}

    html_dir.mkdir(parents=True, exist_ok=True)
    chrome = None if "--html-only" in flags else find_chrome()

    # HTML 可能在任意层级（out/文章/章节/html/），按实际深度回指 templates/
    css_href = "../" * len(html_dir.relative_to(ROOT).parts) + "templates/system.css"

    shots = []
    for i, p in enumerate(pages, 1):
        if only and i not in only:
            continue
        lay = p.get("layout", "cover")
        name = f"{folio(i)}-{lay}"
        hp = html_dir / f"{name}.html"
        hp.write_text(build(p, i, meta, css_href), encoding="utf-8")
        shots.append((name, lay, p.get("kicker") or LAYOUT_CN.get(lay, lay)))
        if chrome:
            dst = dest / f"{name}.png"
            shoot(chrome, hp, dst)
            w, h = png_size(dst)
            print(f"  {name}.png  {w}x{h}  {'OK' if (w, h) == (W, H) else '!! 尺寸异常'}")
        else:
            print(f"  {name}.html")

    if chrome and not only:
        # 章节名取文件名去掉序号前缀：01-导言 → 导言
        chap = src.stem
        if "-" in chap and chap.split("-", 1)[0].isdigit():
            chap = chap.split("-", 1)[1]
        write_index(dest, shots, meta, chap)
        print(f"  index.html  ← {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
