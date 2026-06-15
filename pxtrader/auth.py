"""
Authentication and request headers for the ProjectX gateway.

The gateway authenticates with a username/password login that returns a bearer token, and it
expects a set of browser-style headers (the same ones the official web/desktop app sends). This
module manages both: build the headers, log in, and attach the token to subsequent requests.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests

from .config import FirmConfig, get_firm


# ── Device / browser fingerprint ──────────────────────────────────────────────
# The gateway expects stable per-device identifiers. We derive them from a machine seed so they
# stay constant for a given install without collecting any personal data.

def _fingerprint_seed() -> str:
    factors = {
        "platform": "Windows-10-x64",
        "machine": "AMD64",
        "node": uuid.getnode(),
    }
    return hashlib.sha256(json.dumps(factors, sort_keys=True).encode()).hexdigest()


def _derive_identifier(name: str, length: int = 32) -> str:
    return hashlib.sha256((_fingerprint_seed() + name).encode()).hexdigest()[:length]


@dataclass
class SystemProfile:
    """The browser/app profile the gateway expects in request headers.

    Defaults mimic the official desktop app. Values are intentionally static (calling
    ``platform.*`` can hang on some Windows setups); override them if you need to.
    """
    system: str = "Windows"
    release: str = "10.0"
    machine: str = "x64"
    browser_brand: str = "Chromium"
    browser_version: str = "142.0.0.0"
    app_type: str = "px-desktop"
    app_version: str = "1.22.24"
    locale: str = "en-US"

    def user_agent(self) -> str:
        os_fragment = f"Windows NT {self.release}; {self.machine}"
        if self.system == "Darwin":
            os_fragment = f"Macintosh; Intel Mac OS X {self.release.replace('.', '_')}"
        elif self.system != "Windows":
            os_fragment = f"{self.system} {self.release}; {self.machine}"
        return (
            f"Mozilla/5.0 ({os_fragment}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{self.browser_version} Safari/537.36"
        )

    def sec_ch_ua(self) -> str:
        major = self.browser_version.split(".", 1)[0]
        return f'"{self.browser_brand}";v="{major}", "Not_A Brand";v="99"'

    def accept_language(self) -> str:
        short = self.locale.split("-", 1)[0]
        return f"{self.locale},{short};q=0.9"


def _default_headers(profile: SystemProfile, origin: str) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": profile.accept_language(),
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": origin,
        "Sec-Ch-Ua": profile.sec_ch_ua(),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": f'"{profile.system}"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": profile.user_agent(),
        "X-App-Type": profile.app_type,
        "X-App-Version": profile.app_version,
    }


@dataclass
class HeaderManager:
    """Builds and reuses the gateway's request headers, including the bearer token."""
    origin: str = "https://topstepx.com"
    profile: SystemProfile = field(default_factory=SystemProfile)
    inject_identifiers: bool = True
    auth_token: Optional[str] = None
    base_headers: Dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.base_headers = _default_headers(self.profile, self.origin)
        if self.inject_identifiers:
            self.base_headers.setdefault("X-Browser-Id", _derive_identifier("browser-id"))
            self.base_headers.setdefault("X-Toeprint", _derive_identifier("toeprint"))
        if self.auth_token:
            self.set_token(self.auth_token)

    def set_token(self, token: Optional[str]) -> None:
        """Set or clear the Authorization bearer token in place."""
        self.auth_token = token
        if token:
            self.base_headers["Authorization"] = f"Bearer {token}"
        else:
            self.base_headers.pop("Authorization", None)

    def build(self, overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = self.base_headers.copy()
        if overrides:
            headers.update(overrides)
        return headers


@dataclass
class LoginResponse:
    """Wraps the raw login payload with convenient accessors."""
    payload: Dict[str, Any]

    @property
    def token(self) -> Optional[str]:
        return self.payload.get("token") or self.payload.get("accessToken")

    @property
    def user_id(self) -> Optional[int]:
        return self.payload.get("userId") or self.payload.get("userID")

    @property
    def success(self) -> bool:
        return bool(self.payload.get("success", self.token is not None))


class AuthClient:
    """Logs in to the ProjectX gateway and holds the authenticated session/token.

    Args:
        firm:    Firm preset (or name). Defaults to the configured/default firm.
        verify:  TLS certificate verification. **On by default** — only set False if you hit
                 Windows certificate-revocation hangs, and understand the MITM risk of doing so.
    """

    def __init__(self, firm: FirmConfig | str | None = None, verify: bool = True):
        self.firm = firm if isinstance(firm, FirmConfig) else get_firm(firm)
        self.verify = verify
        self.headers = HeaderManager(origin=self.firm.web)
        self.session = requests.Session()
        if not verify:
            # The caller opted out of TLS verification; silence the noisy per-request warning.
            requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    def _url(self, path: str) -> str:
        return f"{self.firm.user_api.rstrip('/')}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> requests.Response:
        """Shared transport: injects auth headers, TLS policy, and session.

        Returns the raw response (does NOT raise) so callers can parse API-specific error
        bodies before deciding to raise. Sub-clients (market data, orders, accounts) build on this.
        """
        return self.session.request(
            method, url, params=params, json=json_body,
            headers=self.headers.build(), timeout=timeout, verify=self.verify,
        )

    def post(self, path: str, payload: Dict[str, Any], *, timeout: int = 30) -> requests.Response:
        resp = self.request("POST", self._url(path), json_body=payload, timeout=timeout)
        resp.raise_for_status()
        return resp

    def login(self, username: str, password: str) -> LoginResponse:
        """Authenticate and attach the returned bearer token to future requests."""
        resp = self.post("/Login", {"userName": username, "password": password})
        result = LoginResponse(resp.json())
        if result.token:
            self.set_token(result.token)
        return result

    def set_token(self, token: Optional[str]) -> None:
        self.headers.set_token(token)

    @property
    def token(self) -> Optional[str]:
        return self.headers.auth_token
