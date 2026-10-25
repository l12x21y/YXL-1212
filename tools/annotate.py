#!/usr/bin/env python3
"""标注工具：把正文拆成可选段，生成一个可以直接在浏览器里划重点的页面。

    python tools/annotate.py build "content/<文章>/<章节>.json"
        → out/<文章>/<章节>/annotate.html   （浏览器打开，选字 → 点按钮，可多选叠加）

    python tools/annotate.py apply "content/<文章>/<章节>.json" [marks.json]
        把标记写回 JSON。不给 marks.json 时用同目录的 <章节>.suggestions.json。

行内语法（render.py 的 accentize 解析，可嵌套）：
    *字*     染色      ^^句^^   放大 2 倍
    !!句!!   加重 500  ==句==   反白色块
    [[句]]   单独占一行    @@句@@  大字句（独立成块、换色）
    叠加顺序由外到内：@@ [[ == !! ^^ *
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT = ROOT / "out"

EFFECTS = {
    "accent": ("*", "*", "染色"),
    "big": ("^^", "^^", "放大"),
    "bold": ("!!", "!!", "加重"),
    "block": ("==", "==", "底框"),
    "line": ("[[", "]]", "整行"),
    "pull": ("@@", "@@", "大字"),
    "dim": ("<~", "~>", "压灰"),
}
FIELD = {"accent": "ac", "big": "big", "bold": "wt", "block": "inv", "line": "line", "pull": "pull", "dim": "dim"}
ORDER = ["pull", "line", "block", "bold", "big", "accent", "dim"]      # 外 → 内

MARK_RE = re.compile(r"\*([^*]+)\*|\^\^(.+?)\^\^|==(.+?)==|\[\[(.+?)\]\]|!!(.+?)!!|@@(.+?)@@|<~(.+?)~>")


def strip_marks(s):
    return MARK_RE.sub(lambda m: next(g for g in m.groups() if g is not None), s)


TOKENS = [("[[", "line"), ("]]", "line"), ("==", "block"), ("!!", "bold"), ("^^", "big"), ("*", "accent"), ("@@", "pull"), ("<~", "dim"), ("~>", "dim")]
TOKENS.sort(key=lambda t: -len(t[0]))


def readback(s):
    """带标记的字符串 → (plain, [{start,end,effects}])，用来让标注页反映当前成图。"""
    i, plain, stack, marks = 0, [], [], []
    while i < len(s):
        for tok, eff in TOKENS:
            if s.startswith(tok, i):
                if tok in ("]]",):
                    if stack and stack[-1][0] == "line":
                        _, st = stack.pop()
                        marks.append({"start": st, "end": len(plain), "effects": ["line"]})
                    i += 2
                    break
                if tok == "[[":
                    stack.append(("line", len(plain)))
                    i += 2
                    break
                # 其余标记开合同形：栈里已有同效 → 收；否则 → 开
                idx = next((k for k, (e, _) in enumerate(stack) if e == eff), None)
                if idx is None:
                    stack.append((eff, len(plain)))
                else:
                    _, st = stack.pop(idx)
                    got = [e for e, _ in stack] + [eff]
                    marks.append({"start": st, "end": len(plain),
                                  "effects": [e for e in ORDER if e in got or e == eff]})
                i += len(tok)
                break
        else:
            plain.append(s[i])
            i += 1
            continue
        continue
    return "".join(plain), sorted(marks, key=lambda m: m["start"])


def effects_of(m):
    """兼容老的 effect 单值写法。"""
    e = m.get("effects")
    if e:
        return list(e)
    return [m["effect"]] if m.get("effect") else []


def wrap(seg, effects):
    for e in reversed(ORDER):        # 内 → 外 包，最后包的是最外层
        if e in effects:
            l, r, _ = EFFECTS[e]
            seg = l + seg + r
    return seg


def collect(doc):
    """返回 [(uid, 页码, 说明, container, key, idx)]。
    key=None 表示 container 本身是列表，用 idx 取；否则 container[key]。"""
    out = []
    for i, p in enumerate(doc.get("pages", []), 1):
        lay = p.get("layout")
        if lay in ("essay", "split"):
            for j in range(len(p.get("paragraphs", []))):
                out.append((f"p{i}_para{j}", i, f"正文第 {j + 1} 段", p["paragraphs"], None, j))
        elif lay == "list":
            for j, it in enumerate(p.get("items", [])):
                if it.get("d"):
                    out.append((f"p{i}_item{j}d", i, f"条目 {j + 1} 说明", it, "d", None))
        elif lay == "statement":
            if p.get("note"):
                out.append((f"p{i}_note", i, "竖排页左下注", p, "note", None))
        elif lay == "quote":
            if isinstance(p.get("text"), list):
                for j in range(len(p["text"])):
                    out.append((f"p{i}_text{j}", i, f"引文第 {j + 1} 行", p["text"], None, j))
        elif lay == "cover":
            if p.get("subtitle"):
                out.append((f"p{i}_subtitle", i, "封面副标", p, "subtitle", None))
    return out


def get_text(cont, key, idx):
    return cont[idx] if key is None else cont[key]


def set_text(cont, key, idx, val):
    if key is None:
        cont[idx] = val
    else:
        cont[key] = val


def dest_for(src):
    rel = src.resolve().relative_to(CONTENT.resolve())
    return OUT / rel.parent / src.stem


# ─────────────────────────── build ───────────────────────────

PAGE_TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>标注 · {title}</title>
<style>
  @font-face{{font-family:"NSSC";src:url("{font}") format("truetype");font-weight:100 900;font-display:swap}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#efece5;color:#26231f;font-family:"NSSC","Songti SC",SimSun,serif;font-weight:300;
    -webkit-font-smoothing:antialiased}}
  .bar{{position:sticky;top:0;z-index:30;background:#efece5f2;backdrop-filter:blur(8px);
    border-bottom:1px solid #26231f22;padding:12px 26px;display:flex;align-items:center;gap:18px}}
  .bar b{{font-weight:400;letter-spacing:.06em;font-size:15px}}
  .bar .sp{{flex:1}}
  .bar button{{font-family:inherit;font-size:13px;letter-spacing:.06em;padding:7px 14px;border:1px solid #26231f33;
    background:transparent;color:#26231f;cursor:pointer;border-radius:0}}
  .bar button:hover{{background:#26231f;color:#efece5}}
  .bar .hint{{font-size:12px;color:#26231f88;letter-spacing:.04em}}
  .wrap{{display:flex;align-items:flex-start;gap:0}}
  main{{flex:1;min-width:0;padding:40px 26px 140px 26px;display:flex;justify-content:center}}
  .doc{{width:660px;max-width:100%}}
  .unit{{margin-bottom:34px}}
  .unit .h{{font-family:Consolas,monospace;font-size:11px;letter-spacing:.16em;color:#26231f66;
    margin-bottom:9px;text-transform:uppercase}}
  .para{{font-size:19px;line-height:2.05;letter-spacing:.02em;white-space:pre-wrap;
    padding:2px 0;border-left:2px solid transparent;padding-left:12px;margin-left:-14px}}
  .para:hover{{border-left-color:#26231f1a}}
  .para::selection, .para *::selection{{background:#c0392b33}}
  /* 与成图一致的强调样式（可叠加） */
  .ac{{color:#c0392b;font-style:normal}}
  .big{{font-size:1.3em;line-height:1;letter-spacing:-.01em}}
  .wt{{font-weight:500}}
  .inv{{background:#c0392b;color:#efece5;padding:.02em .15em .05em;box-decoration-break:clone;-webkit-box-decoration-break:clone}}
  .inv .ac{{color:#efece5}}
  .line{{display:block;font-size:1.36em;line-height:1.72;margin:.24em 0 .2em;letter-spacing:.02em}}
  aside{{width:340px;flex:none;position:sticky;top:53px;max-height:calc(100vh - 53px);overflow:auto;
    border-left:1px solid #26231f22;padding:22px 20px 60px;background:#f6f4ef}}
  aside h3{{font-family:Consolas,monospace;font-size:11px;letter-spacing:.16em;color:#26231f77;
    font-weight:400;margin-bottom:14px;text-transform:uppercase}}
  .row{{display:flex;gap:8px;align-items:flex-start;padding:9px 0;border-bottom:1px solid #26231f14}}
  .tags{{display:flex;flex-direction:column;gap:3px;flex:none}}
  .tag{{font-family:Consolas,monospace;font-size:10px;letter-spacing:.08em;padding:2px 6px;text-align:center;
    background:#26231f;color:#efece5}}
  .tag.accent{{background:#c0392b}}
  .tag.big{{background:#8a7f6d}}
  .tag.bold{{background:#555}}
  .tag.block{{background:#c0392b}}
  .tag.line{{background:#2f4a3e}}
  .row .tx{{flex:1;font-size:14px;line-height:1.55;overflow:hidden}}
  .row .tx .q{{display:block;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .row .tx .m{{display:block;font-family:Consolas,monospace;font-size:10px;letter-spacing:.08em;
    color:#26231f66;margin-top:3px}}
  .row .del{{font-family:Consolas,monospace;font-size:13px;color:#26231f66;cursor:pointer;flex:none;
    border:none;background:none;padding:0 2px}}
  .row .del:hover{{color:#c0392b}}
  .empty{{font-size:13px;color:#26231f66;line-height:1.9}}
  #pop{{position:absolute;z-index:50;display:none;background:#26231f;padding:4px;gap:2px}}
  #pop button{{font-family:inherit;font-size:12.5px;letter-spacing:.06em;padding:7px 11px;border:none;
    background:transparent;color:#efece5;cursor:pointer;white-space:nowrap}}
  #pop button:hover{{background:#c0392b}}
  #pop button.on{{background:#c0392b}}
  #pop button.on::after{{content:" ✓";font-size:10px}}
  #pop .sep{{width:1px;background:#efece544;margin:2px 3px}}
  #pop .tip{{font-size:11px;color:#efece599;padding:7px 4px 0;letter-spacing:.04em}}
</style></head><body>
<div class="bar">
  <b>{title}</b><span class="hint">{chapter} · 选中文字后点按钮，可以同时选多个效果</span>
  <span class="sp"></span>
  <button id="export">导出 marks.json</button>
  <button id="copy">复制 JSON</button>
  <button id="reset">重置为建议</button>
</div>
<div class="wrap">
  <main><div class="doc" id="doc"></div></main>
  <aside><h3>标记 · <span id="cnt">0</span></h3><div id="list"></div></aside>
</div>
<div id="pop">
  <button data-e="accent">染色</button>
  <button data-e="big">放大</button>
  <button data-e="bold">加重</button>
  <button data-e="block">底框</button>
  <button data-e="line">整行</button>
  <button data-e="pull">大字</button>
  <span class="sep"></span>
  <button data-e="clear">清空</button>
</div>
<script>
const CHAPTER = {chapter_json};
const UNITS = {units_json};
const SUGGEST = {suggest_json};
const KEY = "yxl_marks_v2_" + CHAPTER;
const EFFECTS = {effects_json};
const FIELD = {field_json};
const ORDER = ["pull", "line", "block", "bold", "big", "accent"];   // 外 → 内
const PLAIN = Object.fromEntries(UNITS.map(u => [u.uid, u.plain]));

let marks = [];
const eff = m => m.effects && m.effects.length ? m.effects : (m.effect ? [m.effect] : []);

function load() {{
  try {{ const s = localStorage.getItem(KEY); if (s) {{ marks = JSON.parse(s); return; }} }} catch (e) {{}}
  marks = SUGGEST.map(m => ({{...m}}));
}}
function save() {{ try {{ localStorage.setItem(KEY, JSON.stringify(marks)); }} catch (e) {{}} }}

function esc(s) {{ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }}

function wrapHtml(seg, effects) {{
  let out = esc(seg);
  for (const e of ["accent","big","bold","block","line"]) {{   // 内 → 外
    if (effects.includes(e)) out = '<span class="' + FIELD[e] + '">' + out + "</span>";
  }}
  return out;
}}

function paint(uid) {{
  const el = document.querySelector('.para[data-uid="' + uid + '"]');
  if (!el) return;
  const plain = PLAIN[uid] || "";
  const ms = marks.filter(m => m.uid === uid).sort((a, b) => a.start - b.start);
  let html = "", cur = 0;
  for (const m of ms) {{
    if (m.start < cur) continue;
    html += esc(plain.slice(cur, m.start)) + wrapHtml(plain.slice(m.start, m.end), eff(m));
    cur = m.end;
  }}
  html += esc(plain.slice(cur));
  el.innerHTML = html || "&nbsp;";
}}

function paintAll() {{ UNITS.forEach(u => paint(u.uid)); renderList(); }}

function renderList() {{
  const box = document.getElementById("list");
  document.getElementById("cnt").textContent = marks.length;
  if (!marks.length) {{ box.innerHTML = '<div class="empty">还没有标记。拖动选中正文里的词句，点弹出的按钮即可，多个效果可以叠加。</div>'; return; }}
  const order = UNITS.map(u => u.uid);
  const sorted = marks.slice().sort((a, b) => order.indexOf(a.uid) - order.indexOf(b.uid) || a.start - b.start);
  box.innerHTML = sorted.map(m => {{
    const u = UNITS.find(x => x.uid === m.uid) || {{page:"?", label:""}};
    const tags = eff(m).map(e => '<span class="tag ' + e + '">' + EFFECTS[e] + "</span>").join("");
    return '<div class="row"><span class="tags">' + tags + "</span>" +
      '<span class="tx"><span class="q">' + esc(m.text) + '</span>' +
      '<span class="m">p' + u.page + " · " + u.label + "</span></span>" +
      '<button class="del" data-i="' + marks.indexOf(m) + '">✕</button></div>';
  }}).join("");
  box.querySelectorAll(".del").forEach(b => b.onclick = () => {{
    marks.splice(+b.dataset.i, 1); save(); paintAll();
  }});
}}

// ── 选区 → 偏移 ──
function paraOf(node) {{
  let n = node.nodeType === 3 ? node.parentNode : node;
  while (n && n.classList && !n.classList.contains("para")) n = n.parentNode;
  return n;
}}
function offsets(para, range) {{
  const pre = range.cloneRange();
  pre.selectNodeContents(para);
  pre.setEnd(range.startContainer, range.startOffset);
  const start = pre.toString().length;
  return {{start, end: start + range.toString().length}};
}}

const pop = document.getElementById("pop");
let pending = null;

function syncPop() {{
  const cur = pending ? eff(pending) : [];
  pop.querySelectorAll("button[data-e]").forEach(b => {{
    b.classList.toggle("on", cur.includes(b.dataset.e));
  }});
}}

document.addEventListener("mouseup", () => {{
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return;              // 不隐藏，方便继续点按钮
  const a = paraOf(sel.anchorNode), b = paraOf(sel.focusNode);
  if (!a || a !== b) {{ pop.style.display = "none"; return; }}
  const r = sel.getRangeAt(0);
  const o = offsets(a, r);
  if (o.end <= o.start) {{ pop.style.display = "none"; return; }}
  const uid = a.dataset.uid;
  const hit = marks.find(m => m.uid === uid && m.start === o.start && m.end === o.end);
  pending = {{uid, ...o, text: sel.toString(), effects: hit ? eff(hit).slice() : []}};
  const rect = r.getBoundingClientRect();
  pop.style.display = "flex";
  const w = pop.offsetWidth || 380;
  let left = rect.left + window.scrollX + rect.width / 2 - w / 2;
  left = Math.max(8, Math.min(left, document.documentElement.clientWidth - w - 8));
  pop.style.left = left + "px";
  pop.style.top = Math.max(6, rect.top + window.scrollY - pop.offsetHeight - 8) + "px";
  syncPop();
}});

pop.querySelectorAll("button[data-e]").forEach(btn => btn.onclick = () => {{
  if (!pending) return;
  const e = btn.dataset.e;
  // 清掉与选区重叠的旧标记（同范围或交叠都重写）
  marks = marks.filter(m => !(m.uid === pending.uid && m.start < pending.end && pending.start < m.end));
  if (e === "clear") {{
    pending.effects = [];
    save(); paintAll(); pop.style.display = "none";
    window.getSelection().removeAllRanges(); pending = null;
    return;
  }}
  const i = pending.effects.indexOf(e);
  if (i >= 0) pending.effects.splice(i, 1); else pending.effects.push(e);
  if (pending.effects.length) {{
    marks.push({{uid: pending.uid, start: pending.start, end: pending.end,
                 text: pending.text, effects: pending.effects.slice()}});
  }}
  save(); paintAll(); syncPop();
}});

document.getElementById("reset").onclick = () => {{
  if (!confirm("丢弃当前标记，回到建议版？")) return;
  marks = SUGGEST.map(m => ({{...m}})); save(); paintAll();
}};

function dump() {{
  return JSON.stringify({{chapter: CHAPTER,
    marks: marks.map(m => ({{uid: m.uid, start: m.start, end: m.end, text: m.text, effects: eff(m)}}))}}, null, 2);
}}

document.getElementById("export").onclick = () => {{
  const b = new Blob([dump()], {{type: "application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = "marks.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}};

document.getElementById("copy").onclick = async () => {{
  try {{ await navigator.clipboard.writeText(dump()); alert("已复制，直接粘给我即可"); }}
  catch (e) {{ window.prompt("手动复制：", dump()); }}
}};

document.getElementById("doc").innerHTML = UNITS.map(u =>
  '<div class="unit"><div class="h">p' + u.page + " · " + u.label + '</div>' +
  '<p class="para" data-uid="' + u.uid + '"></p></div>').join("");

load(); paintAll();
</script>
</body></html>
"""


def cmd_build(src):
    doc = json.loads(src.read_text(encoding="utf-8"))
    meta = doc.get("meta", {})
    dest = dest_for(src)
    dest.mkdir(parents=True, exist_ok=True)

    units, from_content = [], []
    for uid, page, label, cont, key, idx in collect(doc):
        plain, mk = readback(get_text(cont, key, idx))
        units.append({"uid": uid, "page": page, "label": label, "plain": plain})
        for m in mk:
            from_content.append({"uid": uid, "start": m["start"], "end": m["end"],
                                 "text": plain[m["start"]:m["end"]], "effects": m["effects"]})

    # 初始标记：优先用该目录下已导出的 marks.json（= 当前成图的真实状态），
    # 没有再用 <章节>.suggestions.json 的建议版（用 find 字串定位）
    sug = []
    exported = dest / "marks.json"
    sp = src.with_suffix(".suggestions.json")
    if from_content:
        sug = from_content
        print(f"  初始标记取自 content JSON（{len(sug)} 条，= 当前成图）")
    elif exported.exists():
        for m in json.loads(exported.read_text(encoding="utf-8"))["marks"]:
            sug.append({"uid": m["uid"], "start": m["start"], "end": m["end"],
                        "text": m.get("text", ""), "effects": effects_of(m)})
        print(f"  初始标记取自 {exported.name}")
    elif sp.exists():
        plain_map = {u["uid"]: u["plain"] for u in units}
        for s in json.loads(sp.read_text(encoding="utf-8")).get("marks", []):
            plain = plain_map.get(s["uid"], "")
            at = plain.find(s["find"])
            if at < 0:
                print(f"  !! 建议没找到：{s['uid']} 「{s['find']}」")
                continue
            sug.append({"uid": s["uid"], "start": at, "end": at + len(s["find"]),
                        "text": s["find"], "effects": effects_of(s)})

    depth = len(dest.relative_to(ROOT).parts)
    font = "../" * depth + "assets/NotoSerifSC-VF.ttf"
    html = PAGE_TPL.format(
        title=meta.get("title", "YXL / 1212"),
        chapter=src.stem,
        font=font,
        chapter_json=json.dumps(src.stem, ensure_ascii=False),
        units_json=json.dumps(units, ensure_ascii=False),
        suggest_json=json.dumps(sug, ensure_ascii=False),
        effects_json=json.dumps({k: v[2] for k, v in EFFECTS.items()}, ensure_ascii=False),
        field_json=json.dumps(FIELD, ensure_ascii=False),
    )
    p = dest / "annotate.html"
    p.write_text(html, encoding="utf-8")
    print(f"  annotate.html  ({len(units)} 段, {len(sug)} 条建议)  ← {p.relative_to(ROOT)}")


# ─────────────────────────── apply ───────────────────────────

def cmd_apply(src, marks_path=None):
    doc = json.loads(src.read_text(encoding="utf-8"))
    if marks_path is None:
        raw = json.loads(src.with_suffix(".suggestions.json").read_text(encoding="utf-8"))["marks"]
    else:
        raw = json.loads(Path(marks_path).read_text(encoding="utf-8"))["marks"]

    by_uid = {}
    for m in raw:
        by_uid.setdefault(m["uid"], []).append(m)

    n = 0
    for uid, page, label, cont, key, idx in collect(doc):
        plain = strip_marks(get_text(cont, key, idx))
        spans = []
        for m in by_uid.get(uid, []):
            if "find" in m:
                at = plain.find(m["find"])
                if at < 0:
                    print(f"  !! 跳过 {uid}「{m['find']}」")
                    continue
                spans.append((at, at + len(m["find"]), effects_of(m)))
            else:
                spans.append((m["start"], m["end"], effects_of(m)))
        spans.sort()
        out, cur = [], 0
        for s, e, fx in spans:
            if s < cur:
                print(f"  !! {uid} 标记重叠，跳过 {s}-{e}")
                continue
            out.append(plain[cur:s])
            out.append(wrap(plain[s:e], fx))
            cur = e
            n += 1
        out.append(plain[cur:])
        set_text(cont, key, idx, "".join(out))

    src.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  已写回 {n} 条标记 → {src.name}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, target = sys.argv[1], Path(sys.argv[2])
    if cmd == "build":
        cmd_build(target)
    elif cmd == "apply":
        cmd_apply(target, sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        raise SystemExit(__doc__)
