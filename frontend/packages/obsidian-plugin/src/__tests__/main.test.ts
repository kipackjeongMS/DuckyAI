import { describe, it, expect, vi, beforeEach } from "vitest";
import { Notice } from "obsidian";
import DuckyAIPlugin from "../main";

// Spy on Notice constructor
const NoticeSpy = vi.fn();

describe("DuckyAIPlugin editor-menu", () => {
  let plugin: DuckyAIPlugin;
  let editorMenuHandler: (menu: any, editor: any, view: any) => void;
  let mockTriggerAgent: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();

    mockTriggerAgent = vi.fn().mockResolvedValue(undefined);

    // Build a plugin instance with mocked internals
    plugin = Object.create(DuckyAIPlugin.prototype);
    (plugin as any).addRibbonIcon = vi.fn();
    (plugin as any).addCommand = vi.fn();
    (plugin as any).registerView = vi.fn();
    (plugin as any).registerEvent = vi.fn();
    (plugin as any).registerMarkdownCodeBlockProcessor = vi.fn();

    // Capture workspace.on calls to extract the editor-menu handler
    const onSpy = vi.fn();
    (plugin as any).app = {
      workspace: {
        on: onSpy,
        getLeavesOfType: vi.fn(() => []),
        getRightLeaf: vi.fn(() => ({
          setViewState: vi.fn().mockResolvedValue(undefined),
        })),
        revealLeaf: vi.fn(),
        detachLeavesOfType: vi.fn(),
      },
      vault: {
        adapter: { basePath: "C:\\test\\vault" },
      },
    };

    const mockApi = {
      orchestrator: {
        status: vi.fn().mockResolvedValue({ running: true }),
        triggerAgent: mockTriggerAgent,
        start: vi.fn(),
        stop: vi.fn(),
        listAgents: vi.fn().mockResolvedValue([]),
      },
      vault: { callTool: vi.fn() },
      window: { minimize: vi.fn(), maximize: vi.fn(), close: vi.fn() },
      chat: { send: vi.fn() },
      onNotification: vi.fn(),
    };

    // Inject the mock api before onload tries to use bridge
    (plugin as any).api = mockApi;

    // Override onload to skip createObsidianBridge and checkDaemonHealth,
    // but still register the editor-menu event
    (plugin as any).checkDaemonHealth = vi.fn();

    // We need the real onload logic but with our mock api.
    // The bridge creation in onload assigns this.api — we re-assign after.
    plugin.onload();
    (plugin as any).api = mockApi;

    // Extract the editor-menu handler from workspace.on calls
    const menuCall = onSpy.mock.calls.find(
      (c: any[]) => c[0] === "editor-menu",
    );
    editorMenuHandler = menuCall?.[1];
  });

  function createMockEditor(selection = ""): any {
    return { getSelection: vi.fn(() => selection) };
  }

  function createMockView(filePath: string | null): any {
    return { file: filePath ? { path: filePath } : null };
  }

  function createMockMenu(): any {
    const menuItem = {
      setTitle: vi.fn().mockReturnThis(),
      setIcon: vi.fn().mockReturnThis(),
      onClick: vi.fn().mockReturnThis(),
    };
    return {
      addItem: vi.fn((cb: (item: any) => void) => {
        cb(menuItem);
      }),
      _menuItem: menuItem,
    };
  }

  it("registers an editor-menu event handler on load", () => {
    expect((plugin as any).app.workspace.on).toHaveBeenCalledWith(
      "editor-menu",
      expect.any(Function),
    );
    expect(editorMenuHandler).toBeDefined();
  });

  it("adds 'Plan this task' menu item with brain icon", () => {
    const menu = createMockMenu();
    const editor = createMockEditor();
    const view = createMockView("01-Work/Tasks/some-task.md");

    editorMenuHandler(menu, editor, view);

    expect(menu.addItem).toHaveBeenCalled();
    expect(menu._menuItem.setTitle).toHaveBeenCalledWith("Plan this task");
    expect(menu._menuItem.setIcon).toHaveBeenCalledWith("brain");
  });

  describe("onClick behavior", () => {
    async function triggerMenuClick(
      filePath: string | null,
      selection = "",
    ) {
      const menu = createMockMenu();
      const editor = createMockEditor(selection);
      const view = createMockView(filePath);

      editorMenuHandler(menu, editor, view);

      const onClickCb = menu._menuItem.onClick.mock.calls[0][0];
      await onClickCb();
    }

    it("triggers TP agent with task-file mode for files in 01-Work/Tasks/", async () => {
      await triggerMenuClick("01-Work/Tasks/Fix deployment timeout.md");

      expect(mockTriggerAgent).toHaveBeenCalledWith("TP", {
        file: "01-Work/Tasks/Fix deployment timeout.md",
        mode: "task-file",
        selection_mode: false,
        selection: null,
      });
    });

    it("triggers TP agent with daily-note mode and selection", async () => {
      await triggerMenuClick(
        "04-Periodic/Daily/2026-04-09.md",
        "- [ ] Fix deployment timeout",
      );

      expect(mockTriggerAgent).toHaveBeenCalledWith("TP", {
        file: "04-Periodic/Daily/2026-04-09.md",
        mode: "daily-note",
        selection_mode: true,
        selection: "- [ ] Fix deployment timeout",
      });
    });

    it("triggers TP agent with daily-note mode without selection", async () => {
      await triggerMenuClick("04-Periodic/Daily/2026-04-09.md", "");

      expect(mockTriggerAgent).toHaveBeenCalledWith("TP", {
        file: "04-Periodic/Daily/2026-04-09.md",
        mode: "daily-note",
        selection_mode: false,
        selection: null,
      });
    });

    it("treats whitespace-only selection as no selection", async () => {
      await triggerMenuClick("04-Periodic/Daily/2026-04-09.md", "   \n  ");

      expect(mockTriggerAgent).toHaveBeenCalledWith("TP", {
        file: "04-Periodic/Daily/2026-04-09.md",
        mode: "daily-note",
        selection_mode: false,
        selection: null,
      });
    });

    it("does not trigger for files outside Tasks/ and Daily/", async () => {
      await triggerMenuClick("03-Knowledge/Topics/Azure.md");

      expect(mockTriggerAgent).not.toHaveBeenCalled();
    });

    it("does not trigger when view.file is null", async () => {
      await triggerMenuClick(null);

      expect(mockTriggerAgent).not.toHaveBeenCalled();
    });
  });
});

describe("DuckyAIPlugin duckyai-button code block", () => {
  let plugin: DuckyAIPlugin;
  let blockProcessor: (source: string, el: HTMLElement, ctx: any) => void;
  let mockTriggerAgent: ReturnType<typeof vi.fn>;
  let mockCallTool: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();

    mockTriggerAgent = vi.fn().mockResolvedValue(undefined);
    mockCallTool = vi.fn().mockResolvedValue("OK");

    plugin = Object.create(DuckyAIPlugin.prototype);
    (plugin as any).addRibbonIcon = vi.fn();
    (plugin as any).addCommand = vi.fn();
    (plugin as any).registerView = vi.fn();
    (plugin as any).registerEvent = vi.fn();
    (plugin as any).registerMarkdownCodeBlockProcessor = vi.fn();

    const onSpy = vi.fn();
    (plugin as any).app = {
      workspace: {
        on: onSpy,
        getLeavesOfType: vi.fn(() => []),
        getRightLeaf: vi.fn(() => ({
          setViewState: vi.fn().mockResolvedValue(undefined),
        })),
        revealLeaf: vi.fn(),
        detachLeavesOfType: vi.fn(),
      },
      vault: {
        adapter: { basePath: "C:\\test\\vault" },
        getAbstractFileByPath: vi.fn(() => null),
        read: vi.fn().mockResolvedValue(""),
        modify: vi.fn().mockResolvedValue(undefined),
      },
    };

    const mockApi = {
      orchestrator: {
        status: vi.fn().mockResolvedValue({ running: true }),
        triggerAgent: mockTriggerAgent,
        start: vi.fn(),
        stop: vi.fn(),
        listAgents: vi.fn().mockResolvedValue([]),
      },
      vault: { callTool: mockCallTool },
      window: { minimize: vi.fn(), maximize: vi.fn(), close: vi.fn() },
      chat: { send: vi.fn() },
      onNotification: vi.fn(),
    };

    (plugin as any).api = mockApi;
    (plugin as any).checkDaemonHealth = vi.fn();

    plugin.onload();
    (plugin as any).api = mockApi;

    // Extract the code block processor
    const processorCalls = (plugin as any).registerMarkdownCodeBlockProcessor.mock.calls;
    const duckyaiCall = processorCalls.find(
      (c: any[]) => c[0] === "duckyai-button",
    );
    blockProcessor = duckyaiCall?.[1];
  });

  it("registers a duckyai-button code block processor", () => {
    expect(
      (plugin as any).registerMarkdownCodeBlockProcessor,
    ).toHaveBeenCalledWith("duckyai-button", expect.any(Function));
    expect(blockProcessor).toBeDefined();
  });

  it("renders a button with the specified label", () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Review PR 1234.md" };

    blockProcessor("label: Review this PR\nagent: PR", el, ctx);

    const btn = el.querySelector("button");
    expect(btn).not.toBeNull();
    expect(btn!.textContent).toBe("Review this PR");
  });

  it("only renders button for files in PRReviews/", () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Some PR.md" };

    blockProcessor("label: Review\nagent: PR", el, ctx);

    expect(el.querySelector("button")).not.toBeNull();
  });

  it("shows restriction message for files outside PRReviews/", () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/Tasks/Some task.md" };

    blockProcessor("label: Review\nagent: PR", el, ctx);

    expect(el.querySelector("button")).toBeNull();
    expect(el.textContent).toContain("only available");
  });

  it("triggers the specified agent on click", async () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Review PR 1234.md" };

    blockProcessor("label: Review this PR\nagent: PR", el, ctx);

    const btn = el.querySelector("button")!;
    btn.click();
    // Wait for async handler
    await new Promise((r) => setTimeout(r, 10));

    expect(mockTriggerAgent).toHaveBeenCalledWith("PR", {
      file: "01-Work/PRReviews/Review PR 1234.md",
    });
  });

  it("uses default label if not specified", () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Some PR.md" };

    blockProcessor("agent: PR", el, ctx);

    const btn = el.querySelector("button");
    expect(btn).not.toBeNull();
    expect(btn!.textContent).toBe("Run PR");
  });

  it("renders multiple buttons from --- separated blocks", () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Review PR 1234.md" };

    blockProcessor(
      "label: Review this PR\nagent: PR\n---\nlabel: Confirm Done\naction: set-status-done",
      el,
      ctx,
    );

    const buttons = el.querySelectorAll("button");
    expect(buttons.length).toBe(2);
    expect(buttons[0].textContent).toBe("Review this PR");
    expect(buttons[1].textContent).toBe("Confirm Done");
  });

  it("set-status-done modifies file frontmatter directly", async () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Review PR 1234.md" };

    const mockFile = { path: "01-Work/PRReviews/Review PR 1234.md" };
    (plugin as any).app.vault.getAbstractFileByPath = vi.fn(() => mockFile);
    (plugin as any).app.vault.read = vi.fn().mockResolvedValue(
      "---\nstatus: todo\npriority: P2\n---\n# Content",
    );
    (plugin as any).app.vault.modify = vi.fn().mockResolvedValue(undefined);

    blockProcessor("label: Confirm Done\naction: set-status-done", el, ctx);
    // Wait for async status read
    await new Promise((r) => setTimeout(r, 10));

    const btn = el.querySelector("button")!;
    // Button should still show "Confirm Done" since status is todo
    expect(btn.textContent).toBe("Confirm Done");
    expect(btn.disabled).toBe(false);

    btn.click();
    await new Promise((r) => setTimeout(r, 10));

    expect((plugin as any).app.vault.modify).toHaveBeenCalledWith(
      mockFile,
      "---\nstatus: done\npriority: P2\n---\n# Content",
    );
    expect(btn.textContent).toBe("✓ Done");
  });

  it("shows ✓ Done and disables button when status is already done", async () => {
    const el = document.createElement("div");
    const ctx = { sourcePath: "01-Work/PRReviews/Review PR 1234.md" };

    const mockFile = { path: "01-Work/PRReviews/Review PR 1234.md" };
    (plugin as any).app.vault.getAbstractFileByPath = vi.fn(() => mockFile);
    (plugin as any).app.vault.read = vi.fn().mockResolvedValue(
      "---\nstatus: done\npriority: P2\n---\n# Content",
    );

    blockProcessor("label: Confirm Done\naction: set-status-done", el, ctx);
    // Wait for async status read
    await new Promise((r) => setTimeout(r, 10));

    const btn = el.querySelector("button")!;
    expect(btn.textContent).toBe("✓ Done");
    expect(btn.disabled).toBe(true);
  });
});
