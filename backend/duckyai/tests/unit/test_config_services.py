"""Unit tests for config.py services accessors and trigger_agent.py watermark helpers."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from duckyai.config import Config, get_global_runtime_dir


class TestConfigServicesAccessors:
    """Tests for Config.get_services_path() and Config.get_services()."""

    @pytest.fixture
    def vault_with_services(self, tmp_path):
        vault = tmp_path / "V1"
        vault.mkdir()
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        (duckyai_dir / "duckyai.yml").write_text(
            'id: v1\n'
            'services:\n'
            '  path: "../V1-Services"\n'
            '  entries:\n'
            '    - name: "SvcA"\n'
            '    - name: "SvcB"\n',
            encoding="utf-8",
        )
        return vault

    @pytest.fixture
    def vault_no_services(self, tmp_path):
        vault = tmp_path / "V2"
        vault.mkdir()
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        (duckyai_dir / "duckyai.yml").write_text('id: v2\n', encoding="utf-8")
        return vault

    def test_get_services_path_configured(self, vault_with_services):
        config = Config(vault_path=vault_with_services)
        result = config.get_services_path()
        expected = str((vault_with_services / ".." / "V1-Services").resolve())
        assert result == expected

    def test_get_services_path_default(self, vault_no_services):
        config = Config(vault_path=vault_no_services)
        result = config.get_services_path()
        assert "V2-Services" in result

    def test_get_services_returns_list(self, vault_with_services):
        config = Config(vault_path=vault_with_services)
        services = config.get_services()
        assert isinstance(services, list)
        assert len(services) == 2
        assert services[0]["name"] == "SvcA"

    def test_get_services_empty_when_not_configured(self, vault_no_services):
        config = Config(vault_path=vault_no_services)
        services = config.get_services()
        assert services == []

    def test_get_services_path_absolute_config(self, tmp_path):
        vault = tmp_path / "V3"
        vault.mkdir()
        abs_path = str(tmp_path / "custom-services").replace("\\", "/")
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        (duckyai_dir / "duckyai.yml").write_text(
            f'id: v3\nservices:\n  path: "{abs_path}"\n  entries: []\n',
            encoding="utf-8",
        )
        config = Config(vault_path=vault)
        result = config.get_services_path()
        assert Path(result).resolve() == (tmp_path / "custom-services").resolve()


def test_get_global_runtime_dir_requires_vault_path():
    with pytest.raises(ValueError, match="vault_path is required"):
        get_global_runtime_dir("v1")


class TestWatermarkHelpers:
    """Tests for _read_watermark and _format_watermark_age from trigger_agent.py."""

    @pytest.fixture
    def vault_with_watermark(self, tmp_path):
        """Create a vault + state dir with a watermark file."""
        vault = tmp_path / "WV"
        vault.mkdir()
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        (duckyai_dir / "duckyai.yml").write_text('id: wv_test\n', encoding="utf-8")

        state_dir = vault / ".duckyai" / "state"
        state_dir.mkdir(parents=True)
        watermark = {
            "lastSynced": "2026-03-13T18:00:00Z",
            "syncCount": 3,
        }
        (state_dir / "tcs-last-sync.json").write_text(
            json.dumps(watermark), encoding="utf-8"
        )
        return vault, state_dir

    def test_format_watermark_age_minutes(self):
        from duckyai.main.trigger_agent import _format_watermark_age

        # 30 minutes ago
        ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        result = _format_watermark_age(ts)
        assert "m ago" in result

    def test_format_watermark_age_hours(self):
        from duckyai.main.trigger_agent import _format_watermark_age

        # 5 hours ago
        ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        result = _format_watermark_age(ts)
        assert "h ago" in result

    def test_format_watermark_age_days(self):
        from duckyai.main.trigger_agent import _format_watermark_age

        # 3 days ago
        ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        result = _format_watermark_age(ts)
        assert "d ago" in result

    def test_format_watermark_age_with_z_suffix(self):
        from duckyai.main.trigger_agent import _format_watermark_age

        ts = "2026-03-13T12:00:00Z"
        result = _format_watermark_age(ts)
        assert "ago" in result

    def test_format_watermark_age_invalid(self):
        from duckyai.main.trigger_agent import _format_watermark_age

        result = _format_watermark_age("not-a-date")
        assert result == "unknown"

    def test_read_watermark_returns_value(self, vault_with_watermark):
        from duckyai.main.trigger_agent import _read_watermark

        vault, state_dir = vault_with_watermark
        # get_global_runtime_dir returns <vault>/.duckyai/, and _read_watermark appends "state/"
        vault_runtime_dir = state_dir.parent
        with patch("duckyai.main.trigger_agent.get_global_runtime_dir") as mock_grd:
            mock_grd.return_value = vault_runtime_dir
            result = _read_watermark(vault, "TCS")
            assert result == "2026-03-13T18:00:00Z"

    def test_read_watermark_returns_none_no_file(self, tmp_path):
        from duckyai.main.trigger_agent import _read_watermark

        vault = tmp_path / "NW"
        vault.mkdir()
        duckyai_dir = vault / ".duckyai"
        duckyai_dir.mkdir()
        (duckyai_dir / "duckyai.yml").write_text('id: nw\n', encoding="utf-8")
        result = _read_watermark(vault, "TCS")
        assert result is None

    def test_prompt_lookback_or_watermark_no_watermark(self):
        """When no watermark exists, should return lookback_hours."""
        from duckyai.main.trigger_agent import _prompt_lookback_or_watermark
        from unittest.mock import MagicMock

        console = MagicMock()
        console.input.return_value = "8"

        result = _prompt_lookback_or_watermark("TCS", 1, None, console)
        assert result == {"lookback_hours": 8}

    def test_prompt_lookback_or_watermark_with_watermark_default(self):
        """When watermark exists and user picks default (since last sync)."""
        from duckyai.main.trigger_agent import _prompt_lookback_or_watermark
        from unittest.mock import MagicMock

        console = MagicMock()
        console.input.return_value = ""  # Default = option 1

        result = _prompt_lookback_or_watermark("TCS", 1, "2026-03-13T18:00:00Z", console)
        assert result is None  # None means use watermark as-is

    def test_prompt_lookback_or_watermark_with_watermark_custom(self):
        """When watermark exists and user picks custom lookback."""
        from duckyai.main.trigger_agent import _prompt_lookback_or_watermark
        from unittest.mock import MagicMock

        console = MagicMock()
        console.input.side_effect = ["2", "24"]  # Choice 2, then 24 hours

        result = _prompt_lookback_or_watermark("TCS", 1, "2026-03-13T18:00:00Z", console)
        assert result == {"lookback_hours": 24, "ignore_watermark": True}

    def test_prompt_lookback_no_watermark_default(self):
        """When no watermark and user hits enter (uses default)."""
        from duckyai.main.trigger_agent import _prompt_lookback_or_watermark
        from unittest.mock import MagicMock

        console = MagicMock()
        console.input.return_value = ""  # Accept default

        result = _prompt_lookback_or_watermark("TMS", 24, None, console)
        assert result == {"lookback_hours": 24}
