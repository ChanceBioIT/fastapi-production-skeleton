"""add worker_id to tasks

Revision ID: 004
Revises: 003
Create Date: 2026-01-27 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("worker_id", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_tasks_worker_id"), "tasks", ["worker_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_worker_id"), table_name="tasks")
    op.drop_column("tasks", "worker_id")
