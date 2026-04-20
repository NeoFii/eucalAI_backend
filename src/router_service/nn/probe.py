"""Probe regression model (legacy, kept for compatibility)."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


class RegressionNN(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.dropout = nn.Dropout(0.3)
        self.linear = nn.Linear(input_dim, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(self.dropout(x))


def load_probe_bundle(probe_path: str):
    bundle = torch.load(probe_path, map_location="cpu", weights_only=False)
    input_dim = int(bundle["input_dim"])
    model = RegressionNN(input_dim=input_dim)
    model.load_state_dict(bundle["model_state_dict"])
    model.eval()
    scaler_mean = np.array(bundle["scaler_mean"], dtype=np.float32)
    scaler_scale = np.array(bundle["scaler_scale"], dtype=np.float32)
    return model, scaler_mean, scaler_scale
