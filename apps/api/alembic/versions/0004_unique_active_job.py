"""One active processing job per document (partial unique index).

A SELECT-then-INSERT race in the reprocess endpoint allowed two concurrent
requests to create two active jobs for the same document; the concurrent
pipeline runs then interleaved the delete-and-rebuild findings cycle
(duplicated/lost findings, double extraction/AI cost). A partial unique index
makes the duplicate INSERT impossible at the storage engine; the endpoint maps
the IntegrityError to 409. The migration first supersedes any duplicate active
jobs already present in existing deployments so the index can be created.

Revision ID: 0004_unique_active_job
Revises: 0003_identity_link
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_unique_active_job"
down_revision: Union[str, None] = "0003_identity_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "status IN ('queued', 'running')"


def _superseded_cleanup() -> None:
    """Close duplicate active jobs (keep the newest per document) and fail any
    document left in a non-terminal state without an active job, so the unique
    index can be created on databases that already contain raced rows."""
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        UPDATE processing_jobs
        SET status = 'failed',
            error = 'Superseded: duplicate active job was closed during upgrade.',
            finished_at = CURRENT_TIMESTAMP
        WHERE status IN ('queued', 'running')
          AND id NOT IN (
              SELECT id FROM (
                  SELECT id, ROW_NUMBER() OVER (
                      PARTITION BY document_id ORDER BY created_at DESC
                  ) AS rn
                  FROM processing_jobs
                  WHERE status IN ('queued', 'running')
              ) ranked WHERE ranked.rn = 1
          )
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE documents
        SET status = 'failed',
            error = 'Processing was interrupted during an upgrade. Reprocess the document.'
        WHERE status IN ('queued', 'processing')
          AND id NOT IN (
              SELECT DISTINCT document_id FROM processing_jobs
              WHERE status IN ('queued', 'running')
          )
        """
    ))


def upgrade() -> None:
    _superseded_cleanup()
    op.create_index(
        "uq_active_job_per_document",
        "processing_jobs",
        ["document_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE),
        postgresql_where=sa.text(_ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_active_job_per_document", table_name="processing_jobs")
