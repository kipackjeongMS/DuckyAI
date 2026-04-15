/**
 * Mock of the Obsidian module for testing.
 * Only includes the APIs actually used by the DuckyAI plugin.
 */
import { vi } from "vitest";

export class Plugin {
  app: any;
  manifest: any;
  constructor(app: any, manifest: any) {
    this.app = app;
    this.manifest = manifest;
  }
  addRibbonIcon = vi.fn(() => ({ addClass: vi.fn() }));
  addCommand = vi.fn();
  addStatusBarItem = vi.fn(() => ({
    setText: vi.fn(),
    addClass: vi.fn(),
  }));
  registerView = vi.fn();
  registerInterval = vi.fn();
  registerEvent = vi.fn();
  registerMarkdownCodeBlockProcessor = vi.fn();
}

export class ItemView {
  app: any;
  leaf: any;
  contentEl: HTMLElement;
  containerEl: HTMLElement;
  icon = "";
  constructor(leaf: any) {
    this.leaf = leaf;
    this.app = leaf?.app;
    this.contentEl = document.createElement("div");
    this.containerEl = document.createElement("div");
    this.containerEl.appendChild(this.contentEl);
  }
  getViewType() {
    return "";
  }
  getDisplayText() {
    return "";
  }
  onOpen() {
    return Promise.resolve();
  }
  onClose() {
    return Promise.resolve();
  }
}

export const requestUrl = vi.fn();

export class Notice {
  constructor(public message: string, public duration?: number) {}
}

export class SuggestModal {
  app: any;
  constructor(app: any) {
    this.app = app;
  }
  open = vi.fn();
  close = vi.fn();
  getSuggestions = vi.fn(() => []);
  renderSuggestion = vi.fn();
  onChooseSuggestion = vi.fn();
  setPlaceholder = vi.fn();
}
