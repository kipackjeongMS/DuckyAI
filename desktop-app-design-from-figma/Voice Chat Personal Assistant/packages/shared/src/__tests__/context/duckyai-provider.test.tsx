import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { DuckyAIProvider, useDuckyAI } from "../../context/duckyai-provider";
import { createMockApi } from "../mock-api";

describe("DuckyAIProvider", () => {
  it("provides the api to child components", () => {
    const mockApi = createMockApi();
    let captured: ReturnType<typeof useDuckyAI> | null = null;

    function Consumer() {
      captured = useDuckyAI();
      return <div data-testid="consumer">ok</div>;
    }

    render(
      <DuckyAIProvider api={mockApi}>
        <Consumer />
      </DuckyAIProvider>
    );

    expect(screen.getByTestId("consumer")).toBeInTheDocument();
    expect(captured).toBe(mockApi);
  });

  it("throws when useDuckyAI is called outside the provider", () => {
    function BadConsumer() {
      useDuckyAI();
      return <div>bad</div>;
    }

    // Suppress console.error output for the expected error
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<BadConsumer />)).toThrow(
      "useDuckyAI must be used within a <DuckyAIProvider>"
    );
    spy.mockRestore();
  });

  it("swaps api when a new instance is provided", () => {
    const api1 = createMockApi();
    const api2 = createMockApi();
    const captured: Array<ReturnType<typeof useDuckyAI>> = [];

    function Consumer() {
      captured.push(useDuckyAI());
      return <div>ok</div>;
    }

    const { rerender } = render(
      <DuckyAIProvider api={api1}>
        <Consumer />
      </DuckyAIProvider>
    );

    rerender(
      <DuckyAIProvider api={api2}>
        <Consumer />
      </DuckyAIProvider>
    );

    expect(captured[0]).toBe(api1);
    expect(captured[1]).toBe(api2);
  });
});
