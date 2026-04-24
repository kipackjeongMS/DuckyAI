"""CLI commands for the terminal server."""

import click
import os
import subprocess
import sys
import time
from pathlib import Path


@click.group("terminal")
def terminal_group():
    """Manage the DuckyAI terminal server."""
    pass


@terminal_group.command("start")
@click.option("--port", default=52847, help="Port number (default: 52847)")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.pass_context
def terminal_start(ctx, port, foreground):
    """Start the terminal server."""
    vault_path = ctx.obj.get("vault_root") if ctx.obj else None
    if not vault_path:
        from .vault import resolve_vault
        vault_path = resolve_vault(None)
    if not vault_path:
        click.echo("Error: Could not resolve vault path.", err=True)
        raise SystemExit(1)

    vault_path = str(vault_path)

    if foreground:
        from ..terminal_server import start_terminal_server
        start_terminal_server(vault_path, port=port)
    else:
        python = sys.executable
        cmd = [python, "-m", "duckyai.terminal_server", "--vault", vault_path, "--port", str(port)]

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

        time.sleep(1.5)
        try:
            os.kill(proc.pid, 0)
            click.echo(f"✓ Terminal server started (PID {proc.pid}, port {port})")
        except OSError:
            click.echo("✗ Terminal server failed to start. Run with --foreground for details.", err=True)


@terminal_group.command("stop")
@click.pass_context
def terminal_stop(ctx):
    """Stop the terminal server."""
    vault_path = ctx.obj.get("vault_root") if ctx.obj else None
    if not vault_path:
        from .vault import resolve_vault
        vault_path = resolve_vault(None)
    if not vault_path:
        click.echo("Error: Could not resolve vault path.", err=True)
        raise SystemExit(1)

    from ..terminal_server import stop_terminal_server
    if stop_terminal_server(str(vault_path)):
        click.echo("✓ Terminal server stopped")
    else:
        click.echo("Terminal server is not running")


@terminal_group.command("status")
@click.pass_context
def terminal_status(ctx):
    """Check terminal server status."""
    vault_path = ctx.obj.get("vault_root") if ctx.obj else None
    if not vault_path:
        from .vault import resolve_vault
        vault_path = resolve_vault(None)
    if not vault_path:
        click.echo("Error: Could not resolve vault path.", err=True)
        raise SystemExit(1)

    from ..terminal_server import terminal_server_status
    status = terminal_server_status(str(vault_path))
    if status["running"]:
        click.echo(f"✓ Terminal server running (PID {status['pid']}, port {status['port']})")
    else:
        click.echo("✗ Terminal server is not running")
