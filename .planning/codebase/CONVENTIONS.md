# Coding Conventions

**Analysis Date:** 2026-05-20

## Naming Patterns

**Files:**
- `snake_case.py` for all Python modules
- Models: singular noun (`user.py`, `pool.py`, `admin_user.py`)
- Repositories: `{entity}_repository.py` (`user_repository.py`, `pool_repository.py`)
- Services: `{entity}_service.py` (`auth_service.py`, `pool_service.py`)
- Controllers: domain noun or verb (`auth.py`, `billing.py`, `pools.py`)
- Schemas: match the controller they serve (`auth.py`, `billing.py`)

**Classes:**
- `PascalCase` for all classes
- Models: singular noun (`User`, `AdminUser`, `PoolAccount`)
- Repositories: `{Entity}Repository` (`UserRepository`, `PoolRepository`)
- Services: `{Entity}Service` (`AuthService`, `PoolService`)
- Schemas: `{Action}{Entity}Request` / `{Entity}Response` / `{Entity}ResponseData`
- Enums: `PascalCase` with `IntEnum` base (`AdminRole`, `PoolAccountStatus`)

**Functions/Methods:**
- `snake_case` for all functions and methods
- Repository methods: verb-first (`get_by_email`, `list_users`, `count_since`)
- Service methods: `@staticmethod` with verb-first (`register`, `login`, `create_pool`)
- Private helpers: leading underscore (`_set_auth_cookies`, `_escape_like`)

**Variables:**
- `snake_case` for all variables
- Constants: `UPPER_SNAKE_CASE` (`MAX_ACTIVE_SESSIONS`, `USER_ACCESS_COOKIE`)
- Settings fields: `UPPER_SNAKE_CASE` (`DATABASE_URL`, `JWT_SECRET_KEY`)

## Import Organization

**Order (enforced by ruff `I` rule):**
1. `from __future__ import annotations` (always first)
2. Standard library (`logging`, `os`, `datetime`, `typing`)
3. Third-party (`fastapi`, `sqlalchemy`, `pydantic`, `redis`)
4. Local application (`api_service.common.*`, `api_service.core.*`, `api_service.models.*`)

**Path Aliases:**
- No path aliases configured; all imports use full dotted paths from `api_service.*`
- Common shared code: `from api_service.common.schemas import BaseResponse`
- DB access: `from api_service.core.db import get_db`
- Models: `from api_service.models import User, AdminUser`

**Pattern — env setup before imports in tests:**
```python
import os
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

import pytest  # noqa: E402
from api_service.core.db import get_db  # noqa: E402
```
<!-- CONVENTIONS_PART2 -->

## Error Handling

**Exception Hierarchy:**
All business exceptions inherit from `APIException` (which extends FastAPI's `HTTPException`):

```python
# Base: api_service/common/core/exceptions.py
class APIException(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str = "error"):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
```

**Naming convention:** `{Domain}{Problem}Exception`
- `EmailAlreadyExistsException`, `InvalidCredentialsException`, `ApiKeyNotFoundException`

**Raising pattern — raise domain exceptions from service layer:**
```python
# In service layer (api_service/services/auth_service.py)
if await user_repo.get_by_email(email):
    raise EmailAlreadyExistsException()
```

**Controller pattern — let exceptions propagate, log only unexpected errors:**
```python
try:
    user = await AuthService.register(db, request)
except Exception:
    logger.exception("用户注册失败")
    raise
```

**Global exception handlers** (`api_service/common/core/exception_handlers.py`):
- `APIException` -> JSON `{"code": status_code, "message": detail, "data": ""}`
- `RequestValidationError` -> JSON `{"code": 422, "message": "Validation failed", "data": errors}`
- Unhandled `Exception` -> JSON `{"code": 500, "message": "Internal server error", "data": ""}`

**Error messages:** Use Chinese for user-facing messages ("该邮箱已被注册", "验证码错误").

## Logging

**Framework:** Python `logging` with structured JSON output via `api_service.common.observability`.

**Structured event logging pattern:**
```python
from api_service.common.observability import log_event

log_event(logger, logging.INFO, "userRegisterSuccess", uid=user.uid)
log_event(logger, logging.WARNING, "userLoginLocked", uid=user.uid)
log_event(logger, logging.ERROR, "unhandled_exception", method=request.method, path=request.url.path, exc_info=True)
```

**Logger naming:** Use `logging.getLogger(__name__)` at module level.

**Log schema fields (auto-injected):**
- `timestamp`, `level`, `service`, `traceId`, `spanId`, `requestId`, `event`, `logger`, `env`
- Sensitive values auto-redacted via regex patterns (passwords, API keys, tokens)

**Ring buffer:** In-memory `RingBufferHandler` (2000 entries) for admin "service logs" panel.

## Configuration Management

**Pattern:** Pydantic Settings with env file loading.

```python
# api_service/common/config.py - shared base
class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

# api_service/core/config.py - service-specific
class ApiServiceSettings(BaseServiceSettings):
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/eucal_ai"
    # ...

@lru_cache
def get_settings() -> ApiServiceSettings:
    return ApiServiceSettings()

settings = get_settings()
```

**Access pattern:** Import the singleton `settings` object directly:
```python
from api_service.core.config import settings
```

**Validation:** `@model_validator(mode="after")` enforces required secrets at startup (JWT_SECRET_KEY, INTERNAL_SECRET).

## Dependency Injection (FastAPI)

**Database session — `get_db` generator dependency:**
```python
from api_service.core.db import get_db

@router.post("/auth/login")
async def login(db: AsyncSession = Depends(get_db)):
    ...
```

**Auth dependencies — layered guards:**
```python
# Layer 1: Extract + validate JWT -> return User/AdminUser
from api_service.core.dependencies import get_current_user, get_current_admin

# Layer 2: Business policy checks (status, role)
from api_service.core.policies import require_active_user, require_super_admin

# Usage in routes:
@router.get("/auth/me")
async def get_me(current_user: User = Depends(require_active_user)):
    ...

@router.post("/pools")
async def create_pool(admin: AdminUser = Depends(require_super_admin)):
    ...
```

**Repository instantiation — per-request, not injected:**
```python
async def login(db: AsyncSession = Depends(get_db)):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(email)
```

## Response Format Conventions

**Canonical envelope (`api_service/common/schemas.py`):**
```python
class BaseResponse(BaseModel):
    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Message")

class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None
```

**Response pattern in controllers:**
```python
return LoginResponse(
    code=200,
    message="登录成功",
    data=LoginResponseData(user=UserData(...), access_token=token),
)
```

**Paginated responses:**
```python
from api_service.common.api.pagination import PaginatedResponse

class PoolListResponse(BaseResponse):
    data: Optional[PaginatedResponse[PoolResponse]] = None
```

**User-facing IDs:** Always expose `uid` (NanoID string), never internal numeric `id`.

## Database Access Patterns

**Repository pattern:**
```python
# api_service/common/infra/db/repository.py
class BaseRepository(Generic[ModelT]):
    def __init__(self, session, model: type[ModelT] | None = None):
        self.session = session
        self.model = model

    async def find_one(self, *filters) -> ModelT | None: ...
    async def get_list(self, params: ListParams, *, extra_filters=None) -> PaginatedResult[ModelT]: ...
    def add(self, instance: ModelT) -> None: ...
```

**Derived repositories add domain-specific queries:**
```python
class UserRepository(BaseRepository[User]):
    def __init__(self, session):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
```

**Session management — caller owns commit:**
```python
# Service layer commits explicitly
user_repo.add(user)
await db.commit()
await db.refresh(user)
```

**Soft-delete support:** `BaseRepository._base_query()` auto-filters `deleted_at IS NULL` when the model has a `deleted_at` column.

**For-update locking:**
```python
async def get_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
    statement = select(User).where(User.id == user_id)
    if for_update:
        statement = statement.with_for_update()
    return (await self.session.execute(statement)).scalar_one_or_none()
```

## Pydantic Model/Schema Conventions

**Request schemas:**
- Inherit from `BaseModel`
- Use `Field(...)` for required fields with descriptions
- Use `@field_validator` for input normalization (email lowercase, code format)
- Use `@model_validator(mode="after")` for cross-field validation (password strength)

```python
class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="Login email")
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)
```

**Response schemas:**
- Data models inherit from `DateTimeModel` (auto-serializes datetime to ISO-8601)
- Response wrappers inherit from `BaseResponse` with `data: Optional[DataModel] = None`

**ORM models:**
- Inherit from `Base` + mixins (`SnowflakeIdMixin`, `TimestampMixin`, `SoftDeleteMixin`)
- Use `Column(...)` with explicit `comment=` for documentation
- Relationships use `lazy="noload"` by default

## Authentication/Authorization in Routes

**User domain:** Bearer token or `user_access_token` cookie -> `get_current_user` -> `require_active_user`

**Admin domain:** Bearer token or `admin_access_token` cookie -> `get_current_admin` (with blacklist check) -> `require_active_admin` / `require_super_admin`

**Relay domain (API Key auth):**
```python
from api_service.relay.auth import require_api_key

# Three-tier validation: in-process cache -> Redis -> DB
principal: ValidatedApiKey = await require_api_key(request, authorization, x_api_key)
```

**Cookie conventions:**
- User cookies: `user_access_token`, `user_refresh_token` (path="/")
- Admin cookies: `admin_access_token`, `admin_refresh_token` (path="/")
- Settings: `httponly=True`, `secure=settings.COOKIE_SECURE`, `samesite=settings.COOKIE_SAMESITE`

## Code Style

**Formatting (ruff):**
- Line length: 100 (E501 ignored)
- Quote style: double quotes
- Indent: spaces (4)
- Target: Python 3.10

**Linting (ruff):**
- Rules: E, F, I, N, W, UP, B, C4, SIM
- Import sorting enforced (`I`)

**Type checking (mypy):**
- `python_version = "3.10"`
- `warn_return_any = true`
- `disallow_untyped_defs = true`

**Service class pattern:** Use `@staticmethod` methods (no instance state):
```python
class AuthService:
    @staticmethod
    async def register(db: AsyncSession, data: RegisterRequest) -> User:
        ...
```

---

*Convention analysis: 2026-05-20*
