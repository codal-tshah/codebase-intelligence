import { useEffect, useRef, useState } from "react";
import { API } from "../api";
import { NodeIcon } from "../icons";
import { createSseParser } from "../sse";
import type { Citation, ToolStep } from "../types";
import { MarkdownContent } from "./MarkdownContent";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools?: ToolStep[];
  citations?: Citation[];
  mode?: string;
  error?: string;
};

const SUGGESTIONS = [
  "Give me an overview of the architecture",
  "Which API endpoints exist and what handles them?",
  "Which database models exist and how are they related?",
  "How does authentication work here?",
];

type Props = {
  projectId: string;
  focusNodeId: string | null;
  focusNodeName?: string | null;
  onHighlightNodes: (ids: string[]) => void;
  onNavigateNode: (id: string) => void;
  onOpenSource: (path: string, line: number) => void;
  /** Set a new token to ask `text` programmatically (e.g. the inspector's Explain button). */
  seed?: { text: string; token: number } | null;
};

let msgCounter = 0;
const nextId = () => `msg-${Date.now()}-${++msgCounter}`;

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Ask about endpoints, data models, authentication, or what a change would affect. Answers come from the indexed code. Linked names open in the diagram; `file:line` links open the source.",
};

export function ChatPanel({ projectId, focusNodeId, focusNodeName, onHighlightNodes, onNavigateNode, onOpenSource, seed }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [useFocus, setUseFocus] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    // a different project is a different conversation
    abortRef.current?.abort();
    setMessages([WELCOME]);
  }, [projectId]);

  const lastSeed = useRef(0);
  useEffect(() => {
    if (seed && seed.token !== lastSeed.current && !loading) {
      lastSeed.current = seed.token;
      void send(seed.text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);

  const update = (id: string, fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((all) => all.map((m) => (m.id === id ? fn(m) : m)));

  const send = async (text: string) => {
    const question = text.trim();
    if (!projectId || !question || loading) return;
    const userMsg: ChatMessage = { id: nextId(), role: "user", content: question };
    const assistantId = nextId();
    const history = [...messages, userMsg]
      .filter((m) => m.id !== "welcome")
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, userMsg, { id: assistantId, role: "assistant", content: "", tools: [] }]);
    setInput("");
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;

    const parser = createSseParser(({ event, data }) => {
      if (event === "message") update(assistantId, (m) => ({ ...m, content: m.content + data }));
      else if (event === "tool") {
        try {
          const step = JSON.parse(data) as ToolStep;
          update(assistantId, (m) => ({ ...m, tools: [...(m.tools ?? []), step] }));
        } catch {
          /* ignore malformed */
        }
      } else if (event === "citations") {
        try {
          const citations = JSON.parse(data) as Citation[];
          update(assistantId, (m) => ({ ...m, citations }));
          const cited = citations.filter((c) => c.cited).map((c) => c.node_id);
          onHighlightNodes(cited.length ? cited : citations.slice(0, 8).map((c) => c.node_id));
        } catch {
          /* ignore */
        }
      } else if (event === "done") {
        try {
          const done = JSON.parse(data) as { mode: string };
          update(assistantId, (m) => ({ ...m, mode: done.mode }));
        } catch {
          /* ignore */
        }
      } else if (event === "error") update(assistantId, (m) => ({ ...m, error: data }));
    });

    try {
      const res = await fetch(`${API}/projects/${projectId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question,
          focus_node_id: useFocus ? focusNodeId : null,
          conversation_history: history,
        }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parser.push(decoder.decode(value, { stream: true }));
      }
      parser.end();
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        update(assistantId, (m) => ({ ...m, error: "Could not reach the assistant. Is the API running?" }));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-thread">
        {messages.map((m) => (
          <article key={m.id} className={`chat-msg chat-msg--${m.role}`}>
            <span className="chat-role">
              {m.role === "user" ? "You" : "Assistant"}
              {m.mode ? <span className="chat-mode">{m.mode === "agent" ? "agent" : "graph lookup"}</span> : null}
            </span>
            {m.tools && m.tools.length > 0 ? (
              <details className="tool-steps" open={loading && !m.content}>
                <summary>
                  {m.tools.length} grounding step{m.tools.length > 1 ? "s" : ""}
                </summary>
                <ol>
                  {m.tools.map((t, i) => (
                    <li key={i}>
                      <code>{t.name}</code>
                      <span className="muted"> {formatArgs(t.args)} → {t.summary}</span>
                    </li>
                  ))}
                </ol>
              </details>
            ) : null}
            {m.role === "assistant" ? (
              <MarkdownContent
                content={m.content}
                onNodeLink={onNavigateNode}
                onSourceLink={onOpenSource}
              />
            ) : (
              <p>{m.content}</p>
            )}
            {loading && m.role === "assistant" && m === messages[messages.length - 1] ? (
              <span className="stream-caret" aria-label="Answer is streaming" />
            ) : null}
            {m.error ? <p className="error-text">{m.error}</p> : null}
            {m.citations && m.citations.length > 0 ? (
              <div className="citations">
                <div className="citations-head">
                  <span className="muted">Sources</span>
                  <button type="button" className="link-btn" onClick={() => onHighlightNodes(m.citations!.map((c) => c.node_id))}>
                    Highlight on diagram
                  </button>
                </div>
                <div className="chip-row">
                  {m.citations.map((c) => (
                    <button
                      key={c.node_id}
                      type="button"
                      className={`chip citation ${c.cited ? "cited" : ""}`}
                      title={c.path ? `${c.path}${c.line ? `:${c.line}` : ""}` : c.label}
                      onClick={() => onNavigateNode(c.node_id)}
                    >
                      <NodeIcon type={c.node_type} size={12} className="citation-glyph" />
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </article>
        ))}
        <div ref={endRef} />
      </div>
      {messages.length <= 1 ? (
        <div className="suggestion-row">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" onClick={() => send(s)} disabled={loading}>
              {s}
            </button>
          ))}
        </div>
      ) : null}
      <div className="chat-composer">
        {focusNodeId && focusNodeName ? (
          <label className="focus-toggle">
            <input type="checkbox" checked={useFocus} onChange={(e) => setUseFocus(e.target.checked)} />
            <span>
              Ask about selection: <strong>{focusNodeName}</strong>
            </span>
          </label>
        ) : null}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this codebase…"
          aria-label="Question"
          rows={3}
          disabled={loading}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void send(input);
            }
          }}
        />
        <div className="composer-row">
          {loading ? (
            <button type="button" className="btn ghost" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          ) : messages.length > 1 ? (
            <button type="button" className="btn ghost" onClick={() => setMessages([WELCOME])}>
              New chat
            </button>
          ) : (
            <span />
          )}
          <button type="button" className="btn primary" disabled={loading || !input.trim()} onClick={() => void send(input)}>
            {loading ? "Answering…" : "Ask"}
          {!loading ? <kbd className="kbd-on-accent">⌘↵</kbd> : null}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args ?? {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v)}`);
  return parts.length ? `(${parts.join(", ")})` : "";
}
