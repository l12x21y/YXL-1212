// YXL/1212 渲染器 —— render.py 七种版式的 TypeScript 1:1 移植。
// 输出与 render.py 完全相同的 HTML 字符串，套 templates/system.css 即成纸面。

export type Meta = { series?: string; issue?: string; date?: string; theme?: string };
export type Page = { layout: string; theme?: string; [k: string]: any };

const W = 1800;

// ────────────────────────── 小工具 ──────────────────────────
const e = (s: any) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function spanEnd(html: string, i: number): number {
  let depth = 1, n = i;
  const re = /<span\b|<\/span>/g;
  re.lastIndex = n;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    depth += m[0] === "</span>" ? -1 : 1;
    if (depth === 0) return m.index + m[0].length;
  }
  return -1;
}

function indentTail(html: string): string {
  const head = '<span class="line">';
  if (!html.startsWith(head)) return html;
  const end = spanEnd(html, head.length);
  if (end <= 0 || end >= html.length) return html;
  return html.slice(0, end) + `<span class="ind">${html.slice(end)}</span>`;
}

export function accentize(s: string): string {
  // <~ ~> 先抽占位符再 escape（尖括号会被 escape 吃掉）
  const dims: string[] = [];
  s = s.replace(/<~(.+?)~>/g, (_, t) => `\x00DIM${dims.push(t) - 1}\x00`);
  s = e(s);
  dims.forEach((t, k) => { s = s.replace(`\x00DIM${k}\x00`, `<span class="dim">${e(t)}</span>`); });
  // 破折号悬挂
  s = s.replace(/@@([—－]{2})(.+?)@@/g, "$1@@$2@@");
  s = s.replace(/@@(.+?)@@/g, '<span class="pull">$1</span>');
  s = s.replace(/\[\[([—－]{2})(.+?)\]\]/g, '$1<span class="line">$2</span>');
  s = s.replace(/\[\[(.+?)\]\]([—－]{2})/g, "[[$1$2]]");
  s = s.replace(/\[\[(.+?)\]\]/g, '<span class="line">$1</span>');
  s = s.replace(/!!(.+?)!!/g, '<b class="wt">$1</b>');
  s = s.replace(/\*(.+?)\*/g, '<em class="ac">$1</em>');
  s = s.replace(/\^\^(.+?)\^\^/g, '<span class="big">$1</span>');
  s = s.replace(/==(.+?)==/g, (_, inner) =>
    inner.includes('class="big"')
      ? `<span class="inv inv-big">${inner}</span>`
      : `<span class="inv">${inner}</span>`);
  return s;
}

export function lines(v: string | string[]): string {
  const arr = Array.isArray(v) ? v : [v];
  const out = arr.map((x) => {
    const segs = String(x).split("\n");
    let h = indentTail(accentize(segs[0]));
    for (const sg of segs.slice(1)) {
      h += "<br>" + (sg.startsWith("@@") ? accentize(sg) : sg ? `<span class="ind">${accentize(sg)}</span>` : "");
    }
    return h;
  });
  return out.join("<br>");
}

const plain = (s: string) => s.replace(/==|\*\*|\*|!!|\^\^|\[\[|\]\]/g, "");

const folio = (i: number) => String(i).padStart(2, "0");

function colophon(p: Page, i: number, meta: Meta): string {
  const items = p.colophon ?? [
    `${meta.series ?? "YXL / 1212"} · ${meta.issue ?? ""}`.replace(/^·+|·+$/g, "").trim(),
    meta.date ?? "",
    `P.${folio(i)}`,
  ];
  return `<div class="colophon meta">${items.map((x) => `<span>${e(x)}</span>`).join("")}</div>`;
}

function topbar(p: Page, meta: Meta): string {
  const left = p.kicker || meta.series || "YXL / 1212";
  const right = p.running_head || "";
  const r = right ? `<span>${e(right)}</span>` : "";
  return `<div class="meta meta-top"><span>${e(left)}</span>${r}</div>`;
}

// ────────────────────────── 七种版式 ──────────────────────────
function l_cover(p: Page, i: number, meta: Meta): string {
  let inner = "";
  if (p.subtitle) inner += `<p class="t-lead">${lines(p.subtitle)}</p>`;
  if (p.subtitle_en) inner += `<p class="t-small latin" style="margin-top:26px">${lines(p.subtitle_en)}</p>`;
  const sub = inner ? `<div class="sub"><span class="bar"></span><div>${inner}</div></div>` : "";
  const rule = p.rule === "accent" ? "rule-accent" : "rule-ink";
  const tt = Array.isArray(p.title) ? p.title : [p.title ?? ""];
  const maxlen = Math.max(0, ...tt.map((x) => plain(x).length));
  const fs = maxlen ? Math.max(96, Math.min(180, Math.floor(1420 / (maxlen * 1.02)))) : 180;
  const style = fs < 180 ? ` style="font-size:${fs}px"` : "";
  return `<div class="frame">
      ${topbar(p, meta)}
      <div class="title-wrap">
        <div class="${rule}"></div>
        <h1 class="t-display"${style}>${lines(p.title ?? "")}</h1>${sub}
      </div>
      ${colophon(p, i, meta)}
    </div>`;
}

function l_statement(p: Page, i: number, meta: Meta): string {
  const t: string | string[] = p.text ?? "";
  let parts: string[], fs: number;
  if (Array.isArray(t)) { parts = t; fs = 132; }
  else {
    const MAXCOL = 12, MAXH = 1760, ADV = 0.93;
    const n = t.length;
    const cols = Math.max(1, Math.min(3, Math.ceil(n / MAXCOL)));
    const per = Math.ceil(n / cols);
    fs = Math.min(150, Math.floor(MAXH / (per * ADV)));
    parts = Array.from({ length: cols }, (_, k) => t.slice(k * per, (k + 1) * per));
  }
  const vertical = parts.filter(Boolean).map((x) => `<p>${accentize(x)}</p>`).join("");
  const pre = p.pre ? `<div class="pre">${accentize(p.pre)}</div>` : "";
  const note = p.note ? `<p class="t-micro">${lines(p.note)}</p>` : "";
  const aside = note ? `<div class="aside"><div class="dot-accent"></div>${note}</div>` : "";
  return `<div class="frame">
      ${topbar(p, meta)}
      ${pre}<div class="vertical" style="font-size:${fs}px">${vertical}</div>${aside}
      ${colophon(p, i, meta)}
    </div>`;
}

function l_quote(p: Page, i: number, meta: Meta): string {
  const sign = p.sign ?? "";
  const signHtml = sign
    ? `<div class="sign"><span class="line"></span><span class="t-small">${e(sign)}</span></div>`
    : "";
  const bodyCls = sign ? "quote-body" : "quote-body no-sign";
  const raw = Array.isArray(p.text) ? p.text.join("") : p.text ?? "";
  const bar = raw.includes("==") ? "" : '<div class="bar-accent"></div>';
  return `<div class="frame">
      ${topbar(p, meta)}
      <div class="${bodyCls}">
        ${bar}
        <blockquote class="t-d2">${lines(p.text ?? "")}</blockquote>
      </div>${signHtml}
      ${colophon(p, i, meta)}
    </div>`;
}

function l_list(p: Page, i: number, meta: Meta): string {
  const headBits = p.lead ? [`<p class="t-small">${lines(p.lead)}</p>`] : [];
  let items = "";
  (p.items ?? []).forEach((it: any, k: number) => {
    const d = it.d ? `<p class="t-small">${lines(it.d)}</p>` : "";
    items += `<div class="item"><div class="n">${String(k + 1).padStart(2, "0")}</div><div><h2 class="t-h2">${e(it.t)}</h2>${d}</div></div>`;
  });
  return `<div class="frame">
      ${topbar(p, meta)}
      <div class="head">
        <h1 class="t-h1">${lines(p.title ?? "")}</h1>${headBits.join("")}
      </div>
      <div class="items">${items}</div>
      ${colophon(p, i, meta)}
    </div>`;
}

function l_essay(p: Page, i: number, meta: Meta): string {
  const body = (p.paragraphs ?? []).map((x: string) => `<p class="t-body">${lines(x)}</p>`).join("");
  const sign = p.sign ?? "";
  const signHtml = sign ? `<div class="sign"><p class="t-small">${e(sign)}</p></div>` : "";
  return `<div class="frame">
      ${topbar(p, meta)}
      <div class="main">
        <div class="head">
          <p class="label">${e(p.label ?? "")}</p>
          <h1 class="t-h1">${lines(p.title ?? "")}</h1>
        </div>
        <div class="body">${body}</div>
      </div>
      ${signHtml}
      ${colophon(p, i, meta)}
    </div>`;
}

function l_index(p: Page, i: number, meta: Meta): string {
  let rows = "";
  (p.items ?? []).forEach((it: any, k: number) => {
    rows += `<div class="row"><span class="n">${String(k + 1).padStart(2, "0")}</span><span class="t">${e(it.t)}</span><span class="pg">${e(it.pg)}</span></div>`;
  });
  const note = p.note ? `<p class="t-micro">${lines(p.note)}</p>` : "";
  return `<div class="frame">
      ${topbar(p, meta)}
      <div class="head">
        <div><h1 class="t-h1">${lines(p.title ?? "")}</h1></div>${note}
      </div>
      <div class="rows">${rows}</div>
      ${colophon(p, i, meta)}
    </div>`;
}

function l_split(p: Page, i: number, meta: Meta): string {
  const fig = p.figure ? `<div class="figure">${lines(p.figure)}</div>` : "<div></div>";
  const lead = p.lead ? `<p class="t-lead">${lines(p.lead)}</p>` : "";
  const body = (p.paragraphs ?? []).map((x: string) => `<p class="t-body">${lines(x)}</p>`).join("");
  return `<div class="frame">
      <div class="top">
        <div class="meta meta-top"><span>${e(p.kicker ?? "")}</span><span>${e(p.side ?? "")}</span></div>
        ${fig}
        <div class="meta">${e(p.figure_caption ?? "")}</div>
      </div>
      <div class="bottom">
        <div class="main">
          <h1 class="t-h1">${lines(p.title ?? "")}</h1>${lead}${body}
        </div>
        ${colophon(p, i, meta)}
      </div>
    </div>`;
}

const LAYOUTS: Record<string, (p: Page, i: number, meta: Meta) => string> = {
  cover: l_cover, statement: l_statement, quote: l_quote, list: l_list,
  essay: l_essay, index: l_index, split: l_split,
};

export const LAYOUT_CN: Record<string, string> = {
  cover: "封面", statement: "竖排宣言", quote: "引文", list: "条目",
  essay: "正文", index: "目录", split: "封底",
};

export function buildPlate(p: Page, i: number, meta: Meta): string {
  const lay = p.layout || "cover";
  const theme = p.theme || meta.theme || "ivory";
  const body = LAYOUTS[lay](p, i, meta);
  return `<div class="folio">${folio(i)}</div>${body}`;
}

export { W, folio, plain };
export const plateClass = (p: Page, meta: Meta) =>
  `plate theme-${p.theme || meta.theme || "ivory"} layout-${p.layout || "cover"}`;
