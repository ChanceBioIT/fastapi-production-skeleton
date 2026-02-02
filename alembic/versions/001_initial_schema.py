"""initial schema

Revision ID: 001
Revises: 
Create Date: 2026-01-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('quotas', sa.JSON(), nullable=True),
        sa.Column('used_quotas', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_tenants_name'), 'tenants', ['name'], unique=True)

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='admin'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('task_type', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('is_sync', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_tasks_job_id'), 'tasks', ['job_id'], unique=True)
    op.create_index(op.f('ix_tasks_task_type'), 'tasks', ['task_type'], unique=False)
    op.create_index(op.f('ix_tasks_user_id'), 'tasks', ['user_id'], unique=False)
    op.create_index(op.f('ix_tasks_tenant_id'), 'tasks', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Drop indexes and tables in reverse order; drop FKs first (MySQL auto-creates indexes for FKs)
    op.drop_index(op.f('ix_tasks_task_type'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_job_id'), table_name='tasks')
    op.drop_constraint('tasks_ibfk_1', 'tasks', type_='foreignkey')
    op.drop_constraint('tasks_ibfk_2', 'tasks', type_='foreignkey')
    op.drop_table('tasks')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_constraint('users_ibfk_1', 'users', type_='foreignkey')
    op.drop_table('users')

    op.drop_index(op.f('ix_tenants_name'), table_name='tenants')
    op.drop_table('tenants')

