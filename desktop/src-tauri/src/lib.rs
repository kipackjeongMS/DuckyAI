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

    // Spawn copilot SDK runner with MCP config
    let mcp_config = build_mcp_config(&vault_root);
    let mut cmd = Command::new(&python);
    cmd.arg(runner_path.to_str().unwrap())
        .arg("--prompt")
        .arg(&prompt)
        .arg("--cwd")
        .arg(&vault_root);

    if let Some(ref mcp) = mcp_config {
        cmd.arg("--mcp-config").arg(mcp);
    }

    let output = cmd
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
    output.lines()
        .filter(|l| !l.contains("__COPILOT_SDK_RESULT__"))
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_string()
}

fn find_vault_root() -> Option<std::path::PathBuf> {
    let mut dir = std::env::current_dir().ok()?;
    loop {
        if dir.join("orchestrator.yaml").exists() {
            return Some(dir);
        }
        if !dir.pop() {
            return None;
        }
    }
}

fn build_mcp_config(vault_root: &str) -> Option<String> {
    let vault = std::path::Path::new(vault_root);

    let mut servers = serde_json::Map::new();

    // Embedded MCP server (from CLI package) or local
    let mcp_index = vault.join("mcp-server").join("dist").join("index.js");
    if mcp_index.exists() {
        let mut entry = serde_json::Map::new();
        entry.insert("command".into(), "node".into());
        entry.insert("args".into(), serde_json::json!([mcp_index.to_string_lossy()]).into());
        let mut env = serde_json::Map::new();
        env.insert("DUCKYAI_VAULT_ROOT".into(), vault_root.into());
        entry.insert("env".into(), serde_json::Value::Object(env));
        servers.insert("duckyai-vault".into(), serde_json::Value::Object(entry));
    }

    // WorkIQ MCP
    let mut workiq = serde_json::Map::new();
    workiq.insert("command".into(), "npx".into());
    workiq.insert("args".into(), serde_json::json!(["-y", "@microsoft/workiq", "mcp"]).into());
    servers.insert("workiq".into(), serde_json::Value::Object(workiq));

    if servers.is_empty() {
        return None;
    }

    let config = serde_json::json!({"mcpServers": servers});
    Some(config.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Detect vault root by walking up from CWD to find orchestrator.yaml
    let vault_root = find_vault_root()
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default())
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
