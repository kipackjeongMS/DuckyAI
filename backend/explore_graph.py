#!/usr/bin/env python3
"""
Microsoft Graph API feasibility exploration.

Tests GET /users/{id}/chats/ via two auth paths:

  --az-cli   Use existing `az login` credential (fast; may lack Chat.Read)
  --msal     MSAL device-code flow with Chat.Read scope (requires app registration)

MSAL setup (one-time):
  1. Register an app in https://portal.azure.com > Azure AD > App Registrations
  2. Add delegated API permissions: Chat.Read (or Chat.ReadBasic) + User.Read
  3. Authentication > Enable "Allow public client flows" (device code)
  4. Copy the Application (client) ID and your Tenant ID

Usage:
  py explore_graph.py --az-cli
  py explore_graph.py --msal --client-id <APP_ID> --tenant-id <TENANT_ID>

  # Or via env vars:
  set AZURE_CLIENT_ID=<APP_ID>
  set AZURE_TENANT_ID=<TENANT_ID>
  py explore_graph.py --msal
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Tuple

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CHAT_SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Chat.Read",
]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_token_az_cli() -> str:
    """Acquire a Graph token from the existing `az login` session."""
    # On Windows, az is az.cmd — use shell=True to resolve it via PATH
    result = subprocess.run(
        "az account get-access-token"
        " --resource https://graph.microsoft.com"
        " --query accessToken -o tsv",
        capture_output=True, text=True, shell=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"az CLI error: {result.stderr.strip()}")
    return result.stdout.strip()


def get_token_msal(client_id: str, tenant_id: str) -> str:
    """Acquire a Graph token via MSAL device-code flow (caches between runs)."""
    import msal

    cache = msal.SerializableTokenCache()
    cache_path = os.path.join(os.path.expanduser("~"), ".duckyai", "graph_token_cache.bin")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )

    # Try silent refresh first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(CHAT_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache, cache_path)
            return result["access_token"]

    # Device code flow
    flow = app.initiate_device_flow(scopes=CHAT_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow init failed: {flow}")

    print("\n" + "=" * 60)
    print(flow["message"])
    print("=" * 60 + "\n")

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(
            f"MSAL error: {result.get('error_description', json.dumps(result))}"
        )

    _save_cache(cache, cache_path)
    return result["access_token"]


def _save_cache(cache: Any, path: str) -> None:
    if cache.has_state_changed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(cache.serialize())


# ---------------------------------------------------------------------------
# Graph helper
# ---------------------------------------------------------------------------

def call_graph(token: str, path: str, params: dict | None = None) -> Tuple[int, Any]:
    resp = requests.get(
        f"{GRAPH_BASE}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        params=params,
    )
    content_type = resp.headers.get("content-type", "")
    body = resp.json() if "application/json" in content_type else resp.text
    return resp.status_code, body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Graph API feasibility: GET /users/{id}/chats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--az-cli", action="store_true",
                       help="Use Azure CLI credential (az login)")
    group.add_argument("--msal", action="store_true",
                       help="MSAL device-code flow with Chat.Read scope")
    parser.add_argument("--client-id",
                        default=os.environ.get("AZURE_CLIENT_ID"),
                        help="App client ID (MSAL only)")
    parser.add_argument("--tenant-id",
                        default=os.environ.get("AZURE_TENANT_ID", "organizations"),
                        help="Tenant ID (MSAL only, default: organizations)")
    parser.add_argument("--top", type=int, default=5,
                        help="Max chats to display (default: 5)")
    args = parser.parse_args()

    # ── 1. Acquire token ──────────────────────────────────────────────────
    print("🔑  Acquiring token...")
    if args.az_cli:
        token = get_token_az_cli()
        print("✅  Token acquired via Azure CLI")
        print("⚠️   Note: az CLI token may not include Chat.Read scope\n")
    else:
        if not args.client_id:
            print("❌  --client-id (or AZURE_CLIENT_ID env var) is required for --msal")
            sys.exit(1)
        print(f"    client_id : {args.client_id}")
        print(f"    tenant_id : {args.tenant_id}")
        token = get_token_msal(args.client_id, args.tenant_id)
        print("✅  Token acquired via MSAL\n")

    # ── 2. GET /me  ───────────────────────────────────────────────────────
    print("📋  GET /me")
    status, me = call_graph(token, "/me")
    print(f"    status : {status}")
    if status != 200:
        print(f"    error  : {json.dumps(me, indent=4)}")
        sys.exit(1)

    oid = me["id"]
    upn = me.get("userPrincipalName", "(unknown)")
    display = me.get("displayName", "(unknown)")
    print(f"    OID    : {oid}")
    print(f"    UPN    : {upn}")
    print(f"    Name   : {display}\n")

    # ── 3. GET /users/{oid}/chats  ────────────────────────────────────────
    path = f"/users/{oid}/chats"
    print(f"💬  GET {path}")
    status, chats = call_graph(token, path, params={"$top": args.top})
    print(f"    status : {status}")

    if status == 200:
        items = chats.get("value", [])
        print(f"    count  : {len(items)} (of up to {args.top} returned)\n")
        for chat in items:
            chat_id = chat.get("id", "?")
            chat_type = chat.get("chatType", "?")
            topic = chat.get("topic") or "(no topic)"
            updated = chat.get("lastUpdatedDateTime", "")
            print(f"    [{chat_type:12s}] {topic[:50]:<50s}  {updated[:19]}  {chat_id}")
    elif status == 401:
        print("    ❌  401 Unauthorized — token invalid or expired")
        print("       Try: az logout && az login")
    elif status == 403:
        print("    ❌  403 Forbidden — token lacks Chat.Read permission")
        print("       Fix: use --msal with an app that has Chat.Read delegated permission")
        print("       Error detail:")
        err = chats.get("error", {}) if isinstance(chats, dict) else chats
        print(f"       {json.dumps(err, indent=8)}")
    else:
        print(f"    ❌  Unexpected error:")
        print(json.dumps(chats, indent=4))


if __name__ == "__main__":
    main()
