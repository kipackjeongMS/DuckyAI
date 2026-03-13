"""Unit tests for main/orchestrator.py"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from duckyai_cli.main.orchestrator import run_orchestrator_daemon


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

