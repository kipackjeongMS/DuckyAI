import { X, FileText, Copy, Check } from "lucide-react";
import { useState, useCallback } from "react";

interface NoteViewerProps {
  filePath: string;
  content: string;
  onClose: () => void;
}

export function NoteViewer({ filePath, content, onClose }: NoteViewerProps) {
  const [copied, setCopied] = useState(false);
  const fileName = filePath.split("/").pop() ?? filePath;

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [content]);

  // Simple markdown rendering: parse frontmatter, headings, lists, bold, links, blockquotes
  const renderContent = () => {
    let body = content;
    let frontmatter: string | null = null;

    // Extract YAML frontmatter
    const fmMatch = body.match(/^---\n([\s\S]*?)\n---\n?/);
    if (fmMatch) {
      frontmatter = fmMatch[1];
      body = body.slice(fmMatch[0].length);
    }

    const lines = body.split("\n");

    return (
      <div className="space-y-1">
        {frontmatter && (
          <div
            className="mb-4 px-3 py-2 rounded-md"
            style={{
              background: "rgba(0,212,255,0.04)",
              border: "1px solid rgba(0,212,255,0.08)",
              fontSize: "0.72rem",
              color: "#64748b",
              fontFamily: "monospace",
              whiteSpace: "pre-wrap",
            }}
          >
            {frontmatter}
          </div>
        )}
        {lines.map((line, i) => renderLine(line, i))}
      </div>
    );
  };

  const renderLine = (line: string, key: number) => {
    const trimmed = line.trimStart();

    // Headings
    if (trimmed.startsWith("######")) return <h6 key={key} className="text-foreground mt-3 mb-1" style={{ fontSize: "0.8rem", fontWeight: 600 }}>{formatInline(trimmed.slice(7))}</h6>;
    if (trimmed.startsWith("#####")) return <h5 key={key} className="text-foreground mt-3 mb-1" style={{ fontSize: "0.82rem", fontWeight: 600 }}>{formatInline(trimmed.slice(6))}</h5>;
    if (trimmed.startsWith("####")) return <h4 key={key} className="text-foreground mt-3 mb-1" style={{ fontSize: "0.85rem", fontWeight: 600 }}>{formatInline(trimmed.slice(5))}</h4>;
    if (trimmed.startsWith("###")) return <h3 key={key} className="text-foreground mt-4 mb-1" style={{ fontSize: "0.9rem", fontWeight: 600 }}>{formatInline(trimmed.slice(4))}</h3>;
    if (trimmed.startsWith("##")) return <h2 key={key} className="text-foreground mt-5 mb-1.5" style={{ fontSize: "1rem", fontWeight: 600 }}>{formatInline(trimmed.slice(3))}</h2>;
    if (trimmed.startsWith("# ")) return <h1 key={key} className="text-foreground mt-5 mb-2" style={{ fontSize: "1.15rem", fontWeight: 700 }}>{formatInline(trimmed.slice(2))}</h1>;

    // Blockquote
    if (trimmed.startsWith(">")) {
      return (
        <div
          key={key}
          className="pl-3 my-1"
          style={{
            borderLeft: "2px solid rgba(0,212,255,0.3)",
            color: "#94a3b8",
            fontSize: "0.78rem",
            fontStyle: "italic",
          }}
        >
          {formatInline(trimmed.slice(1).trimStart())}
        </div>
      );
    }

    // Horizontal rule
    if (/^[-*_]{3,}\s*$/.test(trimmed)) {
      return <hr key={key} className="my-3" style={{ border: "none", borderTop: "1px solid rgba(0,212,255,0.08)" }} />;
    }

    // Checkbox list items
    if (/^[-*]\s*\[[ x]\]/.test(trimmed)) {
      const checked = /\[x\]/i.test(trimmed);
      const text = trimmed.replace(/^[-*]\s*\[[ x]\]\s*/, "");
      return (
        <div key={key} className="flex items-start gap-2 py-0.5" style={{ paddingLeft: (line.length - trimmed.length) * 4 }}>
          <span style={{ color: checked ? "#00ffa3" : "#475569", fontSize: "0.8rem" }}>
            {checked ? "☑" : "☐"}
          </span>
          <span className="text-foreground" style={{ fontSize: "0.78rem", textDecoration: checked ? "line-through" : "none", opacity: checked ? 0.6 : 1 }}>
            {formatInline(text)}
          </span>
        </div>
      );
    }

    // List items
    if (/^[-*]\s/.test(trimmed)) {
      const text = trimmed.replace(/^[-*]\s/, "");
      return (
        <div key={key} className="flex items-start gap-2 py-0.5" style={{ paddingLeft: (line.length - trimmed.length) * 4 }}>
          <span style={{ color: "#00d4ff", fontSize: "0.6rem", marginTop: "0.35rem" }}>●</span>
          <span className="text-foreground" style={{ fontSize: "0.78rem" }}>{formatInline(text)}</span>
        </div>
      );
    }

    // Numbered list items
    if (/^\d+\.\s/.test(trimmed)) {
      const match = trimmed.match(/^(\d+)\.\s(.*)/);
      if (match) {
        return (
          <div key={key} className="flex items-start gap-2 py-0.5" style={{ paddingLeft: (line.length - trimmed.length) * 4 }}>
            <span style={{ color: "#00d4ff", fontSize: "0.72rem", minWidth: "1rem", textAlign: "right" }}>{match[1]}.</span>
            <span className="text-foreground" style={{ fontSize: "0.78rem" }}>{formatInline(match[2])}</span>
          </div>
        );
      }
    }

    // Empty line
    if (trimmed === "") return <div key={key} className="h-2" />;

    // Normal paragraph
    return <p key={key} className="text-foreground" style={{ fontSize: "0.78rem", lineHeight: 1.6 }}>{formatInline(trimmed)}</p>;
  };

  return (
    <div className="h-full flex flex-col">
      {/* File header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 shrink-0"
        style={{
          background: "rgba(8,12,22,0.9)",
          borderBottom: "1px solid rgba(0,212,255,0.06)",
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={14} style={{ color: "#00d4ff" }} />
          <span className="text-foreground truncate" style={{ fontSize: "0.8rem" }}>{fileName}</span>
          <span className="text-muted-foreground truncate" style={{ fontSize: "0.65rem" }}>
            {filePath}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="Copy content"
          >
            {copied ? <Check size={14} style={{ color: "#00ffa3" }} /> : <Copy size={14} />}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {renderContent()}
      </div>
    </div>
  );
}

/* ── Inline formatting ────────────────────────── */
function formatInline(text: string): React.ReactNode {
  // Process bold, italic, inline code, wiki links, and markdown links
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    // Wiki links: [[target|display]] or [[target]]
    const wikiMatch = remaining.match(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/);
    // Inline code: `code`
    const codeMatch = remaining.match(/`([^`]+)`/);
    // Bold: **text** or __text__
    const boldMatch = remaining.match(/\*\*(.+?)\*\*|__(.+?)__/);
    // Italic: *text* or _text_
    const italicMatch = remaining.match(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/);
    // Markdown link: [text](url)
    const linkMatch = remaining.match(/\[([^\]]+)\]\(([^)]+)\)/);

    // Find earliest match
    const matches = [
      wikiMatch && { index: wikiMatch.index!, type: "wiki" as const, match: wikiMatch },
      codeMatch && { index: codeMatch.index!, type: "code" as const, match: codeMatch },
      boldMatch && { index: boldMatch.index!, type: "bold" as const, match: boldMatch },
      italicMatch && { index: italicMatch.index!, type: "italic" as const, match: italicMatch },
      linkMatch && { index: linkMatch.index!, type: "link" as const, match: linkMatch },
    ].filter(Boolean).sort((a, b) => a!.index - b!.index);

    if (matches.length === 0) {
      parts.push(remaining);
      break;
    }

    const first = matches[0]!;

    // Add text before match
    if (first.index > 0) {
      parts.push(remaining.slice(0, first.index));
    }

    switch (first.type) {
      case "wiki":
        parts.push(
          <span key={key++} style={{ color: "#00d4ff", fontSize: "inherit" }}>
            {first.match[2] ?? first.match[1]}
          </span>,
        );
        remaining = remaining.slice(first.index + first.match[0].length);
        break;
      case "code":
        parts.push(
          <code
            key={key++}
            style={{
              background: "rgba(0,212,255,0.08)",
              padding: "0.1em 0.35em",
              borderRadius: "3px",
              fontSize: "0.9em",
              fontFamily: "monospace",
              color: "#e2e8f0",
            }}
          >
            {first.match[1]}
          </code>,
        );
        remaining = remaining.slice(first.index + first.match[0].length);
        break;
      case "bold":
        parts.push(
          <strong key={key++} style={{ color: "#e2e8f0" }}>
            {first.match[1] ?? first.match[2]}
          </strong>,
        );
        remaining = remaining.slice(first.index + first.match[0].length);
        break;
      case "italic":
        parts.push(
          <em key={key++} style={{ color: "#cbd5e1" }}>
            {first.match[1] ?? first.match[2]}
          </em>,
        );
        remaining = remaining.slice(first.index + first.match[0].length);
        break;
      case "link":
        parts.push(
          <span key={key++} style={{ color: "#00d4ff", textDecoration: "underline", cursor: "pointer" }}>
            {first.match[1]}
          </span>,
        );
        remaining = remaining.slice(first.index + first.match[0].length);
        break;
    }
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>;
}
