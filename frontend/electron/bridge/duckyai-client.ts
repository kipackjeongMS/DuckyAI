import fs from "node:fs";
import path from "node:path";

/**
 * HTTP client for the DuckyAI Python daemon API.
 * Replaces both McpClient (vault tools) and OrchestratorBridge (CLI shell-outs)
 * with a single fetch-based client that talks to http://localhost:52845/api/*.
 *
 * Service discovery: reads .duckyai/api.json written by the Python daemon.
 */

export interface OrchestratorStatus {
  running: boolean;
  vault_path?: string;
  agents_loaded?: number;
  running_executions?: number;
}

export interface AgentInfo {
  abbreviation: string;
  name: string;
  category: string;
  cron: string | null;
  running?: number;
}

interface DiscoveryFile {
  host: string;
  port: number;
  pid: number;
  url: string;
}

const DEFAULT_URL = "http://127.0.0.1:52845";

export class DuckyAIClient {
  private baseUrl: string;

  constructor(private vaultPath: string) {
    this.baseUrl = this.discover();
  }

  // ── Service Discovery ────────────────────────────────────────

  /** Read .duckyai/api.json or fall back to default URL. */
  private discover(): string {
    const discoveryPath = path.join(this.vaultPath, ".duckyai", "api.json");
    try {
      if (fs.existsSync(discoveryPath)) {
        const data: DiscoveryFile = JSON.parse(fs.readFileSync(discoveryPath, "utf-8"));
        if (data.url) {
          console.log(`[duckyai-client] Discovered API at ${data.url}`);
          return data.url;
        }
      }
    } catch (err) {
      console.warn("[duckyai-client] Failed to read discovery file:", err);
    }
    console.log(`[duckyai-client] Using default API URL: ${DEFAULT_URL}`);
    return DEFAULT_URL;
  }

  /** Re-read discovery file (call after daemon restart). */
  refreshDiscovery(): void {
    this.baseUrl = this.discover();
  }

  // ── Health ───────────────────────────────────────────────────

  async health(): Promise<{ status: string; pid: number }> {
    return this.get("/api/health");
  }

  // ── Orchestrator ─────────────────────────────────────────────

  async status(): Promise<OrchestratorStatus> {
    return this.get("/api/orchestrator/status");
  }

  async listAgents(): Promise<AgentInfo[]> {
    return this.get("/api/orchestrator/agents");
  }

  async triggerAgent(
    abbr: string,
    opts?: { file?: string; lookback?: number; sinceLastSync?: boolean },
  ): Promise<{ status: string; agent: string }> {
    const body: Record<string, unknown> = { agent: abbr };
    if (opts?.file) body.input_file = opts.file;

    // Map desktop options to API agent_params
    const agentParams: Record<string, unknown> = {};
    if (opts?.lookback) {
      agentParams.lookback = opts.lookback;
    } else if (opts?.sinceLastSync) {
      agentParams.sinceLastSync = true;
    }
    if (Object.keys(agentParams).length > 0) {
      body.agent_params = agentParams;
    }

    return this.post("/api/orchestrator/trigger", body);
  }

  // ── Vault Tools ──────────────────────────────────────────────

  async listTools(): Promise<string[]> {
    return this.get("/api/vault/tools");
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<string> {
    const resp = await this.post("/api/vault/tool", { tool: name, arguments: args });
    // Extract text content from MCP-style response
    if (resp.content && Array.isArray(resp.content)) {
      return resp.content.map((c: { text?: string }) => c.text ?? "").join("\n");
    }
    if (resp.error) {
      throw new Error(resp.error);
    }
    return JSON.stringify(resp);
  }

  // ── Lifecycle ────────────────────────────────────────────────

  /** No-op — HTTP client has no persistent connection to close. */
  close(): void {
    // Nothing to clean up (no child processes, no persistent connections)
  }

  // ── HTTP Helpers ─────────────────────────────────────────────

  private async get(endpoint: string): Promise<any> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      method: "GET",
      headers: { "Accept": "application/json" },
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`GET ${endpoint} failed (${response.status}): ${body}`);
    }
    return response.json();
  }

  async post(endpoint: string, body: Record<string, unknown> = {}, timeoutMs?: number): Promise<any> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs ?? 600_000), // default 10 min for long agent runs
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(`POST ${endpoint} failed (${response.status}): ${text}`);
    }
    return response.json();
  }

  /** Quick health probe with a short timeout (for lifecycle checks). */
  async quickHealth(): Promise<boolean> {
    try {
      const url = `${this.baseUrl}/api/health`;
      const response = await fetch(url, {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal: AbortSignal.timeout(3_000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /** Remove stale discovery file so refreshDiscovery picks up a fresh one. */
  clearDiscovery(): void {
    const discoveryPath = path.join(this.vaultPath, ".duckyai", "api.json");
    try {
      if (fs.existsSync(discoveryPath)) {
        fs.unlinkSync(discoveryPath);
        console.log("[duckyai-client] Cleared stale discovery file");
      }
    } catch (err) {
      console.warn("[duckyai-client] Failed to clear discovery file:", err);
    }
    this.baseUrl = DEFAULT_URL;
  }
}
