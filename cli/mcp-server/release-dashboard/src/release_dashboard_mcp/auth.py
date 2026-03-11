"""Azure Identity authentication for EV2 API using DefaultAzureCredential."""

from __future__ import annotations

import logging

from azure.identity import AzureCliCredential
from azure.core.exceptions import ClientAuthenticationError

logger = logging.getLogger("release-dashboard.auth")


class AuthRequired(Exception):
    """Raised when no valid credential is available."""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(
            "🔐 EV2 Authentication required.\n"
            "No valid Azure credential found. Sign in using one of:\n\n"
            "    az login --scope https://azureservicedeploy.msft.net/.default\n\n"
            "DefaultAzureCredential checks: Environment → Managed Identity → "
            "VS Code → Azure CLI → PowerShell → azd CLI.\n"
            "Ensure at least one is configured, then retry."
            + (f"\n\nDetails: {detail}" if detail else "")
        )


class Ev2Auth:
    """Acquires EV2 API tokens via DefaultAzureCredential."""

    def __init__(self, resource: str) -> None:
        self._scope = f"{resource}/.default"
        self._credential = AzureCliCredential()

    async def get_token(self) -> str:
        """Return a valid access token. Raises AuthRequired on failure."""
        try:
            token = self._credential.get_token(self._scope)
            logger.debug("Token acquired for scope %s", self._scope)
            return token.token
        except ClientAuthenticationError as e:
            logger.error("Auth failed: %s", str(e)[:200])
            raise AuthRequired(str(e)[:300])
        except Exception as e:
            logger.error("Auth failed (unexpected): %s", str(e)[:200])
            raise AuthRequired(str(e)[:300])
