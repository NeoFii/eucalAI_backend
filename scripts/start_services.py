#!/usr/bin/env python
"""
启动所有后端服务的脚本

用法:
    python scripts/start_services.py

或者直接运行:
    python -m scripts.start_services
"""

import subprocess
import sys
import os
import signal
import time

# 添加 backend 到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

# 服务配置
SERVICES = [
    {
        "name": "User Service",
        "module": "user.main",
        "port": 8000,
    },
    {
        "name": "Admin Service",
        "module": "admin.main",
        "port": 8001,
    },
]

processes = []


def signal_handler(sig, frame):
    """捕获 Ctrl+C 信号"""
    print("\n正在停止所有服务...")
    for p in processes:
        p.terminate()
    sys.exit(0)


def main():
    global processes

    print("=" * 50)
    print("  Eucal AI 后端服务启动器")
    print("=" * 50)
    print()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)

    # 启动所有服务
    for svc in SERVICES:
        print(f"启动 {svc['name']} (端口 {svc['port']})...")

        proc = subprocess.Popen(
            [sys.executable, "-m", svc["module"]],
            cwd=backend_dir,
            env=os.environ.copy(),
        )
        processes.append(proc)

    print()
    print("服务已启动:")
    for svc in SERVICES:
        print(f"  - {svc['name']}: http://localhost:{svc['port']}")
    print()
    print("按 Ctrl+C 停止所有服务")
    print()

    # 等待并监控进程
    try:
        while True:
            time.sleep(1)
            # 检查进程是否退出
            for i, p in enumerate(processes):
                if p.poll() is not None:
                    print(f"警告: {SERVICES[i]['name']} 已退出!")
    except KeyboardInterrupt:
        pass
    finally:
        # 停止所有进程
        for p in processes:
            p.terminate()
        print("\n所有服务已停止")


if __name__ == "__main__":
    main()
