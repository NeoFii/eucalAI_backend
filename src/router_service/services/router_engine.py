"""HybridIntegratedDifficultyRouter: core routing engine.

Loads Qwen backbone + 5 CG-TabM routers + proto artifact.
Accepts chat messages, returns routing decision (no upstream invocation).
"""

from __future__ import annotations

import gc
import os
import pickle
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn

from router_service.config import (
    FIVEWAY_ROUTE_ORDER,
    FINAL_SCORE_LOWER,
    FINAL_SCORE_UPPER,
    FINAL_SCORE_SOURCE,
    ModelPathsConfig,
    NORMALIZE_RANGES,
    PROTO_LABEL_ORDER,
    PROTO_LABEL_TO_ROUTE,
    PROTO_ROUTE_TO_LABEL,
    ROUTE_CODE,
    ROUTE_ERROR,
    ROUTE_GENERAL,
    ROUTE_TASK,
    ROUTE_TOOL,
)
from router_service.logging import get_app_logger
from router_service.nn.cg_tabm import CGTabMRegressor
from router_service.utils.input_builder import (
    build_full_llm_input_for_chat_messages,
    build_proto_semantic_text,
    shared_record_from_chat_messages,
)
from router_service.utils.runtime_config import clone_runtime_config, normalize_runtime_config
from router_service.utils.scoring import (
    compute_weighted_total_score_0_10,
    l2_normalize_vec,
    level_from_0_10,
    normalize_route,
    norm_0_2_to_bucket,
    resolve_score_band,
    scale_final_score_to_0_10,
    softmax_np,
)
from router_service.utils.text import normalize_chat_or_text

logger = get_app_logger()


def _ensure_special_tokens_map(model_dir: str):
    import json
    path = os.path.join(model_dir, "special_tokens_map.json")
    if os.path.exists(path):
        return
    tok_cfg_path = os.path.join(model_dir, "tokenizer_config.json")
    data = {}
    if os.path.exists(tok_cfg_path):
        with open(tok_cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k in [
            "bos_token", "eos_token", "unk_token", "pad_token",
            "sep_token", "cls_token", "mask_token", "additional_special_tokens",
        ]:
            if k in cfg:
                data[k] = cfg[k]
    if not data:
        data = {
            "additional_special_tokens": ["<|im_start|>", "<|im_end|>"],
            "eos_token": "<|im_end|>",
            "pad_token": "<|endoftext|>",
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_input_text(tokenizer, raw_text_or_chat):
    chat = normalize_chat_or_text(raw_text_or_chat)
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template is not None:
        return tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
    parts = []
    for turn in chat:
        parts.append(f"{turn['role']}: {turn['content']}")
    parts.append("assistant:")
    return "\n".join(parts)


def release_memory(*objs):
    for obj in objs:
        try:
            del obj
        except Exception:
            pass
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


class HybridIntegratedDifficultyRouter:
    def __init__(
        self,
        model_paths: ModelPathsConfig,
        *,
        runtime_config: Dict[str, Any] | None = None,
    ):
        from transformers import AutoTokenizer, AutoModelForCausalLM

        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

        self.model_paths = model_paths
        self.device = torch.device(model_paths.device)
        self.max_input_length = model_paths.max_input_length
        self.default_runtime_config = normalize_runtime_config(runtime_config)

        logger.info("loading Qwen backbone: %s", model_paths.qwen_backbone)
        _ensure_special_tokens_map(model_paths.qwen_backbone)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_paths.qwen_backbone,
            use_fast=False,
            trust_remote_code=True,
            local_files_only=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            model_paths.qwen_backbone,
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            trust_remote_code=True,
            local_files_only=True,
            low_cpu_mem_usage=True,
        ).to(self.device)
        self.model.eval()

        self.hidden_size = self.model.config.hidden_size
        self.num_heads = self.model.config.num_attention_heads
        self.head_dim = self.hidden_size // self.num_heads
        self.cg_input_dim = 30 * self.head_dim

        logger.info("loading 5 CG-TabM routers...")
        self._routers: Dict[str, Tuple[Any, CGTabMRegressor, List[Tuple[int, int]]]] = {}
        for name in ["swe", "tool", "gaia", "task", "prog"]:
            scaler_path = model_paths.get_scaler_path(name)
            router_path = model_paths.get_model_path(name)
            heads = model_paths.get_heads(name)

            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)
            router_model = CGTabMRegressor(input_dim=self.cg_input_dim, token_dim=self.head_dim).to(self.device)
            bundle = torch.load(router_path, map_location=self.device)
            if isinstance(bundle, dict) and "model_state_dict" in bundle:
                router_model.load_state_dict(bundle["model_state_dict"])
            else:
                router_model.load_state_dict(bundle)
            router_model.eval()
            self._routers[name] = (scaler, router_model, heads)

        # Proto artifact
        self.proto_enabled = False
        self.proto_prototypes = None
        self.proto_label_order = list(PROTO_LABEL_ORDER)
        self.proto_temperature = 0.2
        if model_paths.proto_artifact and os.path.exists(model_paths.proto_artifact):
            bundle = np.load(model_paths.proto_artifact, allow_pickle=True)
            self.proto_prototypes = bundle["prototypes"].astype(np.float32)
            self.proto_label_order = [str(x) for x in bundle["label_order"].tolist()]
            self.proto_temperature = float(bundle["temperature"][0])
            self.proto_enabled = True
            logger.info("loaded proto artifact: %s", model_paths.proto_artifact)
        else:
            logger.warning("proto artifact not found; proto weighting disabled")

        logger.info("all router components loaded")

    def _resolve_runtime_config(self, runtime_config: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if runtime_config is None:
            return clone_runtime_config(self.default_runtime_config)
        return normalize_runtime_config(runtime_config)

    @torch.no_grad()
    def _run_with_heads(self, raw_text_or_chat, heads_group: List[List[Tuple[int, int]]]) -> Dict[int, torch.Tensor]:
        input_text = _build_input_text(self.tokenizer, raw_text_or_chat)
        inputs = self.tokenizer(
            input_text,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_input_length,
        ).to(self.device)

        base_llm = self.model.model if hasattr(self.model, "model") else self.model
        all_target_layers: set[int] = set()
        for heads in heads_group:
            all_target_layers.update([layer for layer, _ in heads])

        cache: Dict[int, torch.Tensor] = {}
        hooks = []

        def get_hook(layer_idx):
            def hook(module, hook_input, output):
                cache[layer_idx] = hook_input[0][:, -1, :].detach().to(torch.float32)
            return hook

        for layer_idx in all_target_layers:
            h = base_llm.layers[layer_idx].self_attn.o_proj.register_forward_hook(get_hook(layer_idx))
            hooks.append(h)

        try:
            _ = base_llm(**inputs, return_dict=True)
        finally:
            for h in hooks:
                h.remove()
        return cache

    def _get_head_features(self, cache: Dict[int, torch.Tensor], target_heads: List[Tuple[int, int]]) -> np.ndarray:
        sample_vecs = []
        for (l, h) in target_heads:
            start = h * self.head_dim
            end = (h + 1) * self.head_dim
            sample_vecs.append(cache[l][0, start:end].detach().to(torch.float32).cpu())
        flat_vec = torch.cat(sample_vecs, dim=0).unsqueeze(0).numpy().astype(np.float32)
        return flat_vec

    @torch.no_grad()
    def _forward_cgtabm(self, cache, scaler, router_model, heads) -> float:
        feats = self._get_head_features(cache, heads)
        feats = scaler.transform(feats).astype(np.float32)
        feats_tensor = torch.from_numpy(feats).to(device=self.device, dtype=torch.float32)
        pred = router_model(feats_tensor)
        if pred.dim() == 3:
            pred = pred.mean(dim=1)
        return float(pred.item())

    @torch.no_grad()
    def _embed_semantic_text_for_proto(self, semantic_text: str) -> np.ndarray:
        rendered = _build_input_text(self.tokenizer, semantic_text)
        toks = self.tokenizer(
            rendered, return_tensors="pt", truncation=True, max_length=1024,
        ).to(self.device)
        base_llm = self.model.model if hasattr(self.model, "model") else self.model
        out = base_llm(**toks, return_dict=True)
        last_hidden = out.last_hidden_state
        attn = toks["attention_mask"]
        last_idx = attn.sum(dim=1) - 1
        emb = last_hidden[torch.arange(last_hidden.shape[0], device=self.device), last_idx, :]
        emb = emb[0].float().detach().cpu().numpy().astype(np.float32)
        return l2_normalize_vec(emb)

    @torch.no_grad()
    def _compute_proto_weighting(self, raw_input, d_vec_0_2: np.ndarray) -> Optional[Dict[str, Any]]:
        if not self.proto_enabled or self.proto_prototypes is None:
            return None
        semantic_text = build_proto_semantic_text(raw_input)
        emb = self._embed_semantic_text_for_proto(semantic_text)
        sims = emb @ self.proto_prototypes.T
        weights = softmax_np(sims / self.proto_temperature, axis=0).astype(np.float32)
        weighted_scores = weights * d_vec_0_2.astype(np.float32)
        weighted_score_0_2 = float(weighted_scores.sum())
        weighted_level_0_2 = norm_0_2_to_bucket(weighted_score_0_2)

        proto_weights = {}
        proto_weighted_scores = {}
        similarities = {}
        for i, label in enumerate(self.proto_label_order):
            proto_weights[f"w_{label}"] = float(weights[i])
            proto_weighted_scores[f"z_{label}"] = float(weighted_scores[i])
            similarities[f"sim_{label}"] = float(sims[i])

        dominant_weight_label = self.proto_label_order[int(np.argmax(weights))]
        dominant_score_label = self.proto_label_order[int(np.argmax(weighted_scores))]
        return {
            "semantic_text": semantic_text,
            "temperature": float(self.proto_temperature),
            "similarities": similarities,
            "proto_weights": proto_weights,
            "proto_weighted_scores": proto_weighted_scores,
            "weighted_score_0_2": weighted_score_0_2,
            "weighted_level_0_2": weighted_level_0_2,
            "dominant_w_route": PROTO_LABEL_TO_ROUTE.get(dominant_weight_label, dominant_weight_label),
            "dominant_z_route": PROTO_LABEL_TO_ROUTE.get(dominant_score_label, dominant_score_label),
        }

    @torch.no_grad()
    def predict_chat_messages(
        self,
        messages: List[Dict[str, Any]],
        *,
        request_id: str | None = None,
        runtime_config: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Run routing decision on chat messages. Returns scores + selected model."""
        request_id = request_id or f"chat-{uuid.uuid4().hex[:12]}"
        config = self._resolve_runtime_config(runtime_config)
        weights = config["weights"]
        score_bands = config["score_bands"]
        score_bands_raw = config["score_bands_raw"]
        tier_model_map = config["tier_model_map"]

        # Build inputs
        shared_tool = shared_record_from_chat_messages(messages, request_id=request_id)
        other_full_chat, other_full_debug_text = build_full_llm_input_for_chat_messages(messages)

        tool_canonical_text = shared_tool["canonical_text"]

        # Get all heads needed
        swe_scaler, swe_router, swe_heads = self._routers["swe"]
        tool_scaler, tool_router, tool_heads = self._routers["tool"]
        gaia_scaler, gaia_router, gaia_heads = self._routers["gaia"]
        task_scaler, task_router, task_heads = self._routers["task"]
        prog_scaler, prog_router, prog_heads = self._routers["prog"]

        # Forward pass
        tool_cache = self._run_with_heads(tool_canonical_text, [tool_heads])
        cache_other = self._run_with_heads(other_full_chat, [swe_heads, gaia_heads, task_heads, prog_heads])

        raw_swe = self._forward_cgtabm(cache_other, swe_scaler, swe_router, swe_heads)
        raw_tool = self._forward_cgtabm(tool_cache, tool_scaler, tool_router, tool_heads)
        raw_gaia = self._forward_cgtabm(cache_other, gaia_scaler, gaia_router, gaia_heads)
        raw_task = self._forward_cgtabm(cache_other, task_scaler, task_router, task_heads)
        raw_prog = self._forward_cgtabm(cache_other, prog_scaler, prog_router, prog_heads)

        swe_0_2, _ = normalize_route(ROUTE_ERROR, raw_swe)
        tool_0_2, _ = normalize_route(ROUTE_TOOL, raw_tool)
        gaia_0_2, _ = normalize_route(ROUTE_GENERAL, raw_gaia)
        task_0_2, _ = normalize_route(ROUTE_TASK, raw_task)
        prog_0_2, _ = normalize_route(ROUTE_CODE, raw_prog)

        fiveway_scores_0_2 = {
            ROUTE_ERROR: swe_0_2,
            ROUTE_TOOL: tool_0_2,
            ROUTE_GENERAL: gaia_0_2,
            ROUTE_TASK: task_0_2,
            ROUTE_CODE: prog_0_2,
        }
        config_total_score_0_10, weighted_components = compute_weighted_total_score_0_10(
            fiveway_scores_0_2, weights,
        )

        # Proto weighting
        d_vec_0_2 = np.array([swe_0_2, tool_0_2, gaia_0_2, task_0_2, prog_0_2], dtype=np.float32)
        proto_info = self._compute_proto_weighting(messages, d_vec_0_2)

        if proto_info and proto_info.get("weighted_score_0_2") is not None:
            final_score_raw = float(proto_info["weighted_score_0_2"])
            total_score_0_10 = scale_final_score_to_0_10(final_score_raw)
            final_score_source = FINAL_SCORE_SOURCE
        else:
            final_score_raw = config_total_score_0_10 / 5.0
            total_score_0_10 = config_total_score_0_10
            final_score_source = "runtime_weighted_0_10_fallback"

        routing_tier = resolve_score_band(total_score_0_10, score_bands)
        selected_model = tier_model_map[routing_tier]

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return {
            "request_id": request_id,
            "scores_0_2": {k: round(v, 4) for k, v in fiveway_scores_0_2.items()},
            "proto_weighted_0_2": round(proto_info["weighted_score_0_2"], 4) if proto_info else None,
            "total_score_0_10": round(total_score_0_10, 4),
            "score_source": final_score_source,
            "routing_tier": routing_tier,
            "selected_model": selected_model,
            "tier_model_map": tier_model_map,
            "score_bands_raw": score_bands_raw,
        }
