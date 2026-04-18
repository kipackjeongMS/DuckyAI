"""CLI commands for the chat server."""

import click
import os
import subprocess
import sys
import time
from pathlib import Path


@click.group("chat")
def chat_group():
    """Manage the DuckyAI chat server."""
    pass


@chat_group.command("start")
@click.option("--port", default=52846, help="Port number (default: 52846)")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.pass_context
def chat_start(ctx, port, foreground):
    """Start the chat server."""
    vault_path = ctx.obj.get("vault_root") if ctx.obj else None
    if not vault_path:
        from .vault import resolve_vault
        vault_path = resolve_vault(None)
    if not vault_path:
        click.echo("Error: Could not resolve vault path.", err=True)
        raise SystemExit(1)

    vault_path = str(vault_path)

    if foreground:
        from .chat_server import start_chat_server
        start_chat_server(vault_path, port=port)
    else:
        # Spawn as a detached background process
        python = sys.executable
        cmd = [python, "-m", "duckyai_cli.chat_server", "--vault", vault_path, "--port", str(port)]

        if os.name == "nt":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            proc = subprocess.Popen(
                cmd,
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )

        # Wait briefly and verify it started
        time.sleep(1.5)
        try:
            os.kill(proc.pid, 0)
            click.echo(f"✓ Chat server started (PID {proc.pid}, port {port})")
        except OSError:
            click.echo("✗ Chat server failed to start. Run with --foreground for details.", err=True)


@chat_group.command("stop")
@click.pass_context
def chat_stop(ctx):
    """Stop the chat server."""
    vault_path = ctx.obj.get("vault_root") if ctx.obj else None
    if not vault_path:
        from .vault import resolve_vault
        vault_path = resolve_vault(None)
    if not vault_path:
        click.echo("Error: Could not resolve vault path.", err=True)
        raise SystemExit(1)

    from .chat_server import stop_chat_server
    if stop_chat_server(str(vault_path)):
        click.echo("✓ Chat server stopped")
    else:
        click.echo("Chat server is not running")


@chat_group.command("status")
@click.pass_context
def chat_status(ctx):
    """Check chat server status."""
    vault_path = ctx.obj.get("vault_root") if ctx.obj else None
    if not vault_path:
        from .vault import resolve_vault
        vault_path = resolve_vault(None)
    if not vault_path:
        click.echo("Error: Could not resolve vault path.", err=True)
        raise SystemExit(1)

    from .chat_server import chat_server_status
    status = chat_server_status(str(vault_path))
    if status["running"]:
        click.echo(f"✓ Chat server running (PID {status['pid']}, port {status['port']})")
    else:
        click.echo("✗ Chat server is not running")
