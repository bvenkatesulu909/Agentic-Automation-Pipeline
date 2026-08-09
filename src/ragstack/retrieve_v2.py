"""Retrieval with production-grade vector store: hybrid search, caching, backups.

Replaces retrieve.py with:
- Qdrant backend option for scale
- Hybrid search (semantic + BM25)
- Query embedding cache
- Backup/recovery management
- Metadata filtering
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from . import config, embed
from .backup import BackupManager
from .embedding_cache import cached_embed_one, get_cache
from .hybrid_search import HybridSearcher, SearchConfig
from .qdrant_store import QdrantVectorStore, SearchHit

if TYPE_CHECKING:
    from .qdrant_store import QdrantVectorStore as Store

logger = logging.getLogger(__name__)

_store: QdrantVectorStore | None = None
_store_dir: Path | None = None
_searcher: HybridSearcher | None = None
_backup_manager: BackupManager | None = None
_lock = threading.Lock()


def get_store(
    collection_name: str | None = None,
    url: str | None = None,
    api_key: str | None = None,
    path: Path | None = None,
    reload: bool = False,
) -> QdrantVectorStore:
    """Get or create the Qdrant vector store.

    The store is cached process-wide. Different configurations trigger a reload.

    Args:
        collection_name: Qdrant collection name
        url: Remote Qdrant server URL
        api_key: API key for remote Qdrant
        path: Local path for embedded Qdrant
        reload: Force reload of store

    Returns:
        QdrantVectorStore instance
    """
    global _store, _store_dir
    collection = collection_name or config.QDRANT_COLLECTION
    target_url = url or config.QDRANT_URL
    target_path = path or (config.INDEX_DIR / "qdrant_db")

    cache_key = (collection, target_url, target_path)

    if reload or _store is None or _store_dir != target_path:
        with _lock:
            if reload or _store is None or _store_dir != target_path:
                _store = QdrantVectorStore(
                    collection_name=collection,
                    url=target_url,
                    api_key=api_key or config.QDRANT_API_KEY,
                    path=target_path,
                    vector_size=config.QDRANT_VECTOR_SIZE,
                )
                _store_dir = target_path
                logger.info(f"Loaded Qdrant store: {collection}")

    return _store


def get_searcher(store: QdrantVectorStore | None = None) -> HybridSearcher:
    """Get or create hybrid searcher with BM25 indexing.

    Args:
        store: QdrantVectorStore to search (uses default if None)

    Returns:
        HybridSearcher instance
    """
    global _searcher
    store = store or get_store()

    if _searcher is None or _searcher.store != store:
        with _lock:
            if _searcher is None or _searcher.store != store:
                _searcher = HybridSearcher(store)
                logger.info("Initialized hybrid searcher")

    return _searcher


def get_backup_manager(backup_dir: Path | None = None) -> BackupManager:
    """Get or create backup manager.

    Args:
        backup_dir: Directory for backups

    Returns:
        BackupManager instance
    """
    global _backup_manager
    if _backup_manager is None:
        with _lock:
            if _backup_manager is None:
                _backup_manager = BackupManager(
                    backup_dir=backup_dir,
                    max_backups=config.BACKUP_MAX_BACKUPS,
                    retention_days=config.BACKUP_RETENTION_DAYS,
                )

    return _backup_manager


def search(
    query: str,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
    filters: dict | None = None,
    use_hybrid: bool = True,
    semantic_weight: float | None = None,
    keyword_weight: float | None = None,
) -> list[SearchHit]:
    """Search the vector store with optional hybrid ranking.

    Args:
        query: Query text
        top_k: Number of results to return
        min_score: Minimum similarity score
        filters: Metadata filters, e.g. {"source": "sales.md"}
        use_hybrid: Use hybrid search (semantic + BM25) if True
        semantic_weight: Weight for semantic similarity (0-1)
        keyword_weight: Weight for keyword match (0-1)

    Returns:
        Ranked SearchHit results

    Example:
        >>> hits = search("sales pricing", top_k=5, filters={"source": "pricing.md"})
        >>> for hit in hits:
        ...     print(f"[{hit.score:.2f}] {hit.citation()}: {hit.text[:50]}")
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    top_k = top_k or config.TOP_K
    min_score = config.MIN_SCORE if min_score is None else min_score

    query_vector = cached_embed_one(embed.embed_one, query)

    if use_hybrid:
        semantic_w = semantic_weight or config.HYBRID_SEMANTIC_WEIGHT
        keyword_w = keyword_weight or config.HYBRID_KEYWORD_WEIGHT

        searcher = get_searcher()
        return searcher.search(
            query,
            query_vector,
            top_k=top_k,
            semantic_weight=semantic_w,
            keyword_weight=keyword_w,
            filters=filters,
        )
    else:
        store = get_store()
        return store.search(
            query_vector,
            top_k=top_k,
            min_score=min_score,
            filters=filters,
        )


def search_by_source(
    query: str,
    source: str,
    *,
    top_k: int | None = None,
    use_hybrid: bool = True,
) -> list[SearchHit]:
    """Search within a specific document source.

    Args:
        query: Query text
        source: Source document name (e.g., "sales-guide.md")
        top_k: Number of results
        use_hybrid: Use hybrid search

    Returns:
        Ranked results from the specified source
    """
    return search(
        query,
        top_k=top_k,
        filters={"source": source},
        use_hybrid=use_hybrid,
    )


def search_with_config(
    query: str,
    config: SearchConfig,
    *,
    filters: dict | None = None,
) -> list[SearchHit]:
    """Search with a custom SearchConfig.

    Args:
        query: Query text
        config: SearchConfig instance (includes weights, top_k, min_score)
        filters: Metadata filters

    Returns:
        Ranked results

    Example:
        >>> config = SearchConfig.for_sales_query()
        >>> hits = search_with_config("pricing tiers", config)
    """
    return search(
        query,
        top_k=config.top_k,
        min_score=config.min_score,
        filters=filters,
        semantic_weight=config.semantic_weight,
        keyword_weight=config.keyword_weight,
    )


def format_context(hits: list[SearchHit]) -> str:
    """Render hits as a numbered, citable context block.

    Args:
        hits: SearchHit results

    Returns:
        Formatted context string with citations

    Example:
        >>> hits = search("pricing")
        >>> context = format_context(hits)
        >>> print(context)
        [1] source: sales-guide.md#chunk0 (similarity 0.856)
        Annual pricing starts at $X per user...
    """
    if not hits:
        return "(no relevant passages found)"

    blocks = []
    for i, hit in enumerate(hits, start=1):
        score_pct = hit.score * 100
        blocks.append(
            f"[{i}] source: {hit.citation()} ({score_pct:.1f}% match)\n{hit.text}"
        )
    return "\n\n---\n\n".join(blocks)


# Backup and recovery
def create_backup(name: str | None = None) -> Path:
    """Create a backup of the vector store.

    Args:
        name: Custom backup name (default: auto-generated timestamp)

    Returns:
        Path to the backup

    Example:
        >>> backup_path = create_backup("before-refresh")
    """
    store = get_store()
    manager = get_backup_manager()
    return manager.create_backup(store, name=name)


def restore_backup(backup_name: str, verify: bool = True) -> None:
    """Restore from a backup snapshot.

    Args:
        backup_name: Name of the backup to restore
        verify: Verify backup integrity before restoring
    """
    store = get_store()
    manager = get_backup_manager()
    manager.restore_backup(store, backup_name, verify=verify)
    logger.info(f"Restored from backup: {backup_name}")


def list_backups() -> list[dict]:
    """List all available backups.

    Returns:
        List of backup metadata dicts
    """
    manager = get_backup_manager()
    backups = manager.list_backups()
    return [
        {
            "name": b.name,
            "timestamp": b.timestamp,
            "points": b.point_count,
            "size_mb": round(b.size_bytes / 1024 / 1024, 2),
        }
        for b in backups
    ]


# Introspection and stats
def cache_stats() -> dict:
    """Get embedding cache statistics.

    Returns:
        Dict with hit/miss stats and cache size
    """
    cache = get_cache()
    return cache.stats()


def store_stats() -> dict:
    """Get vector store statistics.

    Returns:
        Dict with store size and source breakdown
    """
    store = get_store()
    return {
        "total_chunks": len(store),
        "sources": store.list_sources(),
    }


def clear_embedding_cache() -> None:
    """Clear the embedding cache (forces re-embedding on next query)."""
    cache = get_cache()
    cache.clear()


def save_embedding_cache() -> None:
    """Persist embedding cache to disk."""
    cache = get_cache()
    cache.save()
