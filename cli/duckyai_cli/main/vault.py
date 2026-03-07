"""Shared vault utilities for DuckyAI CLI."""

from pathlib import Path

VAULT_MARKERS = ['orchestrator.yaml', 'Home.md']


def find_vault_root(start: Path = None) -> Path:
    """Walk up from start to find the DuckyAI vault root."""
    current = start or Path.cwd()
    while current != current.parent:
        if any((current / m).exists() for m in VAULT_MARKERS):
            return current
        current = current.parent
    return start or Path.cwd()
