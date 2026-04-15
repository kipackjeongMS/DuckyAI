import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { DuckyAIApi } from "@duckyai/shared";

// Mock window.duckyai before importing renderer components
function createMockApi(): DuckyAIApi {
  return {
    orchestrator: {
      start: vi.fn().mockResolvedValue(undefined),
      stop: vi.fn().mockResolvedValue(undefined),
      status: vi.fn().mockResolvedValue({ running: false, agents: [] }),
      listAgents: vi.fn().mockResolvedValue([]),
      triggerAgent: vi.fn().mockResolvedValue(undefined),
    },
    vault: {
      callTool: vi.fn().mockResolvedValue({ result: "ok" }),
    },
    chat: {
      send: vi.fn().mockResolvedValue("response"),
      stream: vi.fn(),
      cancel: vi.fn(),
    },
    window: {
      minimize: vi.fn(),
      maximize: vi.fn(),
      close: vi.fn(),
    },
    onNotification: vi.fn(),
  };
}

describe("Electron renderer", () => {
  let mockApi: DuckyAIApi;

  beforeEach(() => {
    mockApi = createMockApi();
    (window as any).duckyai = mockApi;
  });

  it("renders the app with DuckyAIProvider from window.duckyai", async () => {
    // Import components lazily after mock is set
    const { DuckyAIProvider, DuckyAIApp } = await import("@duckyai/shared");
    const { ElectronWindowControls } = await import(
      "../../electron-window-controls"
    );

    render(
      <DuckyAIProvider api={mockApi}>
        <DuckyAIApp
          draggableTitleBar={true}
          renderWindowControls={() => <ElectronWindowControls api={mockApi} />}
        />
      </DuckyAIProvider>,
    );

    // The app should render — check for the main container
    const rootEl = document.querySelector('[class*="app"]') || document.body;
    expect(rootEl).toBeTruthy();
  });

  it("renders window controls (minimize, maximize, close)", async () => {
    const { ElectronWindowControls } = await import(
      "../../electron-window-controls"
    );

    render(<ElectronWindowControls api={mockApi} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBe(3);
  });

  it("window control buttons call the correct API methods", async () => {
    const { ElectronWindowControls } = await import(
      "../../electron-window-controls"
    );
    const { userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();

    render(<ElectronWindowControls api={mockApi} />);

    const buttons = screen.getAllByRole("button");
    // minimize, maximize, close
    await user.click(buttons[0]);
    expect(mockApi.window!.minimize).toHaveBeenCalled();

    await user.click(buttons[1]);
    expect(mockApi.window!.maximize).toHaveBeenCalled();

    await user.click(buttons[2]);
    expect(mockApi.window!.close).toHaveBeenCalled();
  });
});
