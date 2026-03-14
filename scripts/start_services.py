#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Start backend services together."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from scripts.check_service_environment import (
    format_validation_result,
    load_project_dotenv,
    validate_environment,
)
from scripts.runtime_probe import probe_http_ready

BACKEND_DIR = Path(__file__).resolve().parent.parent

SERVICES = {
    "admin-service": {
        "name": "admin-service",
        "app": "admin_service.main:app",
        "port": 8001,
        "color": "\033[94m",
    },
    "user-service": {
        "name": "user-service",
        "app": "user_service.main:app",
        "port": 8000,
        "color": "\033[92m",
    },
    "content-service": {
        "name": "content-service",
        "app": "content_service.main:app",
        "port": 8004,
        "color": "\033[97m",
    },
    "testing-service": {
        "name": "testing-service",
        "app": "testing_service.main:app",
        "port": 8002,
        "color": "\033[95m",
        "env": {
            "PROBE_SCHEDULER_ENABLED": "false",
            "PORT": "8002",
        },
    },
    "router-service": {
        "name": "router-service",
        "app": "router_service.main:app",
        "port": 8003,
        "color": "\033[96m",
    },
    "testing-scheduler": {
        "name": "testing-scheduler",
        "app": "testing_service.main:app",
        "port": 8012,
        "color": "\033[90m",
        "env": {
            "PROBE_SCHEDULER_ENABLED": "true",
            "PORT": "8012",
        },
    },
    "testing-worker": {
        "name": "testing-worker",
        "cmd": [sys.executable, "-m", "arq", "testing_service.worker.WorkerSettings"],
        "color": "\033[93m",
        "healthcheck": False,
        "env": {
            "PROBE_SCHEDULER_ENABLED": "false",
        },
    },
}
DEFAULT_SERVICES = [
    "admin-service",
    "user-service",
    "content-service",
    "testing-service",
    "router-service",
    "testing-worker",
    "testing-scheduler",
]
START_ORDER = {
    service_name: index
    for index, service_name in enumerate(
        [
            "admin-service",
            "user-service",
            "content-service",
            "testing-service",
            "router-service",
            "testing-worker",
            "testing-scheduler",
        ]
    )
}

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
YELLOW = "\033[93m"

_processes: list[subprocess.Popen] = []
_shutdown = threading.Event()
_reported_exits: set[int] = set()


def _log(message: str, color: str = "") -> None:
    print(f"{color}{message}{RESET}", flush=True)


def _stream_output(proc: subprocess.Popen, label: str, color: str) -> None:
    """Stream child process output with a service prefix."""
    prefix = f"{color}[{label}]{RESET} "
    try:
        for line in iter(proc.stdout.readline, ""):
            if _shutdown.is_set():
                break
            if line:
                sys.stdout.write(f"{prefix}{line}")
                sys.stdout.flush()
    except (ValueError, OSError):
        return


def _start_one(service: dict[str, object], dev: bool) -> subprocess.Popen:
    """Start a single uvicorn app."""
    if "cmd" in service:
        cmd = [str(part) for part in service["cmd"]]
    else:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            str(service["app"]),
            "--host",
            "0.0.0.0",
            "--port",
            str(service["port"]),
        ]
        if dev:
            cmd.append("--reload")

    proc = subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            **{str(key): str(value) for key, value in service.get("env", {}).items()},
        },
    )
    threading.Thread(
        target=_stream_output,
        args=(proc, str(service["name"]), str(service["color"])),
        daemon=True,
    ).start()
    return proc


def _health_check(port: int, timeout: int = 15) -> bool:
    """Poll the health endpoint until a service is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if probe_http_ready(host="127.0.0.1", port=port, path="/ready", timeout=2.0):
            return True
        time.sleep(0.5)
    return False


def _shutdown_all() -> None:
    """Terminate all child processes."""
    _shutdown.set()
    for proc in _processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in _processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Start Eucal AI backend services")
    parser.add_argument(
        "services",
        nargs="*",
        help="Services to start, defaults to all",
    )
    parser.add_argument("--dev", action="store_true", help="Enable uvicorn --reload")
    parser.add_argument("--no-check", action="store_true", help="Skip health checks")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip environment validation")
    args = parser.parse_args()

    unknown = sorted(service for service in args.services if service not in SERVICES)
    if unknown:
        parser.error(
            "invalid choice: "
            + ", ".join(unknown)
            + " (choose from "
            + ", ".join(repr(name) for name in SERVICES)
            + ")"
        )

    selected = args.services or list(DEFAULT_SERVICES)
    selected = sorted(selected, key=lambda item: START_ORDER[item])
    mode_label = "dev" if args.dev else "prod"

    load_project_dotenv()
    if not args.skip_preflight:
        validation = validate_environment(selected)
        report = format_validation_result(validation)
        if validation.warnings:
            _log(report + "\n", YELLOW if validation.ok else RED)
        if not validation.ok:
            raise SystemExit(1)

    _log(f"\n{'=' * 50}", BOLD)
    _log(f"  Eucal AI backend services [{mode_label}]", BOLD)
    _log(f"{'=' * 50}\n", BOLD)

    for key in selected:
        service = SERVICES[key]
        port = service.get("port")
        label = f"  Starting {service['name']}" if port is None else f"  Starting {service['name']} on port {port}"
        _log(label, str(service["color"]))
        proc = _start_one(service, dev=args.dev)
        _processes.append(proc)

    if not args.no_check:
        _log("\n  Waiting for services to become healthy...\n", YELLOW)
        time.sleep(2)
        for key in selected:
            service = SERVICES[key]
            if not service.get("healthcheck", True):
                _log(f"  SKIP {service['name']} healthcheck", str(service["color"]))
                continue
            if _health_check(int(service["port"])):
                _log(
                    f"  OK  {service['name']}  http://localhost:{service['port']}/ready",
                    str(service["color"]),
                )
            else:
                _log(f"  FAIL  {service['name']} on port {service['port']}", RED)

    _log("\n  Press Ctrl+C to stop all services\n", YELLOW)

    try:
        while not _shutdown.is_set():
            time.sleep(1)
            for index, proc in enumerate(list(_processes)):
                if proc.poll() is not None and index not in _reported_exits:
                    _reported_exits.add(index)
                    service = SERVICES[selected[index]]
                    _log(f"  EXIT  {service['name']} code={proc.returncode}", RED)
            if all(proc.poll() is not None for proc in _processes):
                _log("\n  All services exited", RED)
                break
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_all()
        _log("\n  All services stopped\n", BOLD)


if __name__ == "__main__":
    main()
