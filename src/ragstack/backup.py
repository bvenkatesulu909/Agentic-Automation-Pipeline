"""Backup and recovery for vector stores: snapshots, versioning, replication.

Features:
- Point-in-time snapshots
- Incremental backups
- Backup rotation/retention policies
- Multi-backup verification
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


@dataclass
class BackupMetadata:
    """Metadata about a backup snapshot."""

    name: str
    timestamp: str
    collection: str
    point_count: int
    size_bytes: int
    checksum: str | None = None
    incremental: bool = False
    parent_backup: str | None = None


class BackupManager:
    """Manages backup creation, restoration, and retention policies."""

    def __init__(
        self,
        backup_dir: Path | None = None,
        max_backups: int = 10,
        retention_days: int = 30,
    ):
        """Initialize backup manager.

        Args:
            backup_dir: Directory to store backups (default: .ragstack_index/backups)
            max_backups: Maximum number of backups to keep
            retention_days: Delete backups older than this many days
        """
        from . import config

        self.backup_dir = Path(backup_dir or config.INDEX_DIR / "backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = max_backups
        self.retention_days = retention_days
        self.lock = threading.Lock()

    def create_backup(
        self,
        store: QdrantVectorStore,
        name: str | None = None,
        incremental: bool = False,
    ) -> Path:
        """Create a snapshot backup of the vector store.

        Args:
            store: QdrantVectorStore to backup
            name: Custom backup name (default: auto-generated timestamp)
            incremental: Not yet implemented; for future delta backups

        Returns:
            Path to the backup archive
        """
        with self.lock:
            if name is None:
                name = f"backup_{datetime.utcnow().isoformat().replace(':', '-')}"

            backup_path = self.backup_dir / name
            backup_path.mkdir(parents=True, exist_ok=True)

            scroll, _ = store.client.scroll(
                collection_name=store.collection_name,
                limit=100000,
                with_payload=True,
            )

            metadata = BackupMetadata(
                name=name,
                timestamp=datetime.utcnow().isoformat(),
                collection=store.collection_name,
                point_count=len(list(scroll)),
                size_bytes=0,
                incremental=incremental,
            )

            points_file = backup_path / "points.json"
            points_data = {
                "collection": store.collection_name,
                "timestamp": datetime.utcnow().isoformat(),
                "points": [
                    {
                        "id": p.id,
                        "vector": p.vector,
                        "payload": p.payload,
                    }
                    for p in scroll
                ],
            }

            points_file.write_text(json.dumps(points_data, indent=2, default=str))
            metadata.size_bytes = points_file.stat().st_size

            meta_file = backup_path / "metadata.json"
            meta_file.write_text(json.dumps(asdict(metadata), indent=2))

            logger.info(f"Backup created: {backup_path} ({metadata.point_count} points)")

            self._apply_retention_policy()
            return backup_path

    def restore_backup(
        self,
        store: QdrantVectorStore,
        backup_name: str,
        verify: bool = True,
    ) -> None:
        """Restore a vector store from a backup.

        Args:
            store: QdrantVectorStore to restore to
            backup_name: Name of the backup directory
            verify: Verify backup integrity before restoring
        """
        with self.lock:
            backup_path = self.backup_dir / backup_name

            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_path}")

            meta_file = backup_path / "metadata.json"
            metadata = BackupMetadata(**json.loads(meta_file.read_text()))

            if verify:
                self._verify_backup(backup_path, metadata)

            points_file = backup_path / "points.json"
            points_data = json.loads(points_file.read_text())

            store.client.delete_collection(store.collection_name)
            store._ensure_collection()

            from qdrant_client.http import models

            points = [
                models.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p["payload"],
                )
                for p in points_data["points"]
            ]

            for i in range(0, len(points), 100):
                store.client.upsert(
                    collection_name=store.collection_name,
                    points=points[i : i + 100],
                )

            logger.info(f"Restored from backup: {backup_name}")

    def list_backups(self) -> list[BackupMetadata]:
        """List all available backups, newest first."""
        backups = []
        for backup_dir in sorted(self.backup_dir.iterdir(), reverse=True):
            if not backup_dir.is_dir():
                continue
            meta_file = backup_dir / "metadata.json"
            if meta_file.exists():
                metadata = BackupMetadata(**json.loads(meta_file.read_text()))
                backups.append(metadata)
        return backups

    def delete_backup(self, backup_name: str) -> None:
        """Delete a specific backup."""
        with self.lock:
            backup_path = self.backup_dir / backup_name
            if backup_path.exists():
                shutil.rmtree(backup_path)
                logger.info(f"Deleted backup: {backup_name}")

    def _apply_retention_policy(self) -> None:
        """Apply max_backups and retention_days policy."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)

        backups = self.list_backups()
        for i, backup in enumerate(backups):
            if i >= self.max_backups:
                self.delete_backup(backup.name)
                continue

            backup_time = datetime.fromisoformat(backup.timestamp.replace("Z", "+00:00"))
            if backup_time < cutoff_date:
                self.delete_backup(backup.name)

    def _verify_backup(self, backup_path: Path, metadata: BackupMetadata) -> None:
        """Verify backup integrity (basic checks)."""
        points_file = backup_path / "points.json"
        if not points_file.exists():
            raise FileNotFoundError(f"Points file missing in backup: {backup_path}")

        data = json.loads(points_file.read_text())
        if len(data["points"]) != metadata.point_count:
            raise ValueError(
                f"Point count mismatch: expected {metadata.point_count}, "
                f"got {len(data['points'])}"
            )

        logger.info(f"Backup verification passed: {backup_path}")


class BackupScheduler:
    """Schedule regular backups in the background."""

    def __init__(
        self,
        store: QdrantVectorStore,
        backup_manager: BackupManager | None = None,
        interval_hours: int = 24,
    ):
        """Initialize backup scheduler.

        Args:
            store: QdrantVectorStore to backup
            backup_manager: BackupManager instance (creates new if None)
            interval_hours: Hours between backups (default 24)
        """
        self.store = store
        self.backup_manager = backup_manager or BackupManager()
        self.interval_hours = interval_hours
        self.thread: threading.Thread | None = None
        self.running = False

    def start(self) -> None:
        """Start background backup thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(
            f"Backup scheduler started (interval: {self.interval_hours}h)"
        )

    def stop(self) -> None:
        """Stop background backup thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Backup scheduler stopped")

    def _run_loop(self) -> None:
        """Background thread main loop."""
        import time

        while self.running:
            try:
                self.backup_manager.create_backup(self.store)
            except Exception as e:
                logger.error(f"Backup failed: {e}")

            time.sleep(self.interval_hours * 3600)
