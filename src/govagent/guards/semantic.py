from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("govagent.guards.semantic")


class SemanticGuard:
    """
    Qualitative Integrity Layer.
    Uses localized Sentence-Transformer embeddings when the enterprise extra
    is installed; otherwise alignment checks are skipped (fail-open with a warning).
    """

    def __init__(self, mission: str, prohibited: list[str], threshold: float = 0.60):
        self.mission = mission
        self.prohibited = prohibited
        self.threshold = threshold
        self.model: Any | None = None
        self.prohibited_embeddings = np.empty((0, 384))

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning(
                "SemanticGuard: sentence-transformers is not installed. "
                "Install govagent[enterprise] to enable vector alignment checks."
            )
            return

        logger.info("🧠 SemanticGuard: Initializing localized SentenceTransformer embedding engine...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        if self.prohibited:
            embeddings = self.model.encode(self.prohibited, convert_to_numpy=True)
            norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
            self.prohibited_embeddings = embeddings / (norms + 1e-8)

    def _calculate_max_similarity(self, target_vector: np.ndarray) -> float:
        target_norm = np.linalg.norm(target_vector)
        if target_norm < 1e-8:
            return 0.0
        normalized_target = target_vector / target_norm
        similarities = np.dot(self.prohibited_embeddings, normalized_target)
        return float(np.max(similarities))

    def evaluate_alignment(self, agent_thought: str) -> float:
        """
        Maximum cosine similarity against prohibited strategies.
        Returns 0.0 on a threshold breach, or the residual margin (1 - max similarity).
        Returns 1.0 when there is nothing to evaluate or the model is unavailable.
        """
        if not agent_thought or not str(agent_thought).strip():
            return 1.0
        if self.model is None or self.prohibited_embeddings.shape[0] == 0:
            return 1.0

        target_vector = self.model.encode(agent_thought, convert_to_numpy=True)
        max_violation_score = self._calculate_max_similarity(target_vector)
        logger.info(
            "🧠 SemanticGuard: Vector comparison sweep hit a maximum proximity index of %.4f",
            max_violation_score,
        )
        if max_violation_score >= self.threshold:
            logger.warning(
                "🛑 [govAgent Semantic Breach] Prohibited intent matching threshold hit: "
                "Max Sim %.4f >= Tolerance %s",
                max_violation_score,
                self.threshold,
            )
            return 0.0
        return float(1.0 - max_violation_score)
