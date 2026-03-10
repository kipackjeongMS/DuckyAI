import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const chatEl = document.getElementById("chat")!;
const micBtn = document.getElementById("mic-btn")!;
const micLabel = document.getElementById("mic-label")!;
const statusEl = document.getElementById("status")!;

let isRecording = false;

// ── Chat UI helpers ────────────────────────────────

function addMessage(text: string, type: "user" | "ai" | "system", toolTag?: string) {
  // Remove welcome message
  const welcome = chatEl.querySelector(".welcome");
  if (welcome) welcome.remove();

  const msg = document.createElement("div");
  msg.className = `message ${type}`;
  if (toolTag) {
    const tag = document.createElement("div");
    tag.className = "tool-tag";
    tag.textContent = `🔧 ${toolTag}`;
    msg.appendChild(tag);
  }
  const content = document.createElement("div");
  content.textContent = text;
  msg.appendChild(content);
  chatEl.appendChild(msg);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function setStatus(text: string, className?: string) {
  statusEl.textContent = text;
  statusEl.className = `status ${className || ""}`;
}

// ── Recording controls ─────────────────────────────

async function startRecording() {
  if (isRecording) return;
  isRecording = true;
  micBtn.classList.add("recording");
  micLabel.textContent = "Recording... release to send";
  setStatus("🔴 Recording", "recording");

  try {
    await invoke("start_recording");
  } catch (e) {
    console.error("Failed to start recording:", e);
    stopRecording();
  }
}

async function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  micBtn.classList.remove("recording");
  micLabel.textContent = "Processing...";
  setStatus("🤔 Processing");

  try {
    const transcript: string = await invoke("stop_recording_and_process");
    if (transcript) {
      addMessage(transcript, "user");
    }
  } catch (e) {
    console.error("Failed to process:", e);
    micLabel.textContent = "Hold Space or click to talk";
    setStatus("Ready");
  }
}

// ── Keyboard: Space push-to-talk ───────────────────

document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat) {
    e.preventDefault();
    startRecording();
  }
});

document.addEventListener("keyup", (e) => {
  if (e.code === "Space") {
    e.preventDefault();
    stopRecording();
  }
});

// ── Mouse: click-and-hold mic button ───────────────

micBtn.addEventListener("mousedown", () => startRecording());
micBtn.addEventListener("mouseup", () => stopRecording());
micBtn.addEventListener("mouseleave", () => { if (isRecording) stopRecording(); });

// ── Listen for backend events ──────────────────────

listen<string>("ai-response", (event) => {
  addMessage(event.payload, "ai");
  micLabel.textContent = "Hold Space or click to talk";
  setStatus("Ready");
});

listen<string>("ai-response-with-tool", (event) => {
  const data = JSON.parse(event.payload);
  addMessage(data.text, "ai", data.tool);
  micLabel.textContent = "Hold Space or click to talk";
  setStatus("Ready");
});

listen<string>("ai-speaking", (_event) => {
  setStatus("🔊 Speaking", "connected");
});

listen<string>("ai-error", (event) => {
  addMessage(event.payload, "system");
  micLabel.textContent = "Hold Space or click to talk";
  setStatus("Error");
});

// ── Init ───────────────────────────────────────────

setStatus("Ready");
micLabel.textContent = "Hold Space or click to talk";
