import { useEffect, useMemo, useRef, useState } from "react";
import { toPng } from "html-to-image";
import {
  buildPlate, plateClass, LAYOUT_CN, folio, applyMarks, EFFECTS,
  type Meta, type Page, type Mark,
} from "./plate";

const THEMES: { id: string; name: string; paper: string; ink: string; accent: string }[] = [
  { id: "ivory", name: "米纸 · 克莱因蓝", paper: "#f2efe7", ink: "#17160f", accent: "#1b2ac6" },
  { id: "bone", name: "骨白 · 番茄红", paper: "#efeeea", ink: "#14161a", accent: "#d93b22" },
  { id: "kraft", name: "淡牛皮 · 赭橘", paper: "#e7dcc7", ink: "#2b2113", accent: "#bf4218" },
  { id: "slate", name: "冷灰 · 洋红", paper: "#e8e9e5", ink: "#101216", accent: "#c3216b" },
  { id: "night", name: "墨夜 · 朱砂", paper: "#15150f", ink: "#edeae1", accent: "#e4543a" },
];

type Field = { key: string; label: string; ph?: string; area?: boolean };

const FIELDS: Record<string, Field[]> = {
  cover: [
    { key: "title", label: "标题（一行一句）", ph: "留白\n也是一种内容", area: true },
    { key: "subtitle", label: "副标", ph: "版面之所以有重量，是因为它知道在哪里停下。" },
    { key: "subtitle_en", label: "英文副标（可选）" },
  ],
  statement: [
    { key: "text", label: "宣言（自动分列，~12 字一列）", ph: "不是没有东西\n是不急着说", area: true },
    { key: "pre", label: "横排前缀（拉丁字母用，可选）" },
    { key: "note", label: "左下注（可选）", area: true },
  ],
  quote: [
    { key: "text", label: "引文（一行一句，可在预览里划线标重点）", ph: "空的地方，\n读者会自己走进去。", area: true },
    { key: "sign", label: "出处（可选）", ph: "— 关于负空间的旧话" },
  ],
  list: [
    { key: "title", label: "标题" },
    { key: "lead", label: "引言（可选）" },
    { key: "items", label: "条目（每行一条：名称 | 说明）", ph: "分配注意力 | 眼睛先落在哪里，由空处决定", area: true },
  ],
  essay: [
    { key: "label", label: "栏目标签", ph: "札记" },
    { key: "title", label: "标题" },
    { key: "paragraphs", label: "正文（一行一段，在预览里划线标重点）", ph: "排一张版，最难的不是放什么。", area: true },
    { key: "sign", label: "落款（可选）" },
  ],
  index: [
    { key: "title", label: "标题" },
    { key: "note", label: "注（可选）" },
    { key: "items", label: "条目（每行：名称 | 页码）", ph: "留白也是一种内容 | P.01", area: true },
  ],
  split: [
    { key: "figure", label: "大字（上半墨块内）", ph: "3:4" },
    { key: "figure_caption", label: "图注", ph: "1800 × 2400 PX" },
    { key: "title", label: "标题" },
    { key: "lead", label: "引言" },
    { key: "paragraphs", label: "正文（一行一段）", area: true },
  ],
};

type PageItem = { id: string; layout: string; values: Record<string, string> };

const parseItems = (s: string, pg = false) =>
  s.split("\n").map((l) => l.trim()).filter(Boolean)
    .map((l) => {
      const [a, b] = l.split("|").map((x) => x.trim());
      return pg ? { t: a ?? "", pg: b ?? "" } : { t: a ?? "", d: b ?? "" };
    });

const splitParas = (s: string) => s.split(/\n+/).map((x) => x.trim()).filter(Boolean);

let uidSeq = 1;
const newId = () => `pg${uidSeq++}`;
const mkPage = (layout: string, values: Record<string, string> = {}): PageItem =>
  ({ id: newId(), layout, values });

const DEMO: PageItem[] = [
  mkPage("cover", {
    title: "留白\n也是一种内容",
    subtitle: "版面之所以有重量，是因为它知道在哪里停下。",
  }),
  mkPage("essay", {
    label: "札记",
    title: "把字放下，手先离开",
    paragraphs:
      "排一张版，最难的不是放什么，而是决定不放什么。每一块空白都在替读者让路，让视线有地方转身。\n删到只剩一句，那句话才有分量。留白不是给视觉的福利，它是给判断力的。一个版面敢空着，说明作者知道自己要说什么。",
    sign: "2026 · 于桌前",
  }),
  mkPage("quote", { text: "空的地方，\n读者会自己走进去。", sign: "— 关于负空间的旧话" }),
  mkPage("split", { figure: "3:4", figure_caption: "1800 × 2400 PX", title: "一套规则，七张纸。", lead: "多一张，都是在替读者做决定。" }),
];

const DEMO_MARKS: Record<string, Mark[]> = {
  [`${DEMO[1].id}:p0`]: [{ start: 4, end: 13, effects: ["accent"] }],
  [`${DEMO[1].id}:p1`]: [{ start: 12, end: 22, effects: ["block"] }],
};

// ── 全篇导入：`---` 分页；首页=封面（首行=标题），末页=封底，中间=正文 ──
function parseBulk(bulk: string): PageItem[] {
  const blocks = bulk.split(/\n---+\n/).map((s) => s.trim()).filter(Boolean);
  if (!blocks.length) return [];
  return blocks.map((b, i) => {
    const lines = b.split("\n").map((x) => x.trim()).filter(Boolean);
    if (i === 0)
      return mkPage("cover", { title: lines[0] ?? "", subtitle: lines.slice(1).join("") });
    if (blocks.length > 2 && i === blocks.length - 1)
      return mkPage("split", {
        title: lines[0] ?? "", lead: lines[1] ?? "", paragraphs: lines.slice(2).join("\n"),
      });
    return mkPage("essay", {
      label: "札记", title: lines[0] ?? "", paragraphs: lines.slice(1).join("\n"),
    });
  });
}

const rgba = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

const load = <T,>(key: string, fallback: T): T => {
  try { const s = localStorage.getItem(key); if (s) return JSON.parse(s); } catch (e) { /* ignore */ }
  return fallback;
};

export default function App() {
  const [pages, setPages] = useState<PageItem[]>(() => load("yxl_web_pages", DEMO));
  const [cur, setCur] = useState(0);
  const [view, setView] = useState<"single" | "series">(() => load<"single" | "series">("yxl_web_view", "single"));
  const [theme, setTheme] = useState("ivory");
  const [custom, setCustom] = useState({ paper: "#f2efe7", ink: "#17160f", accent: "#1b2ac6" });
  const [series, setSeries] = useState("YXL / 1212");
  const [date, setDate] = useState("2026");
  const [folioStart, setFolioStart] = useState(1);
  const [bulk, setBulk] = useState("");
  const [busy, setBusy] = useState(false);
  const plateRef = useRef<HTMLDivElement>(null);

  const page = pages[Math.min(cur, pages.length - 1)] ?? pages[0];

  useEffect(() => { localStorage.setItem("yxl_web_pages", JSON.stringify(pages)); }, [pages]);
  useEffect(() => { localStorage.setItem("yxl_web_view", JSON.stringify(view)); }, [view]);
  const [marks, setMarks] = useState<Record<string, Mark[]>>(() => load("yxl_web_marks", DEMO_MARKS));
  useEffect(() => { localStorage.setItem("yxl_web_marks", JSON.stringify(marks)); }, [marks]);

  const meta: Meta = { series, date, theme: theme === "custom" ? "ivory" : theme };
  const folioOf = (idx: number) => folioStart + idx;

  const buildPage = (item: PageItem, idx: number): Page => {
    const p: Page = { layout: item.layout, theme: meta.theme, ...item.values };
    if (item.layout === "essay") {
      p.paragraphs = splitParas(item.values.paragraphs ?? "")
        .map((plain, j) => applyMarks(plain, marks[`${item.id}:p${j}`] ?? []));
      p._paraUids = splitParas(item.values.paragraphs ?? "").map((_, j) => `${item.id}:p${j}`);
    }
    if (item.layout === "quote") {
      p.text = (item.values.text ?? "").split("\n").filter((x) => x.trim())
        .map((line, j) => applyMarks(line, marks[`${item.id}:q${j}`] ?? []));
      p._quoteUid = `${item.id}:quoteSel`;
    }
    if (item.layout === "list") p.items = parseItems(item.values.items ?? "", false);
    if (item.layout === "index") p.items = parseItems(item.values.items ?? "", true);
    return p;
  };

  const builtList = useMemo(() => pages.map((it, idx) => ({ item: it, page: buildPage(it, idx) })), [pages, marks, meta]);

  // ── 划选 → 标注条 ──
  const [pop, setPop] = useState<{ x: number; y: number; uid: string; start: number; end: number } | null>(null);
  const popEffects = useMemo(() => {
    if (!pop) return [] as string[];
    const hit = (marks[pop.uid] ?? []).find((m) => m.start === pop.start && m.end === pop.end);
    return hit ? hit.effects : [];
  }, [pop, marks]);

  const onMouseUp = () => {
    if (view !== "single") { setPop(null); return; }
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) { setPop(null); return; }
    const node = sel.anchorNode;
    const para = (node?.nodeType === 3 ? node.parentElement : node as HTMLElement | null)
      ?.closest?.("[data-mk]") as HTMLElement | null;
    if (!para || !plateRef.current?.contains(para)) { setPop(null); return; }
    const uid = para.dataset.mk!;
    if (sel.anchorNode !== sel.focusNode || !para.contains(sel.focusNode)) { setPop(null); return; }
    const range = sel.getRangeAt(0);
    const pre = range.cloneRange();
    pre.selectNodeContents(para);
    pre.setEnd(range.startContainer, range.startOffset);
    const start = pre.toString().length;
    const end = start + range.toString().length;
    if (end <= start) { setPop(null); return; }
    const rect = range.getBoundingClientRect();
    setPop({
      x: Math.min(Math.max(rect.left + rect.width / 2, 230), window.innerWidth - 230),
      y: rect.top - 6, uid, start, end,
    });
  };

  const applyEffect = (eff: string) => {
    if (!pop) return;
    setMarks((s) => {
      const list = (s[pop.uid] ?? []).filter((m) => !(m.start < pop.end && pop.start < m.end));
      const curM = (s[pop.uid] ?? []).find((m) => m.start === pop.start && m.end === pop.end);
      const effects = curM ? curM.effects.filter((x) => x !== eff) : [eff];
      if (effects.length) list.push({ start: pop.start, end: pop.end, effects });
      return { ...s, [pop.uid]: list };
    });
    setPop(null);
    window.getSelection()?.removeAllRanges();
  };

  const clearMark = () => {
    if (!pop) return;
    setMarks((s) => ({ ...s, [pop.uid]: (s[pop.uid] ?? []).filter((m) => m.start !== pop.start || m.end !== pop.end) }));
    setPop(null);
    window.getSelection()?.removeAllRanges();
  };

  // ── 页管理 ──
  const addPage = () => {
    const p = mkPage("essay", { label: "札记", title: "新的一页", paragraphs: "正文…" });
    setPages((s) => [...s.slice(0, cur + 1), p, ...s.slice(cur + 1)]);
    setCur(cur + 1);
  };
  const delPage = () => {
    if (pages.length <= 1) return;
    setPages((s) => s.filter((_, i) => i !== cur));
    setCur(Math.max(0, cur - 1));
  };
  const movePage = (d: number) => {
    const j = cur + d;
    if (j < 0 || j >= pages.length) return;
    setPages((s) => { const c = [...s]; [c[cur], c[j]] = [c[j], c[cur]]; return c; });
    setCur(j);
  };
  const importBulk = () => {
    const ps = parseBulk(bulk);
    if (!ps.length) { alert("没有可导入的内容。用一行 --- 分隔页，例如：\n\n留白\n也是一种内容\n---\n把字放下\n正文第一段…"); return; }
    setPages(ps); setCur(0); setBulk("");
  };

  const patch = (k: string, v: string) =>
    setPages((s) => s.map((it, i) => (i === cur ? { ...it, values: { ...it.values, [k]: v } } : it)));
  const setLayoutOf = (ly: string) =>
    setPages((s) => s.map((it, i) => (i === cur ? { ...it, layout: ly } : it)));

  const scale = view === "single" ? 0.36 : 0.17;
  const customStyle = theme === "custom" ? ({
    "--paper": custom.paper, "--ink": custom.ink, "--accent": custom.accent,
    "--ink-2": rgba(custom.ink, 0.6), "--ink-3": rgba(custom.ink, 0.34), "--hair": rgba(custom.ink, 0.16),
  } as React.CSSProperties) : undefined;

  const downloadOne = async (idx: number) => {
    const node = plateRef.current;
    if (!node) return;
    const url = await toPng(node, { width: 1800, height: 2400, pixelRatio: 1, cacheBust: true });
    const a = document.createElement("a");
    a.href = url;
    a.download = `${folio(folioOf(idx))}-${pages[idx].layout}.png`;
    a.click();
  };

  const download = async () => {
    setBusy(true);
    try { await downloadOne(cur); }
    catch (err) { alert("导出失败：" + err); }
    finally { setBusy(false); }
  };

  const downloadAll = async () => {
    setBusy(true);
    try {
      for (let i = 0; i < pages.length; i++) {
        if (i !== cur) { setCur(i); await new Promise((r) => setTimeout(r, 350)); }
        await downloadOne(i);
        await new Promise((r) => setTimeout(r, 350));
      }
    } catch (err) { alert("导出失败：" + err); }
    finally { setBusy(false); }
  };

  const built = builtList[Math.min(cur, builtList.length - 1)];

  return (
    <div className="app" onMouseUp={onMouseUp}>
      <aside>
        <header>
          <h1>YXL / 1212</h1>
          <p>3:4 纸面排版 · 全篇输入 → 划重点 → 下载 PNG</p>
        </header>

        <section>
          <h2>配色组</h2>
          <div className="chips">
            {THEMES.map((t) => (
              <button key={t.id} className={theme === t.id ? "on theme-chip" : "theme-chip"}
                onClick={() => setTheme(t.id)} title={t.name}>
                <i style={{ background: t.paper }}><b style={{ background: t.accent }} /></i>
                {t.id}
              </button>
            ))}
            <button className={theme === "custom" ? "on theme-chip" : "theme-chip"} onClick={() => setTheme("custom")}>自定义</button>
          </div>
          {theme === "custom" && (
            <div className="row3 colors">
              <label>纸<input type="color" value={custom.paper} onChange={(e) => setCustom((c) => ({ ...c, paper: e.target.value }))} /></label>
              <label>墨<input type="color" value={custom.ink} onChange={(e) => setCustom((c) => ({ ...c, ink: e.target.value }))} /></label>
              <label>强调<input type="color" value={custom.accent} onChange={(e) => setCustom((c) => ({ ...c, accent: e.target.value }))} /></label>
            </div>
          )}
        </section>

        <section>
          <h2>刊头 · 页码</h2>
          <div className="row-imp">
            <label>系列<input value={series} onChange={(e) => setSeries(e.target.value)} /></label>
            <label className="w-date">日期<input value={date} onChange={(e) => setDate(e.target.value)} /></label>
            <label className="w-num">起始页码<input type="number" min={1} value={folioStart}
              onChange={(e) => setFolioStart(Math.max(1, +e.target.value || 1))} /></label>
          </div>
          <label>页眉左（可选）<input value={page.values.kicker ?? ""} placeholder="留空则显示系列名"
            onChange={(e) => patch("kicker", e.target.value)} /></label>
        </section>

        <section>
          <h2>{LAYOUT_CN[page.layout]} · 当前页内容</h2>
          <div className="chips">
            {Object.entries(LAYOUT_CN).map(([id, cn]) => (
              <button key={id} className={page.layout === id ? "on" : ""} onClick={() => setLayoutOf(id)}>{cn}</button>
            ))}
          </div>
          {FIELDS[page.layout].map((f) => (
            <label key={f.key}>
              {f.label}
              {f.area
                ? <textarea rows={f.key === "paragraphs" ? 7 : 4} value={page.values[f.key] ?? ""} placeholder={f.ph}
                    onChange={(e) => patch(f.key, e.target.value)} />
                : <input value={page.values[f.key] ?? ""} placeholder={f.ph} onChange={(e) => patch(f.key, e.target.value)} />}
            </label>
          ))}
        </section>

        <section>
          <h2>全篇导入（可选）</h2>
          <label>
            粘贴整篇文字，用一行 --- 分页；首页自动成封面、末页成封底、中间成正文
            <textarea rows={4} value={bulk} placeholder={"留白\n也是一种内容\n---\n把字放下，手先离开\n正文第一段…\n---\n一套规则，七张纸。"}
              onChange={(e) => setBulk(e.target.value)} />
          </label>
          <button className="ghost" onClick={importBulk}>导入并重建系列</button>
        </section>

        <footer>
          <button className="dl" disabled={busy} onClick={download}>{busy ? "正在出图…" : `下载当前页 PNG`}</button>
          <button className="dl sub" disabled={busy} onClick={downloadAll}>{busy ? "…" : `整系列下载（${pages.length} 页）`}</button>
          <p className="tip">在预览里划选文字即可标重点（可叠加）；内容自动保存在浏览器。</p>
        </footer>
      </aside>

      <div className="right">
        <div className="topbar">
          <div className="vt">
            <button className={view === "single" ? "on" : ""} onClick={() => setView("single")}>单页</button>
            <button className={view === "series" ? "on" : ""} onClick={() => setView("series")}>系列 {pages.length}</button>
          </div>
          <div className="pills">
            {pages.map((it, i) => (
              <button key={it.id} className={i === cur ? "on" : ""} onClick={() => { setCur(i); setView("single"); }}
                title={`${LAYOUT_CN[it.layout]} · ${it.values.title?.split("\n")[0] ?? ""}`}>
                {folio(folioOf(i))}
              </button>
            ))}
            <button className="add" onClick={addPage} title="添加一页">＋</button>
          </div>
          {view === "single" && (
            <div className="pgops">
              <button onClick={() => movePage(-1)} title="前移">↑</button>
              <button onClick={() => movePage(1)} title="后移">↓</button>
              <button onClick={delPage} title="删除此页">✕</button>
            </div>
          )}
        </div>

        <main className={view === "series" ? "gallery" : ""}>
          {view === "single" ? (
            <div className="stage" style={{ width: 1800 * scale, height: 2400 * scale }}>
              <div style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}>
                <div ref={plateRef} className={plateClass(built.page, meta)} style={customStyle}
                  dangerouslySetInnerHTML={{ __html: buildPlate(built.page, folioOf(cur), meta) }} />
              </div>
            </div>
          ) : (
            builtList.map(({ item, page: pg }, i) => (
              <figure key={item.id} className="thumb" onClick={() => { setCur(i); setView("single"); }}>
                <div className="tstage" style={{ width: 1800 * 0.17, height: 2400 * 0.17 }}>
                  <div style={{ transform: "scale(0.17)", transformOrigin: "top left" }}>
                    <div className={plateClass(pg, meta)} style={customStyle}
                      dangerouslySetInnerHTML={{ __html: buildPlate(pg, folioOf(i), meta) }} />
                  </div>
                </div>
                <figcaption>
                  <b>{folio(folioOf(i))}</b>{LAYOUT_CN[item.layout]}
                </figcaption>
              </figure>
            ))
          )}
        </main>
      </div>

      {pop && (
        <div className="pop" style={{ left: pop.x, top: pop.y }}>
          {EFFECTS.map((ef) => (
            <button key={ef.id} className={popEffects.includes(ef.id) ? "on" : ""}
              onClick={() => applyEffect(ef.id)}>{ef.label}</button>
          ))}
          <span className="sep" />
          <button className="clr" onClick={clearMark}>清除</button>
        </div>
      )}
    </div>
  );
}
