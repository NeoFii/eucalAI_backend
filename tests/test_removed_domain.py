from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOVED_TOKENS = (
    "testing" + "_service",
    "testing" + "-service",
    "TESTING" + "_DATABASE_URL",
    "testing" + "-worker",
    "testing" + "-scheduler",
    "BENCHMARK" + "_QUEUE_REDIS_URL",
)
ACTIVE_SCAN_PATHS = (
    "src",
    "scripts",
    "deploy",
    "migrations",
    "tests",
    "README.md",
    ".env.example",
    "pyproject.toml",
)


def test_backend_app_import_does_not_load_removed_package(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("INTERNAL_SECRET", "internal-secret")
    monkeypatch.setenv("ADMIN_DATABASE_URL", "mysql+aiomysql://root:pw@localhost/admin")
    monkeypatch.setenv("USER_DATABASE_URL", "mysql+aiomysql://root:pw@localhost/user")

    sys.modules.pop("backend_app.main", None)
    for name in list(sys.modules):
        if name == REMOVED_TOKENS[0] or name.startswith(REMOVED_TOKENS[0] + "."):
            sys.modules.pop(name, None)

    importlib.import_module("backend_app.main")

    assert not any(
        name == REMOVED_TOKENS[0] or name.startswith(REMOVED_TOKENS[0] + ".")
        for name in sys.modules
    )


def test_service_migration_configs_are_admin_and_user_only():
    from scripts.migrate import SERVICE_CONFIGS

    assert set(SERVICE_CONFIGS) == {"admin-service", "user-service"}


def test_active_runtime_files_do_not_reference_removed_domain():
    hits: list[str] = []
    for relative in ACTIVE_SCAN_PATHS:
        path = ROOT / relative
        files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        for file_path in files:
            if ".git" in file_path.parts or "__pycache__" in file_path.parts:
                continue
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for token in REMOVED_TOKENS:
                if token in text:
                    hits.append(f"{file_path.relative_to(ROOT)} contains {token}")

    assert hits == []
