"""initialize schema

Revision ID: bd47810d168d
Revises:
Create Date: 2026-09-18 12:45:51.247328
"""

from collections.abc import Sequence

revision: str = "bd47810d168d"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    pass


def downgrade() -> None:
    """Revert the migration."""
    pass
