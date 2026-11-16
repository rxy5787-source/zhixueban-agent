"""SQLite-level retry depth limit shared by local and browser-trial services.

The first manual retry remains user-confirmed. A task that is itself a retry
cannot be used as a new retry source. This guard is installed on each space's
own SQLite database; it protects concurrent requests and direct SQL writers,
including deployments with existing retry receipts.
"""
from __future__ import annotations

MAX_RETRY_DEPTH = 1
RETRY_DEPTH_ERROR = "task_retry_depth_limit"


def install_retry_guard(db) -> None:
    """Add an idempotent, non-destructive trigger to the existing retry table.

    No data is deleted or changed. Existing historical chains are preserved,
    but new links that extend a chain or introduce an alias/cycle are rejected.
    """
    db.execute(
        """CREATE TRIGGER IF NOT EXISTS limit_task_retry_depth
           BEFORE INSERT ON web_task_retries
           WHEN NEW.original_id=NEW.retry_id
             OR EXISTS (
               SELECT 1 FROM web_task_retries
               WHERE retry_id=NEW.original_id OR retry_id=NEW.retry_id
             )
           BEGIN
             SELECT RAISE(ABORT, 'task_retry_depth_limit');
           END"""
    )
