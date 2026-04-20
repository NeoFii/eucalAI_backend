# Phase 2 Cutover Runbook

> 历史运维工具：从共享数据库切换到 database-per-service 的流程记录。`scripts/phase2_cutover.py` + `migrations/cutover_manifest.json` 是工具入口。

## 入口命令

```bash
uv run phase2-cutover --check-env
uv run phase2-cutover --dry-run
uv run phase2-cutover
```

## 执行顺序

按 `migrations/cutover_manifest.json::execution_order` 描述，依次处理：

1. router-service
2. testing-service
3. admin-service
4. user-service

## 每个服务切换要点

### router-service
对 `ROUTER_DATABASE_URL` 目标库执行 Alembic baseline + router-specific 迁移；切换完成后运行 `post_cutover_checks`。

### testing-service
对 `TESTING_DATABASE_URL` 初始化全部 testing 域表 + 视图；确认 `admin-service` 内部 identity 端点可达。

### admin-service
初始化 admin schema；确认 bootstrap-super-admin 凭据已配置。

### user-service
初始化 user schema；确认 admin 的邀请码 internal 端点可达。

## 状态

数据库-per-服务切换已全部完成（backend-app 合并后仍保留每库独立）。本脚本主要作为历史参考和紧急恢复工具。
