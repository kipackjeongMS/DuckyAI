#!/usr/bin/env python3
"""Self-update command for DuckyAI CLI."""

import shutil
import sys
import tempfile
import zipfile
import subprocess
from pathlib import Path
from importlib.metadata import version as get_installed_version, PackageNotFoundError
from typing import Optional

import click
import requests

# GitHub repository configuration
GITHUB_REPO = "kipackjeongMS/DuckyAI"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"


def get_current_version() -> Optional[str]:
    """Get the currently installed version of duckyai."""
    try:
        return get_installed_version("duckyai")
    except PackageNotFoundError:
        return None


def get_releases() -> list[dict]:
    """Fetch all releases from GitHub API."""
    try:
        response = requests.get(f"{GITHUB_API_BASE}/releases", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


def get_latest_release() -> Optional[dict]:
    """Fetch the latest release from GitHub API."""
    try:
        response = requests.get(f"{GITHUB_API_BASE}/releases/latest", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def get_release_by_tag(tag: str) -> Optional[dict]:
    """Fetch a specific release by tag name."""
    try:
        response = requests.get(f"{GITHUB_API_BASE}/releases/tags/{tag}", timeout=10)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        pass
    return None


def download_zip(url: str, dest_path: Path) -> None:
    """Download a ZIP file from URL with progress indicator."""
    click.echo("Downloading...")
    
    response = requests.get(url, stream=True, timeout=60, allow_redirects=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest_path, 'wb') as f:
        if total_size == 0:
            f.write(response.content)
        else:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                percent = int(100 * downloaded / total_size)
                click.echo(f"\rProgress: {percent}%", nl=False)
    
    click.echo("\nDownload complete.")


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract ZIP file and return path to extracted content."""
    click.echo("Extracting...")
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)
    
    # GitHub ZIPs contain a single directory
    extracted_dirs = [d for d in dest_dir.iterdir() if d.is_dir()]
    if len(extracted_dirs) == 1:
        return extracted_dirs[0]
    
    return dest_dir


def install_package(package_dir: Path) -> bool:
    """Install the package using pip."""
    click.echo("Installing...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", str(package_dir)],
            capture_output=True,
            text=True,
            check=True
        )
        click.echo(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        click.echo(f"Installation failed: {e.stderr}", err=True)
        return False


# ---------------------------------------------------------------------------
# Vault sync — update CLI-managed files in the user's vault
# ---------------------------------------------------------------------------

# Files that are always overwritten on update (CLI-managed, not user-editable)
_SYSTEM_FILES = {
    ".obsidian/plugins/duckyai/main.js",
    ".obsidian/plugins/duckyai/manifest.json",
    ".obsidian/plugins/duckyai/styles.css",
}


def sync_vault(vault_root: Path) -> None:
    """Sync CLI-managed vault files after a package update.

    1. Calls ensure_init() to sync .playbook prompts, copilot-instructions, skills.
    2. Force-overwrites CLI-managed system files (Obsidian plugin).
    3. Copies new vault-template files that don't exist yet (skip-if-exists).
    """
    from .cli import ensure_init

    click.echo()
    click.echo("Syncing vault files...")

    # 1) .playbook → .github/ (prompts-agent, copilot-instructions, skills)
    ensure_init(vault_root)
    click.echo("  ✓ Prompts, copilot-instructions, and skills synced")

    # 2) Vault-template files
    vault_template_dir = Path(__file__).resolve().parent.parent / ".vault-template"
    if not vault_template_dir.is_dir():
        click.echo("  ⚠ Bundled vault-template not found — skipping", err=True)
        return

    updated = 0
    created = 0
    for item in vault_template_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(vault_template_dir)
        rel_posix = rel.as_posix()
        dest = vault_root / rel

        if rel_posix in _SYSTEM_FILES:
            # Always overwrite system files
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))
            updated += 1
        elif not dest.exists():
            # New template file — copy it
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))
            created += 1
        # else: user-owned file exists — leave it alone

    if updated:
        click.echo(f"  ✓ {updated} system file(s) updated (Obsidian plugin)")
    if created:
        click.echo(f"  ✓ {created} new template file(s) added")
    if not updated and not created:
        click.echo("  · Vault files already up to date")


def _find_active_vaults() -> list[Path]:
    """Return all known vault roots."""
    vaults: list[Path] = []

    # Check the vault registry (home vault)
    try:
        from duckyai.vault_registry import get_home_vault
        home = get_home_vault()
        if home:
            p = Path(home["path"])
            if p.is_dir():
                vaults.append(p)
    except Exception:
        pass

    # Also try to find vault from current directory
    try:
        from .vault import find_vault_root, is_inside_vault
        if is_inside_vault():
            cwd_vault = find_vault_root()
            if cwd_vault.resolve() not in [v.resolve() for v in vaults]:
                vaults.append(cwd_vault)
    except Exception:
        pass

    return vaults


@click.command("update")
@click.option("--force", "-f", is_flag=True, help="Force update even if already up to date")
@click.option("--version", "-v", "target_version", type=str, help="Install a specific version")
@click.option("--list", "-l", "list_releases", is_flag=True, help="List available releases")
@click.option("--sync-only", is_flag=True, help="Skip pip install, only sync vault files")
def update_cli(force: bool, target_version: Optional[str], list_releases: bool, sync_only: bool) -> None:
    """Self-update the DuckyAI CLI from GitHub releases."""
    click.echo("=" * 50)
    click.echo("DuckyAI CLI Self-Update")
    click.echo("=" * 50)
    click.echo()

    if list_releases:
        releases = get_releases()
        if not releases:
            click.echo("No releases available.")
            return

        click.echo("Available releases:")
        for release in releases[:10]:
            tag = release.get("tag_name", "unknown")
            name = release.get("name", "")
            prerelease = " (pre-release)" if release.get("prerelease") else ""
            click.echo(f"  {tag}{prerelease} - {name}")

        if len(releases) > 10:
            click.echo(f"  ... and {len(releases) - 10} more")
        return

    # --sync-only: skip pip install, just sync vault files
    if sync_only:
        click.echo("Sync-only mode — skipping pip install")
        _sync_all_vaults()
        return

    current_version = get_current_version()
    click.echo(f"Current version: {current_version or 'not installed'}")

    if target_version:
        release = get_release_by_tag(target_version)
        if not release:
            click.echo(f"Error: Release '{target_version}' not found.", err=True)
            click.echo("Use --list to see available releases.", err=True)
            sys.exit(1)
    else:
        release = get_latest_release()
        if not release:
            click.echo("Error: No releases available.", err=True)
            sys.exit(1)

    release_version = release.get("tag_name", "unknown")
    zipball_url = release.get("zipball_url")

    click.echo(f"Target version:  {release_version}")
    click.echo()

    if not force and current_version and current_version == release_version:
        click.echo("Already up to date!")
        # Still sync vault files in case they're stale
        _sync_all_vaults()
        return

    if not zipball_url:
        click.echo("Error: No download URL found for release.", err=True)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        zip_path = tmpdir_path / "release.zip"

        try:
            download_zip(zipball_url, zip_path)
            extracted_path = extract_zip(zip_path, tmpdir_path)

            # pyproject.toml lives in backend/ subdirectory
            backend_path = extracted_path / "backend"
            install_dir = backend_path if backend_path.is_dir() and (backend_path / "pyproject.toml").exists() else extracted_path

            if install_package(install_dir):
                click.echo()
                click.echo("✓ Python package updated")
            else:
                click.echo("Update failed.", err=True)
                sys.exit(1)

        except requests.RequestException as e:
            click.echo(f"Download failed: {e}", err=True)
            sys.exit(1)
        except zipfile.BadZipFile as e:
            click.echo(f"Extraction failed: {e}", err=True)
            sys.exit(1)

    # After pip install, sync vault files with the new package contents
    _sync_all_vaults()

    click.echo()
    click.echo("=" * 50)
    click.echo("Update completed successfully!")
    click.echo("=" * 50)


def _sync_all_vaults() -> None:
    """Find all registered vaults and sync each one."""
    vaults = _find_active_vaults()
    if not vaults:
        click.echo()
        click.echo("No vaults found — run 'duckyai setup' to create one.")
        return

    for vault in vaults:
        click.echo()
        click.echo(f"─── Syncing vault: {vault} ───")
        try:
            sync_vault(vault)
        except Exception as e:
            click.echo(f"  ⚠ Error syncing vault: {e}", err=True)


if __name__ == "__main__":
    update_cli()
