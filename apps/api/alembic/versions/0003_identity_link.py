"""Add federated-identity columns to users (OIDC SSO links).

Revision ID: 0003_identity_link
Revises: 0002_malware_scan
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_identity_link"
down_revision: Union[str, None] = "0002_malware_scan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("idp_issuer", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("idp_subject", sa.String(255), nullable=True))
    # Unique on the composite; NULLs (local-only accounts) never collide.
    op.create_index("uq_users_idp", "users", ["idp_issuer", "idp_subject"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_idp", table_name="users")
    op.drop_column("users", "idp_subject")
    op.drop_column("users", "idp_issuer")
