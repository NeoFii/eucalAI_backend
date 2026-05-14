# 性能与稳定性改造优先级

> 版本：2026-05-02
> 作用域：services/{router,admin,user,inference}-service
> 评估依据：dev.md《FastAPI 生产部署指南（2026）》§2 / §5 / §13 / §14
> 状态：经一轮校正后定稿

---

## 1. 评估框架

按照 dev.md §2「不同负载类型的部署关注点」分两条线对照：

- **I/O 密集型**（router / admin / user / inference 的 HTTP 边界）：异步 DB 驱动、连接池、合理超时、较少 worker + 更高并发
- **AI/ML 负载**（inference-service）：GPU 实例、模型热启动、缓存、队列推理、独立模型服务

每个改造项标注：
- **性质**：性能 / 鲁棒 / 正确性 / 可观测
- **影响面**：具体文件路径
- **优先级**：🔥🔥（紧急，本轮必做） / 🔥（重要，下一轮） / 中

---

## 2. 优先级总表

| 优先级 | 项 | 性质 | 影响面 |
|---|---|---|---|
| 🔥🔥 | **httpx 单例化（连接复用为主、超时为辅）** | 性能 + 鲁棒 | 4 个服务 `common/internal.py:351`、admin `pool_service.py:455/522`、admin `health_check_service.py:79/104` |
| 🔥🔥 | **router circuit breaker 状态搬 Redis** | **正确性** | router `services/inference_client.py`，外加 4 个服务共有的 `common/internal.py:_CIRCUIT_BREAKERS` |
| 🔥🔥 | **DB 池补 `pool_recycle` / `pool_timeout`** | 鲁棒性 | admin/user `common/db/runtime.py:29-35` |
| 🔥 | inference 启动 warmup forward + `cudnn.benchmark=True` | 性能（p99） | inference `main.py` lifespan |
| 🔥 | readiness / liveness 拆分 | K8s 行为正确性 | 4 个服务 `/ready` `/health` |
| 🔥 | Prometheus 指标导出 | 可观测性 | 4 个服务（DB 池 / GPU 闸门 / arq 队列） |
| 中 | gunicorn 替换 uvicorn `--workers`（**仅 router/admin/user**，inference 排除） | 优雅关闭 / 自愈 | 3 个 Dockerfile，**inference-service 不动** |
| 中 | classify 结果短期缓存 | 性能 | inference `ClassifyService.classify` |
| 中 | OOM 自愈 `try/except torch.cuda.OutOfMemoryError` | 鲁棒性 | inference `classify_service.py` |
| 中 | OpenTelemetry exporter 接入 | 可观测性 | 已有 trace_id，缺导出端 |
| ❌ 撤回 | inference micro-batching | 需先解决 hook 语义 / 精度 | 见下文备注 |

---

## 3. 关键校正记录

### ✅ 校正 1：gunicorn 不能用于 inference-service

inference-service 的 GPU 并发控制是**进程级 `asyncio.Semaphore`**（`classify_service.py:24`），其语义只在单进程内成立。多 worker 会：
- 让每个进程各自持有 `Semaphore(N)`，实际 GPU 并发变成 `workers × N`
- 多进程同时持有 model weights，**显存 ×N**，bfloat16 模型 ×2 起步就可能爆
- 多进程争抢同一 CUDA context，cuDNN autotune 反复触发

**结论**：gunicorn 替换只针对 router / admin / user 三个无状态服务，inference-service 必须保留 `uvicorn --workers 1`。

### ✅ 校正 2：CB 升到 🔥🔥（正确性问题，不只是鲁棒性）

router 4 worker × 各自独立 CB 计数：
- 阈值 3 失败 → 至少打到 4×3 = 12 次失败请求才能让所有 worker 全部熔断
- 每次失败附带 `max_retries=1` → 实际 12×2 = **24 次穿透到下游**
- 30s cooldown 后还要再来一轮——熔断器从"快速失败"退化成"勉强限速"

**附加发现**：除了 `InferenceClient` 的 CB，还有 `common/internal.py:_CIRCUIT_BREAKERS` 全局字典——4 个服务都有同样的进程级 CB（vendored copy）。改造需一并处理。

### ✅ 校正 3：httpx 单例化的核心收益是连接复用，不是超时

| 收益 | 量级 |
|---|---|
| TCP 三次握手免除 | 同机房 ~0.5ms，跨可用区 1-3ms |
| TLS 握手免除 | HTTPS 上游通常省 5-15ms |
| HTTP/2 多路复用 | 多请求共享连接 |
| Keep-Alive 池本身 | 避免高 QPS 下 `TIME_WAIT` 堆积 |
| 分层超时 | 次要 |

router→inference 这条路径每个 chat 请求都走一次，是全系统最高频内部 RPC。

### ❌ 校正 4：micro-batching 撤回

`router_engine.py:265-307` 实际行为：
```python
cache[layer_idx] = hook_input[0][:, -1, :]    # 取 padding 后的"位置 -1"
sample_vecs.append(cache[l][0, start:end]...) # batch index 硬编码 0
```

问题：
1. `[:, -1, :]` 是按 padding 后的位置，短句子被 right-pad 之后此处全是 pad token，提取出来是噪声
2. `[0, ...]` 硬编码 batch_size=1
3. 改造需重写 hook 逻辑、按真实 `attention_mask.sum(-1) - 1` 算每条样本末位置，且会改变特征语义本身——可能影响已训练好的 CG-TabM 上游精度

**结论**：从优先级表撤掉。后续若真成瓶颈，正确路径是 vLLM 风格的 continuous batching，非简单 static batch；属独立研究项。

---

## 4. 本轮（🔥🔥）执行顺序

按"低风险高收益→正确性问题→鲁棒性"的顺序：

1. **httpx 单例化**（详见 `docs/plans/01-httpx-singleton.md`）—— 改动面小、零功能风险、立刻可见的延迟改善
2. **CB 状态搬 Redis**（详见 `docs/plans/02-cb-redis.md`）—— 修正多 worker 下熔断失效，影响生产可靠性
3. **DB 池补全**（详见 `docs/plans/03-db-pool.md`）—— 防 MySQL `wait_timeout` 黑天鹅，单文件改动

每项独立可发布，不存在跨项依赖。

---

## 5. 不在本轮范围

- gunicorn 替换 / readiness 拆分 / Prometheus / OTel：列入下一轮
- inference 优化（warmup / cache / OOM 自愈）：列入下一轮
- micro-batching：撤回，需先做精度评估
