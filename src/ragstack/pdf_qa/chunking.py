"""Document chunking with page-level metadata preservation."""

import uuid

from .models import Document, Chunk


class DocumentChunker:
    """Split documents into chunks while preserving page information."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 100):
        """Initialize chunker.

        Args:
            chunk_size: Target characters per chunk
            chunk_overlap: Characters to overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, document: Document) -> list[Chunk]:
        """Split document into chunks with page tracking.

        Args:
            document: Document to chunk

        Returns:
            List of chunks with page metadata
        """
        chunks = []
        text = document.text
        lines = text.split("[PAGE_BREAK]\n")

        # Build a mapping of text position to page number
        page_positions = {}
        current_pos = 0
        for page_idx, line in enumerate(lines):
            page_positions[current_pos] = page_idx + 1  # Pages are 1-indexed
            current_pos += len(line) + len("[PAGE_BREAK]\n")

        # Split into chunks
        chunk_idx = 0
        start_idx = 0

        while start_idx < len(text):
            end_idx = min(start_idx + self.chunk_size, len(text))

            # Find nearest sentence boundary if possible
            if end_idx < len(text):
                # Look for a period within the last 100 chars
                search_end = max(start_idx + self.chunk_size - 100, start_idx + 50)
                last_period = text.rfind(".", search_end, end_idx)
                if last_period > start_idx:
                    end_idx = last_period + 1

            chunk_text = text[start_idx:end_idx].strip()
            if not chunk_text:
                start_idx += self.chunk_overlap
                continue

            # Determine page range for this chunk
            start_page = self._get_page_at_position(page_positions, start_idx)
            end_page = self._get_page_at_position(page_positions, end_idx)

            chunk = Chunk(
                id=f"{document.id}_chunk_{chunk_idx}",
                document_id=document.id,
                text=chunk_text,
                start_page=start_page,
                end_page=end_page,
                chunk_index=chunk_idx,
            )
            chunks.append(chunk)
            chunk_idx += 1

            # Move forward with overlap
            start_idx = end_idx - self.chunk_overlap

        return chunks

    @staticmethod
    def _get_page_at_position(page_positions: dict[int, int], pos: int) -> int:
        """Get page number at a text position."""
        matching_positions = [p for p in page_positions.keys() if p <= pos]
        if matching_positions:
            return page_positions[max(matching_positions)]
        return 1
