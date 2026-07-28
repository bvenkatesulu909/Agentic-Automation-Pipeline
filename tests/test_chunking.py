from pathlib import Path

import pytest

from ragstack import chunking


def test_splits_on_paragraph_boundaries():
    text = "\n\n".join(f"Paragraph number {i}. " * 10 for i in range(10))
    chunks = chunking.chunk_text(text, size=400, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 400 + 50 for c in chunks), "chunks should respect the size bound"


def test_short_text_is_one_chunk():
    assert chunking.chunk_text("Just a sentence.", size=500, overlap=50) == [
        "Just a sentence."
    ]


def test_empty_text_yields_no_chunks():
    assert chunking.chunk_text("   \n\n  ", size=500, overlap=50) == []


def test_oversized_paragraph_is_hard_split():
    # A single paragraph with no blank lines, far larger than the chunk size.
    text = "x" * 2000
    chunks = chunking.chunk_text(text, size=300, overlap=0)

    assert len(chunks) == 7  # ceil(2000 / 300)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks) == text, "hard split must not lose characters"


def test_overlap_carries_context_forward():
    paragraphs = ["A" * 200, "B" * 200, "C" * 200]
    chunks = chunking.chunk_text("\n\n".join(paragraphs), size=250, overlap=60)

    assert len(chunks) >= 2
    # The tail of chunk 0 should reappear at the head of chunk 1.
    assert chunks[0][-60:] in chunks[1]


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError, match="overlap must be smaller"):
        chunking.chunk_text("text", size=100, overlap=100)


def test_chunk_document_ids_are_stable_and_unique(tmp_path: Path):
    doc = tmp_path / "notes.md"
    doc.write_text("\n\n".join(f"Section {i} body text." for i in range(5)), encoding="utf-8")

    first = chunking.chunk_document(doc, tmp_path)
    second = chunking.chunk_document(doc, tmp_path)

    assert [c.id for c in first] == [c.id for c in second], "IDs must be deterministic"
    assert len({c.id for c in first}) == len(first), "IDs must be unique"
    assert all(c.source == "notes.md" for c in first)
    assert [c.ordinal for c in first] == list(range(len(first)))


def test_discover_finds_supported_files_only(tmp_path: Path):
    (tmp_path / "a.md").write_text("markdown", encoding="utf-8")
    (tmp_path / "b.txt").write_text("text", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"\x89PNG")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "d.md").write_text("nested markdown", encoding="utf-8")

    found = {p.name for p in chunking.discover(tmp_path)}

    assert found == {"a.md", "b.txt", "d.md"}


def test_nested_source_paths_use_forward_slashes(tmp_path: Path):
    nested = tmp_path / "team" / "policies"
    nested.mkdir(parents=True)
    doc = nested / "security.md"
    doc.write_text("Security policy body.", encoding="utf-8")

    (chunk,) = chunking.chunk_document(doc, tmp_path)

    # Windows backslashes would make citations inconsistent across platforms.
    assert chunk.source == "team/policies/security.md"
