"""MSAL device-code-flow authentication for EV2 API."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import msal


_TOKEN_CACHE_FILE = Path(os.environ.get(
    "EV2_TOKEN_CACHE",
    Path.home() / ".cache" / "release-dashboard-mcp" / "token_cache.json",
))


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if _TOKEN_CACHE_FILE.exists():
        cache.deserialize(_TOKEN_CACHE_FILE.read_text())
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        _TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE_FILE.write_text(cache.serialize())


class Ev2Auth:
    """Manages authentication to the EV2 API via MSAL device code flow."""

    def __init__(self, client_id: str, authority: str, scopes: list[str]) -> None:
        self._scopes = scopes
        self._cache = _load_cache()
        self._app = msal.PublicClientApplication(
            client_id,
            authority=authority,
            token_cache=self._cache,
        )

    async def get_token(self) -> str:
        """Return a valid access token, prompting device code flow if needed."""
        accounts = self._app.get_accounts()
        result = None

        if accounts:
            result = self._app.acquire_token_silent(self._scopes, account=accounts[0])

        if not result or "access_token" not in result:
            flow = self._app.initiate_device_flow(scopes=self._scopes)
            if "user_code" not in flow:
                raise RuntimeError(f"Device flow initiation failed: {json.dumps(flow, indent=2)}")
            # Print to stderr so it shows up in the MCP host's log but doesn't
            # corrupt the stdio JSON-RPC transport.
            print(
                f"\n🔐 EV2 Authentication required.\n"
                f"   Go to: {flow['verification_uri']}\n"
                f"   Enter code: {flow['user_code']}\n",
                file=sys.stderr,
                flush=True,
            )
            result = self._app.acquire_token_by_device_flow(flow)

        _save_cache(self._cache)

        if "access_token" not in result:
            raise RuntimeError(f"Authentication failed: {result.get('error_description', result)}")

        return result["access_token"]
