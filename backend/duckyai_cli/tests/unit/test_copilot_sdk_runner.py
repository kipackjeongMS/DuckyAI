import asyncio
import json
import io
import sys
import types
from types import SimpleNamespace

from duckyai_cli.scripts import copilot_sdk_runner


class _FakeSession:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(payload)
        return "message-1"


def test_send_prompt_uses_string_api_when_supported():
    session = _FakeSession()

    asyncio.run(copilot_sdk_runner._send_prompt(session, "hello"))

    assert session.sent == ["hello"]


def test_send_prompt_falls_back_to_legacy_dict_api():
    class _LegacySession:
        def __init__(self):
            self.sent = []
            self.calls = 0

        async def send(self, payload):
            self.calls += 1
            if self.calls == 1:
                raise TypeError("expected dict payload")
            self.sent.append(payload)
            return "message-1"

    session = _LegacySession()

    asyncio.run(copilot_sdk_runner._send_prompt(session, "hello"))

    assert session.sent == [{"prompt": "hello"}]


def test_load_mcp_servers_merges_multiple_inputs(tmp_path):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"file-server": {"command": "python", "args": ["srv.py"]}}}),
        encoding="utf-8",
    )

    servers = copilot_sdk_runner._load_mcp_servers(
        [
            json.dumps({"mcpServers": {"inline-server": {"command": "node", "args": ["srv.js"], "tools": ["one"]}}}),
            str(config_path),
        ]
    )

    assert servers == {
        "inline-server": {"command": "node", "args": ["srv.js"], "tools": ["one"]},
        "file-server": {"command": "python", "args": ["srv.py"], "tools": ["*"]},
    }


def test_create_client_uses_subprocess_config_when_available(monkeypatch):
    captured = {}

    class _FakeSubprocessConfig:
        def __init__(self, **kwargs):
            self.cli_path = kwargs.get("cli_path")
            self.cwd = kwargs.get("cwd")
            self.log_level = kwargs.get("log_level")

    class _FakeCopilotClient:
        def __init__(self, config, auto_start=True):
            captured["config"] = config
            captured["auto_start"] = auto_start

    fake_module = types.SimpleNamespace(
        CopilotClient=_FakeCopilotClient,
        SubprocessConfig=_FakeSubprocessConfig,
        __file__="C:/Python314/Lib/site-packages/copilot/__init__.py",
    )

    monkeypatch.setitem(sys.modules, "copilot", fake_module)
    monkeypatch.setattr(copilot_sdk_runner.Path, "exists", lambda self: str(self).endswith("copilot.exe"))

    copilot_sdk_runner._create_client("C:/vault")

    assert isinstance(captured["config"], _FakeSubprocessConfig)
    assert captured["config"].cli_path.replace("\\", "/") == "C:/Python314/Lib/site-packages/copilot/bin/copilot.exe"
    assert captured["config"].cwd == "C:/vault"
    assert captured["config"].log_level == "warning"
    assert captured["auto_start"] is True


def test_resolve_sdk_cli_path_falls_back_to_path(monkeypatch):
    fake_module = types.SimpleNamespace(
        __file__="C:/Python314/Lib/site-packages/copilot/__init__.py",
    )

    monkeypatch.setitem(sys.modules, "copilot", fake_module)
    monkeypatch.setattr(copilot_sdk_runner.Path, "exists", lambda self: False)
    monkeypatch.setattr(copilot_sdk_runner.shutil, "which", lambda _: "C:/Tools/copilot.exe")

    assert copilot_sdk_runner._resolve_sdk_cli_path() == "C:/Tools/copilot.exe"


def test_safe_print_falls_back_for_unicode_encode_error():
    class _FlakyStream(io.StringIO):
        def write(self, text):
            if any(ord(ch) > 127 for ch in text):
                raise UnicodeEncodeError("charmap", text, 0, 1, "cannot encode")
            return super().write(text)

    stream = _FlakyStream()

    copilot_sdk_runner._safe_print("hello ✓", stream=stream)

    assert "hello ?" in stream.getvalue()


def test_create_session_uses_keyword_api_and_falls_back(monkeypatch):
    approve_all = object()
    fake_module = types.SimpleNamespace(PermissionHandler=types.SimpleNamespace(approve_all=approve_all))
    monkeypatch.setitem(sys.modules, "copilot", fake_module)

    class _KeywordClient:
        def __init__(self):
            self.kwargs = None

        async def create_session(self, **kwargs):
            self.kwargs = kwargs
            return "session"

    keyword_client = _KeywordClient()
    result = asyncio.run(
        copilot_sdk_runner._create_session(
            keyword_client,
            model="claude-haiku-4.5",
            mcp_servers={"server": {"command": "node", "tools": ["*"]}},
        )
    )

    assert result == "session"
    assert keyword_client.kwargs == {
        "on_permission_request": approve_all,
        "model": "claude-haiku-4.5",
        "mcp_servers": {"server": {"command": "node", "tools": ["*"]}},
    }

    class _LegacyClient:
        def __init__(self):
            self.payload = None

        async def create_session(self, *args, **kwargs):
            if kwargs:
                raise TypeError("legacy positional options only")
            self.payload = args[0]
            return "legacy-session"

    legacy_client = _LegacyClient()
    result = asyncio.run(
        copilot_sdk_runner._create_session(
            legacy_client,
            model=None,
            mcp_servers={},
        )
    )

    assert result == "legacy-session"
    assert legacy_client.payload == {"on_permission_request": approve_all}


def test_snapshot_process_tree_returns_root_without_psutil(monkeypatch):
    monkeypatch.setattr(copilot_sdk_runner, "_get_psutil", lambda: None)

    assert copilot_sdk_runner._snapshot_process_tree(1234) == {1234}


def test_kill_process_ids_returns_empty_when_no_targets():
    assert copilot_sdk_runner._kill_process_ids(set()) == []


def test_get_client_process_pid_reads_private_process():
    client = SimpleNamespace(_process=SimpleNamespace(pid=4321))

    assert copilot_sdk_runner._get_client_process_pid(client) == 4321


def test_shutdown_client_force_stops_and_kills_snapshot(monkeypatch):
    calls = []

    class _FakeClient:
        def __init__(self):
            self._process = SimpleNamespace(pid=9876)

        async def stop(self):
            calls.append("stop")
            raise RuntimeError("stop failed")

        async def force_stop(self):
            calls.append("force_stop")

    monkeypatch.setattr(copilot_sdk_runner, "_snapshot_process_tree", lambda pid: {pid, 111, 222})
    monkeypatch.setattr(copilot_sdk_runner, "_kill_process_ids", lambda pids: sorted(pids))
    monkeypatch.setattr(copilot_sdk_runner.os, "getpid", lambda: 222)

    killed = asyncio.run(copilot_sdk_runner._shutdown_client(_FakeClient()))

    assert calls == ["stop", "force_stop"]
    assert killed == [111, 9876]