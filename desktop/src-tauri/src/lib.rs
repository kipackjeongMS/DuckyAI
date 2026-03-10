use std::process::Command;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};

struct AppState {
    vault_root: Mutex<String>,
}

#[tauri::command]
fn start_recording() -> Result<(), String> {
    // Recording is handled by the frontend's MediaRecorder API
    // This command is a placeholder for any backend state tracking
    Ok(())
}

#[tauri::command]
async fn stop_recording_and_process(
    app: AppHandle,
    transcript: String,
) -> Result<String, String> {
    // The frontend sends the transcript (from Web Speech API or whisper)
    // We forward it to the Copilot SDK runner
    let state = app.state::<AppState>();
    let vault_root = state.vault_root.lock().unwrap().clone();

    // Find the copilot SDK runner script
    let runner_path = std::path::Path::new(&vault_root)
        .join("scripts")
        .join("copilot_sdk_runner.py");

    if !runner_path.exists() {
        let _ = app.emit("ai-error", "Copilot SDK runner not found");
        return Err("Runner not found".into());
    }

    // Build the prompt with voice context
    let prompt = format!(
        "You are responding to a voice request. Be concise and conversational — \
        this will be spoken aloud. Avoid markdown formatting. \
        Summarize key points in natural speech.\n\nUser request: {}",
        transcript
    );

    // Find Python 3.10+
    let python = find_sdk_python().ok_or("Python 3.10+ not found")?;

    // Spawn copilot SDK runner
    let output = Command::new(&python)
        .arg(runner_path.to_str().unwrap())
        .arg("--prompt")
        .arg(&prompt)
        .arg("--cwd")
        .arg(&vault_root)
        .current_dir(&vault_root)
        .output()
        .map_err(|e| format!("Failed to run agent: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let response_text = extract_sdk_response(&stdout);

    // Emit response to frontend
    let _ = app.emit("ai-response", &response_text);

    Ok(transcript)
}

fn find_sdk_python() -> Option<String> {
    // Check uv-managed Pythons
    if let Some(appdata) = std::env::var_os("APPDATA") {
        let uv_dir = std::path::Path::new(&appdata).join("uv").join("python");
        if uv_dir.exists() {
            if let Ok(entries) = std::fs::read_dir(&uv_dir) {
                let mut versions: Vec<_> = entries
                    .filter_map(|e| e.ok())
                    .filter(|e| {
                        let name = e.file_name().to_string_lossy().to_string();
                        name.contains("cpython-3.1") || name.contains("cpython-3.2")
                    })
                    .collect();
                versions.sort_by(|a, b| b.file_name().cmp(&a.file_name()));
                for v in versions {
                    let py = v.path().join("python.exe");
                    if py.exists() {
                        return Some(py.to_string_lossy().to_string());
                    }
                }
            }
        }
    }
    // Fallback to PATH
    which::which("python3").ok().map(|p| p.to_string_lossy().to_string())
        .or_else(|| which::which("python").ok().map(|p| p.to_string_lossy().to_string()))
}

fn extract_sdk_response(output: &str) -> String {
    let marker = "__COPILOT_SDK_RESULT__";
    if let Some(idx) = output.find(marker) {
        let json_str = &output[idx + marker.len()..].trim();
        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(json_str) {
            if let Some(text) = parsed.get("output").and_then(|v| v.as_str()) {
                if !text.is_empty() {
                    return text.to_string();
                }
            }
        }
    }
    // Fall back to raw output minus marker
    output.lines()
        .filter(|l| !l.contains(marker))
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Detect vault root (current dir or parent with orchestrator.yaml)
    let vault_root = std::env::current_dir()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            vault_root: Mutex::new(vault_root),
        })
        .invoke_handler(tauri::generate_handler![
            start_recording,
            stop_recording_and_process,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
