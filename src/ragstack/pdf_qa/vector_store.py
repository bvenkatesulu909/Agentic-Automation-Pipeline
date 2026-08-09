"""SQLite-vec based vector store for embeddings."""

import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np

from .models import Chunk


class SQLiteVecStore:
    """Vector store using SQLite with vec extension for embeddings."""

    def __init__(self, db_path: str | Path = ":memory:", embedding_dim: int = 384):
        """Initialize vector store.

        Args:
            db_path: Path to SQLite database file
            embedding_dim: Dimension of embeddings (default 384 for MiniLM)
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else ":memory:"
        self.embedding_dim = embedding_dim
        self.connection: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Initialize database and create tables."""
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.enable_load_extension(True)

        try:
            self.connection.load_extension("sqlite_vec")
        except sqlite3.OperationalError:
            # sqlite_vec might not be available; create a fallback schema
            print(
                "Warning: sqlite_vec extension not available. "
                "Using standard SQLite for storage only."
            )

        cursor = self.connection.cursor()

        # Create chunks table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                text TEXT NOT NULL,
                start_page INTEGER NOT NULL,
                end_page INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create embeddings table
        # Try to use vec type if extension is available
        try:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL UNIQUE,
                    embedding vec({self.embedding_dim}),
                    FOREIGN KEY(chunk_id) REFERENCES chunks(id)
                )
                """
            )
        except sqlite3.OperationalError:
            # Fallback to BLOB storage
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL UNIQUE,
                    embedding BLOB NOT NULL,
                    FOREIGN KEY(chunk_id) REFERENCES chunks(id)
                )
                """
            )

        # Create indices
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings(chunk_id)"
        )

        self.connection.commit()

    def add_chunk(self, chunk: Chunk) -> None:
        """Add a chunk to the store.

        Args:
            chunk: Chunk to add
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO chunks
            (id, document_id, text, start_page, end_page, chunk_index)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.id,
                chunk.document_id,
                chunk.text,
                chunk.start_page,
                chunk.end_page,
                chunk.chunk_index,
            ),
        )
        self.connection.commit()

    def add_embedding(self, chunk_id: str, embedding: list[float]) -> None:
        """Add embedding for a chunk.

        Args:
            chunk_id: ID of the chunk
            embedding: Embedding vector
        """
        cursor = self.connection.cursor()
        embed_id = f"{chunk_id}_embed"

        try:
            # Try vec-based insertion
            cursor.execute(
                "INSERT OR REPLACE INTO embeddings (id, chunk_id, embedding) VALUES (?, ?, ?)",
                (embed_id, chunk_id, embedding),
            )
        except (sqlite3.OperationalError, TypeError):
            # Fallback to BLOB
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
            cursor.execute(
                "INSERT OR REPLACE INTO embeddings (id, chunk_id, embedding) VALUES (?, ?, ?)",
                (embed_id, chunk_id, embedding_bytes),
            )

        self.connection.commit()

    def similarity_search(
        self, query_embedding: list[float], k: int = 5
    ) -> list[tuple[str, float]]:
        """Find k most similar chunks to the query embedding.

        Args:
            query_embedding: Query embedding vector
            k: Number of results to return

        Returns:
            List of (chunk_id, similarity_score) tuples
        """
        cursor = self.connection.cursor()

        try:
            # Try using vec extension with distance function
            cursor.execute(
                """
                SELECT e.chunk_id, distance AS score
                FROM embeddings e
                ORDER BY distance(e.embedding, ?)
                LIMIT ?
                """,
                (query_embedding, k),
            )
            results = cursor.fetchall()
            if results:
                return [(r[0], 1 - r[1]) for r in results]  # Convert distance to similarity
        except sqlite3.OperationalError:
            pass

        # Fallback: manual similarity computation
        cursor.execute("SELECT id, chunk_id, embedding FROM embeddings")
        embeddings = cursor.fetchall()

        similarities = []
        query_array = np.array(query_embedding, dtype=np.float32)

        for embed_id, chunk_id, embed_blob in embeddings:
            try:
                embed_array = np.frombuffer(embed_blob, dtype=np.float32)
            except (TypeError, ValueError):
                embed_array = np.array(embed_blob, dtype=np.float32)

            if embed_array.shape[0] != self.embedding_dim:
                continue

            similarity = np.dot(query_array, embed_array) / (
                np.linalg.norm(query_array) * np.linalg.norm(embed_array) + 1e-8
            )
            similarities.append((chunk_id, float(similarity)))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:k]

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Retrieve a chunk by ID.

        Args:
            chunk_id: ID of the chunk

        Returns:
            Chunk object or None if not found
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, document_id, text, start_page, end_page, chunk_index
            FROM chunks WHERE id = ?
            """,
            (chunk_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return Chunk(
            id=row[0],
            document_id=row[1],
            text=row[2],
            start_page=row[3],
            end_page=row[4],
            chunk_index=row[5],
        )

    def get_all_chunks_for_document(self, document_id: str) -> list[Chunk]:
        """Retrieve all chunks for a document.

        Args:
            document_id: ID of the document

        Returns:
            List of chunks
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, document_id, text, start_page, end_page, chunk_index
            FROM chunks WHERE document_id = ?
            ORDER BY chunk_index
            """,
            (document_id,),
        )
        rows = cursor.fetchall()

        return [
            Chunk(
                id=row[0],
                document_id=row[1],
                text=row[2],
                start_page=row[3],
                end_page=row[4],
                chunk_index=row[5],
            )
            for row in rows
        ]

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
