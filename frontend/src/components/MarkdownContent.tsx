import ReactMarkdown, { defaultUrlTransform } from "react-markdown";

type Props = {
  content: string;
  className?: string;
  /** `[Name](node:<id>)` links in assistant answers */
  onNodeLink?: (id: string) => void;
  /** `[path:12](source:path#L12)` links */
  onSourceLink?: (path: string, line: number) => void;
};

/** Allow the assistant's in-app link schemes; everything else goes through the safe default. */
const urlTransform = (url: string) => (url.startsWith("node:") || url.startsWith("source:") ? url : defaultUrlTransform(url));

export function MarkdownContent({ content, className = "", onNodeLink, onSourceLink }: Props) {
  return (
    <div className={`markdown ${className}`}>
      <ReactMarkdown
        urlTransform={urlTransform}
        components={{
          p: ({ children }) => <p className="md-p">{children}</p>,
          ul: ({ children }) => <ul className="md-ul">{children}</ul>,
          li: ({ children }) => <li className="md-li">{children}</li>,
          code: ({ children }) => <code className="md-code">{children}</code>,
          strong: ({ children }) => <strong className="md-strong">{children}</strong>,
          a: ({ href = "", children }) => {
            if (href.startsWith("node:")) {
              const id = href.slice(5);
              return (
                <button type="button" className="md-link md-link--node" onClick={() => onNodeLink?.(id)} title="Show in graph">
                  {children}
                </button>
              );
            }
            if (href.startsWith("source:")) {
              const [path, frag = ""] = href.slice(7).split("#");
              const line = Number(frag.replace(/^L/, "")) || 1;
              return (
                <button type="button" className="md-link md-link--source" onClick={() => onSourceLink?.(path, line)} title="Open source">
                  {children}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
