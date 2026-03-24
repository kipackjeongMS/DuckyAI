import { spawn } from "node:child_process";
import path from "node:path";
import { createInterface } from "node:readline";
/**
 * MCP client that spawns the vault MCP server as a child process
 * and communicates via JSON-RPC over stdio.
 */
export class McpClient {
    process;
    requestId = 0;
    pending = new Map();
    constructor(vaultPath) {
        const serverPath = path.join(vaultPath, "cli", "mcp-server", "dist", "index.js");
        this.process = spawn("node", [serverPath], {
            cwd: vaultPath,
            env: { ...process.env, DUCKYAI_VAULT_ROOT: vaultPath },
            stdio: ["pipe", "pipe", "pipe"],
        });
        const rl = createInterface({ input: this.process.stdout });
        rl.on("line", (line) => this.handleLine(line));
        this.process.stderr?.on("data", (chunk) => {
            console.error("[mcp-server]", chunk.toString());
        });
        this.process.on("exit", (code) => {
            console.error(`MCP server exited with code ${code}`);
            // Reject all pending requests
            for (const [, { reject }] of this.pending) {
                reject(new Error("MCP server exited"));
            }
            this.pending.clear();
        });
    }
    async callTool(name, args = {}) {
        const id = ++this.requestId;
        const request = {
            jsonrpc: "2.0",
            id,
            method: "tools/call",
            params: { name, arguments: args },
        };
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.process.stdin.write(JSON.stringify(request) + "\n");
        });
    }
    close() {
        this.process.kill();
    }
    handleLine(line) {
        if (!line.trim())
            return;
        try {
            const msg = JSON.parse(line);
            if (msg.id != null && this.pending.has(msg.id)) {
                const { resolve, reject } = this.pending.get(msg.id);
                this.pending.delete(msg.id);
                if (msg.error) {
                    reject(new Error(msg.error.message ?? "MCP error"));
                }
                else {
                    // Extract text content from MCP response
                    const text = msg.result?.content
                        ?.map((c) => c.text ?? "")
                        .join("\n") ?? JSON.stringify(msg.result);
                    resolve(text);
                }
            }
        }
        catch {
            // Ignore non-JSON lines (e.g., log output)
        }
    }
}
