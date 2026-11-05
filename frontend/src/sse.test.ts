import { describe, expect, it } from "vitest";
import { createSseParser, type SseEvent } from "./sse";

function run(chunks: string[]): SseEvent[] {
  const out: SseEvent[] = [];
  const parser = createSseParser((e) => out.push(e));
  chunks.forEach((c) => parser.push(c));
  parser.end();
  return out;
}

describe("createSseParser", () => {
  it("keeps newlines in multi-line data (markdown survives)", () => {
    expect(run(["event: message\ndata: line one\ndata: \ndata: line two\n\n"])).toEqual([
      { event: "message", data: "line one\n\nline two" },
    ]);
  });

  it("reassembles events split across arbitrary chunk boundaries", () => {
    const events = run(["event: tool\nda", 'ta: {"name":"x"}\n', "\nevent: done\ndata: ok\n\n"]);
    expect(events).toEqual([
      { event: "tool", data: '{"name":"x"}' },
      { event: "done", data: "ok" },
    ]);
  });

  it("handles CRLF, comments, and a missing trailing blank line", () => {
    expect(run([": ping\r\nevent: message\r\ndata: hi\r\n\r\ndata: tail"])).toEqual([
      { event: "message", data: "hi" },
      { event: "message", data: "tail" },
    ]);
  });
});
