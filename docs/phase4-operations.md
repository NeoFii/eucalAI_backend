# Phase 4 Operations Runbook

> Phase 4 引入的运行时契约：/ready 探针、X-Request-ID 传播、testing-worker 存活探测、无 generic `DATABASE_URL` fallback。

## Compose Orchestration

`deploy/docker-compose.yml` 定义了 backend-app + router-service + testing-worker + testing-scheduler（scheduler 需 `--profile scheduler` 激活）+ redis 的联合部署。

### dependency probe

每个容器的 `healthcheck` 用 `scripts/runtime_probe.py` 做**依赖探测**，而非简单 HTTP ping：

- 普通 FastAPI 服务 → `http-ready --port <X>`
- testing-worker → `worker-ready --database-url-env TESTING_DATABASE_URL --redis-url-env BENCHMARK_QUEUE_REDIS_URL`

`depends_on.condition: service_healthy` 确保启动顺序正确。

## Env 契约

- 所有数据库 URL 必须指定服务前缀（`ADMIN_DATABASE_URL`、`USER_DATABASE_URL`、`ROUTER_DATABASE_URL`、`TESTING_DATABASE_URL`）
- **没有** generic `DATABASE_URL` fallback；误设会被 `check-env` 报警
- `BENCHMARK_QUEUE_REDIS_URL` 必须对 testing-worker 和 testing-scheduler 可达

## 存活探测命令速查

```bash
# API 服务
python scripts/runtime_probe.py http-ready --port 8001
python scripts/runtime_probe.py http-ready --port 8003

# worker
python scripts/runtime_probe.py worker-ready --database-url-env TESTING_DATABASE_URL --redis-url-env BENCHMARK_QUEUE_REDIS_URL
```

## 请求追踪

每个请求的 `X-Request-ID`（`common/observability.REQUEST_ID_HEADER`）会：
1. 若客户端传入则沿用；否则生成 UUID
2. 写入日志每一行
3. 通过 HMAC header 透传到下游服务
4. 回写到响应 header

可用于跨服务日志串联。
