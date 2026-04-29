"""Runtime probes shared by compose healthchecks and local startup checks."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def probe_http_ready(*, host: str, port: int, path: str = "/ready", timeout: float = 2.0) -> bool:
    """Return True when the HTTP readiness endpoint responds with 200."""
    url = f"http://{host}:{port}{path}"
    request = urllib.request.Request(url, headers={"Connection": "close"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            # Read the response body before closing so Windows local probes do not
            # trigger noisy ConnectionResetError logs in the probed service.
            response.read()
            return status == 200
    except (urllib.error.URLError, OSError):
        return False


async def probe_database_ready(*, database_url: str, timeout: float = 2.0) -> bool:
    """Return True when the configured database responds to SELECT 1."""
    engine = create_async_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": timeout})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


def probe_redis_ready(*, redis_url: str, timeout: float = 2.0) -> bool:
    """Return True when Redis responds to a PING command."""
    parsed = urllib.parse.urlparse(redis_url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        return False

    host = parsed.hostname
    port = parsed.port or 6379
    password = parsed.password
    username = parsed.username
    use_tls = parsed.scheme == "rediss"

    try:
        with socket.create_connection((host, port), timeout=timeout) as raw_sock:
            sock = raw_sock
            if use_tls:
                context = ssl.create_default_context()
                sock = context.wrap_socket(raw_sock, server_hostname=host)

            def _send_command(parts: Sequence[str]) -> str:
                payload = [f"*{len(parts)}\r\n".encode("utf-8")]
                for part in parts:
                    encoded = part.encode("utf-8")
                    payload.append(f"${len(encoded)}\r\n".encode("utf-8"))
                    payload.append(encoded + b"\r\n")
                sock.sendall(b"".join(payload))
                return sock.recv(1024).decode("utf-8", errors="replace")

            if password:
                auth_parts = ["AUTH", password] if not username else ["AUTH", username, password]
                auth_response = _send_command(auth_parts)
                if not auth_response.startswith("+OK"):
                    return False

            return _send_command(["PING"]).startswith("+PONG")
    except OSError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runtime probe helpers for local and compose healthchecks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    http_parser = subparsers.add_parser("http-ready", help="Probe an HTTP readiness endpoint")
    http_parser.add_argument("--host", default="127.0.0.1")
    http_parser.add_argument("--port", type=int, required=True)
    http_parser.add_argument("--path", default="/ready")
    http_parser.add_argument("--timeout", type=float, default=2.0)

    worker_parser = subparsers.add_parser(
        "worker-ready",
        help="Probe worker dependencies via database and Redis readiness",
    )
    worker_parser.add_argument("--database-url-env", required=True)
    worker_parser.add_argument("--redis-url-env", required=True)
    worker_parser.add_argument("--timeout", type=float, default=2.0)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "http-ready":
        ok = probe_http_ready(host=args.host, port=args.port, path=args.path, timeout=args.timeout)
    else:
        database_url = os.environ.get(args.database_url_env, "").strip()
        redis_url = os.environ.get(args.redis_url_env, "").strip()
        ok = bool(database_url and redis_url)
        if ok:
            ok = asyncio.run(
                probe_database_ready(database_url=database_url, timeout=args.timeout)
            ) and probe_redis_ready(redis_url=redis_url, timeout=args.timeout)

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
