"""Request-scoped context for IP address and user-agent propagation."""

from __future__ import annotations

from contextvars import ContextVar, Token

_ip_address_var: ContextVar[str | None] = ContextVar("request_ip_address", default=None)
_user_agent_var: ContextVar[str | None] = ContextVar("request_user_agent", default=None)


def set_request_meta(ip: str | None, ua: str | None) -> tuple[Token, Token]:
    ip_token = _ip_address_var.set(ip)
    ua_token = _user_agent_var.set(ua)
    return ip_token, ua_token


def reset_request_meta(ip_token: Token, ua_token: Token) -> None:
    _ip_address_var.reset(ip_token)
    _user_agent_var.reset(ua_token)


def get_request_ip() -> str | None:
    return _ip_address_var.get()


def get_request_user_agent() -> str | None:
    return _user_agent_var.get()
