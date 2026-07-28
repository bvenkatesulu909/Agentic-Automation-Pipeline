"""End-to-end test with the real embedding model.

Marked `slow` because the first run loads torch and the model weights (~30s
cold, seconds once cached):

    uv run pytest -m "not slow"    # skip these
"""

import pytest

from ragstack import index, retrieve
from ragstack.store import VectorStore

pytestmark = pytest.mark.slow


CORPUS = {
    "coffee.md": (
        "# Brewing Guide\n\n"
        "Use water just off the boil, around 94 degrees Celsius. Grind size "
        "matters more than dose: too fine and the espresso chokes, too coarse "
        "and it runs sour and thin.\n\n"
        "## Ratios\n\n"
        "A standard espresso pulls 18 grams of ground coffee into 36 grams of "
        "liquid, in roughly 28 seconds."
    ),
    "bicycle.md": (
        "# Drivetrain Maintenance\n\n"
        "Degrease the chain every 300 kilometres, more often in wet weather. "
        "A worn chain wears the cassette, so replace it at 0.5 percent stretch "
        "rather than waiting for it to skip.\n\n"
        "## Tyre pressure\n\n"
        "Run 5.5 bar for a 28mm tyre on tarmac. Lower pressure improves grip "
        "on rough surfaces."
    ),
}


@pytest.fixture(scope="module")
def built_index(tmp_path_factory):
    docs = tmp_path_factory.mktemp("docs")
    idx = tmp_path_factory.mktemp("index")

    for name, body in CORPUS.items():
        (docs / name).write_text(body, encoding="utf-8")

    index.build_index(docs_dir=docs, index_dir=idx, show_progress=False, verbose=False)
    return idx


def test_index_is_persisted_with_metadata(built_index):
    store = VectorStore.load(built_index)

    assert len(store) >= 2
    assert set(store.sources()) == {"coffee.md", "bicycle.md"}
    assert store.info["dimension"] == 384
    assert store.info["documents"] == 2
    assert store.vectors.shape[0] == len(store)


def test_embeddings_are_normalised(built_index):
    """Cosine similarity is computed as a plain dot product, which is only
    correct if every stored vector has unit length."""
    import numpy as np

    store = VectorStore.load(built_index)
    norms = np.linalg.norm(store.vectors, axis=1)

    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


@pytest.mark.parametrize(
    "query, expected_source",
    [
        ("how finely should I grind the beans?", "coffee.md"),
        ("when do I need to replace a worn chain?", "bicycle.md"),
        ("what pressure for my tyres?", "bicycle.md"),
        ("how many grams of coffee for a shot?", "coffee.md"),
    ],
)
def test_semantic_search_finds_the_right_document(built_index, query, expected_source):
    """Queries share almost no literal vocabulary with the documents, so a
    keyword search would miss these — this is the real test of the embeddings."""
    hits = retrieve.search(query, top_k=1, index_dir=built_index, min_score=0.0)

    assert hits, f"no hits for {query!r}"
    assert hits[0].source == expected_source


def test_unrelated_query_scores_below_threshold(built_index):
    hits = retrieve.search(
        "quarterly revenue recognition under IFRS 15",
        index_dir=built_index,
        min_score=0.35,
    )

    assert hits == [], "an off-topic query should return nothing, not a weak match"


def test_source_filter_end_to_end(built_index):
    hits = retrieve.search(
        "grind size", top_k=5, index_dir=built_index, min_score=0.0, source_filter="bicycle"
    )

    assert hits
    assert all(h.source == "bicycle.md" for h in hits)


def test_format_context_numbers_passages_for_citation(built_index):
    hits = retrieve.search("espresso ratio", top_k=2, index_dir=built_index, min_score=0.0)
    context = retrieve.format_context(hits)

    assert "[1]" in context
    assert "coffee.md#chunk" in context


def test_empty_corpus_is_a_clear_error(tmp_path):
    (tmp_path / "docs").mkdir()

    with pytest.raises(ValueError, match="No indexable documents"):
        index.build_index(docs_dir=tmp_path / "docs", index_dir=tmp_path / "idx", verbose=False)


def test_missing_docs_dir_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        index.build_index(docs_dir=tmp_path / "nope", index_dir=tmp_path / "idx", verbose=False)
