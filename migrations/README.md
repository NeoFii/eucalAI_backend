# Database Migrations

## Schema 真理来源

- **Alembic revision 是唯一的 schema 真理**。每一次 schema 变更都通过
  `uv run migrate --service <X> revision --autogenerate -m "..."` 生成新的
  revision 文件，然后人工审查。
- `scripts/sql/*.sql` 是 schema 快照，由 `scripts/phase2_cutover.py` 引用
  （见 `migrations/cutover_manifest.json`）。**它们不是真理，也不被任何 runtime
  代码读取**。若需要重新生成，请从对应的数据库 dump：

  ```bash
  mysqldump --no-data --skip-triggers --compact <db> > scripts/sql/<svc>_schema.sql
  ```

- `migrations/cutover_manifest.json` 描述每个服务拥有的表、外部引用列、前置
  检查。主要供 `phase2-cutover` 运维工具使用；开发者可将其视为当前 schema
  所有权的活文档。

## 统一 Alembic 环境

所有服务共享 `migrations/_env_shared.py` 的 Alembic 入口逻辑。每个服务的
`migrations/<service>/env.py` 都是 3 行代理：

```python
from migrations._env_shared import run_env
run_env()
```

服务身份通过 `scripts/migrate.py::build_alembic_config` 注入到 Alembic 主
选项：`service_name`、`service_package`、`database_env`。共享 env 据此动态
导入对应服务的 ORM metadata 并解析 DB URL。

## 常用命令

```bash
# 单服务 upgrade
uv run migrate --service admin-service upgrade head

# 单服务新建 autogenerate revision
uv run migrate --service user-service revision -m "add new column" --autogenerate

# 查看 head / history
uv run migrate --service testing-service history
uv run migrate --service router-service heads

# 所有服务一把跑（等价于循环 5 次 upgrade head）
uv run bootstrap-databases
```

## 目录布局

```
migrations/
├── _env_shared.py          # 唯一的 Alembic env 逻辑
├── helpers.py              # revision 里可复用的工具函数
├── cutover_manifest.json   # phase2-cutover 所有权与依赖图（活文档）
├── README.md               # 本文件
├── <service>/
│   ├── env.py              # 3-line 代理到 _env_shared.run_env()
│   ├── script.py.mako      # revision 模板（Alembic 标配）
│   └── versions/           # 服务自己的线性 revision 链
```

## 新增一个服务的迁移空间

1. 建 `migrations/<new_service>/env.py`（复用上述 3 行代理）
2. 建 `migrations/<new_service>/script.py.mako`（从现有服务复制即可）
3. 建 `migrations/<new_service>/versions/__init__.py`（空文件）
4. 在 `scripts/migrate.py::SERVICE_CONFIGS` 中注册 `ServiceMigrationConfig`
5. 在 `scripts/check_service_environment.py::SERVICE_DATABASE_ENV` 中注册
   对应的 `*_DATABASE_URL`

不需要再写新的 Alembic env.py——`_env_shared.run_env` 自动处理。

## 时区约定

所有 `DateTime` 列存储 **UTC naive**（底层 MySQL `DATETIME`，不带时区）。应用
层写入前经过 `common/utils/timezone.py::now()` 转为 UTC；响应序列化时按
`TIMEZONE` env（默认 `Asia/Shanghai`）转换展示。

未来若迁移到 PostgreSQL，`DateTime` 应升级为 `TIMESTAMPTZ`，届时该约定需要
重新审视（数据库会提供真正的时区感知）。
