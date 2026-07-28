"""Vector store tests. Synthetic vectors keep these fast and model-free."""

import json

import numpy as np
import pytest

from ragstack.chunking import Chunk
from ragstack.store import VectorStore


def unit(*values: float) -> np.ndarray:
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def store() -> VectorStore:
    chunks = [
        Chunk(id="a", text="about cats", source="animals.md", ordinal=0),
        Chunk(id="b", text="about dogs", source="animals.md", ordinal=1),
        Chunk(id="c", text="about servers", source="infra.md", ordinal=0),
    ]
    vectors = np.stack([unit(1, 0, 0), unit(0.9, 0.1, 0), unit(0, 0, 1)])
    return VectorStore.build(chunks, vectors, info={"embed_model": "test"})


def test_search_ranks_by_similarity(store: VectorStore):
    hits = store.search(unit(1, 0, 0), top_k=3, min_score=0.0)

    assert [h.id for h in hits] == ["a", "b", "c"]
    assert hits[0].score > hits[1].score > hits[2].score


def test_min_score_filters_weak_matches(store: VectorStore):
    hits = store.search(unit(0, 0, 1), top_k=3, min_score=0.5)

    assert [h.id for h in hits] == ["c"], "orthogonal chunks should be dropped"


def test_source_filter_restricts_candidate_pool(store: VectorStore):
    # Query points at the infra chunk, but the filter excludes it entirely.
    hits = store.search(unit(0, 0, 1), top_k=2, min_score=0.0, source_filter="animals")

    assert {h.source for h in hits} == {"animals.md"}


def test_source_filter_still_returns_top_k(store: VectorStore):
    """Filtering must narrow before ranking, not rank then narrow.

    Ranking first with top_k=1 would return only the infra chunk, and the filter
    would then leave nothing.
    """
    hits = store.search(unit(0, 0, 1), top_k=1, min_score=0.0, source_filter="animals")

    assert len(hits) == 1
    assert hits[0].source == "animals.md"


def test_unmatched_source_filter_returns_nothing(store: VectorStore):
    assert store.search(unit(1, 0, 0), min_score=0.0, source_filter="nope") == []


def test_top_k_larger_than_corpus_is_safe(store: VectorStore):
    hits = store.search(unit(1, 0, 0), top_k=99, min_score=0.0)

    assert len(hits) == 3


def test_roundtrip_through_disk(store: VectorStore, tmp_path):
    store.save(tmp_path)
    loaded = VectorStore.load(tmp_path)

    assert len(loaded) == len(store)
    assert loaded.info["embed_model"] == "test"
    np.testing.assert_allclose(loaded.vectors, store.vectors, rtol=1e-6)
    assert [h.id for h in loaded.search(unit(1, 0, 0), min_score=0.0)] == ["a", "b", "c"]


def test_exists_reflects_disk_state(store: VectorStore, tmp_path):
    assert not VectorStore.exists(tmp_path)
    store.save(tmp_path)
    assert VectorStore.exists(tmp_path)


def test_load_without_index_explains_how_to_build(tmp_path):
    with pytest.raises(FileNotFoundError, match="ragstack index"):
        VectorStore.load(tmp_path)


def test_schema_version_mismatch_is_rejected(store: VectorStore, tmp_path):
    store.save(tmp_path)
    meta_path = tmp_path / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["schema_version"] = 999
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(ValueError, match="rebuild"):
        VectorStore.load(tmp_path)


def test_vector_chunk_count_mismatch_is_rejected():
    chunks = [Chunk(id="a", text="one", source="x.md", ordinal=0)]
    with pytest.raises(ValueError, match="mismatch"):
        VectorStore(np.zeros((2, 3), dtype=np.float32), [c.__dict__ for c in chunks])


def test_empty_store_searches_cleanly():
    empty = VectorStore(np.zeros((0, 3), dtype=np.float32), [])

    assert empty.search(unit(1, 0, 0)) == []
    assert len(empty) == 0


def test_sources_counts_chunks_per_document(store: VectorStore):
    assert store.sources() == {"animals.md": 2, "infra.md": 1}


def test_citation_format(store: VectorStore):
    (hit,) = store.search(unit(0, 0, 1), top_k=1, min_score=0.5)

    assert hit.citation() == "infra.md#chunk0"
