"""Unit tests for router_service.utils.scoring."""

import pytest
import numpy as np
from router_service.utils.scoring import (
    minmax_scale_to_0_2,
    norm_0_2_to_bucket,
    raw_score_to_bucket,
    scale_final_score_to_0_10,
    level_from_0_10,
    parse_score_bands,
    resolve_score_band,
    compute_weighted_total_score_0_10,
    normalize_route,
    softmax_np,
    l2_normalize_vec,
)


class TestMinmaxScale:
    def test_midpoint(self):
        assert minmax_scale_to_0_2(0.5, 0.0, 1.0) == pytest.approx(1.0)

    def test_min(self):
        assert minmax_scale_to_0_2(0.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_max(self):
        assert minmax_scale_to_0_2(1.0, 0.0, 1.0) == pytest.approx(2.0)

    def test_clipping(self):
        assert minmax_scale_to_0_2(-1.0, 0.0, 1.0) == pytest.approx(0.0)
        assert minmax_scale_to_0_2(2.0, 0.0, 1.0) == pytest.approx(2.0)

    def test_equal_range(self):
        assert minmax_scale_to_0_2(5.0, 5.0, 5.0) == 1.0


class TestBuckets:
    def test_norm_0_2_to_bucket(self):
        assert norm_0_2_to_bucket(0.3) == "level1"
        assert norm_0_2_to_bucket(1.0) == "level2"
        assert norm_0_2_to_bucket(1.8) == "level3"

    def test_raw_score_to_bucket(self):
        assert raw_score_to_bucket(0.2) == "level1"
        assert raw_score_to_bucket(1.0) == "level2"
        assert raw_score_to_bucket(2.0) == "level3"

    def test_level_from_0_10(self):
        assert level_from_0_10(2.0) == "level1"
        assert level_from_0_10(5.0) == "level2"
        assert level_from_0_10(8.0) == "level3"


class TestScoreBands:
    def test_parse(self):
        bands = parse_score_bands("0-3:5,3-5:4,5-7:3,7-9:2,9-10:1")
        assert len(bands) == 5
        assert bands[0] == (0.0, 3.0, 5)
        assert bands[4] == (9.0, 10.0, 1)

    def test_resolve(self):
        bands = parse_score_bands("0-3:5,3-5:4,5-7:3,7-9:2,9-10:1")
        assert resolve_score_band(1.0, bands) == 5
        assert resolve_score_band(4.0, bands) == 4
        assert resolve_score_band(6.0, bands) == 3
        assert resolve_score_band(8.0, bands) == 2
        assert resolve_score_band(9.5, bands) == 1

    def test_resolve_out_of_range(self):
        bands = parse_score_bands("2-4:3,4-6:2")
        assert resolve_score_band(0.0, bands) == 3  # below first
        assert resolve_score_band(10.0, bands) == 2  # above last

    def test_parse_empty_raises(self):
        with pytest.raises(ValueError):
            parse_score_bands("")


class TestWeightedScore:
    def test_equal_weights(self):
        scores = {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0}
        weights = {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0}
        total, components = compute_weighted_total_score_0_10(scores, weights)
        assert total == pytest.approx(5.0)

    def test_zero_weights_raises(self):
        scores = {"纠错": 1.0, "工具调用": 1.0, "通用任务": 1.0, "任务拆解": 1.0, "编程": 1.0}
        weights = {"纠错": 0.0, "工具调用": 0.0, "通用任务": 0.0, "任务拆解": 0.0, "编程": 0.0}
        with pytest.raises(ValueError):
            compute_weighted_total_score_0_10(scores, weights)


class TestNormalizeRoute:
    def test_known_route(self):
        score, level = normalize_route("纠错", 1.0)
        assert 0.0 <= score <= 2.0
        assert level in ("level1", "level2", "level3")


class TestSoftmaxAndL2:
    def test_softmax(self):
        x = np.array([1.0, 2.0, 3.0])
        result = softmax_np(x)
        assert result.sum() == pytest.approx(1.0, abs=1e-6)

    def test_l2_normalize(self):
        x = np.array([3.0, 4.0])
        result = l2_normalize_vec(x)
        assert np.linalg.norm(result) == pytest.approx(1.0, abs=1e-6)
