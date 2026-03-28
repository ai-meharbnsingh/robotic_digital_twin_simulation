"""
SGEngine — Semantic Gravity attractor landscape for fleet state patterns.

Stores known patterns (attractors) and classifies new states by
finding the closest attractor in the energy landscape.

Uses a Hopfield-style energy function for attractor dynamics.
"""

import numpy as np
from typing import Any, Optional


class SGEngine:
    """
    Semantic Gravity engine — attractor landscape for fleet state classification.

    Stores fleet state patterns as attractors. Given a new state vector,
    finds which attractor basin it belongs to (pattern matching).
    """

    def __init__(self, dim: int = 128, convergence_threshold: float = 1e-6, max_iterations: int = 20):
        """
        Args:
            dim: Dimensionality of state vectors.
            convergence_threshold: Stop when energy change < threshold.
            max_iterations: Max Hopfield iterations.
        """
        self.dim = dim
        self.convergence_threshold = convergence_threshold
        self.max_iterations = max_iterations
        self._attractors: list[dict[str, Any]] = []
        self._weight_matrix: Optional[np.ndarray] = None
        self._dirty = True

    def add_attractor(self, state_vector: np.ndarray, label: str, metadata: dict = None):
        """
        Add a known fleet state pattern as an attractor.

        Args:
            state_vector: Feature vector (dim,).
            label: Human-readable label for this pattern.
            metadata: Optional metadata about the pattern.
        """
        if len(state_vector) != self.dim:
            raise ValueError(f"Expected dim={self.dim}, got {len(state_vector)}")

        self._attractors.append({
            "vector": state_vector.copy(),
            "label": label,
            "metadata": metadata or {},
        })
        self._dirty = True

    def _rebuild_weights(self):
        """Rebuild Hopfield weight matrix from attractors."""
        if not self._attractors:
            self._weight_matrix = np.zeros((self.dim, self.dim))
        else:
            self._weight_matrix = np.zeros((self.dim, self.dim))
            for attr in self._attractors:
                v = attr["vector"]
                norm = np.linalg.norm(v)
                if norm > 1e-12:
                    vn = v / norm
                    self._weight_matrix += np.outer(vn, vn)
            np.fill_diagonal(self._weight_matrix, 0)
        self._dirty = False

    def classify(self, state_vector: np.ndarray) -> dict[str, Any]:
        """
        Classify a state vector by finding the closest attractor.

        Args:
            state_vector: Feature vector (dim,).

        Returns:
            Dict with {label, similarity, energy, converged_in}.
        """
        if self._dirty:
            self._rebuild_weights()

        if not self._attractors:
            return {"label": "unknown", "similarity": 0.0, "energy": 0.0, "converged_in": 0}

        # Normalize
        norm = np.linalg.norm(state_vector)
        if norm < 1e-12:
            return {"label": "unknown", "similarity": 0.0, "energy": 0.0, "converged_in": 0}

        state = state_vector / norm

        # Hopfield dynamics
        prev_energy = self._energy(state)
        iterations = 0
        for i in range(self.max_iterations):
            new_state = np.tanh(self._weight_matrix @ state)
            new_norm = np.linalg.norm(new_state)
            if new_norm > 1e-12:
                new_state /= new_norm
            new_energy = self._energy(new_state)

            iterations = i + 1
            if abs(new_energy - prev_energy) < self.convergence_threshold:
                state = new_state
                break
            state = new_state
            prev_energy = new_energy

        # Find closest attractor
        best_label = "unknown"
        best_sim = -float("inf")
        for attr in self._attractors:
            v = attr["vector"]
            vnorm = np.linalg.norm(v)
            if vnorm < 1e-12:
                continue
            sim = float(np.dot(state, v / vnorm))
            if sim > best_sim:
                best_sim = sim
                best_label = attr["label"]

        return {
            "label": best_label,
            "similarity": round(best_sim, 4),
            "energy": round(float(self._energy(state)), 4),
            "converged_in": iterations,
        }

    def _energy(self, state: np.ndarray) -> float:
        """Compute Hopfield energy: E = -0.5 * s^T W s."""
        return -0.5 * float(state @ self._weight_matrix @ state)

    @property
    def num_attractors(self) -> int:
        return len(self._attractors)

    @property
    def attractor_labels(self) -> list[str]:
        return [a["label"] for a in self._attractors]
