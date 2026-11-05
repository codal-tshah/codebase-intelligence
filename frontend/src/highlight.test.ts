import { describe, expect, it } from "vitest";
import { highlightLines, languageOf } from "./highlight";

const kinds = (line: string, lang: "python" | "ts") =>
  highlightLines([line], lang)[0].filter((t) => t.kind).map((t) => `${t.kind}:${t.text}`);

describe("highlightLines", () => {
  it("colours python keywords, calls, decorators, strings and comments", () => {
    expect(kinds('@router.get("/x")  # route', "python")).toEqual(["deco:@router.get", 'str:"/x"', "com:# route"]);
    expect(kinds("def get_item(db): return Item(1)", "python")).toEqual(["kw:def", "fn:get_item", "kw:return", "fn:Item", "num:1"]);
  });

  it("carries block comments and docstrings across lines", () => {
    const out = highlightLines(["/* start", "middle */ const x = 1"], "ts");
    expect(out[1][0]).toEqual({ text: "middle", kind: "com" });
    expect(out[1].some((t) => t.kind === "kw" && t.text === "const")).toBe(true);
    const py = highlightLines(['"""Doc', 'more"""', "x = 1"], "python");
    expect(py[1].every((t) => t.kind === "str")).toBe(true);
  });

  it("keeps text intact and leaves unknown languages plain", () => {
    const line = "const a = `x${1}` // hi";
    expect(highlightLines([line], "ts")[0].map((t) => t.text).join("")).toBe(line);
    expect(languageOf("a.md")).toBeNull();
    expect(highlightLines(["plain"], null)).toEqual([[{ text: "plain" }]]);
  });
});
