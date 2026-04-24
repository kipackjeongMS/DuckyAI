import { useEffect, useRef, useCallback, useState } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";

export interface TerminalPanelProps {
  /** WebSocket URL, e.g. ws://127.0.0.1:52847/ws/terminal */
  wsUrl: string;
}

type ConnState = "connecting" | "connected" | "disconnected";

export function TerminalPanel({ wsUrl }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retriesRef = useRef(0);
  const [connState, setConnState] = useState<ConnState>("disconnected");

  const MAX_RETRIES = 4;
  const BASE_DELAY_MS = 1500;

  const connect = useCallback(() => {
    if (!termRef.current) return;
    const term = termRef.current;

    // Clear any pending retry
    if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }

    setConnState("connecting");
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      setConnState("connected");
      if (fitRef.current) {
        const dims = fitRef.current.proposeDimensions();
        if (dims) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      }
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(event.data));
      } else if (typeof event.data === "string") {
        term.write(event.data);
      }
    };

    const handleDisconnect = () => {
      setConnState("disconnected");
      if (retriesRef.current < MAX_RETRIES) {
        const delay = BASE_DELAY_MS * Math.pow(2, retriesRef.current);
        retriesRef.current++;
        term.write(`\r\n\x1b[90m[Reconnecting in ${(delay / 1000).toFixed(0)}s…]\x1b[0m\r\n`);
        retryRef.current = setTimeout(connect, delay);
      } else {
        term.write(
          "\r\n\x1b[90m[Terminal server unreachable. Run: \x1b[37mduckyai terminal start\x1b[90m]\x1b[0m\r\n" +
          "\x1b[90m[Click to retry]\x1b[0m\r\n"
        );
      }
    };

    ws.onclose = handleDisconnect;
    ws.onerror = () => { /* onclose will fire after onerror */ };
  }, [wsUrl]);

  // Initialize xterm + addons
  useEffect(() => {
    if (!containerRef.current) return;

    const term = new XTerm({
      cursorBlink: true,
      fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace",
      fontSize: 13,
      lineHeight: 1.3,
      theme: {
        background: "#0a0e1a",
        foreground: "#e2e8f0",
        cursor: "#00d4ff",
        cursorAccent: "#0a0e1a",
        selectionBackground: "rgba(0,212,255,0.2)",
        black: "#1e293b",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#facc15",
        blue: "#60a5fa",
        magenta: "#c084fc",
        cyan: "#00d4ff",
        white: "#e2e8f0",
        brightBlack: "#475569",
        brightRed: "#fca5a5",
        brightGreen: "#86efac",
        brightYellow: "#fde68a",
        brightBlue: "#93c5fd",
        brightMagenta: "#d8b4fe",
        brightCyan: "#67e8f9",
        brightWhite: "#f8fafc",
      },
    });

    const fit = new FitAddon();
    const webLinks = new WebLinksAddon();
    term.loadAddon(fit);
    term.loadAddon(webLinks);

    term.open(containerRef.current);
    fit.fit();

    termRef.current = term;
    fitRef.current = fit;

    // Forward keystrokes to WebSocket
    term.onData((data) => {
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    // Handle resize
    const ro = new ResizeObserver(() => {
      fit.fit();
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        const dims = fit.proposeDimensions();
        if (dims) {
          ws.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      }
    });
    ro.observe(containerRef.current);

    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      ro.disconnect();
      wsRef.current?.close();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
      wsRef.current = null;
    };
  }, []);

  // Connect once after terminal is initialized
  const mountedRef = useRef(false);
  useEffect(() => {
    if (termRef.current && !mountedRef.current) {
      mountedRef.current = true;
      connect();
    }
  }, [connect]);

  const handleClick = useCallback(() => {
    if (connState === "disconnected") {
      retriesRef.current = 0; // reset retries on manual click
      connect();
    }
    termRef.current?.focus();
  }, [connState, connect]);

  return (
    <div
      className="flex flex-col h-full w-full bg-[#0a0e1a]"
      onClick={handleClick}
    >
      {/* Status bar */}
      <div
        className="flex items-center gap-2 px-3 py-1 border-b border-[rgba(0,212,255,0.08)]"
        style={{ fontSize: "0.68rem", letterSpacing: "0.05em" }}
      >
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{
            backgroundColor:
              connState === "connected"
                ? "#4ade80"
                : connState === "connecting"
                  ? "#facc15"
                  : "#64748b",
          }}
        />
        <span className="text-muted-foreground uppercase">
          {connState === "connected"
            ? "Terminal"
            : connState === "connecting"
              ? "Connecting…"
              : "Disconnected"}
        </span>
      </div>

      {/* Terminal viewport */}
      <div ref={containerRef} className="flex-1 overflow-hidden p-1" />
    </div>
  );
}
