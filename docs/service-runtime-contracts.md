# Service Runtime Contracts

> 每个服务的运行时契约：lifespan、健康探针、共享 env、跨服务调用、日志约定。

## 共享 env 要求

所有服务都要求：
- `JWT_SECRET_KEY`
- `INTERNAL_SECRET`

各服务自己的数据库 URL：
- `ADMIN_DATABASE_URL` — admin 域
- `USER_DATABASE_URL` — user 域
- `ROUTER_DATABASE_URL` — router-service
- `TESTING_DATABASE_URL` — testing 域（testing-worker 和 testing-scheduler 共用）

不存在通用 `DATABASE_URL` fallback。

## 健康探针

每个 FastAPI app 暴露：
- `GET /health` — 进程存活（不查 DB）
- `GET /ready` — 依赖就绪检查（由 `common/health.py::build_readiness_response` 构造，经 `install_observability` 注入请求 ID）

docker-compose 健康检查脚本：
```bash
python scripts/runtime_probe.py http-ready --port <PORT>
```

## testing-worker 契约

testing-worker 是非 FastAPI 的 arq 消费者，探活使用：
```bash
python scripts/runtime_probe.py worker-ready --database-url-env TESTING_DATABASE_URL --redis-url-env BENCHMARK_QUEUE_REDIS_URL
```

运行时依赖：
- `TESTING_DATABASE_URL`
- `BENCHMARK_QUEUE_REDIS_URL`
- `TESTING_SECRET_MASTER_KEY`（用于解密 provider probe key 密文）

## HMAC 跨服务调用

所有跨服务 HTTP 调用经过 HMAC 签名（`common/internal.py`），Header：
- `X-Internal-Service` — 调用方标识
- `X-Internal-Timestamp` — Unix 秒
- `X-Internal-Signature` — HMAC-SHA256

断路器在 `common/internal.py::_CIRCUIT_BREAKERS`，进程内状态，多副本各自独立。

## 日志

所有服务启动时调用 `configure_logging`、`install_observability`；日志是结构化 JSON，包含 `request_id`（由 `REQUEST_ID_HEADER` 传播）。
