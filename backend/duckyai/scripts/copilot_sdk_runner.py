#!/usr/bin/env python3
"""
Copilot SDK runner — thin wrapper invoked by the orchestrator's execution_manager.

Runs on Python 3.10+ (required by github-copilot-sdk).
Receives prompt, model, and MCP config via CLI args, streams output to stdout.
"""
import asyncio
import argparse
import json
import sys
import os
import shutil
from pathlib import Path
from typing import Any


def _load_mcp_servers(raw_configs: str | list[str] | None) -> dict[str, dict[str, Any]]:
    if not raw_configs:
        return {}

    config_values = raw_configs if isinstance(raw_configs, list) else [raw_configs]
    servers: dict[str, dict[str, Any]] = {}

    for raw_config in config_values:
        config = None
        try:
            config = json.loads(raw_config)
        except json.JSONDecodeError:
            if os.path.exists(raw_config):
                with open(raw_config, encoding="utf-8") as handle:
                    config = json.load(handle)

        if not config or "mcpServers" not in config:
            continue

        for name, srv in config["mcpServers"].items():
            srv_config = dict(srv)
            if "tools" not in srv_config:
                srv_config["tools"] = ["*"]
            servers[name] = srv_config

    return servers


def _resolve_sdk_cli_path() -> str | None:
    try:
        import copilot
    except ImportError:
        return shutil.which("copilot") or None

    binary_name = "copilot.exe" if os.name == "nt" else "copilot"
    bundled_cli = Path(copilot.__file__).resolve().parent / "bin" / binary_name
    if bundled_cli.exists():
        return str(bundled_cli)

    return shutil.which("copilot") or None


def _safe_print(message: str, *, stream=None) -> None:
    target = stream or sys.stdout
    try:
        print(message, file=target, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(target, "encoding", None) or "ascii"
        fallback = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback, file=target, flush=True)


def _get_psutil():
    try:
        import psutil
    except ImportError:
        return None
    return psutil


def _get_client_process_pid(client) -> int | None:
    process = getattr(client, "_process", None)
    pid = getattr(process, "pid", None)
    return int(pid) if pid else None


def _snapshot_process_tree(root_pid: int | None) -> set[int]:
    if not root_pid:
        return set()

    psutil = _get_psutil()
    if psutil is None:
        return {root_pid}

    try:
        root = psutil.Process(root_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return {root_pid}

    snapshot = {root_pid}
    try:
        snapshot.update(child.pid for child in root.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        pass
    return snapshot


def _kill_process_ids(process_ids: set[int]) -> list[int]:
    if not process_ids:
        return []

    psutil = _get_psutil()
    killed: list[int] = []
    if psutil is None:
        for pid in sorted(process_ids, reverse=True):
            try:
                if os.name == "nt":
                    os.kill(pid, 9)
                else:
                    os.kill(pid, 15)
                killed.append(pid)
            except OSError:
                continue
        return killed

    processes = []
    for pid in sorted(process_ids, reverse=True):
        try:
            processes.append(psutil.Process(pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue

    for proc in processes:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue

    gone, _ = psutil.wait_procs(processes, timeout=3.0)
    killed.extend(proc.pid for proc in gone)
    return sorted(set(killed))


async def _shutdown_client(client) -> list[int]:
    process_snapshot = _snapshot_process_tree(_get_client_process_pid(client))

    try:
        await asyncio.wait_for(client.stop(), timeout=10.0)
    except Exception:
        try:
            await asyncio.wait_for(client.force_stop(), timeout=5.0)
        except Exception:
            pass

    lingering = [pid for pid in process_snapshot if pid != os.getpid()]
    return _kill_process_ids(set(lingering))


def _create_client(cwd: str | None):
    from copilot import CopilotClient

    try:
        from copilot import SubprocessConfig
    except ImportError:
        SubprocessConfig = None

    cli_path = _resolve_sdk_cli_path()
    github_token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if SubprocessConfig is not None:
        config_kwargs = dict(
            cli_path=cli_path,
            cwd=cwd,
            log_level="warning",
            use_logged_in_user=True,
        )
        if github_token:
            config_kwargs['github_token'] = github_token
        client_config = SubprocessConfig(**config_kwargs)
        return CopilotClient(client_config, auto_start=True)

    client_opts = {
        "auto_start": True,
        "auto_restart": False,
        "log_level": "warning",
        "cli_path": cli_path,
    }
    if cwd:
        client_opts["cwd"] = cwd
    return CopilotClient(client_opts)


async def _create_session(client, *, model: str | None, mcp_servers: dict[str, dict[str, Any]]):
    # SDK renamed PermissionHandler → SessionFsHandler across versions
    _Handler = None
    for _mod in ("copilot", "copilot.types", "copilot.session"):
        try:
            _m = __import__(_mod, fromlist=["PermissionHandler"])
            _Handler = getattr(_m, "PermissionHandler", None)
            if _Handler is None:
                _Handler = getattr(_m, "SessionFsHandler", None)
            if _Handler:
                break
        except ImportError:
            continue

    session_opts: dict[str, Any] = {}
    approve = getattr(_Handler, "approve_all", None) if _Handler else None
    if approve is not None:
        session_opts["on_permission_request"] = approve
    if model:
        session_opts["model"] = model
    if mcp_servers:
        session_opts["mcp_servers"] = mcp_servers

    try:
        return await client.create_session(**session_opts)
    except TypeError:
        return await client.create_session(session_opts)


async def _send_prompt(session, prompt: str):
    try:
        return await session.send(prompt)
    except TypeError:
        return await session.send({"prompt": prompt})


async def run_agent(prompt: str, model: str = None, mcp_config: str | list[str] = None, cwd: str = None):
    client = _create_client(cwd)
    done = asyncio.Event()
    final_content = []
    errors = []
    usage_records = []
    session_usage = {}

    def on_event(event):
        event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
        if event_type == "assistant.message":
            if hasattr(event.data, 'content') and event.data.content:
                final_content.append(event.data.content)
                _safe_print(event.data.content)
        elif event_type == "assistant.usage":
            d = event.data
            record = {
                "input_tokens": int(getattr(d, 'input_tokens', 0) or 0),
                "output_tokens": int(getattr(d, 'output_tokens', 0) or 0),
                "cache_read_tokens": int(getattr(d, 'cache_read_tokens', 0) or 0),
                "cache_write_tokens": int(getattr(d, 'cache_write_tokens', 0) or 0),
                "cost": getattr(d, 'cost', 0) or 0,
                "model": getattr(d, 'model', '') or '',
                "duration_ms": int(getattr(d, 'duration', 0) or 0),
            }
            usage_records.append(record)
        elif event_type == "session.shutdown":
            d = event.data
            model_metrics = getattr(d, 'model_metrics', None)
            if model_metrics and isinstance(model_metrics, dict):
                for model_id, metric in model_metrics.items():
                    u = getattr(metric, 'usage', None)
                    r = getattr(metric, 'requests', None)
                    session_usage[model_id] = {
                        "input_tokens": int(getattr(u, 'input_tokens', 0) or 0) if u else 0,
                        "output_tokens": int(getattr(u, 'output_tokens', 0) or 0) if u else 0,
                        "cache_read_tokens": int(getattr(u, 'cache_read_tokens', 0) or 0) if u else 0,
                        "cache_write_tokens": int(getattr(u, 'cache_write_tokens', 0) or 0) if u else 0,
                        "requests": int(getattr(r, 'count', 0) or 0) if r else 0,
                        "cost": getattr(r, 'cost', 0) or 0 if r else 0,
                    }
            session_usage["_total_api_duration_ms"] = int(getattr(d, 'total_api_duration_ms', 0) or 0)
            session_usage["_total_premium_requests"] = int(getattr(d, 'total_premium_requests', 0) or 0)
        elif event_type in {"error", "session.error"}:
            err_msg = str(event.data) if hasattr(event, 'data') else str(event)
            errors.append(err_msg)
            _safe_print(f"[ERROR] {err_msg}", stream=sys.stderr)
        elif event_type == "session.idle":
            done.set()

    try:
        await client.start()
        mcp_servers = _load_mcp_servers(mcp_config)

        async with await _create_session(client, model=model, mcp_servers=mcp_servers) as session:
            session.on(on_event)
            await _send_prompt(session, prompt)

            try:
                await asyncio.wait_for(done.wait(), timeout=1800)  # 30 min timeout
            except asyncio.TimeoutError:
                errors.append("Timeout: agent did not complete within 30 minutes")
    finally:
        killed = await _shutdown_client(client)
        if killed:
            _safe_print(f"[cleanup] terminated lingering process ids: {', '.join(str(pid) for pid in killed)}", stream=sys.stderr)

    # Build aggregated usage from per-call records (fallback if session.shutdown missed)
    if usage_records and not session_usage:
        totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost": 0, "duration_ms": 0, "requests": 0}
        for r in usage_records:
            totals["input_tokens"] += r["input_tokens"]
            totals["output_tokens"] += r["output_tokens"]
            totals["cache_read_tokens"] += r["cache_read_tokens"]
            totals["cache_write_tokens"] += r["cache_write_tokens"]
            totals["cost"] += r["cost"]
            totals["duration_ms"] += r["duration_ms"]
            totals["requests"] += 1
        token_usage = {"_aggregated": totals}
    else:
        token_usage = session_usage if session_usage else {}

    # Output summary as JSON on the last line for the execution_manager to parse
    result = {
        "status": "error" if errors else "completed",
        "output": "\n".join(final_content),
        "errors": errors,
        "token_usage": token_usage,
    }
    print(f"\n__COPILOT_SDK_RESULT__{json.dumps(result)}", flush=True)

    return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description="Copilot SDK agent runner")
    parser.add_argument("--prompt", default=None, help="Agent prompt text")
    parser.add_argument("--prompt-file", default=None, help="Path to file containing agent prompt text")
    parser.add_argument("--model", default=None, help="Model name (e.g., claude-sonnet-4.6)")
    parser.add_argument("--mcp-config", action="append", default=None, help="MCP config JSON string or file path")
    parser.add_argument("--cwd", default=None, help="Working directory")
    args = parser.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        prompt = prompt_path.read_text(encoding="utf-8")
        # Clean up the temp file after reading
        try:
            prompt_path.unlink()
        except OSError:
            pass
    if not prompt:
        parser.error("Either --prompt or --prompt-file is required")

    exit_code = asyncio.run(run_agent(
        prompt=prompt,
        model=args.model,
        mcp_config=args.mcp_config,
        cwd=args.cwd,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
