from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any


AUTH_COOKIE_NAME = "ghost_dvr_session"
PBKDF2_ITERATIONS = 210_000


@dataclass(frozen=True)
class AuthStatus:
    setup_required: bool
    auth_enabled: bool
    authenticated: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "setup_required": self.setup_required,
            "auth_enabled": self.auth_enabled,
            "authenticated": self.authenticated,
        }


def default_auth_config() -> dict[str, Any]:
    return {
        "_notes": "Web dashboard auth is local-only. mode is unset, disabled, or password. Passwords are stored as salted PBKDF2 hashes.",
        "mode": "unset",
    }


def auth_status(config: dict[str, Any], *, authenticated: bool = False) -> AuthStatus:
    mode = _auth_mode(config)
    return AuthStatus(
        setup_required=mode == "unset",
        auth_enabled=mode == "password",
        authenticated=authenticated or mode == "disabled",
    )


def auth_required(config: dict[str, Any]) -> bool:
    return _auth_mode(config) == "password"


def setup_required(config: dict[str, Any]) -> bool:
    return _auth_mode(config) == "unset"


def configure_password(config: dict[str, Any], password: str) -> dict[str, Any]:
    if len(password) < 8:
        raise ValueError("Dashboard password must be at least 8 characters")
    salt = secrets.token_hex(16)
    config["web_auth"] = {
        **default_auth_config(),
        "mode": "password",
        "salt": salt,
        "password_hash": _hash_password(password, salt),
    }
    return config["web_auth"]


def disable_auth(config: dict[str, Any]) -> dict[str, Any]:
    config["web_auth"] = {
        **default_auth_config(),
        "mode": "disabled",
    }
    return config["web_auth"]


def verify_password(config: dict[str, Any], password: str) -> bool:
    auth = config.get("web_auth", {})
    if not isinstance(auth, dict):
        return False
    salt = str(auth.get("salt") or "")
    expected = str(auth.get("password_hash") or "")
    if not salt or not expected:
        return False
    actual = _hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _auth_mode(config: dict[str, Any]) -> str:
    auth = config.get("web_auth")
    if not isinstance(auth, dict):
        return "disabled"
    mode = str(auth.get("mode") or "unset")
    if mode in {"unset", "disabled", "password"}:
        return mode
    return "unset"


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return digest.hex()
