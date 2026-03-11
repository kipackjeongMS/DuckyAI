import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const chatEl = document.getElementById("chat")!;
const micBtn = document.getElementById("mic-btn")!;
const micLabel = document.getElementById("mic-label")!;
const statusEl = document.getElementById("status")!;

let isRecording = false;
let recognition: any = null;
let currentTranscript = "";

// ── Speech Recognition (Web Speech API) ────────────

function initSpeechRecognition() {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SpeechRecognition) {
    addMessage("Speech recognition not supported in this WebView", "system");
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  recognition.onresult = (event: any) => {
    let interim = "";
    let final_ = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final_ += t;
      } else {
        interim += t;
      }
    }
    currentTranscript = (currentTranscript + " " + final_).trim();
    micLabel.textContent = currentTranscript + (interim ? ` ${interim}...` : "") || "Listening...";
  };

  recognition.onerror = (event: any) => {
    console.error("Speech recognition error:", event.error);
    if (event.error !== "no-speech" && event.error !== "aborted") {
      addMessage(`Speech error: ${event.error}`, "system");
    }
  };
}

// ── Text-to-Speech ─────────────────────────────────

function speak(text: string): Promise<void> {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    // Cancel any ongoing speech
    synth.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.1;
    utterance.pitch = 1.0;

    // Try to find a good voice
    const voices = synth.getVoices();
    const preferred = voices.find(v =>
      v.name.includes("Microsoft Ava") ||
      v.name.includes("Microsoft Aria") ||
      v.name.includes("Microsoft Jenny") ||
      (v.lang.startsWith("en") && v.localService)
    );
    if (preferred) utterance.voice = preferred;

    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    synth.speak(utterance);

    setStatus("🔊 Speaking", "connected");
  });
}

// ── Chat UI helpers ────────────────────────────────

function addMessage(text: string, type: "user" | "ai" | "system", toolTag?: string) {
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

function startRecording() {
  if (isRecording || !recognition) return;
  isRecording = true;
  currentTranscript = "";
  micBtn.classList.add("recording");
  micLabel.textContent = "Listening...";
  setStatus("🔴 Recording", "recording");

  // Stop any ongoing TTS
  window.speechSynthesis.cancel();

  try {
    recognition.start();
  } catch (e) {
    // Already started
  }
}

async function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  micBtn.classList.remove("recording");

  try {
    recognition.stop();
  } catch (e) {
    // Already stopped
  }

  // Small delay to capture final results
  await new Promise(r => setTimeout(r, 300));

  const transcript = currentTranscript.trim();
  if (!transcript) {
    micLabel.textContent = "Hold Space or click to talk";
    setStatus("Ready");
    return;
  }

  addMessage(transcript, "user");
  micLabel.textContent = "Processing...";
  setStatus("🤔 Processing");

  try {
    await invoke("stop_recording_and_process", { transcript });
  } catch (e) {
    console.error("Failed to process:", e);
    addMessage(`Error: ${e}`, "system");
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

micBtn.addEventListener("mousedown", (e) => { e.preventDefault(); startRecording(); });
micBtn.addEventListener("mouseup", () => stopRecording());
micBtn.addEventListener("mouseleave", () => { if (isRecording) stopRecording(); });

// ── Listen for backend events ──────────────────────

listen<string>("ai-response", async (event) => {
  const text = event.payload;
  addMessage(text, "ai");
  await speak(text);
  micLabel.textContent = "Hold Space or click to talk";
  setStatus("Ready");
});

listen<string>("ai-response-with-tool", async (event) => {
  const data = JSON.parse(event.payload);
  addMessage(data.text, "ai", data.tool);
  await speak(data.text);
  micLabel.textContent = "Hold Space or click to talk";
  setStatus("Ready");
});

listen<string>("ai-error", (event) => {
  addMessage(event.payload, "system");
  micLabel.textContent = "Hold Space or click to talk";
  setStatus("Error");
});

// ── Init ───────────────────────────────────────────

initSpeechRecognition();

// Preload voices (needed for some browsers)
window.speechSynthesis.getVoices();
window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();

setStatus("Ready");
micLabel.textContent = "Hold Space or click to talk";
