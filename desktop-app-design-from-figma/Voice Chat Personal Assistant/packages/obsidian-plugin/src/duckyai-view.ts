import { ItemView, SuggestModal, Notice, type WorkspaceLeaf, type App } from "obsidian";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { DuckyAIProvider, DuckyAIApp } from "@duckyai/shared";
import type { DuckyAIApi } from "@duckyai/shared";
import { exec } from "child_process";
import { join } from "path";

export const DUCKYAI_VIEW_TYPE = "duckyai-panel";

interface EditorOption {
  label: string;
  command: string;
}

function findEditorOptions(): EditorOption[] {
  if (process.platform === "win32") {
    const localApps = process.env.LOCALAPPDATA || "";
    const programFiles = process.env.ProgramFiles || "C:\\Program Files";
    return [
      {
        label: "VS Code Insiders",
        command: join(localApps, "Programs", "Microsoft VS Code Insiders", "bin", "code-insiders.cmd"),
      },
      {
        label: "VS Code",
        command: join(programFiles, "Microsoft VS Code", "bin", "code.cmd"),
      },
    ];
  }
  // macOS / Linux — CLI commands are typically on PATH
  return [
    { label: "VS Code Insiders", command: "code-insiders" },
    { label: "VS Code", command: "code" },
  ];
}

class EditorPickerModal extends SuggestModal<EditorOption> {
  private onChoose: (option: EditorOption) => void;

  constructor(app: App, onChoose: (option: EditorOption) => void) {
    super(app);
    this.onChoose = onChoose;
    this.setPlaceholder("Choose editor to open workspace...");
  }

  getSuggestions(): EditorOption[] {
    return findEditorOptions();
  }

  renderSuggestion(option: EditorOption, el: HTMLElement): void {
    el.createEl("div", { text: option.label });
    el.createEl("small", { text: `Opens with: ${option.command}` });
  }

  onChooseSuggestion(option: EditorOption): void {
    this.onChoose(option);
  }
}

export class DuckyAIView extends ItemView {
  private root: Root | null = null;

  constructor(
    leaf: WorkspaceLeaf,
    private api: DuckyAIApi,
  ) {
    super(leaf);
  }

  getViewType(): string {
    return DUCKYAI_VIEW_TYPE;
  }

  getDisplayText(): string {
    return "DuckyAI";
  }

  getIcon(): string {
    return "bot";
  }

  private openWorkspace(): void {
    const vaultPath = (this.app.vault.adapter as any).basePath as string;
    const vaultName = this.app.vault.getName();
    const servicesPath = join(vaultPath, "..", `${vaultName}-Services`);

    new EditorPickerModal(this.app, (option) => {
      exec(`"${option.command}" "${servicesPath}"`, { shell: "cmd.exe" }, (err) => {
        if (err) {
          new Notice(`Failed to open ${option.label}: ${err.message}`);
        } else {
          new Notice(`Opened ${servicesPath} in ${option.label}`);
        }
      });
    }).open();
  }

  async onOpen(): Promise<void> {
    const container = this.containerEl.children[1];
    container.empty();

    // Add a wrapper div for the React app
    const mountPoint = container.createDiv({ cls: "duckyai-root" });
    mountPoint.style.height = "100%";
    mountPoint.style.overflow = "hidden";

    this.root = createRoot(mountPoint);
    this.root.render(
      createElement(
        DuckyAIProvider,
        { api: this.api },
        createElement(DuckyAIApp, {
          draggableTitleBar: false,
          fullscreen: false,
          sidebarOnly: true,
          onOpenWorkspace: () => this.openWorkspace(),
        }),
      ),
    );
  }

  async onClose(): Promise<void> {
    this.root?.unmount();
    this.root = null;
  }
}
