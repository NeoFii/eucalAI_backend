#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Eucal AI 后端服务一键启动脚本

用法:
    python scripts/start_services.py              # 启动全部服务（生产模式）
    python scripts/start_services.py --dev         # 启动全部服务（开发模式，自动重载）
    python scripts/start_services.py user testing  # 仅启动指定服务
    python scripts/start_services.py --dev admin   # 开发模式启动指定服务
"""

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# 后端根目录
BACKEND_DIR = Path(__file__).resolve().parent.parent

# 服务定义：key 用于命令行参数选择
SERVICES = {
    "user": {
        "name": "用户服务",
        "app": "user.main:app",
        "port": 8000,
        "color": "\033[92m",  # 绿色
    },
    "admin": {
        "name": "管理服务",
        "app": "admin.main:app",
        "port": 8001,
        "color": "\033[94m",  # 蓝色
    },
    "testing": {
        "name": "测试服务",
        "app": "testing.main:app",
        "port": 8002,
        "color": "\033[95m",  # 紫色
    },
}

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
YELLOW = "\033[93m"

# 全局进程列表
_processes: list[subprocess.Popen] = []
_shutdown = threading.Event()


def _log(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{RESET}", flush=True)


def _stream_output(proc: subprocess.Popen, label: str, color: str) -> None:
    """持续读取子进程输出并加上服务标签前缀"""
    tag = f"{color}[{label}]{RESET} "
    try:
        for line in iter(proc.stdout.readline, ""):
            if _shutdown.is_set():
                break
            if line:
                sys.stdout.write(f"{tag}{line}")
                sys.stdout.flush()
    except (ValueError, OSError):
        pass


def _start_one(key: str, svc: dict, dev: bool) -> subprocess.Popen:
    """启动单个 uvicorn 服务"""
    cmd = [
        sys.executable, "-m", "uvicorn",
        svc["app"],
        "--host", "0.0.0.0",
        "--port", str(svc["port"]),
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
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
    )

    # 后台线程读取日志
    threading.Thread(
        target=_stream_output,
        args=(proc, svc["name"], svc["color"]),
        daemon=True,
    ).start()

    return proc


def _health_check(port: int, timeout: int = 15) -> bool:
    """轮询 /health 端点，确认服务可用"""
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def _shutdown_all() -> None:
    """终止全部子进程"""
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
    parser = argparse.ArgumentParser(description="Eucal AI 后端服务一键启动器")
    parser.add_argument(
        "services",
        nargs="*",
        choices=[*SERVICES.keys(), []],
        default=[],
        help="要启动的服务名（留空则启动全部）",
    )
    parser.add_argument("--dev", action="store_true", help="开发模式（启用 uvicorn --reload）")
    parser.add_argument("--no-check", action="store_true", help="跳过启动后健康检查")
    args = parser.parse_args()

    selected = args.services or list(SERVICES.keys())
    mode_label = "开发" if args.dev else "生产"

    _log(f"\n{'=' * 50}", BOLD)
    _log(f"  Eucal AI 后端服务启动器  [{mode_label}模式]", BOLD)
    _log(f"{'=' * 50}\n", BOLD)

    # 逐个启动
    for key in selected:
        svc = SERVICES[key]
        _log(f"  启动 {svc['name']}  → 端口 {svc['port']}", svc["color"])
        proc = _start_one(key, svc, dev=args.dev)
        _processes.append(proc)

    # 健康检查
    if not args.no_check:
        _log(f"\n  等待服务就绪...\n", YELLOW)
        time.sleep(2)
        for key in selected:
            svc = SERVICES[key]
            ok = _health_check(svc["port"])
            if ok:
                _log(f"  ✓ {svc['name']}  http://localhost:{svc['port']}/docs", svc["color"])
            else:
                _log(f"  ✗ {svc['name']}  端口 {svc['port']} 未响应，请检查日志", RED)

    _log(f"\n  按 Ctrl+C 停止所有服务\n", YELLOW)

    # 阻塞监控
    try:
        while not _shutdown.is_set():
            time.sleep(1)
            for i, proc in enumerate(list(_processes)):
                if proc.poll() is not None:
                    svc = SERVICES[selected[i]]
                    _log(f"  ⚠ {svc['name']} 已退出（代码 {proc.returncode}）", RED)
            if all(p.poll() is not None for p in _processes):
                _log("\n  所有服务均已退出", RED)
                break
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_all()
        _log(f"\n  所有服务已停止\n", BOLD)


if __name__ == "__main__":
    main()
