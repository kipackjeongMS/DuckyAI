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


async def run_agent(prompt: str, model: str = None, mcp_config: str = None, cwd: str = None):
    from copilot import CopilotClient, PermissionHandler

    client_opts = {
        "auto_start": True,
        "auto_restart": False,
        "log_level": "warning",
    }
    if cwd:
        client_opts["cwd"] = cwd

    client = CopilotClient(client_opts)
    await client.start()

    session_opts = {
        "on_permission_request": PermissionHandler.approve_all,
    }
    if model:
        session_opts["model"] = model

    # Load MCP config and pass as mcp_servers (SDK's MCPLocalServerConfig format)
    if mcp_config:
        try:
            config = json.loads(mcp_config)
        except json.JSONDecodeError:
            config = None
            if os.path.exists(mcp_config):
                with open(mcp_config) as f:
                    config = json.load(f)

        if config and "mcpServers" in config:
            servers = {}
            for name, srv in config["mcpServers"].items():
                srv_config = dict(srv)
                # SDK requires 'tools' field — default to all tools
                if "tools" not in srv_config:
                    srv_config["tools"] = ["*"]
                servers[name] = srv_config
            session_opts["mcp_servers"] = servers

    done = asyncio.Event()
    final_content = []
    errors = []

    def on_event(event):
        event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)
        if event_type == "assistant.message":
            if hasattr(event.data, 'content') and event.data.content:
                final_content.append(event.data.content)
                print(event.data.content, flush=True)
        elif event_type == "error":
            err_msg = str(event.data) if hasattr(event, 'data') else str(event)
            errors.append(err_msg)
            print(f"[ERROR] {err_msg}", file=sys.stderr, flush=True)
        elif event_type == "session.idle":
            done.set()

    async with await client.create_session(session_opts) as session:
        session.on(on_event)
        await session.send({"prompt": prompt})

        try:
            await asyncio.wait_for(done.wait(), timeout=1800)  # 30 min timeout
        except asyncio.TimeoutError:
            errors.append("Timeout: agent did not complete within 30 minutes")

    await client.stop()

    # Output summary as JSON on the last line for the execution_manager to parse
    result = {
        "status": "error" if errors else "completed",
        "output": "\n".join(final_content),
        "errors": errors,
    }
    print(f"\n__COPILOT_SDK_RESULT__{json.dumps(result)}", flush=True)

    return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description="Copilot SDK agent runner")
    parser.add_argument("--prompt", required=True, help="Agent prompt text")
    parser.add_argument("--model", default=None, help="Model name (e.g., claude-sonnet-4.6)")
    parser.add_argument("--mcp-config", default=None, help="MCP config JSON string or file path")
    parser.add_argument("--cwd", default=None, help="Working directory")
    args = parser.parse_args()

    exit_code = asyncio.run(run_agent(
        prompt=args.prompt,
        model=args.model,
        mcp_config=args.mcp_config,
        cwd=args.cwd,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
