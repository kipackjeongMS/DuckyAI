"""DuckAI CLI - Personal Knowledge Management CLI framework."""

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("duckyai")
except Exception:
    __version__ = "0.0.0"
