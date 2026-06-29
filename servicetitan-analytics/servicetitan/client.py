"""ServiceTitan API v2 client.

Auth model (per ServiceTitan docs): OAuth2 client-credentials grant. POST
client_id/client_secret to the auth server, receive an access token that
expires in ~15 minutes (no refresh token). Every API request also carries the
`ST-App-Key` header. This client refreshes the token automatically when it is
close to expiry, paginates list endpoints, and retries transient failures.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config

log = logging.getLogger("servicetitan.client")

_TOKEN_SKEW_SECONDS = 60  # refresh a minute before the 15-min expiry


class ServiceTitanError(RuntimeError):
    pass


class _Retryable(ServiceTitanError):
    """Transient error worth retrying (429 / 5xx / network)."""


class ServiceTitanClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        app_key: str | None = None,
        tenant_id: str | None = None,
        auth_base: str | None = None,
        api_base: str | None = None,
    ) -> None:
        config.require_servicetitan()
        self.client_id = client_id or config.ST_CLIENT_ID
        self.client_secret = client_secret or config.ST_CLIENT_SECRET
        self.app_key = app_key or config.ST_APP_KEY
        self.tenant_id = tenant_id or config.ST_TENANT_ID
        self.auth_base = (auth_base or config.AUTH_BASE).rstrip("/")
        self.api_base = (api_base or config.API_BASE).rstrip("/")
        self._session = requests.Session()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # --- auth -------------------------------------------------------------
    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expiry - _TOKEN_SKEW_SECONDS:
            return self._token
        resp = self._session.post(
            f"{self.auth_base}/connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise ServiceTitanError(
                f"Auth failed ({resp.status_code}): {resp.text[:300]}"
            )
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 900))
        log.debug("Obtained ServiceTitan token, expires in %ss", payload.get("expires_in"))
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "ST-App-Key": self.app_key,
            "Accept": "application/json",
        }

    # --- requests ---------------------------------------------------------
    @retry(
        retry=retry_if_exception_type(_Retryable),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.api_base}/{path.lstrip('/')}"
        try:
            resp = self._session.get(url, headers=self._headers(), params=params, timeout=60)
        except requests.RequestException as exc:
            raise _Retryable(f"network error: {exc}") from exc
        if resp.status_code == 401:
            # token might have just expired; force refresh once and let retry handle it
            self._token = None
            raise _Retryable("401 unauthorized (token refresh)")
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _Retryable(f"{resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ServiceTitanError(f"{resp.status_code} on {url}: {resp.text[:300]}")
        return resp.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Single GET. `path` may be a full ServiceTitan path; `{tenant}` is substituted."""
        return self._get(path.replace("{tenant}", self.tenant_id), params)

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        page_size: int = 200,
    ) -> Iterator[dict[str, Any]]:
        """Yield every record across pages of a ServiceTitan list endpoint.

        ServiceTitan list responses have shape:
        {"page": N, "pageSize": M, "hasMore": bool, "data": [...]}.
        """
        path = path.replace("{tenant}", self.tenant_id)
        params = dict(params or {})
        params["pageSize"] = page_size
        page = 1
        while True:
            params["page"] = page
            body = self._get(path, params)
            for row in body.get("data", []):
                yield row
            if not body.get("hasMore"):
                break
            page += 1

    def download(self, url: str, dest) -> None:
        """Stream a binary asset (e.g. a call recording) to `dest`."""
        with self._session.get(
            url, headers=self._headers(), stream=True, timeout=120
        ) as resp:
            if resp.status_code >= 400:
                raise ServiceTitanError(f"download {resp.status_code}: {url}")
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
