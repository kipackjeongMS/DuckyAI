import { exec } from "node:child_process";
/** Thin wrapper around `duckyai orchestrator *` CLI commands. */
export class OrchestratorBridge {
    vaultPath;
    constructor(vaultPath) {
        this.vaultPath = vaultPath;
    }
    start() {
        return this.exec(["orchestrator", "start", "--json-output"]).then((json) => json.vaults?.[0] ?? { running: false });
    }
    stop() {
        return this.exec(["orchestrator", "stop", "--json-output"]).then((json) => json.vaults?.[0] ?? { running: false });
    }
    status() {
        return this.exec(["orchestrator", "status", "--json-output"]).then((json) => json.vaults?.[0] ?? { running: false });
    }
    listAgents() {
        return this.exec(["orchestrator", "list-agents", "--json-output"]).then((json) => json.vaults?.[0]?.agents ?? []);
    }
    triggerAgent(abbr, opts) {
        const args = ["orchestrator", "trigger", abbr];
        if (opts?.file)
            args.push("--file", String(opts.file));
        if (opts?.lookback)
            args.push("--lookback", String(opts.lookback));
        return this.exec(args).then((json) => json.message ?? JSON.stringify(json));
    }
    exec(args) {
        const cmd = `duckyai ${args.map(a => a.includes(" ") ? `"${a}"` : a).join(" ")}`;
        return new Promise((resolve, reject) => {
            exec(cmd, { cwd: this.vaultPath, timeout: 30_000 }, (err, stdout, stderr) => {
                if (err) {
                    reject(new Error(`${cmd} failed: ${stderr || err.message}`));
                    return;
                }
                try {
                    resolve(JSON.parse(stdout));
                }
                catch {
                    // Non-JSON output is fine for some commands
                    resolve({});
                }
            });
        });
    }
}
