# 数据库迁移

Alembic 迁移文件是本仓库唯一的 schema 权威来源。

## 活跃服务

| 服务 | Baseline | 表数量 |
|------|----------|--------|
| `admin-service` | `20260423_01_admin_baseline` | 9（含 seed data） |
| `user-service` | `20260423_01_user_baseline` | 10 |

每个 service 当前只有一个 baseline 迁移，使用显式 DDL（非 ORM metadata 反射），
包含全部建表、索引、外键约束和 seed 数据。后续新增迁移接在 baseline 之后即可。

## 常用命令

```bash
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service upgrade head
uv run migrate --service admin-service revision -m "add column" --autogenerate
uv run bootstrap-databases
```

## 共享环境

所有 service 的迁移命名空间共享 `migrations/_env_shared.py`。每个 service 目录包含
一个 `env.py` 代理、一个 `script.py.mako` 和一个 `versions/` 目录。

## 新增迁移

新迁移的 `down_revision` 指向当前 service 的 head revision：

```python
revision = "20260424_01_your_description"
down_revision = "20260423_01_admin_baseline"  # 或 user_baseline
```

## SQL 快照

`scripts/sql/*.sql` 是用于运维审查的快照文件，运行时代码不会读取它们。
