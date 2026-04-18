import { createRoot } from "react-dom/client";
import { DuckyAIApp } from "@duckyai/shared";
import "../packages/shared/src/styles/index.css";

createRoot(document.getElementById("root")!).render(<DuckyAIApp />);
  