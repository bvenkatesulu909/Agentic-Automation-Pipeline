"""Uncertainty detection for triggering human review in workflows.

Evaluates when human intervention is needed based on:
- Retrieval confidence (semantic similarity scores)
- Semantic coherence (consistency within retrieved documents)
- LLM response confidence (token probabilities if available)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .pdf_qa.models import QAResponse, RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class UncertaintyScore:
    """Result of uncertainty evaluation."""

    score: float  # 0-1, higher = more uncertain
    confidence: float  # 0-1, inverse of score (higher = more confident)
    reason: str  # Human-readable explanation
    retrieval_confidence: float  # 0-1
    coherence_score: float  # 0-1, semantic consistency
    response_confidence: float | None  # 0-1 if available


class UncertaintyDetector:
    """Detects when human review is needed in RAG workflows."""

    def __init__(
        self,
        retrieval_threshold: float = 0.5,
        coherence_threshold: float = 0.6,
        response_threshold: float = 0.5,
        approval_trigger: float = 0.7,
    ):
        """Initialize uncertainty detector.

        Args:
            retrieval_threshold: Min confidence for retrieval (0-1)
            coherence_threshold: Min coherence within retrieved docs (0-1)
            response_threshold: Min confidence for LLM response (0-1)
            approval_trigger: Score threshold that triggers approval gate (0-1)
        """
        self.retrieval_threshold = retrieval_threshold
        self.coherence_threshold = coherence_threshold
        self.response_threshold = response_threshold
        self.approval_trigger = approval_trigger

    def evaluate_retrieval(
        self,
        retrieved_chunks: list[RetrievalResult],
        min_chunks: int = 3,
    ) -> UncertaintyScore:
        """Evaluate uncertainty of retrieved documents.

        High uncertainty if:
        - Few documents retrieved
        - Low average confidence scores
        - Low semantic coherence between results
        - Large gaps in similarity scores (some high, some low)

        Args:
            retrieved_chunks: Results from retrieval step
            min_chunks: Minimum acceptable retrieval count

        Returns:
            UncertaintyScore for retrieval quality
        """
        if not retrieved_chunks:
            return UncertaintyScore(
                score=1.0,
                confidence=0.0,
                reason="No documents retrieved",
                retrieval_confidence=0.0,
                coherence_score=0.0,
                response_confidence=None,
            )

        # Check retrieval quantity
        if len(retrieved_chunks) < min_chunks:
            return UncertaintyScore(
                score=0.9,
                confidence=0.1,
                reason=f"Only {len(retrieved_chunks)} documents retrieved (min {min_chunks})",
                retrieval_confidence=float(len(retrieved_chunks)) / min_chunks,
                coherence_score=0.0,
                response_confidence=None,
            )

        # Extract confidence scores (final_score from RetrievalResult)
        scores = np.array([chunk.final_score for chunk in retrieved_chunks])

        # Calculate metrics
        avg_score = float(np.mean(scores))
        std_score = float(np.std(scores))
        min_score = float(np.min(scores))
        max_score = float(np.max(scores))

        # Coherence: penalize high variance in scores
        # High variance = inconsistent relevance = low coherence
        coherence = 1.0 - min(1.0, std_score)

        # Calculate retrieval confidence
        # Penalize low average scores and low minimum score
        retrieval_conf = (avg_score + min_score) / 2.0

        # Composite uncertainty score
        reasons = []

        if avg_score < self.retrieval_threshold:
            reasons.append(
                f"Low average confidence ({avg_score:.2f} < {self.retrieval_threshold})"
            )

        if coherence < self.coherence_threshold:
            reasons.append(
                f"Low coherence ({coherence:.2f} < {self.coherence_threshold})"
            )

        if min_score < 0.3:
            reasons.append(f"Weak lowest-scored match ({min_score:.2f})")

        if max_score - min_score > 0.4:
            reasons.append(f"Large score variance ({max_score - min_score:.2f})")

        # Combine uncertainty signals
        uncertainty = (
            (1.0 - retrieval_conf) * 0.6 +  # 60% weight on retrieval confidence
            (1.0 - coherence) * 0.4  # 40% weight on coherence
        )

        return UncertaintyScore(
            score=float(uncertainty),
            confidence=1.0 - float(uncertainty),
            reason=" | ".join(reasons) if reasons else "Retrieval appears confident",
            retrieval_confidence=retrieval_conf,
            coherence_score=coherence,
            response_confidence=None,
        )

    def evaluate_response(
        self,
        response: QAResponse,
        retrieved_chunks: list[RetrievalResult],
    ) -> UncertaintyScore:
        """Evaluate uncertainty of LLM-generated response.

        High uncertainty if:
        - Response is very short (incomplete)
        - Response admits uncertainty ("I'm not sure", "I don't know")
        - Response contradicts retrieved documents
        - Few or weak citations

        Args:
            response: Generated answer from LLM
            retrieved_chunks: Retrieved context used for generation

        Returns:
            UncertaintyScore for response quality
        """
        reasons = []
        uncertainty_signals = []

        # Check response length (very short responses are often evasive)
        answer_length = len(response.answer.split())
        if answer_length < 20:
            reasons.append(f"Very short response ({answer_length} words)")
            uncertainty_signals.append(0.6)  # High uncertainty signal

        # Check for explicit uncertainty phrases
        uncertainty_phrases = [
            "i'm not sure",
            "i don't know",
            "unclear",
            "not clear",
            "insufficient",
            "cannot determine",
            "don't have enough",
            "limited information",
        ]
        answer_lower = response.answer.lower()
        for phrase in uncertainty_phrases:
            if phrase in answer_lower:
                reasons.append(f'Response contains "{phrase}"')
                uncertainty_signals.append(0.7)

        # Check citation strength
        if response.sources:
            source_scores = [s.final_score for s in response.sources]
            avg_source_score = float(np.mean(source_scores))
            if avg_source_score < 0.5:
                reasons.append(f"Weak source citations ({avg_source_score:.2f})")
                uncertainty_signals.append(0.5)
        else:
            reasons.append("No sources cited")
            uncertainty_signals.append(0.4)

        # Check if response covers key retrieved concepts
        # (simplified: just check if it references any source documents)
        if not response.sources and retrieved_chunks:
            reasons.append("Response does not cite retrieved documents")
            uncertainty_signals.append(0.5)

        # Composite uncertainty
        if uncertainty_signals:
            uncertainty = float(np.mean(uncertainty_signals))
        else:
            uncertainty = 0.2  # Low uncertainty if no signals found

        return UncertaintyScore(
            score=min(1.0, uncertainty),
            confidence=1.0 - min(1.0, uncertainty),
            reason=" | ".join(reasons) if reasons else "Response appears confident",
            retrieval_confidence=0.0,
            coherence_score=0.0,
            response_confidence=1.0 - min(1.0, uncertainty),
        )

    def should_gate(self, uncertainty_score: UncertaintyScore) -> bool:
        """Check if uncertainty score triggers approval gate.

        Args:
            uncertainty_score: Result from evaluate_retrieval or evaluate_response

        Returns:
            True if score exceeds approval_trigger threshold
        """
        return uncertainty_score.score >= self.approval_trigger


# Preset configurations for common use cases


def detector_for_sales_queries() -> UncertaintyDetector:
    """Detector tuned for sales agent queries.

    Sales queries often need high confidence in retrieval (product info is critical).
    Lower threshold for response confidence (sales responses can be more informal).
    """
    return UncertaintyDetector(
        retrieval_threshold=0.6,  # Stricter retrieval
        coherence_threshold=0.65,
        response_threshold=0.4,  # Looser response confidence
        approval_trigger=0.65,  # Trigger approval earlier
    )


def detector_for_qa_queries() -> UncertaintyDetector:
    """Detector tuned for Q&A workflows.

    Balanced approach: moderate thresholds, trigger approval at 0.7.
    """
    return UncertaintyDetector(
        retrieval_threshold=0.5,
        coherence_threshold=0.6,
        response_threshold=0.5,
        approval_trigger=0.7,
    )


def detector_strict() -> UncertaintyDetector:
    """Strict detector - triggers approval easily.

    Use for critical workflows (legal, medical, financial).
    """
    return UncertaintyDetector(
        retrieval_threshold=0.7,
        coherence_threshold=0.75,
        response_threshold=0.65,
        approval_trigger=0.6,
    )
