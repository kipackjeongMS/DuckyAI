"""Unit tests for main/orchestrator.py"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from duckyai_cli.main.orchestrator import run_orchestrator_daemon
from duckyai_cli.main import orch_cmd


class TestOrchestratorFunctions:
    """Test orchestrator CLI functions."""

    @pytest.fixture
    def temp_vault(self):
        """Create temporary vault."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            (vault_path / "_Settings_" / "Prompts").mkdir(parents=True)
            yield vault_path

    @patch('duckyai_cli.main.orchestrator.Orchestrator')
    @patch('duckyai_cli.main.orchestrator.Config')
    @patch('duckyai_cli.main.orchestrator.signal.signal')
    def test_run_orchestrator_daemon(self, mock_signal, mock_config_class, mock_orchestrator_class, temp_vault):
        """Test run_orchestrator_daemon function."""
        # Setup mocks
        mock_config = Mock()
        mock_config.get_orchestrator_max_concurrent.return_value = 3
        mock_config_class.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator.get_status.return_value = {
            'agents_loaded': 2,
            'agent_list': [
                {'abbreviation': 'EIC', 'name': 'Enrich Ingested Content', 'category': 'ingestion'},
                {'abbreviation': 'CTP', 'name': 'Create Thread Postings', 'category': 'publish'}
            ]
        }
        mock_orchestrator.poller_manager.pollers.items.return_value = []
        mock_orchestrator.agent_registry.agents = {}
        mock_orchestrator_class.return_value = mock_orchestrator
        
        # Call function (will hang on run_forever, so we'll mock it)
        mock_orchestrator.run_forever = Mock()
        
        # This will call run_forever which we've mocked, so it won't hang
        run_orchestrator_daemon(vault_path=temp_vault, debug=False)
        
        # Verify orchestrator was created
        mock_orchestrator_class.assert_called_once()
        call_kwargs = mock_orchestrator_class.call_args[1]
        assert call_kwargs['vault_path'] == temp_vault
        assert call_kwargs['max_concurrent'] == 3
        
        # Verify signal handlers were set
        assert mock_signal.call_count == 2
        
        # Verify status was retrieved
        mock_orchestrator.get_status.assert_called_once()
        
        # Verify run_forever was called
        mock_orchestrator.run_forever.assert_called_once()

    @patch('duckyai_cli.main.orchestrator.Orchestrator')
    @patch('duckyai_cli.main.orchestrator.Config')
    def test_run_orchestrator_daemon_with_debug(self, mock_config_class, mock_orchestrator_class, temp_vault):
        """Test run_orchestrator_daemon with debug enabled."""
        mock_config = Mock()
        mock_config.get_orchestrator_max_concurrent.return_value = 5
        mock_config_class.return_value = mock_config
        
        mock_orchestrator = Mock()
        mock_orchestrator.get_status.return_value = {'agents_loaded': 0, 'agent_list': []}
        mock_orchestrator.poller_manager.pollers.items.return_value = []
        mock_orchestrator.agent_registry.agents = {}
        mock_orchestrator.run_forever = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator
        
        run_orchestrator_daemon(vault_path=temp_vault, debug=True)

    @patch('duckyai_cli.main.orchestrator.Path.cwd')
    def test_run_orchestrator_daemon_defaults_to_cwd(self, mock_cwd, temp_vault):
        """Test that run_orchestrator_daemon defaults to CWD."""
        mock_cwd.return_value = temp_vault
        
        with patch('duckyai_cli.main.orchestrator.Config') as mock_config_class, \
             patch('duckyai_cli.main.orchestrator.Orchestrator') as mock_orchestrator_class:
            
            mock_config = Mock()
            mock_config.get_orchestrator_max_concurrent.return_value = 3
            mock_config_class.return_value = mock_config
            
            mock_orchestrator = Mock()
            mock_orchestrator.get_status.return_value = {'agents_loaded': 0, 'agent_list': []}
            mock_orchestrator.poller_manager.pollers.items.return_value = []
            mock_orchestrator.agent_registry.agents = {}
            mock_orchestrator.run_forever = Mock()
            mock_orchestrator_class.return_value = mock_orchestrator
            
            run_orchestrator_daemon(vault_path=None, debug=False)
            
            # Should use CWD
            mock_cwd.assert_called_once()
            call_kwargs = mock_orchestrator_class.call_args[1]
            assert call_kwargs['vault_path'] == temp_vault


class _FakeProc:
    def __init__(self, pid, vault_path, cmdline):
        self.pid = pid
        self._cwd = str(vault_path)
        self.info = {"pid": pid, "cmdline": cmdline}
        self.terminated = False
        self.killed = False

    def cwd(self):
        return self._cwd

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def test_cleanup_orchestrator_processes_fresh_start_terminates_matching_process(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()
    (vault_root / ".orchestrator.pid").write_text("123", encoding="utf-8")
    discovery_dir = vault_root / ".duckyai"
    discovery_dir.mkdir()
    (discovery_dir / "api.json").write_text(json.dumps({"pid": 123, "url": "http://127.0.0.1:52845"}), encoding="utf-8")

    proc = _FakeProc(123, vault_root, ["python", "-m", "duckyai_cli", "-o"])

    class _Psutil:
        NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        AccessDenied = type("AccessDenied", (Exception,), {})

        @staticmethod
        def process_iter(attrs=None):
            return [proc]

        @staticmethod
        def wait_procs(processes, timeout=0):
            return processes, []

    monkeypatch.setattr(orch_cmd, "_get_psutil", lambda: _Psutil)
    monkeypatch.setattr(orch_cmd, "_probe_discovery_health", lambda discovery: 123)

    result = orch_cmd._cleanup_orchestrator_processes(vault_root, fresh_start=True)

    assert proc.terminated is True
    assert result["terminated_pids"] == [123]
    assert result["healthy_pid"] is None
    assert not (vault_root / ".orchestrator.pid").exists()
    assert not (vault_root / ".duckyai" / "api.json").exists()


def test_cleanup_orchestrator_processes_keeps_healthy_process_when_not_fresh(monkeypatch, tmp_path):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()
    pid_file = vault_root / ".orchestrator.pid"
    pid_file.write_text("123", encoding="utf-8")
    discovery_dir = vault_root / ".duckyai"
    discovery_dir.mkdir()
    discovery_file = discovery_dir / "api.json"
    discovery_file.write_text(json.dumps({"pid": 123, "url": "http://127.0.0.1:52845"}), encoding="utf-8")

    healthy_proc = _FakeProc(123, vault_root, ["python", "-m", "duckyai_cli", "-o"])
    stale_proc = _FakeProc(456, vault_root, ["python", "-m", "duckyai_cli", "-o"])

    class _Psutil:
        NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        AccessDenied = type("AccessDenied", (Exception,), {})

        @staticmethod
        def process_iter(attrs=None):
            return [healthy_proc, stale_proc]

        @staticmethod
        def wait_procs(processes, timeout=0):
            return processes, []

    monkeypatch.setattr(orch_cmd, "_get_psutil", lambda: _Psutil)
    monkeypatch.setattr(orch_cmd, "_probe_discovery_health", lambda discovery: 123)

    result = orch_cmd._cleanup_orchestrator_processes(vault_root, fresh_start=False)

    assert healthy_proc.terminated is False
    assert stale_proc.terminated is True
    assert result["healthy_pid"] == 123
    assert result["terminated_pids"] == [456]
    assert pid_file.exists()
    assert discovery_file.exists()


@patch('duckyai_cli.main.orch_cmd.get_duckyai_launch_cmd', return_value=['duckyai', '-o'])
@patch('duckyai_cli.main.orch_cmd.subprocess.Popen')
def test_start_single_vault_reports_restarted_when_cleanup_replaces_processes(mock_popen, mock_launch_cmd, tmp_path, monkeypatch):
    vault_root = tmp_path / "Vault"
    vault_root.mkdir()
    (vault_root / "duckyai.yml").write_text("id: vault1\n", encoding="utf-8")

    pid_file = vault_root / ".orchestrator.pid"
    pid_file.write_text("999", encoding="utf-8")

    mock_proc = Mock(pid=321)
    mock_popen.return_value = mock_proc

    monkeypatch.setattr(
        orch_cmd,
        "_cleanup_orchestrator_processes",
        lambda vault_root, fresh_start=True: {
            "terminated_pids": [999],
            "killed_pids": [],
            "healthy_pid": None,
            "errors": [],
        },
    )

    result = orch_cmd._start_single_vault(vault_root, vault_root.name)

    assert result["status"] == "restarted"
    assert result["replaced_pids"] == [999]

