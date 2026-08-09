"""LLM integration for answer generation with reasoning."""

from typing import Optional

from anthropic import Anthropic

from .models import RetrievalResult, QAResponse


class AnswerGenerator:
    """Generate answers from retrieved context using Claude."""

    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        """Initialize answer generator.

        Args:
            model: Claude model to use
        """
        self.model = model
        self.client = Anthropic()

    def generate_answer(
        self,
        query: str,
        retrieved_chunks: list[RetrievalResult],
        include_reasoning: bool = False,
    ) -> QAResponse:
        """Generate an answer based on retrieved context.

        Args:
            query: Original query
            retrieved_chunks: Retrieved and ranked chunks
            include_reasoning: Whether to include reasoning in response

        Returns:
            QAResponse with answer and citations
        """
        if not retrieved_chunks:
            return QAResponse(
                question=query,
                answer="No relevant documents found to answer this question.",
                sources=[],
            )

        # Format context with clear chunk boundaries
        context = self._format_context(retrieved_chunks)

        system_prompt = """You are a helpful assistant that answers questions based on provided documents.
When answering:
1. Use only information from the provided context
2. Be accurate and concise
3. If you're uncertain, say so
4. Focus on directly answering the question

The context below contains relevant excerpts from the documents."""

        user_prompt = f"""Context:
{context}

Question: {query}

Please answer this question based on the context provided. If the context doesn't contain information needed to fully answer the question, state that clearly."""

        messages = [{"role": "user", "content": user_prompt}]

        # Request extended thinking if reasoning is needed
        extra_headers = None
        if include_reasoning:
            extra_headers = {"anthropic-beta": "interleaved-thinking-2025-05-14"}

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            thinking={
                "type": "enabled",
                "budget_tokens": 1000,
            } if include_reasoning else None,
            extra_headers=extra_headers,
        )

        # Extract answer text
        answer_text = ""
        reasoning_text = ""

        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "thinking":
                    reasoning_text = block.thinking
                elif block.type == "text":
                    answer_text = block.text

        return QAResponse(
            question=query,
            answer=answer_text,
            sources=retrieved_chunks,
            reasoning=reasoning_text if include_reasoning else None,
        )

    @staticmethod
    def _format_context(chunks: list[RetrievalResult]) -> str:
        """Format chunks into a readable context string.

        Args:
            chunks: Retrieved chunks

        Returns:
            Formatted context string
        """
        formatted = []
        for i, result in enumerate(chunks, 1):
            formatted.append(
                f"[Source {i}: {result.citation} (confidence: {result.final_score:.2f})]"
            )
            formatted.append(result.chunk.text)
            formatted.append("")

        return "\n".join(formatted)
