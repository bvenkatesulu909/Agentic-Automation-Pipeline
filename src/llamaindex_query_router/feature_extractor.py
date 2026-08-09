"""
Query feature extraction and analysis.

This module extracts and analyzes features from queries to inform
routing decisions. Features include:
- Query specificity (how targeted the query is)
- Temporal markers (time-sensitive language)
- Reasoning keywords (analytical intent)
- Structural patterns (boolean operators, quotes, etc.)
"""

from dataclasses import dataclass
from typing import List, Dict, Set
import re


@dataclass
class QueryFeatures:
    """
    Features extracted from a query for routing analysis.

    Attributes:
        query: The original query string
        length: Number of tokens in query (approx)
        has_quotes: Whether query contains exact phrase markers
        has_boolean_operators: Whether query uses AND, OR, NOT operators
        has_special_chars: Whether query contains special characters
        keyword_density: Ratio of nouns/verbs to total tokens (approx)
        entity_count: Number of detected named entities (approx)
        is_question: Whether query is phrased as a question
        question_type: Type of question (what, how, why, when, where, etc.)
        avg_word_length: Average character length of words
        contains_acronyms: Whether query contains potential acronyms
        contains_numbers: Whether query contains numerical values
        specificity_score: Score (0-1) indicating query specificity
        has_temporal: Whether query contains temporal markers
        has_reasoning_keywords: Whether query contains analytical reasoning keywords
        temporal_markers: List of detected temporal expressions
        reasoning_keywords: List of detected reasoning keywords
    """

    query: str
    length: int
    has_quotes: bool
    has_boolean_operators: bool
    has_special_chars: bool
    keyword_density: float
    entity_count: int
    is_question: bool
    question_type: str
    avg_word_length: float
    contains_acronyms: bool
    contains_numbers: bool
    specificity_score: float
    has_temporal: bool
    has_reasoning_keywords: bool
    temporal_markers: List[str]
    reasoning_keywords: List[str]


class QueryFeatureExtractor:
    """
    Extracts and analyzes features from queries.

    Features analyzed include structural patterns, specificity, temporal markers,
    and reasoning keywords to enable intelligent routing decisions.
    """

    # Common question words
    QUESTION_WORDS = {"what", "how", "why", "when", "where", "who", "which"}

    # Common boolean operators
    BOOLEAN_OPERATORS = {"and", "or", "not"}

    # Acronym pattern: sequences of uppercase letters
    ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,}\b")

    # Special characters that might indicate structured queries
    SPECIAL_CHARS = set("[]{}()+-=|&<>")

    # Temporal markers and temporal question types
    TEMPORAL_MARKERS = {
        "today", "yesterday", "tomorrow", "tonight",
        "morning", "afternoon", "evening", "night",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
        "january", "jan", "feb", "march", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "week", "month", "year", "day", "hour", "minute", "second",
        "now", "soon", "recently", "lately", "currently",
        "before", "after", "during", "while", "since", "until",
        "past", "future", "next", "last", "previous",
        "when", "date", "time", "schedule", "deadline"
    }

    # Reasoning keywords indicating analytical queries
    REASONING_KEYWORDS = {
        "analyze", "explain", "understand", "why", "how",
        "reason", "cause", "effect", "because", "therefore",
        "compare", "contrast", "difference", "similarity",
        "evaluate", "assess", "judge", "determine",
        "suggest", "recommend", "propose", "advise",
        "predict", "forecast", "estimate", "calculate",
        "summarize", "overview", "overview", "what is",
        "define", "meaning", "description", "detail",
        "interpret", "conclude", "infer", "deduce"
    }

    def extract_features(self, query: str) -> QueryFeatures:
        """
        Extract comprehensive features from a query.

        Args:
            query: The input query string

        Returns:
            QueryFeatures: Extracted features from the query
        """
        tokens = self._tokenize(query.lower())
        raw_tokens = self._tokenize(query)
        temporal_markers = self._extract_temporal_markers(tokens)
        reasoning_keywords = self._extract_reasoning_keywords(tokens)

        return QueryFeatures(
            query=query,
            length=len(tokens),
            has_quotes=self._check_quotes(query),
            has_boolean_operators=self._check_boolean_operators(tokens),
            has_special_chars=self._check_special_chars(query),
            keyword_density=self._calculate_keyword_density(tokens),
            entity_count=self._estimate_entity_count(raw_tokens),
            is_question=self._is_question(tokens),
            question_type=self._get_question_type(tokens),
            avg_word_length=self._calculate_avg_word_length(tokens),
            contains_acronyms=self._check_acronyms(query),
            contains_numbers=self._check_numbers(query),
            specificity_score=self._calculate_specificity_score(tokens, raw_tokens, query),
            has_temporal=len(temporal_markers) > 0,
            has_reasoning_keywords=len(reasoning_keywords) > 0,
            temporal_markers=temporal_markers,
            reasoning_keywords=reasoning_keywords,
        )

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization by splitting on whitespace and punctuation.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        # Split on whitespace and common punctuation
        tokens = re.findall(r"\b\w+\b", text)
        return tokens

    def _check_quotes(self, query: str) -> bool:
        """Check if query contains quoted phrases."""
        return bool(re.search(r'["\'].*["\']', query))

    def _check_boolean_operators(self, tokens: List[str]) -> bool:
        """Check if query contains boolean operators."""
        return any(token in self.BOOLEAN_OPERATORS for token in tokens)

    def _check_special_chars(self, query: str) -> bool:
        """Check if query contains special characters."""
        return any(char in self.SPECIAL_CHARS for char in query)

    def _calculate_keyword_density(self, tokens: List[str]) -> float:
        """
        Estimate keyword density (nouns, verbs) as ratio of total tokens.

        Args:
            tokens: List of query tokens

        Returns:
            Estimated keyword density (0.0 to 1.0)
        """
        # Simple heuristic: longer words are more likely to be keywords
        if not tokens:
            return 0.0

        keyword_tokens = sum(1 for token in tokens if len(token) > 4)
        return keyword_tokens / len(tokens)

    def _estimate_entity_count(self, tokens: List[str]) -> int:
        """
        Estimate number of named entities in query.

        Args:
            tokens: List of query tokens

        Returns:
            Estimated entity count
        """
        # Simple heuristic: capitalized words are potential entities
        entity_count = sum(1 for token in tokens if token[0].isupper())
        return max(0, entity_count)

    def _is_question(self, tokens: List[str]) -> bool:
        """Check if query is phrased as a question."""
        return len(tokens) > 0 and tokens[0] in self.QUESTION_WORDS

    def _get_question_type(self, tokens: List[str]) -> str:
        """
        Determine type of question based on question word.

        Args:
            tokens: List of query tokens

        Returns:
            Question type or empty string if not a question
        """
        if len(tokens) > 0 and tokens[0] in self.QUESTION_WORDS:
            return tokens[0]
        return ""

    def _calculate_avg_word_length(self, tokens: List[str]) -> float:
        """
        Calculate average word length in query.

        Args:
            tokens: List of query tokens

        Returns:
            Average word length
        """
        if not tokens:
            return 0.0
        return sum(len(token) for token in tokens) / len(tokens)

    def _check_acronyms(self, query: str) -> bool:
        """Check if query contains potential acronyms."""
        return bool(self.ACRONYM_PATTERN.search(query))

    def _check_numbers(self, query: str) -> bool:
        """Check if query contains numbers."""
        return bool(re.search(r"\d", query))

    def _calculate_specificity_score(
        self, tokens: List[str], raw_tokens: List[str], query: str
    ) -> float:
        """
        Calculate query specificity score (0-1).

        Specificity is determined by:
        - Query length (longer = more specific)
        - Keyword density (higher = more specific)
        - Presence of proper nouns/entities (more = more specific)
        - Presence of numbers/measurements (more = more specific)
        - Quoted phrases (exact phrases = very specific)

        Args:
            tokens: Tokenized query (lowercase)
            raw_tokens: Tokenized query (original case)
            query: Original query string

        Returns:
            Specificity score from 0.0 (very general) to 1.0 (very specific)
        """
        score = 0.0

        # Length component (up to 0.25)
        # Queries with 5-15 tokens are most specific
        if len(tokens) >= 5:
            score += min(0.25, len(tokens) / 20.0)

        # Keyword density component (up to 0.25)
        keyword_density = self._calculate_keyword_density(tokens)
        score += keyword_density * 0.25

        # Entity/proper noun component (up to 0.25)
        entity_count = self._estimate_entity_count(raw_tokens)
        if entity_count > 0:
            score += min(0.25, entity_count / 5.0)

        # Number/measurement component (up to 0.15)
        if self._check_numbers(query):
            score += 0.15

        # Exact phrase component (up to 0.10)
        if self._check_quotes(query):
            score += 0.10

        return min(1.0, score)

    def _extract_temporal_markers(self, tokens: List[str]) -> List[str]:
        """
        Extract temporal markers from query tokens.

        Args:
            tokens: Tokenized query (lowercase)

        Returns:
            List of detected temporal markers
        """
        markers = []
        for token in tokens:
            if token in self.TEMPORAL_MARKERS:
                markers.append(token)
        return markers

    def _extract_reasoning_keywords(self, tokens: List[str]) -> List[str]:
        """
        Extract reasoning/analytical keywords from query tokens.

        Args:
            tokens: Tokenized query (lowercase)

        Returns:
            List of detected reasoning keywords
        """
        keywords = []
        for token in tokens:
            if token in self.REASONING_KEYWORDS:
                keywords.append(token)
        return keywords
