"""GPU Memory Stress Test for Inference Service.

Directly loads the HybridIntegratedDifficultyRouter and measures GPU memory
usage under increasing concurrency levels. Produces CSV + JSON + text reports.

Usage:
    cd /root/autodl-tmp/eucalAI_backend
    PYTHONPATH=services/inference-service/src python gpu_stress_test/gpu_stress_test.py \
        --concurrency 1,2,4,8,16,32 \
        --input-lengths 256,1024,4096 \
        --requests-per-level 20
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import torch

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StressTestConfig:
    concurrency_levels: list[int] = field(default_factory=lambda: [1, 2, 4, 8, 16, 32])
    input_lengths: list[int] = field(default_factory=lambda: [256, 1024, 4096])
    requests_per_level: int = 20
    warmup_requests: int = 3
    cooldown_seconds: float = 5.0
    stop_on_oom: bool = True
    model_paths_config: str = "services/inference-service/config/model_paths.json"
    output_dir: str = "gpu_stress_test/results"


@dataclass
class InferenceResult:
    request_id: str
    success: bool
    latency_ms: float
    error: str | None = None
    is_oom: bool = False


@dataclass
class MemorySnapshot:
    peak_allocated_mb: float
    peak_reserved_mb: float
    mean_allocated_mb: float
    p95_allocated_mb: float
    samples_count: int


@dataclass
class LevelResult:
    input_length: int
    concurrency: int
    memory: MemorySnapshot
    latencies_ms: list[float]
    success_count: int
    failure_count: int
    oom_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float


# ---------------------------------------------------------------------------
# Memory Sampler
# ---------------------------------------------------------------------------

class MemorySampler:
    """Background thread that polls torch.cuda memory at ~50ms intervals."""

    def __init__(self, device: torch.device):
        self._device = device
        self._samples_allocated: list[float] = []
        self._samples_reserved: list[float] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        torch.cuda.reset_peak_memory_stats(self._device)
        self._samples_allocated.clear()
        self._samples_reserved.clear()
        self._running = True
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self) -> MemorySnapshot:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        peak_alloc = torch.cuda.max_memory_allocated(self._device) / (1024 ** 2)
        peak_reserved = torch.cuda.max_memory_reserved(self._device) / (1024 ** 2)

        samples = self._samples_allocated
        if not samples:
            samples = [torch.cuda.memory_allocated(self._device) / (1024 ** 2)]

        mean_alloc = statistics.mean(samples)
        p95_alloc = sorted(samples)[int(len(samples) * 0.95)] if len(samples) > 1 else samples[0]

        return MemorySnapshot(
            peak_allocated_mb=round(peak_alloc, 1),
            peak_reserved_mb=round(peak_reserved, 1),
            mean_allocated_mb=round(mean_alloc, 1),
            p95_allocated_mb=round(p95_alloc, 1),
            samples_count=len(samples),
        )

    def _poll(self) -> None:
        while self._running:
            alloc = torch.cuda.memory_allocated(self._device) / (1024 ** 2)
            reserved = torch.cuda.memory_reserved(self._device) / (1024 ** 2)
            self._samples_allocated.append(alloc)
            self._samples_reserved.append(reserved)
            time.sleep(0.05)


# ---------------------------------------------------------------------------
# Synthetic Input Generator
# ---------------------------------------------------------------------------

def generate_synthetic_input(tokenizer: Any, target_tokens: int) -> list[dict]:
    """Generate a chat message list that tokenizes to approximately target_tokens."""
    filler = "The quick brown fox jumps over the lazy dog. "
    long_text = filler * (target_tokens * 2)

    encoded = tokenizer.encode(long_text, add_special_tokens=False)
    overhead_tokens = 20
    content_tokens = max(1, target_tokens - overhead_tokens)
    trimmed_ids = encoded[:content_tokens]
    content = tokenizer.decode(trimmed_ids, skip_special_tokens=True)

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": content},
    ]

    actual = len(tokenizer.apply_chat_template(messages, tokenize=True))
    return messages


# ---------------------------------------------------------------------------
# Single Inference Runner
# ---------------------------------------------------------------------------

def run_single_inference(engine: Any, messages: list[dict], request_id: str) -> InferenceResult:
    """Execute one inference call, catching OOM gracefully."""
    t0 = time.perf_counter()
    try:
        engine.predict_chat_messages(messages, request_id=request_id)
        latency = (time.perf_counter() - t0) * 1000
        return InferenceResult(request_id=request_id, success=True, latency_ms=round(latency, 2))
    except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
        latency = (time.perf_counter() - t0) * 1000
        err_str = str(e)[:200]
        is_oom = "CUDA out of memory" in err_str or isinstance(e, torch.cuda.OutOfMemoryError)
        if not is_oom:
            raise
        return InferenceResult(
            request_id=request_id, success=False, latency_ms=round(latency, 2),
            error=err_str, is_oom=True,
        )
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return InferenceResult(
            request_id=request_id, success=False, latency_ms=round(latency, 2),
            error=str(e)[:200], is_oom=False,
        )


# ---------------------------------------------------------------------------
# Concurrency Level Runner
# ---------------------------------------------------------------------------

def run_concurrency_level(
    engine: Any,
    device: torch.device,
    messages_pool: list[list[dict]],
    concurrency: int,
    input_length: int,
    requests_per_level: int,
) -> tuple[LevelResult, list[InferenceResult]]:
    """Run a batch of concurrent inferences and collect metrics."""
    sampler = MemorySampler(device)
    sampler.start()

    all_results: list[InferenceResult] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for i in range(requests_per_level):
            msg = messages_pool[i % len(messages_pool)]
            rid = f"stress-{input_length}t-c{concurrency}-{i:03d}-{uuid.uuid4().hex[:6]}"
            futures.append(executor.submit(run_single_inference, engine, msg, rid))

        for future in as_completed(futures):
            all_results.append(future.result())

    memory = sampler.stop()

    success_latencies = [r.latency_ms for r in all_results if r.success]
    all_latencies = [r.latency_ms for r in all_results]
    success_count = sum(1 for r in all_results if r.success)
    failure_count = sum(1 for r in all_results if not r.success)
    oom_count = sum(1 for r in all_results if r.is_oom)

    latencies_for_stats = success_latencies if success_latencies else all_latencies

    def percentile(data: list[float], p: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = int(len(s) * p / 100)
        return s[min(idx, len(s) - 1)]

    level_result = LevelResult(
        input_length=input_length,
        concurrency=concurrency,
        memory=memory,
        latencies_ms=all_latencies,
        success_count=success_count,
        failure_count=failure_count,
        oom_count=oom_count,
        p50_ms=round(percentile(latencies_for_stats, 50), 2),
        p95_ms=round(percentile(latencies_for_stats, 95), 2),
        p99_ms=round(percentile(latencies_for_stats, 99), 2),
        mean_ms=round(statistics.mean(latencies_for_stats), 2) if latencies_for_stats else 0.0,
    )

    return level_result, all_results


# ---------------------------------------------------------------------------
# Main Experiment
# ---------------------------------------------------------------------------

def run_experiment(config: StressTestConfig) -> None:
    """Full experiment orchestration."""
    print("=" * 70)
    print("  GPU Memory Stress Test")
    print("=" * 70)

    # Setup output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(config.output_dir) / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save config
    with open(run_dir / "config.json", "w") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)

    # Load engine
    print(f"\n[Phase 1] Loading model from: {config.model_paths_config}")
    from inference_service.core.config import ModelPathsConfig
    from inference_service.services.router_engine import HybridIntegratedDifficultyRouter

    model_paths = ModelPathsConfig.from_file(config.model_paths_config)
    device = torch.device(model_paths.device)

    t_load_start = time.perf_counter()
    engine = HybridIntegratedDifficultyRouter(model_paths)
    t_load = time.perf_counter() - t_load_start
    print(f"  Model loaded in {t_load:.1f}s")

    # Baseline memory
    baseline_allocated = torch.cuda.memory_allocated(device) / (1024 ** 2)
    baseline_reserved = torch.cuda.memory_reserved(device) / (1024 ** 2)
    total_gpu_mb = torch.cuda.get_device_properties(device).total_memory / (1024 ** 2)
    gpu_name = torch.cuda.get_device_properties(device).name

    print(f"  GPU: {gpu_name} ({total_gpu_mb:.0f} MiB total)")
    print(f"  Baseline: {baseline_allocated:.0f} MB allocated / {baseline_reserved:.0f} MB reserved")

    # Generate synthetic inputs
    print(f"\n[Phase 2] Generating synthetic inputs...")
    tokenizer = engine.tokenizer
    input_pools: dict[int, list[list[dict]]] = {}
    for length in config.input_lengths:
        pool = [generate_synthetic_input(tokenizer, length) for _ in range(5)]
        actual_tokens = len(tokenizer.apply_chat_template(pool[0], tokenize=True))
        input_pools[length] = pool
        print(f"  {length} tokens target -> {actual_tokens} actual tokens")

    # Warmup
    print(f"\n[Phase 3] Warmup ({config.warmup_requests} requests per length)...")
    for length in config.input_lengths:
        for i in range(config.warmup_requests):
            msg = input_pools[length][i % len(input_pools[length])]
            engine.predict_chat_messages(msg, request_id=f"warmup-{length}-{i}")
        print(f"  {length} tokens: done")

    # Measurement
    print(f"\n[Phase 4] Measurement")
    print("-" * 70)

    all_level_results: list[LevelResult] = []
    all_per_request: list[dict] = []

    for input_length in config.input_lengths:
        print(f"\n  Input length: {input_length} tokens")
        print(f"  {'Conc':>6} | {'Peak MB':>9} | {'Delta MB':>9} | {'P50 ms':>8} | {'P95 ms':>8} | {'P99 ms':>8} | {'OK':>4} | {'OOM':>4}")
        print(f"  {'-'*6}-+-{'-'*9}-+-{'-'*9}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*4}-+-{'-'*4}")

        for concurrency in config.concurrency_levels:
            level_result, request_results = run_concurrency_level(
                engine=engine,
                device=device,
                messages_pool=input_pools[input_length],
                concurrency=concurrency,
                input_length=input_length,
                requests_per_level=config.requests_per_level,
            )

            all_level_results.append(level_result)
            delta = level_result.memory.peak_allocated_mb - baseline_allocated

            oom_marker = f" ← OOM!" if level_result.oom_count > 0 else ""
            print(
                f"  {concurrency:>6} | {level_result.memory.peak_allocated_mb:>9.0f} | "
                f"{delta:>+9.0f} | {level_result.p50_ms:>8.0f} | "
                f"{level_result.p95_ms:>8.0f} | {level_result.p99_ms:>8.0f} | "
                f"{level_result.success_count:>4} | {level_result.oom_count:>4}{oom_marker}"
            )

            for r in request_results:
                all_per_request.append({
                    "input_length": input_length,
                    "concurrency": concurrency,
                    "request_id": r.request_id,
                    "success": r.success,
                    "latency_ms": r.latency_ms,
                    "is_oom": r.is_oom,
                    "error": r.error,
                })

            if level_result.oom_count > 0 and config.stop_on_oom:
                print(f"  *** OOM detected, skipping higher concurrency for {input_length} tokens ***")
                break

            time.sleep(config.cooldown_seconds)

    # Save results
    print(f"\n[Phase 5] Saving results to {run_dir}")

    # raw_results.csv
    csv_path = run_dir / "raw_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "input_length", "concurrency", "baseline_allocated_mb",
            "peak_allocated_mb", "peak_reserved_mb", "delta_from_baseline_mb",
            "mean_allocated_mb", "p95_allocated_mb",
            "p50_latency_ms", "p95_latency_ms", "p99_latency_ms", "mean_latency_ms",
            "success_count", "failure_count", "oom_count", "total_gpu_mb",
        ])
        for lr in all_level_results:
            writer.writerow([
                lr.input_length, lr.concurrency, round(baseline_allocated, 1),
                lr.memory.peak_allocated_mb, lr.memory.peak_reserved_mb,
                round(lr.memory.peak_allocated_mb - baseline_allocated, 1),
                lr.memory.mean_allocated_mb, lr.memory.p95_allocated_mb,
                lr.p50_ms, lr.p95_ms, lr.p99_ms, lr.mean_ms,
                lr.success_count, lr.failure_count, lr.oom_count, round(total_gpu_mb, 0),
            ])
    print(f"  raw_results.csv saved")

    # per_request.csv
    per_req_path = run_dir / "per_request.csv"
    with open(per_req_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "input_length", "concurrency", "request_id", "success",
            "latency_ms", "is_oom", "error",
        ])
        writer.writeheader()
        writer.writerows(all_per_request)
    print(f"  per_request.csv saved")

    # summary.json
    summary = {
        "timestamp": timestamp,
        "gpu_name": gpu_name,
        "total_gpu_mb": round(total_gpu_mb, 0),
        "baseline_allocated_mb": round(baseline_allocated, 1),
        "baseline_reserved_mb": round(baseline_reserved, 1),
        "model_load_time_seconds": round(t_load, 1),
        "levels": [],
    }
    for lr in all_level_results:
        summary["levels"].append({
            "input_length": lr.input_length,
            "concurrency": lr.concurrency,
            "peak_allocated_mb": lr.memory.peak_allocated_mb,
            "delta_mb": round(lr.memory.peak_allocated_mb - baseline_allocated, 1),
            "p50_ms": lr.p50_ms,
            "p95_ms": lr.p95_ms,
            "p99_ms": lr.p99_ms,
            "success_count": lr.success_count,
            "oom_count": lr.oom_count,
        })

    # Recommendations
    safe_levels: dict[int, int] = {}
    for input_length in config.input_lengths:
        levels_for_length = [l for l in all_level_results if l.input_length == input_length and l.oom_count == 0]
        if levels_for_length:
            max_safe = max(l.concurrency for l in levels_for_length)
            safe_levels[input_length] = max_safe
    summary["recommendations"] = {
        "max_safe_concurrency_by_input_length": safe_levels,
        "utilization_at_max_safe": {},
    }
    for input_length, max_conc in safe_levels.items():
        level = next(l for l in all_level_results if l.input_length == input_length and l.concurrency == max_conc)
        util = level.memory.peak_allocated_mb / total_gpu_mb * 100
        summary["recommendations"]["utilization_at_max_safe"][str(input_length)] = round(util, 1)

    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  summary.json saved")

    # report.txt
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("  GPU Memory Stress Test Report")
    report_lines.append("=" * 70)
    report_lines.append(f"  Date: {timestamp}")
    report_lines.append(f"  GPU: {gpu_name} ({total_gpu_mb:.0f} MiB total)")
    report_lines.append(f"  Model: Qwen2.5-7B-Instruct (bf16) + 5x CG-TabM")
    report_lines.append(f"  Baseline: {baseline_allocated:.0f} MB allocated / {baseline_reserved:.0f} MB reserved")
    report_lines.append(f"  Load time: {t_load:.1f}s")
    report_lines.append("")
    report_lines.append(f"  {'Length':>8} | {'Conc':>6} | {'Peak MB':>9} | {'Delta MB':>9} | {'P50 ms':>8} | {'P95 ms':>8} | {'P99 ms':>8} | {'OK':>4} | {'OOM':>4}")
    report_lines.append(f"  {'-'*8}-+-{'-'*6}-+-{'-'*9}-+-{'-'*9}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*4}-+-{'-'*4}")
    for lr in all_level_results:
        delta = lr.memory.peak_allocated_mb - baseline_allocated
        report_lines.append(
            f"  {lr.input_length:>8} | {lr.concurrency:>6} | {lr.memory.peak_allocated_mb:>9.0f} | "
            f"{delta:>+9.0f} | {lr.p50_ms:>8.0f} | {lr.p95_ms:>8.0f} | "
            f"{lr.p99_ms:>8.0f} | {lr.success_count:>4} | {lr.oom_count:>4}"
        )
    report_lines.append("")
    report_lines.append("  RECOMMENDATIONS:")
    for input_length, max_conc in safe_levels.items():
        level = next(l for l in all_level_results if l.input_length == input_length and l.concurrency == max_conc)
        util = level.memory.peak_allocated_mb / total_gpu_mb * 100
        report_lines.append(f"    {input_length} tokens: max safe concurrency = {max_conc} (peak {level.memory.peak_allocated_mb:.0f} MB, {util:.0f}% utilization)")
    report_lines.append("")

    report_text = "\n".join(report_lines)
    with open(run_dir / "report.txt", "w") as f:
        f.write(report_text)
    print(f"  report.txt saved")

    print(f"\n{report_text}")
    print(f"\nAll results saved to: {run_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GPU Memory Stress Test for Inference Service")
    parser.add_argument("--concurrency", type=str, default="1,2,4,8,16,32",
                        help="Comma-separated concurrency levels (default: 1,2,4,8,16,32)")
    parser.add_argument("--input-lengths", type=str, default="256,1024,4096",
                        help="Comma-separated input token lengths (default: 256,1024,4096)")
    parser.add_argument("--requests-per-level", type=int, default=20,
                        help="Number of requests per (concurrency, length) pair (default: 20)")
    parser.add_argument("--warmup", type=int, default=3,
                        help="Warmup requests per input length (default: 3)")
    parser.add_argument("--cooldown", type=float, default=5.0,
                        help="Cooldown seconds between levels (default: 5.0)")
    parser.add_argument("--no-stop-on-oom", action="store_true",
                        help="Continue testing higher concurrency even after OOM")
    parser.add_argument("--model-config", type=str,
                        default="services/inference-service/config/model_paths.json",
                        help="Path to model_paths.json")
    parser.add_argument("--output-dir", type=str, default="gpu_stress_test/results",
                        help="Output directory for results")

    args = parser.parse_args()

    config = StressTestConfig(
        concurrency_levels=[int(x) for x in args.concurrency.split(",")],
        input_lengths=[int(x) for x in args.input_lengths.split(",")],
        requests_per_level=args.requests_per_level,
        warmup_requests=args.warmup,
        cooldown_seconds=args.cooldown,
        stop_on_oom=not args.no_stop_on_oom,
        model_paths_config=args.model_config,
        output_dir=args.output_dir,
    )

    if not torch.cuda.is_available():
        print("ERROR: CUDA is not available. This test requires a GPU.")
        sys.exit(1)

    run_experiment(config)


if __name__ == "__main__":
    main()
