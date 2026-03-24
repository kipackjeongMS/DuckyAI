import { exec } from "node:child_process";

export interface OrchestratorStatus {
  running: boolean;
  pid?: number;
  agents_loaded?: number;
}

export interface AgentInfo {
  abbreviation: string;
  name: string;
  category: string;
  cron: string | null;
  enabled: boolean;
}

/** Thin wrapper around `duckyai orchestrator *` CLI commands. */
export class OrchestratorBridge {
  constructor(private vaultPath: string) {}

  start(): Promise<OrchestratorStatus> {
    return this.exec(["orchestrator", "start", "--json-output"]).then(
      (json) => json.vaults?.[0] ?? { running: false },
    );
  }

  stop(): Promise<OrchestratorStatus> {
    return this.exec(["orchestrator", "stop", "--json-output"]).then(
      (json) => json.vaults?.[0] ?? { running: false },
    );
  }

  status(): Promise<OrchestratorStatus> {
    return this.exec(["orchestrator", "status", "--json-output"]).then(
      (json) => json.vaults?.[0] ?? { running: false },
    );
  }

  listAgents(): Promise<AgentInfo[]> {
    return this.exec(["orchestrator", "list-agents", "--json-output"]).then(
      (json) => json.vaults?.[0]?.agents ?? [],
    );
  }

  triggerAgent(abbr: string, opts?: Record<string, unknown>): Promise<string> {
    const args = ["orchestrator", "trigger", abbr];
    if (opts?.file) args.push("--file", String(opts.file));
    if (opts?.lookback) args.push("--lookback", String(opts.lookback));
    return this.exec(args).then((json) => json.message ?? JSON.stringify(json));
  }

  private exec(args: string[]): Promise<Record<string, any>> {
    const cmd = `duckyai ${args.map(a => a.includes(" ") ? `"${a}"` : a).join(" ")}`;
    return new Promise((resolve, reject) => {
      exec(
        cmd,
        { cwd: this.vaultPath, timeout: 30_000 },
        (err, stdout, stderr) => {
          if (err) {
            reject(new Error(`${cmd} failed: ${stderr || err.message}`));
            return;
          }
          try {
            resolve(JSON.parse(stdout));
          } catch {
            // Non-JSON output is fine for some commands
            resolve({});
          }
        },
      );
    });
  }
}
