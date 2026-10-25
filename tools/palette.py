#!/usr/bin/env python3
"""色卡：在浏览器里改纸/墨/强调色，实时看 3:4 小样，导出后写回 CSS。

    python tools/palette.py build          → palette.html（项目根目录，浏览器打开）
    python tools/palette.py apply themes.json   → 改写 templates/system.css 的 .theme-* 块

只改三个变量：纸、墨、强调色。ink-2 / ink-3 / hair 由墨色按固定透明度派生；
glow / shade / grain-blend 沿用原主题的设置（新主题按明暗自动推）。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "templates" / "system.css"

BLOCK_RE = re.compile(r"\.theme-([a-z0-9\-]+)\s*\{[^}]*\}", re.S)


def lum(hex6):
    h = hex6.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + .05) / (lo + .05)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def parse_themes():
    css = CSS.read_text(encoding="utf-8")
    out = []
    for m in BLOCK_RE.finditer(css):
        body = m.group(0)
        key = m.group(1)
        note = re.search(r"/\*\s*(.*?)\s*\*/", body)
        g = lambda n, d="": (re.search(r"--%s:\s*([^;]+);" % n, body) or [None, d])[1].strip()
        # 透明度沿用原值：只换颜色，不改灰阶节奏
        a = lambda n, d: float((re.search(r"--%s:\s*rgba\([^)]*?,\s*([\d.]+)\s*\)" % n, body)
                                or [None, d])[1])
        out.append({
            "key": key,
            "name": note.group(1) if note else key,
            "paper": g("paper", "#ffffff"),
            "ink": g("ink", "#000000"),
            "accent": g("accent", "#cc0000"),
            "a2": a("ink-2", .60), "a3": a("ink-3", .34), "ah": a("hair", .16),
            "glow": g("glow"), "shade": g("shade"), "blend": g("grain-blend", "multiply"),
        })
    return out


def render_block(t):
    paper, ink, accent = t["paper"], t["ink"], t["accent"]
    r, g, b = hex_to_rgb(ink)
    dark = lum(paper) < .4
    a2, a3, ah = t.get("a2", .60), t.get("a3", .34), t.get("ah", .16)
    fp = lambda v: f"{v:.2f}".lstrip("0")   # .60 而不是 0.6，跟手写风格一致
    glow = t.get("glow") or ("rgba(255, 245, 225, .07)" if dark else "rgba(255, 255, 255, .5)")
    shade = t.get("shade") or ("rgba(0, 0, 0, .45)" if dark else "rgba(0, 0, 0, .07)")
    blend = t.get("blend") or ("screen" if dark else "multiply")
    return f""".theme-{t['key']} {{            /* {t['name']} */
  --paper: {paper}; --ink: {ink};
  --ink-2: rgba({r}, {g}, {b}, {fp(a2)}); --ink-3: rgba({r}, {g}, {b}, {fp(a3)});
  --hair: rgba({r}, {g}, {b}, {fp(ah)});
  --accent: {accent};
  --glow: {glow}; --shade: {shade};
  --grain-blend: {blend};
}}"""


def cmd_apply(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    css = CSS.read_text(encoding="utf-8")
    old = {t["key"]: t for t in parse_themes()}
    for t in data["themes"]:
        t.setdefault("name", t["key"])
        prev = old.get(t["key"], {})
        for k in ("glow", "shade", "blend", "a2", "a3", "ah"):
            if k in prev:
                t.setdefault(k, prev[k])
        block = render_block(t)
        pat = re.compile(r"\.theme-%s\s*\{[^}]*\}" % re.escape(t["key"]), re.S)
        if pat.search(css):
            css = pat.sub(lambda m: block, css, count=1)
            print(f"  更新 .theme-{t['key']}")
        else:
            anchor = "/* ---------- 重置 ---------- */"
            css = css.replace(anchor, block + "\n" + anchor, 1)
            print(f"  新增 .theme-{t['key']}")
    CSS.write_text(css, encoding="utf-8")
    print("  → templates/system.css")


# ─────────────────────────── build ───────────────────────────

TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>色卡 · YXL / 1212</title>
<style>
  @font-face{{font-family:"NSSC";src:url("assets/NotoSerifSC-VF.ttf") format("truetype");font-weight:100 900;font-display:swap}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#e9e6df;font-family:"NSSC","Songti SC",SimSun,serif;font-weight:300;color:#1a1815;
    -webkit-font-smoothing:antialiased;padding:0 0 60px}}
  .top{{position:sticky;top:0;z-index:20;background:#e9e6dff2;backdrop-filter:blur(8px);
    border-bottom:1px solid #1a181522;padding:13px 28px;display:flex;align-items:center;gap:16px}}
  .top b{{font-weight:400;font-size:15px;letter-spacing:.06em}}
  .top .hint{{font-size:12px;color:#1a181588;letter-spacing:.04em}}
  .top .sp{{flex:1}}
  .top button{{font-family:inherit;font-size:13px;letter-spacing:.06em;padding:7px 14px;border:1px solid #1a181533;
    background:transparent;cursor:pointer;color:#1a1815}}
  .top button:hover{{background:#1a1815;color:#e9e6df}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:26px;padding:26px 28px}}
  .card{{background:#f7f5f0;border:1px solid #1a18151a}}
  .card header{{display:flex;align-items:baseline;gap:9px;padding:11px 13px;border-bottom:1px solid #1a181514}}
  .card header b{{font-family:Consolas,monospace;font-size:12px;letter-spacing:.1em;font-weight:400}}
  .card header span{{font-size:12px;color:#1a181577}}
  .card header .ratio{{margin-left:auto;font-family:Consolas,monospace;font-size:10.5px;letter-spacing:.06em;white-space:nowrap}}
  .mini{{height:292px;padding:14px;display:flex;justify-content:center;align-items:flex-start;background:#e2ded5}}
  .page{{width:206px;height:274px;padding:16px 15px;display:flex;flex-direction:column;overflow:hidden;
    box-shadow:0 1px 4px #00000018}}
  .rule{{width:26px;height:3px;margin-bottom:13px}}
  .t1{{font-size:29px;line-height:1.25;letter-spacing:.02em;font-weight:200}}
  .t2{{display:inline-block;font-size:29px;line-height:1.25;letter-spacing:.02em;padding:0 3px;margin-top:2px}}
  .sub{{font-size:10px;margin-top:16px;letter-spacing:.06em}}
  .body{{font-size:7.2px;line-height:2;margin-top:9px;color:#00000099}}
  .foot{{margin-top:auto;border-top:1px solid #00000026;padding-top:5px;display:flex;
    justify-content:space-between;font-family:Consolas,monospace;font-size:5.5px;letter-spacing:.1em}}
  .ctl{{display:flex;gap:0;border-top:1px solid #1a181514}}
  .ctl label{{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;padding:10px 6px;
    font-size:11px;letter-spacing:.1em;color:#1a181588;cursor:pointer}}
  .ctl label:hover{{background:#1a181508}}
  .ctl input[type=color]{{-webkit-appearance:none;appearance:none;width:100%;height:26px;border:1px solid #1a181520;
    padding:0;background:none;cursor:pointer}}
  .ctl input[type=color]::-webkit-color-swatch-wrapper{{padding:0}}
  .ctl input[type=color]::-webkit-color-swatch{{border:none}}
  .warn{{color:#c0392b !important}}
  footer{{padding:0 28px;font-size:12px;color:#1a181577;line-height:2;max-width:820px}}
</style></head><body>
<div class="top">
  <b>色卡 · YXL / 1212</b>
  <span class="hint">改纸 / 墨 / 强调色，右边小样实时变</span>
  <span class="sp"></span>
  <button id="add">＋ 新增主题</button>
  <button id="export">导出 themes.json</button>
  <button id="css">复制 CSS 块</button>
</div>
<div class="grid" id="grid"></div>
<footer>
  对比度 ≥ 7:1 才算正文舒服（AAA），≥ 4.5:1 是底线。强调色只用在小面积元件上，别指望它承担正文可读性。<br>
  改完导出的 themes.json 交给 R：<code>python tools/palette.py apply themes.json</code>，再 <code>python render.py …</code> 出图。
</footer>
<script>
const START = {themes_json};
const SAMPLE = {sample_json};
let themes = START.map(t => ({{...t}}));

const $ = s => document.querySelector(s);
function lum(h) {{
  h = h.replace("#",""); const c = [0,2,4].map(i => parseInt(h.substr(i,2),16)/255)
    .map(v => v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4));
  return .2126*c[0] + .7152*c[1] + .0722*c[2];
}}
function ratio(a,b) {{ const la=lum(a), lb=lum(b); const hi=Math.max(la,lb), lo=Math.min(la,lb); return (hi+.05)/(lo+.05); }}

function card(t, i) {{
  const cr = ratio(t.ink, t.paper), ca = ratio(t.paper, t.accent);
  const bad = cr < 4.5;
  return `<section class="card" data-i="${{i}}">
    <header><b>${{t.key}}</b><span>${{t.name}}</span>
      <span class="ratio ${{bad?'warn':''}}">墨纸 ${{cr.toFixed(1)}}:1 · 反白 ${{ca.toFixed(1)}}:1</span></header>
    <div class="mini">
      <div class="page" style="background:${{t.paper}};color:${{t.ink}}">
        <div class="rule" style="background:${{t.accent}}"></div>
        <div class="t1">${{SAMPLE.t1}}</div>
        <div><span class="t2" style="background:${{t.accent}};color:${{t.paper}}">${{SAMPLE.t2}}</span></div>
        <div class="sub">${{SAMPLE.sub}}</div>
        <div class="body">${{SAMPLE.body1}}<span style="color:${{t.accent}}">${{SAMPLE.ac}}</span>${{SAMPLE.body2}}</div>
        <div class="foot" style="border-color:${{t.ink}}26;color:${{t.ink}}77">
          <span>YXL / 1212</span><span>2026</span><span>P.01</span></div>
      </div>
    </div>
    <div class="ctl">
      <label>纸 <input type="color" data-k="paper" value="${{t.paper}}"></label>
      <label>墨 <input type="color" data-k="ink" value="${{t.ink}}"></label>
      <label>强调 <input type="color" data-k="accent" value="${{t.accent}}"></label>
    </div>
  </section>`;
}}

function draw() {{
  $("#grid").innerHTML = themes.map(card).join("");
  document.querySelectorAll(".card").forEach(c => {{
    const i = +c.dataset.i;
    c.querySelectorAll("input[type=color]").forEach(inp => inp.oninput = () => {{
      themes[i][inp.dataset.k] = inp.value;
      draw();
    }});
  }});
}}

$("#add").onclick = () => {{
  const base = themes[themes.length-1] || {{paper:"#f2efe7", ink:"#17160f", accent:"#1b2ac6", name:"新主题"}};
  const n = themes.filter(t => t.key.startsWith("custom")).length + 1;
  themes.push({{...base, key:"custom-"+n, name:"新主题 "+n}});
  draw();
}};

function data() {{ return JSON.stringify({{themes}}, null, 2); }}

$("#export").onclick = () => {{
  const b = new Blob([data()], {{type:"application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = "themes.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}};

$("#css").onclick = async () => {{
  const txt = themes.map(t => `.theme-${{t.key}} {{ /* ${{t.name}} */\\n  --paper: ${{t.paper}}; --ink: ${{t.ink}};\\n  --accent: ${{t.accent}};\\n}}`).join("\\n\\n");
  try {{ await navigator.clipboard.writeText(txt); alert("CSS 已复制"); }}
  catch (e) {{ window.prompt("手动复制：", txt); }}
}};

draw();
</script></body></html>
"""


def cmd_build():
    themes = parse_themes()
    start = [{"key": t["key"], "name": t["name"], "paper": t["paper"],
              "ink": t["ink"], "accent": t["accent"]} for t in themes]
    sample = {
        "t1": "建筑生",
        "t2": "生存指南",
        "sub": "先活下来，再谈设计。",
        "body1": "建筑是一个",
        "ac": "主观审判的行业",
        "body2": "。即便是大师，也照样有人批判，所以别妄想自己的方案能一次通过。",
    }
    html = TPL.format(
        themes_json=json.dumps(start, ensure_ascii=False),
        sample_json=json.dumps(sample, ensure_ascii=False),
    )
    p = ROOT / "palette.html"
    p.write_text(html, encoding="utf-8")
    print(f"  palette.html  ({len(start)} 套主题)  ← {p}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "build":
        cmd_build()
    elif sys.argv[1] == "apply":
        cmd_apply(sys.argv[2])
    else:
        raise SystemExit(__doc__)
