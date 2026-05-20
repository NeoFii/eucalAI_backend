# Phase 6: Relay Core - Validation Strategy

**Phase:** 6
**Slug:** relay-core
**Created:** 2026-05-19

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 0.24 |
| Config file | services/api-service/pytest.ini |
| Quick run command | `cd services/api-service && python -m pytest tests/ -x -q --timeout=30` |
| Full suite command | `cd services/api-service && python -m pytest tests/ --timeout=60` |

## Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RELAY-05 | API Key 本地验证 (Redis hit / miss / DB fallback) | unit | `pytest tests/test_relay_auth.py -x` | Wave 0 |
| RELAY-06 | 余额检查 Redis DECRBY + DB fallback | unit | `pytest tests/test_relay_billing.py -x` | Wave 0 |
| RELAY-07 | RoutingConfigCache load + version poll reload | unit | `pytest tests/test_config_cache.py -x` | Wave 0 |
| RELAY-08 | Admin INCR version 触发 cache reload | integration | `pytest tests/test_config_cache.py::test_version_bump -x` | Wave 0 |
| RELAY-09 | Call Log create_task 两步写入 | unit | `pytest tests/test_call_log_writer.py -x` | Wave 0 |
| RELAY-10 | RelayBillingService pre-consume/settle/refund | unit | `pytest tests/test_relay_billing.py -x` | Wave 0 |
| RELAY-13 | ChannelSelector weighted RR + cooldown + auto-disable | unit | `pytest tests/test_channel_selector.py -x` | Wave 0 |
| RELAY-14 | InferenceClient classify + circuit breaker | unit | `pytest tests/test_inference_client.py -x` | Wave 0 |

## Sampling Rate

- **Per task commit:** `cd services/api-service && python -m pytest tests/test_relay*.py tests/test_config_cache.py tests/test_channel_selector.py tests/test_inference_client.py tests/test_call_log_writer.py -x -q`
- **Per wave merge:** Full suite
- **Phase gate:** Full suite green before `/gsd:verify-work`

## Wave 0 Gaps

- [ ] `tests/test_relay_auth.py` — covers RELAY-05
- [ ] `tests/test_relay_billing.py` — covers RELAY-06, RELAY-10
- [ ] `tests/test_config_cache.py` — covers RELAY-07, RELAY-08
- [ ] `tests/test_call_log_writer.py` — covers RELAY-09
- [ ] `tests/test_channel_selector.py` — covers RELAY-13
- [ ] `tests/test_inference_client.py` — covers RELAY-14
- [ ] `tests/conftest.py` additions — mock Redis, mock DB session factory

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | API Key Bearer token validation (SHA256 hash lookup) |
| V3 Session Management | no | Relay 无 session，每次请求独立验证 |
| V4 Access Control | yes | API Key allowed_models + allow_ips 检查 |
| V5 Input Validation | yes | model name 白名单验证 (user_facing_aliases) |
| V6 Cryptography | no | 无加密操作 |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API Key 暴力破解 | Spoofing | SHA256 hash 比对 + TTLCache 限制查询频率 |
| 余额竞态超扣 | Tampering | Redis DECRBY 原子操作 + 负值检查回滚 |
| 路由配置注入 | Tampering | routing_settings 只有 admin 可写 + 类型验证 |
| 上游 URL SSRF | Tampering | _validate_upstream_url() 阻止内网地址 |
| 禁用 Key 继续使用 | Elevation | 主动 DEL token:{hash} + 60s TTL 兜底 |
| InferenceClient 凭证泄露 | Information Disclosure | X-Inference-Secret header 不记录到日志 |
