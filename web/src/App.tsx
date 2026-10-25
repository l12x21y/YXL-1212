import { useMemo, useRef, useState } from "react";
import { toPng } from "html-to-image";
import { buildPlate, plateClass, LAYOUT_CN, folio, type Meta, type Page } from "./plate";

const THEMES: { id: string; name: string; paper: string; accent: string }[] = [
  { id: "ivory", name: "米纸 · 克莱因蓝", paper: "#f2efe7", accent: "#1b2ac6" },
  { id: "bone", name: "骨白 · 番茄红", paper: "#efeeea", accent: "#d93b22" },
  { id: "kraft", name: "淡牛皮 · 赭橘", paper: "#e7dcc7", accent: "#bf4218" },
  { id: "slate", name: "冷灰 · 洋红", paper: "#e8e9e5", accent: "#c3216b" },
  { id: "night", name: "墨夜 · 朱砂", paper: "#15150f", accent: "#e4543a" },
];

type Field = { key: string; label: string; ph?: string; area?: boolean; hint?: string };

const FIELDS: Record<string, Field[]> = {
  cover: [
    { key: "title", label: "标题（一行一句；*字* 染色）", ph: "留*白*\n也是一种内容", area: true },
    { key: "subtitle", label: "副标", ph: "版面之所以有重量，是因为它知道在哪里停下。" },
    { key: "subtitle_en", label: "英文副标（可选）" },
  ],
  statement: [
    { key: "text", label: "宣言（自动分列，~12 字一列）", ph: "不是没有东西\n是不急着说", area: true },
    { key: "pre", label: "横排前缀（拉丁字母用，可选）" },
    { key: "note", label: "左下注（可选）", area: true },
  ],
  quote: [
    { key: "text", label: "引文（一行一句；==反白== 可用）", ph: "空的地方，\n读者会自己走进去。", area: true },
    { key: "sign", label: "出处（可选）", ph: "— 关于负空间的旧话" },
  ],
  list: [
    { key: "title", label: "标题" },
    { key: "lead", label: "引言（可选）" },
    { key: "items", label: "条目（每行一条：名称 | 说明）", ph: "分配注意力 | 眼睛先落在哪里，由空处决定\n建立节奏 | 段与段之间的停顿是呼吸的长度", area: true },
  ],
  essay: [
    { key: "label", label: "栏目标签", ph: "札记" },
    { key: "title", label: "标题" },
    { key: "paragraphs", label: "正文（空行分段；*染色* ^^放大^^ ==反白== [[提行]] @@大字@@ <~压灰~>）", ph: "排一张版，最难的不是放什么，而是决定不放什么。\n\n删到只剩一句，那句话才有分量。", area: true },
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
    { key: "paragraphs", label: "正文（空行分段）", area: true },
  ],
};

const parseItems = (s: string, pg = false) =>
  s.split("\n").map((l) => l.trim()).filter(Boolean)
    .map((l) => {
      const [a, b] = l.split("|").map((x) => x.trim());
      return pg ? { t: a ?? "", pg: b ?? "" } : { t: a ?? "", d: b ?? "" };
    });

const splitParas = (s: string) => s.split(/\n\s*\n/).map((x) => x.replace(/\n/g, "\n")).filter((x) => x.trim());

const DEMO: Record<string, string> = {
  label: "札记",
  title: "把字放下，手先离开",
  paragraphs:
    "排一张版，最难的不是放什么，而是决定不放什么。每一块空白都在替读者让路，让视线有地方转身。\n\n删到只剩一句，那句话才有分量。留白不是给视觉的福利，它是给判断力的。一个版面敢空着，说明作者知道自己要说什么。",
  sign: "2026 · 于桌前",
};

export default function App() {
  const [layout, setLayout] = useState("essay");
  const [theme, setTheme] = useState("ivory");
  const [series, setSeries] = useState("YXL / 1212");
  const [date, setDate] = useState("2026");
  const [values, setValues] = useState<Record<string, string>>(DEMO);
  const [busy, setBusy] = useState(false);
  const plateRef = useRef<HTMLDivElement>(null);

  const meta: Meta = { series, date, theme };
  const page: Page = useMemo(() => {
    const v = values;
    const p: Page = { layout, theme };
    if (v.kicker) p.kicker = v.kicker;
    FIELDS[layout].forEach((f) => {
      const val = v[f.key] ?? "";
      if (!val) return;
      if (f.key === "items") p.items = parseItems(val, layout === "index");
      else if (f.key === "paragraphs") p.paragraphs = splitParas(val);
      else if (f.key === "title") p.title = val.split("\n");
      else if (f.key === "text" && layout === "quote") p.text = val.split("\n");
      else p[f.key] = val;
    });
    return p;
  }, [layout, theme, values]);

  const html = useMemo(() => buildPlate(page, 1, meta), [page, series, date]);
  const scale = 0.36;

  const download = async () => {
    if (!plateRef.current) return;
    setBusy(true);
    try {
      const url = await toPng(plateRef.current, { width: 1800, height: 2400, pixelRatio: 1, cacheBust: true });
      const a = document.createElement("a");
      a.href = url;
      a.download = `${folio(1)}-${layout}.png`;
      a.click();
    } catch (err) {
      alert("导出失败：" + err);
    } finally {
      setBusy(false);
    }
  };

  const set = (k: string, v: string) => setValues((s) => ({ ...s, [k]: v }));

  return (
    <div className="app">
      <aside>
        <header>
          <h1>YXL / 1212</h1>
          <p>3:4 纸面排版 · 粘贴文字 → 排版 → 下载 PNG</p>
        </header>

        <section>
          <h2>版式</h2>
          <div className="chips">
            {Object.entries(LAYOUT_CN).map(([id, cn]) => (
              <button key={id} className={layout === id ? "on" : ""} onClick={() => setLayout(id)}>{cn}</button>
            ))}
          </div>
        </section>

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
          </div>
        </section>

        <section>
          <h2>刊头</h2>
          <div className="row2">
            <label>系列<input value={series} onChange={(e) => setSeries(e.target.value)} /></label>
            <label>日期<input value={date} onChange={(e) => setDate(e.target.value)} /></label>
          </div>
          <label>页眉左（可选）<input value={values.kicker ?? ""} placeholder="留空则显示系列名"
            onChange={(e) => set("kicker", e.target.value)} /></label>
        </section>

        <section>
          <h2>{LAYOUT_CN[layout]} · 内容</h2>
          {FIELDS[layout].map((f) => (
            <label key={f.key}>
              {f.label}
              {f.area
                ? <textarea rows={f.key === "paragraphs" ? 8 : 4} value={values[f.key] ?? ""} placeholder={f.ph}
                    onChange={(e) => set(f.key, e.target.value)} />
                : <input value={values[f.key] ?? ""} placeholder={f.ph} onChange={(e) => set(f.key, e.target.value)} />}
            </label>
          ))}
        </section>

        <footer>
          <button className="dl" disabled={busy} onClick={download}>{busy ? "正在出图…" : "下载 PNG（1800×2400）"}</button>
          <p className="tip">{"强调语法：*染色*　^^放大^^　!!加重!!　==反白==　[[提行]]　@@大字@@　<~压灰~>　换行 = 空两格续行"}</p>
        </footer>
      </aside>

      <main>
        <div className="stage" style={{ width: 1800 * scale, height: 2400 * scale }}>
          <div style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}>
            <div ref={plateRef} className={plateClass(page, meta)}
              dangerouslySetInnerHTML={{ __html: html }} />
          </div>
        </div>
      </main>
    </div>
  );
}
