import { Notice, Plugin, type Editor, type MarkdownView, type Menu } from "obsidian";
import { DuckyAIView, DUCKYAI_VIEW_TYPE } from "./duckyai-view";
import { createObsidianBridge } from "./bridge";
import type { DuckyAIApi } from "@duckyai/shared";

export default class DuckyAIPlugin extends Plugin {
  private api!: DuckyAIApi;

  async onload(): Promise<void> {
    this.api = createObsidianBridge(this.app);

    // Non-blocking daemon health check on startup
    this.checkDaemonHealth();

    // Register the custom view
    this.registerView(DUCKYAI_VIEW_TYPE, (leaf) => {
      return new DuckyAIView(leaf, this.api);
    });

    // Ribbon icon to toggle the panel
    this.addRibbonIcon("bot", "Open DuckyAI", () => {
      this.activateView();
    });

    // Commands
    this.addCommand({
      id: "open-panel",
      name: "Open DuckyAI panel",
      callback: () => this.activateView(),
    });

    this.addCommand({
      id: "prepare-daily-note",
      name: "Prepare today's daily note",
      callback: async () => {
        try {
          await this.api.vault.callTool("prepareDailyNote");
        } catch (err) {
          console.error("[DuckyAI] Failed to prepare daily note:", err);
        }
      },
    });

    this.addCommand({
      id: "start-orchestrator",
      name: "Start orchestrator",
      callback: async () => {
        try {
          await this.api.orchestrator.start();
        } catch (err) {
          console.error("[DuckyAI] Failed to start orchestrator:", err);
        }
      },
    });

    this.addCommand({
      id: "stop-orchestrator",
      name: "Stop orchestrator",
      callback: async () => {
        try {
          await this.api.orchestrator.stop();
        } catch (err) {
          console.error("[DuckyAI] Failed to stop orchestrator:", err);
        }
      },
    });

    this.addCommand({
      id: "triage-inbox",
      name: "Triage inbox",
      callback: async () => {
        try {
          await this.api.vault.callTool("triageInbox");
        } catch (err) {
          console.error("[DuckyAI] Failed to triage inbox:", err);
        }
      },
    });

    // Right-click context menu: Plan this task
    this.registerEvent(
      this.app.workspace.on("editor-menu", (menu: Menu, editor: Editor, view: MarkdownView) => {
        menu.addItem((item) => {
          item.setTitle("Plan this task").setIcon("brain").onClick(async () => {
            const file = view.file;
            if (!file) {
              new Notice("No active file", 4000);
              return;
            }

            let mode: string;
            if (file.path.startsWith("01-Work/Tasks/")) {
              mode = "task-file";
            } else if (/^04-Periodic\/Daily\/\d{4}-\d{2}-\d{2}\.md$/.test(file.path)) {
              mode = "daily-note";
            } else {
              new Notice("Plan this task only works in task files or daily notes", 4000);
              return;
            }

            const sel = editor.getSelection().trim();
            const selectionMode = mode === "daily-note" && sel.length > 0;

            try {
              new Notice("Planning task…", 5000);
              await this.api.orchestrator.triggerAgent("TP", {
                file: file.path,
                mode,
                selection_mode: selectionMode,
                selection: selectionMode ? sel : null,
              });
              new Notice("Task planning started", 4000);
            } catch (err: any) {
              new Notice(`Failed to trigger planner: ${err.message}`, 6000);
            }
          });
        });
      }),
    );

    // Code block processor: ```duckyai-button``` renders action buttons
    // Supports multiple buttons separated by --- lines
    // Only renders for files in 01-Work/PRReviews/
    this.registerMarkdownCodeBlockProcessor(
      "duckyai-button",
      (source: string, el: HTMLElement, ctx: { sourcePath: string }) => {
        // Restrict to PRReviews folder
        if (!ctx.sourcePath.includes("PRReviews/")) {
          const span = document.createElement("span");
          span.textContent = "⚠️ This button is only available in PRReviews files";
          span.className = "duckyai-button-error";
          el.appendChild(span);
          return;
        }

        // Parse multiple button definitions separated by --- lines
        const blocks = source.split(/^-{3,}\s*$/m).map((b) => b.trim()).filter(Boolean);
        const container = document.createElement("div");
        container.className = "duckyai-button-group";
        container.style.display = "flex";
        container.style.gap = "8px";
        el.appendChild(container);

        for (const block of blocks) {
          const props = Object.fromEntries(
            block
              .split("\n")
              .map((line) => line.trim())
              .filter((line) => line.includes(":"))
              .map((line) => {
                const idx = line.indexOf(":");
                return [line.slice(0, idx).trim(), line.slice(idx + 1).trim()];
              }),
          );

          const agent = props.agent;
          const action = props.action;

          if (!agent && !action) {
            const span = document.createElement("span");
            span.textContent = "⚠️ duckyai-button: need 'agent' or 'action'";
            span.className = "duckyai-button-error";
            container.appendChild(span);
            continue;
          }

          const label = props.label || (agent ? `Run ${agent}` : action);
          const btn = document.createElement("button");
          btn.textContent = label;
          btn.className = "duckyai-action-button";
          container.appendChild(btn);

          if (action === "set-status-done") {
            // Read current status and set initial button state
            const file = this.app.vault.getAbstractFileByPath(ctx.sourcePath);
            if (file) {
              this.app.vault.read(file as any).then((content: string) => {
                const match = content.match(/^status:\s*(.+)$/m);
                const currentStatus = match?.[1]?.trim() || "todo";
                if (currentStatus === "done") {
                  btn.textContent = "✓ Done";
                  btn.className = "duckyai-action-button duckyai-status-done";
                  btn.disabled = true;
                }
              });
            }

            btn.addEventListener("click", async () => {
              btn.disabled = true;
              btn.textContent = "Updating…";
              try {
                const f = this.app.vault.getAbstractFileByPath(ctx.sourcePath);
                if (!f) throw new Error("File not found");
                const content = await this.app.vault.read(f as any);
                const updated = content.replace(
                  /^(status:\s*).+$/m,
                  "$1done",
                );
                if (updated === content) throw new Error("No status field found in frontmatter");
                await this.app.vault.modify(f as any, updated);
                btn.textContent = "✓ Done";
                btn.className = "duckyai-action-button duckyai-status-done";
                new Notice("Status updated to done", 4000);
              } catch (err: any) {
                btn.textContent = label;
                btn.disabled = false;
                new Notice(`Failed: ${err.message}`, 6000);
              }
            });
          } else if (agent) {
            btn.addEventListener("click", async () => {
              btn.disabled = true;
              btn.textContent = "Running…";
              try {
                await this.api.orchestrator.triggerAgent(agent, {
                  file: ctx.sourcePath,
                });
                btn.textContent = "✓ Triggered";
                new Notice(`${agent} agent triggered`, 4000);
              } catch (err: any) {
                btn.textContent = label;
                btn.disabled = false;
                new Notice(`Failed: ${err.message}`, 6000);
              }
            });
          }
        }
      },
    );
  }

  async onunload(): Promise<void> {
    this.app.workspace.detachLeavesOfType(DUCKYAI_VIEW_TYPE);
  }

  private async activateView(): Promise<void> {
    const existing =
      this.app.workspace.getLeavesOfType(DUCKYAI_VIEW_TYPE);

    if (existing.length > 0) {
      // Already open — focus it
      this.app.workspace.revealLeaf(existing[0]);
      return;
    }

    // Open in the right sidebar
    const leaf = this.app.workspace.getRightLeaf(false);
    if (leaf) {
      await leaf.setViewState({
        type: DUCKYAI_VIEW_TYPE,
        active: true,
      });
      this.app.workspace.revealLeaf(leaf);
    }
  }

  /**
   * Non-blocking check: verify the DuckyAI daemon is reachable.
   * Shows a notice if the daemon isn't running. Does NOT block plugin load.
   * Auth is handled by the daemon (Python) — the plugin only needs HTTP access.
   */
  private async checkDaemonHealth(): Promise<void> {
    try {
      const status = await this.api.orchestrator.status();
      console.log("[DuckyAI] Daemon connected:", status);
    } catch {
      console.warn("[DuckyAI] Daemon not reachable at startup. Features will retry on demand.");
      new Notice(
        "DuckyAI: Daemon not running. Start it with 'duckyai -o' or use the Start Orchestrator command.",
        8000,
      );
    }
  }
}
