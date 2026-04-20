"""Unit tests for single home-vault configuration and resolution."""

from pathlib import Path

from duckyai import vault_registry
from duckyai.main import vault as vault_module


def test_set_and_get_home_vault(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    vault_path = tmp_path / "Vault"
    vault_path.mkdir()

    monkeypatch.setattr(vault_registry, "CONFIG_PATH", config_path)

    vault_registry.set_home_vault("home1", "Home One", vault_path, services_path=str(tmp_path / "Vault-Services"))

    result = vault_registry.get_home_vault()
    assert result is not None
    assert result["id"] == "home1"
    assert result["name"] == "Home One"
    assert result["path"] == str(vault_path.resolve())
    assert result["services_path"] == str(tmp_path / "Vault-Services")


def test_get_home_vault_returns_none_without_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"

    monkeypatch.setattr(vault_registry, "CONFIG_PATH", config_path)

    result = vault_registry.get_home_vault()

    assert result is None
    assert not config_path.exists()


def test_resolve_vault_uses_home_vault_when_outside_vault(monkeypatch, tmp_path):
    home_vault = tmp_path / "HomeVault"
    home_vault.mkdir()
    (home_vault / "duckyai.yml").write_text("id: home\n", encoding="utf-8")
    outside = tmp_path / "Outside"
    outside.mkdir()

    monkeypatch.chdir(outside)
    monkeypatch.setattr(
        vault_module,
        "Path",
        vault_module.Path,
    )
    monkeypatch.setattr(
        vault_registry,
        "get_home_vault",
        lambda: {"id": "home", "name": "Home", "path": str(home_vault.resolve())},
    )
    monkeypatch.setattr(vault_registry, "touch_vault", lambda vault_id: None)

    result = vault_module.resolve_vault()

    assert result == home_vault


def test_resolve_vault_prefers_current_vault_over_home_vault(monkeypatch, tmp_path):
    current_vault = tmp_path / "CurrentVault"
    current_vault.mkdir()
    (current_vault / "duckyai.yml").write_text("id: current\n", encoding="utf-8")
    home_vault = tmp_path / "HomeVault"
    home_vault.mkdir()
    (home_vault / "duckyai.yml").write_text("id: home\n", encoding="utf-8")

    monkeypatch.chdir(current_vault)
    monkeypatch.setattr(
        vault_registry,
        "get_home_vault",
        lambda: {"id": "home", "name": "Home", "path": str(home_vault.resolve())},
    )
    monkeypatch.setattr(vault_registry, "touch_vault", lambda vault_id: None)

    result = vault_module.resolve_vault()

    assert result == current_vault