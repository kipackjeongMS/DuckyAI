import { CopilotClient, approveAll, defineTool } from "@github/copilot-sdk";
import { exec } from "node:child_process";
import { z } from "zod";
/** Resolve the copilot CLI path via shell (handles .cmd/.bat on Windows). */
function findCopilotPath() {
    return new Promise((resolve) => {
        exec("where copilot", (err, stdout) => {
            if (!err && stdout.trim()) {
                // Take the first result, prefer .exe over .bat
                const paths = stdout.trim().split("\n").map(p => p.trim());
                const exe = paths.find(p => p.endsWith(".exe")) ?? paths[0];
                resolve(exe);
            }
            else {
                resolve("copilot"); // fallback to PATH
            }
        });
    });
}
const SYSTEM_MESSAGE = `You are DuckyAI, a personal knowledge management assistant.
You help the user manage their Obsidian vault: daily notes, tasks, meetings, PR reviews, and more.
When the user asks about their work, tasks, schedule, or vault content, use the available vault tools.
Be concise and helpful. Respond in a friendly, professional tone.`;
/** How long to wait for a single Copilot response (ms). */
const SEND_TIMEOUT = 180_000; // 3 minutes — accounts for cold-start
/**
 * Chat engine powered by GitHub Copilot SDK.
 * Wraps a CopilotClient with a persistent session to avoid cold-start costs per message.
 */
export class ChatEngine {
    mcpClient;
    orchestrator;
    vaultPath;
    client = null;
    session = null;
    started = false;
    sendLock = Promise.resolve(); // serializes concurrent sends
    constructor(mcpClient, orchestrator, vaultPath) {
        this.mcpClient = mcpClient;
        this.orchestrator = orchestrator;
        this.vaultPath = vaultPath;
    }
    /** Build DuckyAI vault + orchestrator tools for the Copilot SDK session. */
    buildTools() {
        const mcp = this.mcpClient;
        const orch = this.orchestrator;
        // Helper: wrap an MCP tool call so the LLM gets back a string result
        const mcpTool = (name, description, parameters, mapArgs) => defineTool(name, {
            description,
            parameters,
            skipPermission: true,
            handler: async (args) => {
                const a = mapArgs ? mapArgs(args) : args;
                console.log(`[tool] ${name}`, JSON.stringify(a).slice(0, 120));
                try {
                    const result = await mcp.callTool(name, a);
                    return result;
                }
                catch (err) {
                    return { textResultForLlm: `Error: ${err?.message}`, resultType: "failure" };
                }
            },
        });
        return [
            // ── Vault tools (MCP) ──────────────────────────────────────
            mcpTool("getCurrentDate", "Get the current date and time", z.object({})),
            mcpTool("prepareDailyNote", "Create or get today's daily note", z.object({})),
            mcpTool("createTask", "Create a new task file in the vault", z.object({
                title: z.string().describe("Task title"),
                description: z.string().optional().describe("Task description"),
                priority: z.enum(["P0", "P1", "P2", "P3"]).optional().describe("Priority level"),
                project: z.string().optional().describe("Related project name"),
                due: z.string().optional().describe("Due date YYYY-MM-DD"),
            })),
            mcpTool("logTask", "Add a task entry to today's daily note Tasks section", z.object({
                title: z.string().describe("Task title (must match an existing task file)"),
            })),
            mcpTool("updateTaskStatus", "Update status of an existing task", z.object({
                title: z.string().describe("Task title"),
                status: z.enum(["todo", "in-progress", "blocked", "done", "cancelled"]).describe("New status"),
            })),
            mcpTool("archiveTask", "Move a completed/cancelled task to archive", z.object({
                title: z.string().describe("Task title to archive"),
            })),
            mcpTool("logAction", "Log a completed action to today's daily note", z.object({
                action: z.string().describe("Description of the action completed"),
            })),
            mcpTool("logPRReview", "Log a PR review (pending or completed)", z.object({
                title: z.string().describe("PR title"),
                url: z.string().optional().describe("PR URL"),
                author: z.string().optional().describe("PR author name"),
                action: z.enum(["todo", "reviewed", "commented"]).describe("Review action"),
                description: z.string().optional().describe("Brief description"),
            })),
            mcpTool("createMeeting", "Create meeting notes", z.object({
                title: z.string().describe("Meeting title"),
                date: z.string().optional().describe("Meeting date YYYY-MM-DD"),
                attendees: z.array(z.string()).optional().describe("List of attendee names"),
            })),
            mcpTool("create1on1", "Create 1:1 meeting notes", z.object({
                person: z.string().describe("Person name for the 1:1"),
                date: z.string().optional().describe("Date YYYY-MM-DD"),
            })),
            mcpTool("triageInbox", "Triage items in the 00-Inbox folder", z.object({})),
            mcpTool("enrichNote", "Enrich a note with links and structure", z.object({
                file: z.string().describe("Path to the note file to enrich"),
            })),
            mcpTool("updateTopicIndex", "Update the topic index for a given topic", z.object({
                topic: z.string().describe("Topic name to update index for"),
            })),
            mcpTool("generateRoundup", "Generate the daily roundup", z.object({})),
            mcpTool("prepareWeeklyReview", "Create the weekly review note", z.object({})),
            mcpTool("appendTeamsChatHighlights", "Append Teams chat highlights to daily note", z.object({
                highlights: z.string().describe("Chat highlights markdown content"),
            })),
            // ── Orchestrator tools ─────────────────────────────────────
            defineTool("orchestratorStatus", {
                description: "Check if the DuckyAI orchestrator daemon is running",
                parameters: z.object({}),
                skipPermission: true,
                handler: async () => {
                    try {
                        const status = await orch.status();
                        return JSON.stringify(status);
                    }
                    catch (err) {
                        return { textResultForLlm: `Error: ${err?.message}`, resultType: "failure" };
                    }
                },
            }),
            defineTool("startOrchestrator", {
                description: "Start the DuckyAI orchestrator daemon",
                parameters: z.object({}),
                skipPermission: true,
                handler: async () => {
                    try {
                        const status = await orch.start();
                        return JSON.stringify(status);
                    }
                    catch (err) {
                        return { textResultForLlm: `Error: ${err?.message}`, resultType: "failure" };
                    }
                },
            }),
            defineTool("stopOrchestrator", {
                description: "Stop the DuckyAI orchestrator daemon",
                parameters: z.object({}),
                skipPermission: true,
                handler: async () => {
                    try {
                        const status = await orch.stop();
                        return JSON.stringify(status);
                    }
                    catch (err) {
                        return { textResultForLlm: `Error: ${err?.message}`, resultType: "failure" };
                    }
                },
            }),
            defineTool("listAgents", {
                description: "List all available DuckyAI orchestrator agents with their abbreviations and schedules",
                parameters: z.object({}),
                skipPermission: true,
                handler: async () => {
                    try {
                        const agents = await orch.listAgents();
                        return JSON.stringify(agents);
                    }
                    catch (err) {
                        return { textResultForLlm: `Error: ${err?.message}`, resultType: "failure" };
                    }
                },
            }),
            defineTool("triggerAgent", {
                description: "Trigger a DuckyAI agent by abbreviation (e.g. TCS, TMS, GDR, EIC, TIU, TM, EDM)",
                parameters: z.object({
                    agent: z.string().describe("Agent abbreviation (e.g. TCS, GDR, EIC)"),
                    file: z.string().optional().describe("Optional file path for file-triggered agents"),
                    lookback: z.string().optional().describe("Optional lookback period (e.g. '2h', '1d')"),
                }),
                skipPermission: true,
                handler: async (args) => {
                    try {
                        console.log(`[tool] triggerAgent: ${args.agent}`);
                        const result = await orch.triggerAgent(args.agent, {
                            file: args.file,
                            lookback: args.lookback,
                        });
                        return result || `Agent ${args.agent} triggered successfully.`;
                    }
                    catch (err) {
                        return { textResultForLlm: `Error: ${err?.message}`, resultType: "failure" };
                    }
                },
            }),
        ];
    }
    async start() {
        if (this.started)
            return;
        const cliPath = await findCopilotPath();
        console.log("[chat-engine] Starting with cwd:", this.vaultPath, "cli:", cliPath);
        this.client = new CopilotClient({
            autoStart: true,
            logLevel: "info",
            cwd: this.vaultPath,
            cliPath,
            useStdio: false,
        });
        await this.client.start();
        this.started = true;
        console.log("[chat-engine] Copilot client started");
    }
    async stop() {
        if (this.session) {
            try {
                await this.session.disconnect();
            }
            catch { /* ignore */ }
            this.session = null;
        }
        if (this.client) {
            await this.client.stop();
            this.client = null;
            this.started = false;
            console.log("[chat-engine] Copilot client stopped");
        }
    }
    /** Discard session so the next call creates a fresh one. */
    async discardSession() {
        if (!this.session)
            return;
        console.log("[chat-engine] Discarding session");
        try {
            await this.session.disconnect();
        }
        catch { /* ignore */ }
        this.session = null;
    }
    /** Ensure a live session exists, creating one if needed. */
    async ensureSession() {
        if (this.session)
            return this.session;
        if (!this.client || !this.started) {
            // Try to auto-start if not started yet
            await this.start();
        }
        console.log("[chat-engine] Creating new session...");
        const tools = this.buildTools();
        console.log(`[chat-engine] Registering ${tools.length} tools`);
        this.session = await this.client.createSession({
            model: "claude-sonnet-4",
            streaming: false,
            onPermissionRequest: approveAll,
            systemMessage: { content: SYSTEM_MESSAGE },
            tools,
        });
        console.log("[chat-engine] Session created");
        return this.session;
    }
    async sendMessage(userText) {
        // Serialize concurrent sends to prevent duplicate sessions / race conditions
        let resolve;
        const prev = this.sendLock;
        this.sendLock = new Promise((r) => { resolve = r; });
        try {
            await prev; // wait for any in-flight send to finish
            return await this.doSend(userText);
        }
        finally {
            resolve();
        }
    }
    async doSend(userText, isRetry = false) {
        let session;
        try {
            session = await this.ensureSession();
        }
        catch (err) {
            console.error("[chat-engine] ensureSession failed:", err?.message);
            // If session creation fails, reset client and retry once
            if (!isRetry) {
                console.log("[chat-engine] Restarting client for retry...");
                await this.stop();
                return this.doSend(userText, true);
            }
            throw err;
        }
        try {
            console.log("[chat-engine] Sending:", userText.slice(0, 80));
            const result = await session.sendAndWait({ prompt: userText }, SEND_TIMEOUT);
            return result?.data?.content ?? "No response received.";
        }
        catch (err) {
            const msg = err?.message ?? String(err);
            console.error("[chat-engine] sendAndWait error:", msg);
            await this.discardSession();
            // On first attempt, retry with a fresh session (handles stale/sleep scenarios)
            if (!isRetry) {
                console.log("[chat-engine] Retrying with fresh session...");
                return this.doSend(userText, true);
            }
            throw err;
        }
    }
}
