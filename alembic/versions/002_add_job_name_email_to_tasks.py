"""add job_name and email_to to tasks

Revision ID: 003
Revises: 002
Create Date: 2026-01-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("job_name", sa.String(length=255), nullable=True))
    op.add_column("tasks", sa.Column("email_to", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "email_to")
    op.drop_column("tasks", "job_name")

