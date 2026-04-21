# 三个 FastAPI 项目优秀实践经验整理

> 基于以下三个开源项目的分析：
>
> - [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) — 官方全栈模板（⭐ 41.3k）
> - [XiaoLey/fastapi-starter-kit](https://github.com/XiaoLey/fastapi-starter-kit) — 开箱即用的 Web 开发脚手架
> - [arctikant/fastapi-modular-monolith-starter-kit](https://github.com/arctikant/fastapi-modular-monolith-starter-kit) — 模块化单体架构模板

---

## 一、项目概览与定位对比

| 维度 | Full-Stack Template | Starter Kit (XiaoLey) | Modular Monolith (arctikant) |
|------|--------------------|-----------------------|------------------------------|
| **定位** | 全栈 SaaS 应用模板 | 快速原型开发脚手架 | 企业级 API 后端架构 |
| **架构风格** | 前后端 Monorepo | 类 Laravel MVC 分层 | 模块化单体 + 分层架构 |
| **ORM** | SQLModel | SQLAlchemy (async) | SQLAlchemy 2.0+ (async) |
| **数据库** | PostgreSQL | PostgreSQL | PostgreSQL (psycopg3) |
| **认证方案** | JWT + 密码哈希 | JWT | JWT + Refresh Token + RBAC |
| **部署方案** | Docker Compose + Traefik | Docker | Docker + prestart.sh |
| **包管理** | uv | pip (requirements.txt) | uv |
| **适合场景** | 带前端的全栈 SaaS 产品 | 中小型 API 后端快速启动 | 长期维护的大型 API 系统 |

---

## 二、Full-Stack FastAPI Template 优秀实践

### 2.1 前后端一体的 Monorepo 结构

项目将 `backend/` 和 `frontend/` 放在同一仓库中，共享同一套 Docker Compose 编排，CI/CD 流程统一管理。

```
project/
├── backend/          # FastAPI 后端
├── frontend/         # React 前端
├── compose.yml       # 开发环境编排
├── compose.traefik.yml  # 生产部署编排
├── compose.override.yml # 本地覆盖配置
├── .env              # 统一环境变量
└── scripts/          # 通用脚本
```

**优点**：避免了多仓库的版本同步问题，前后端开发者可以在一个 PR 中同时修改接口和界面。

### 2.2 Copier 脚手架生成

通过 [Copier](https://copier.readthedocs.io) 工具实现项目模板化，用户只需回答几个配置问题（项目名、密码、SMTP 等），就能生成完整的定制化项目：

```bash
copier copy https://github.com/fastapi/full-stack-fastapi-template my-project --trust
```

主要配置变量包括：

- `project_name` — 项目名称
- `secret_key` — 安全密钥
- `first_superuser` — 超级管理员邮箱
- `postgres_password` — 数据库密码
- `sentry_dsn` — Sentry 监控 DSN

**优点**：相比直接 fork，"生成而非 fork"的模式让后续同步上游更新变得可行。

### 2.3 完整的生产部署链路

项目提供了从开发到生产的完整部署方案：

- **反向代理**：Traefik 自动处理 HTTPS 证书（Let's Encrypt）和负载均衡
- **CI/CD**：GitHub Actions 实现持续集成与部署，包含后端测试和 Docker Compose 测试两个工作流
- **本地邮件测试**：Mailcatcher 拦截所有发送的邮件用于本地调试
- **多环境配置**：`compose.override.yml` 用于开发覆盖，`compose.traefik.yml` 用于生产

### 2.4 SQLModel 统一数据模型

利用 SQLModel 将 Pydantic 校验模型和 SQLAlchemy ORM 模型合二为一：

```python
# 一个模型同时满足数据库映射和 API 数据校验
class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner_id: int = Field(foreign_key="user.id")
```

**优点**：减少了重复的模型定义代码，同时保留了 FastAPI 自动文档生成的能力。

### 2.5 安全密钥生成规范

项目明确要求更改所有默认密码（`changethis`），并提供标准的密钥生成方式：

```python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**优点**：避免了开发者遗漏安全配置的风险，`.env` 文件中所有敏感项都有明确标注。

---

## 三、XiaoLey/fastapi-starter-kit 优秀实践

### 3.1 Bootstrap 引导式初始化

独立的 `bootstrap/` 目录用于应用启动流程的编排：

```
project/
├── main.py           # 入口文件
├── api_app.py        # API 应用创建
├── bootstrap/        # 启动引导
│   ├── __init__.py
│   └── ...           # 数据库连接、中间件注册、路由挂载
├── app/              # 业务逻辑
├── config/           # 配置管理
└── scheduler.py      # 定时任务入口
```

**核心思路**：将数据库连接、中间件注册、路由挂载等初始化逻辑从 `main.py` 中解耦出来，类似 Laravel 的 ServiceProvider 模式。启动流程可配置、可扩展，新增一个中间件或路由只需在 `bootstrap/` 中添加注册逻辑，不需要修改入口文件。

### 3.2 配置与应用分离

专门的 `config/` 目录集中管理所有配置项：

```
config/
├── __init__.py
├── app.py            # 应用配置
├── database.py       # 数据库配置
└── ...               # 其他配置模块
```

配合 `.env.example` 模板，开发者可以清晰看到所有可调参数。这比将配置散落在代码各处要规范得多。

### 3.3 内置任务调度

项目自带 `scheduler.py` 入口，原生支持定时任务调度能力：

```bash
# 启动 API 服务
python main.py

# 启动定时任务调度器
python scheduler.py
```

**优点**：不需要额外引入 Celery 等重型依赖，对于中小型项目这是一个非常实用的设计——定时数据清理、报表生成、缓存刷新等场景开箱即用。

### 3.4 多环境依赖管理

分别提供三份依赖文件，针对不同环境做精细化拆分：

```
requirements.txt      # 生产依赖
requirements-dev.txt  # 开发依赖（含测试、Lint 工具等）
requirements-win.txt  # Windows 平台特定依赖
```

同时使用 Ruff 作为代码格式化与 Lint 工具（`ruff.toml` 配置），兼顾速度和规范性。

### 3.5 日志与存储规范

```
storage/
└── logs/             # 日志文件集中存放

database/
└── postgresql/       # 数据库相关文件
```

**优点**：明确区分了运行时产生的文件（日志、上传文件）和代码文件的存放位置，符合 12-Factor App 的日志处理原则。

---

## 四、arctikant/fastapi-modular-monolith-starter-kit 优秀实践

### 4.1 模块化单体架构

每个业务模块拥有独立的路由、服务、仓储层，模块之间通过明确的边界隔离：

```
app/
├── core/             # 核心层（通用基类、依赖注入、中间件）
│   ├── db.py         # BaseModel、BaseRepository、SoftDeleteMixin
│   ├── deps.py       # 公共依赖（DBSessionDep 等）
│   └── models.py     # 统一模型导入（供 Alembic 识别）
├── modules/
│   ├── auth/         # 认证模块
│   │   ├── router.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   ├── model.py
│   │   └── schema.py
│   └── user/         # 用户模块（相同结构）
└── ...
```

**优点**：既保持了单体部署的简单性，又为未来拆分微服务留下了空间。新增业务模块只需复制模块结构并注册路由即可。

### 4.2 BaseRepository 通用 CRUD + SoftDeleteMixin

```python
# BaseRepository 提供的通用能力
class BaseRepository:
    async def get(self, model_id: int) -> Model
    async def get_list(self, params: ListParams) -> PaginatedResult
    async def create(self, data: dict) -> Model
    async def update(self, model_id: int, data: dict) -> Model
    async def delete(self, model_id: int) -> None
    async def commit(self) -> None

# 通过 Mixin 添加软删除
class User(BaseModel, SoftDeleteMixin):
    ...
```

**优点**：通过继承 `BaseRepository` 获得标准化的增删改查，通过 Mixin 组合获得软删除等扩展功能，大幅减少了样板代码。`ListParams` 统一了排序、过滤、分页的参数格式。

### 4.3 务实的分层事务管理

作者有意将 `AsyncSession` 传入 Service 层而非封装在 Repository 内部。决策理由：

1. **确定不会更换 ORM**：不需要为此构建额外的抽象层
2. **主数据库将保持 SQL**：其他数据库（如 ElasticSearch）是补充而非替代
3. **事务灵活性**：可以在 Service 层管理事务，在一个事务中组合多个 Repository 的调用

```python
class AuthService:
    async def delete(self, user_id: int) -> None:
        # 在同一个事务中操作多个 Repository
        await self._refresh_token_repository.delete_by_user_id(user_id)
        await self._user_repository.delete(model_id=user_id)
        await self._user_repository.commit()  # 统一提交
```

**启示**：架构设计应务实优于教条。在明确不会更换技术栈的前提下，适度打破分层纯粹性换取开发便利是合理的。

### 4.4 全方位基础设施集成

项目提供了后端应用常见功能的基础实现：

| 功能 | 技术选型 | 说明 |
|------|---------|------|
| 数据库 | PostgreSQL + psycopg3 | 全异步驱动 |
| ORM | SQLAlchemy 2.0+ (async) | 异步 Session 管理 |
| 迁移 | Alembic | 版本化数据库变更 |
| 限流 | fastapi-limiter + Redis | 接口级速率限制 |
| 缓存 | Redis | 通用缓存层 |
| 队列 | Redis (基于事件) | 异步任务处理 |
| 邮件 | 异步邮件服务 | 模板化邮件发送 |
| 测试 | Pytest | 独立的 `.test.env` 配置 |
| 日志 | 结构化日志 | 统一日志格式 |

**优点**：Redis 同时承担缓存、限流和队列的职责，减少了基础设施复杂度。所有与外部服务交互的库都采用异步方式，保持了一致的非阻塞 I/O 模型。

### 4.5 测试环境隔离

```
.sample.env   # 开发环境配置模板
.test.env     # 测试专用环境配置
tests/        # 独立的测试目录
```

**优点**：测试使用独立的环境配置，可以指向单独的测试数据库，避免了测试数据污染开发数据。

---

## 五、三者共同的最佳实践

以下实践在三个项目中形成了共识，可作为任何 FastAPI 项目的基线配置：

### 5.1 数据库迁移管理

三个项目均使用 **Alembic** 进行数据库迁移。版本化管理数据库 Schema 变更，支持升级与回滚：

```bash
alembic revision --autogenerate -m "add user table"
alembic upgrade head
alembic downgrade -1
```

### 5.2 Docker 化开发与部署

全部采用 **Docker / Docker Compose** 统一开发和部署环境，确保"本地能跑，线上也能跑"的一致性。

### 5.3 环境变量集中管理

通过 `.env` 文件 + Pydantic `BaseSettings` 管理配置：

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False

    class Config:
        env_file = ".env"
```

### 5.4 JWT 认证方案

三个项目均采用 JWT 作为标准认证方案，配合密码哈希存储，是当前 FastAPI 社区的主流选择。

### 5.5 异步优先

三个项目都倾向于使用异步数据库驱动和异步 HTTP 客户端，充分利用 FastAPI 基于 ASGI 的异步优势。

---

## 六、选型建议

- **需要全栈应用（含前端 UI）**→ 选 Full-Stack Template，React + FastAPI + Traefik 一站式解决
- **需要快速启动一个 API 后端**→ 选 XiaoLey Starter Kit，开箱即用且内置任务调度
- **需要长期维护的企业级 API**→ 选 Modular Monolith，模块化架构支持团队协作与长期演进

三个项目并不互斥——完全可以将 Modular Monolith 的分层架构思想和 BaseRepository 模式，融合到 Full-Stack Template 的全栈骨架中，再借鉴 Starter Kit 的 Bootstrap 初始化模式，打造适合自己团队的最佳实践。