"""
Tests for SG (Semantic Gravity) prediction module.

- StateEncoder: encode fleet state into feature vector
- SGEngine: attractor classification
- BottleneckPredictor: prediction < 25ms
"""

import time

import numpy as np
import pytest


# Sample robot states for testing
SAMPLE_ROBOTS = [
    {
        "robot_id": f"robot_{i:03d}",
        "status": "moving" if i % 3 == 0 else ("idle" if i % 3 == 1 else "charging"),
        "pose": {"x": float(i * 2), "y": float(i % 5 * 2), "theta": 0.0},
        "velocity": {"linear": 0.5 if i % 3 == 0 else 0.0, "angular": 0.0},
        "battery": {"charge_pct": 90.0 - i * 5},
        "current_node": f"N_{i:02d}",
    }
    for i in range(10)
]


class TestStateEncoder:
    def test_init(self):
        """StateEncoder initializes with configurable dims."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(max_robots=50, feature_dim=128)
        assert enc.feature_dim == 128
        assert enc.max_robots == 50

    def test_encode_empty(self):
        """Encoding empty fleet returns zero vector."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(feature_dim=128)
        vec = enc.encode([])
        assert vec.shape == (128,)
        assert np.all(vec == 0)

    def test_encode_shape(self):
        """Encoding fleet returns correct shape."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(feature_dim=128)
        vec = enc.encode(SAMPLE_ROBOTS)
        assert vec.shape == (128,)
        assert vec.dtype == np.float64

    def test_encode_nonzero(self):
        """Encoding non-empty fleet produces non-zero features."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(feature_dim=128)
        vec = enc.encode(SAMPLE_ROBOTS)
        assert np.any(vec != 0), "Encoded vector should not be all zeros for non-empty fleet"

    def test_encode_deterministic(self):
        """Same input produces same output."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(feature_dim=128)
        v1 = enc.encode(SAMPLE_ROBOTS)
        v2 = enc.encode(SAMPLE_ROBOTS)
        np.testing.assert_array_equal(v1, v2)

    def test_encode_different_for_different_states(self):
        """Different fleet states produce different vectors."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(feature_dim=128)
        v1 = enc.encode(SAMPLE_ROBOTS[:5])
        v2 = enc.encode(SAMPLE_ROBOTS[5:])
        assert not np.array_equal(v1, v2), "Different fleet states should produce different vectors"

    def test_encode_timed(self):
        """Encoding should be fast (< 5ms)."""
        from intelligence.sg_prediction.state_encoder import StateEncoder
        enc = StateEncoder(feature_dim=128)
        _, elapsed_ms = enc.encode_timed(SAMPLE_ROBOTS)
        assert elapsed_ms < 5.0, f"Encoding took {elapsed_ms:.2f}ms"


class TestSGEngine:
    def test_init(self):
        """SGEngine initializes."""
        from intelligence.sg_prediction.sg_engine import SGEngine
        engine = SGEngine(dim=128)
        assert engine.dim == 128
        assert engine.num_attractors == 0

    def test_add_attractor(self):
        """Can add attractors."""
        from intelligence.sg_prediction.sg_engine import SGEngine
        engine = SGEngine(dim=128)
        vec = np.random.randn(128)
        engine.add_attractor(vec, label="test_pattern")
        assert engine.num_attractors == 1
        assert "test_pattern" in engine.attractor_labels

    def test_classify_unknown_empty(self):
        """Classifying with no attractors returns unknown."""
        from intelligence.sg_prediction.sg_engine import SGEngine
        engine = SGEngine(dim=128)
        result = engine.classify(np.random.randn(128))
        assert result["label"] == "unknown"

    def test_classify_finds_correct_attractor(self):
        """Classification finds the closest attractor."""
        from intelligence.sg_prediction.sg_engine import SGEngine
        engine = SGEngine(dim=32)

        # Create two distinct patterns
        rng = np.random.RandomState(42)
        pattern_a = rng.randn(32)
        pattern_b = -pattern_a  # Opposite direction

        engine.add_attractor(pattern_a, label="pattern_a")
        engine.add_attractor(pattern_b, label="pattern_b")

        # Classify a vector close to pattern_a
        test_vec = pattern_a + rng.randn(32) * 0.1
        result = engine.classify(test_vec)
        assert result["label"] == "pattern_a"
        assert result["similarity"] > 0

    def test_classify_returns_structure(self):
        """Classification returns expected dict structure."""
        from intelligence.sg_prediction.sg_engine import SGEngine
        engine = SGEngine(dim=32)
        engine.add_attractor(np.random.randn(32), label="test")
        result = engine.classify(np.random.randn(32))
        assert "label" in result
        assert "similarity" in result
        assert "energy" in result
        assert "converged_in" in result

    def test_classify_performance(self):
        """Classification should be fast (< 10ms)."""
        from intelligence.sg_prediction.sg_engine import SGEngine
        engine = SGEngine(dim=128)
        rng = np.random.RandomState(42)
        for i in range(5):
            engine.add_attractor(rng.randn(128), label=f"pattern_{i}")

        # Warm up
        engine.classify(rng.randn(128))

        # Measure
        times = []
        for _ in range(50):
            start = time.perf_counter()
            engine.classify(rng.randn(128))
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        assert avg < 10.0, f"Average classification time {avg:.2f}ms exceeds 10ms"


class TestBottleneckPredictor:
    def test_init(self):
        """BottleneckPredictor initializes with seeded patterns."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()
        assert bp.engine.num_attractors == 5  # 5 known patterns

    def test_predict_empty_fleet(self):
        """Prediction with empty fleet returns normal operation."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()
        preds = bp.predict([])
        assert len(preds) >= 1
        assert preds[0]["pattern"] == "normal_operation"
        assert preds[0]["severity"] == "info"

    def test_predict_returns_structure(self):
        """Predictions have expected structure."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()
        preds = bp.predict(SAMPLE_ROBOTS)
        assert len(preds) >= 1
        for pred in preds:
            assert "pattern" in pred
            assert "confidence" in pred
            assert "description" in pred
            assert "severity" in pred

    def test_predict_under_25ms(self):
        """Full prediction pipeline must complete in < 25ms."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()

        # Warm up
        bp.predict(SAMPLE_ROBOTS)

        # Measure over 50 runs
        times = []
        for _ in range(50):
            preds, elapsed = bp.predict_timed(SAMPLE_ROBOTS)
            times.append(elapsed)

        avg_ms = sum(times) / len(times)
        max_ms = max(times)
        assert avg_ms < 25.0, f"Average prediction time {avg_ms:.2f}ms exceeds 25ms target"
        assert max_ms < 100.0, f"Max prediction time {max_ms:.2f}ms is too high"

    def test_battery_cascade_detection(self):
        """Detects battery cascade when multiple robots are low battery."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()

        low_battery_robots = [
            {
                "robot_id": f"robot_{i}",
                "status": "moving",
                "pose": {"x": float(i), "y": 0.0},
                "velocity": {"linear": 0.5},
                "battery": {"charge_pct": 10.0},
                "current_node": "N_01",
            }
            for i in range(5)
        ]

        preds = bp.predict(low_battery_robots)
        patterns = [p["pattern"] for p in preds]
        assert "battery_cascade_heuristic" in patterns

    def test_congestion_detection(self):
        """Detects congestion when multiple robots at same node."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()

        congested_robots = [
            {
                "robot_id": f"robot_{i}",
                "status": "waiting",
                "pose": {"x": 4.0, "y": 4.0},
                "velocity": {"linear": 0.0},
                "battery": {"charge_pct": 80.0},
                "current_node": "HUB",
            }
            for i in range(5)
        ]

        preds = bp.predict(congested_robots)
        patterns = [p["pattern"] for p in preds]
        assert "congestion_detected" in patterns

    def test_prediction_count_tracks(self):
        """Prediction count increments correctly."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        bp = BottleneckPredictor()
        assert bp.prediction_count == 0
        bp.predict(SAMPLE_ROBOTS)
        assert bp.prediction_count == 1
        bp.predict(SAMPLE_ROBOTS)
        assert bp.prediction_count == 2
