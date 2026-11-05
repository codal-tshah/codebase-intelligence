/**
 * Tiny line-by-line highlighter for the code viewer (Python, TS/JS). Not a parser: it colours
 * keywords, strings, comments, numbers, decorators, types and called names, and carries state for
 * multi-line strings and block comments. Unknown languages render as plain text.
 */
export type Token = { text: string; kind?: "kw" | "str" | "com" | "num" | "fn" | "type" | "deco" };

const KW: Record<string, Set<string>> = {
  python: new Set(
    "def class return if elif else for while in not and or is import from as with try except finally raise yield async await lambda pass break continue global nonlocal None True False self cls".split(" "),
  ),
  ts: new Set(
    "const let var function return if else for while do switch case break continue new class extends implements interface type enum import from export default as async await try catch finally throw typeof instanceof in of this super null undefined true false void public private protected readonly static".split(" "),
  ),
};

export function languageOf(path?: string | null): "python" | "ts" | null {
  const ext = path?.split(".").pop()?.toLowerCase();
  if (ext === "py") return "python";
  if (ext && ["ts", "tsx", "js", "jsx", "mjs", "cjs"].includes(ext)) return "ts";
  return null;
}

const TOKEN = /("""|'''|\/\*|\*\/|\/\/.*|#.*|`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|@[A-Za-z_][\w.]*|\b\d[\d_.]*\b|[A-Za-z_$][\w$]*|\s+|.)/g;

export function highlightLines(lines: string[], lang: "python" | "ts" | null): Token[][] {
  if (!lang) return lines.map((l) => [{ text: l }]);
  const keywords = KW[lang];
  let open: '"""' | "'''" | "/*" | null = null;
  return lines.map((line) => {
    const out: Token[] = [];
    const parts = line.match(TOKEN) ?? [];
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (open) {
        out.push({ text: p, kind: open === "/*" ? "com" : "str" });
        if ((open === "/*" && p === "*/") || p === open) open = null;
        continue;
      }
      if (lang === "python" && (p === '"""' || p === "'''")) {
        open = p;
        out.push({ text: p, kind: "str" });
      } else if (lang === "ts" && p === "/*") {
        open = "/*";
        out.push({ text: p, kind: "com" });
      } else if ((lang === "ts" && p.startsWith("//")) || (lang === "python" && p.startsWith("#"))) {
        out.push({ text: p, kind: "com" });
      } else if (/^["'`]/.test(p) && p.length > 1) {
        out.push({ text: p, kind: "str" });
      } else if (p.startsWith("@") && p.length > 1) {
        out.push({ text: p, kind: "deco" });
      } else if (/^\d/.test(p)) {
        out.push({ text: p, kind: "num" });
      } else if (/^[A-Za-z_$]/.test(p)) {
        const next = parts.slice(i + 1).find((x) => !/^\s+$/.test(x));
        if (keywords.has(p)) out.push({ text: p, kind: "kw" });
        else if (next === "(") out.push({ text: p, kind: "fn" });
        else if (/^[A-Z][a-z0-9]/.test(p)) out.push({ text: p, kind: "type" });
        else out.push({ text: p });
      } else {
        const prev = out[out.length - 1];
        if (prev && !prev.kind) prev.text += p;
        else out.push({ text: p });
      }
    }
    return out;
  });
}
