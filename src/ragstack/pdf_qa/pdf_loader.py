"""PDF document loader with page tracking."""

import uuid
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from .models import Document


class PDFLoader:
    """Load and parse PDF files with page-level metadata."""

    @staticmethod
    def load(pdf_path: str | Path, doc_id: Optional[str] = None) -> Document:
        """Load a PDF and extract text with page boundaries.

        Args:
            pdf_path: Path to the PDF file
            doc_id: Optional document ID (generated if not provided)

        Returns:
            Document with extracted text and metadata
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)

        # Extract text with page tracking
        full_text = ""
        page_breaks = [0]  # Track where each page starts in the full text

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                full_text += text + "\n[PAGE_BREAK]\n"
                page_breaks.append(len(full_text))

        return Document(
            id=doc_id or str(uuid.uuid4()),
            path=str(pdf_path),
            name=pdf_path.stem,
            text=full_text,
            total_pages=total_pages,
        )

    @staticmethod
    def batch_load(pdf_dir: str | Path) -> list[Document]:
        """Load all PDFs from a directory.

        Args:
            pdf_dir: Directory containing PDF files

        Returns:
            List of loaded documents
        """
        pdf_dir = Path(pdf_dir)
        if not pdf_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {pdf_dir}")

        documents = []
        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            try:
                doc = PDFLoader.load(pdf_file)
                documents.append(doc)
            except Exception as e:
                print(f"Warning: Failed to load {pdf_file}: {e}")
                continue

        return documents
