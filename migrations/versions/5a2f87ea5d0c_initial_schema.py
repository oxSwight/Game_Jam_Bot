"""initial schema

Gateway bot: users, applications and an audit log. No events/teams/scoring —
the bot's sole job is to vet sign-ups and mint group invites.

Revision ID: 5a2f87ea5d0c
Revises:
Create Date: 2026-07-05 09:13:38.090637
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5a2f87ea5d0c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_username', sa.String(length=64), nullable=True),
        sa.Column('nickname', sa.String(length=32), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('language', sa.String(length=8), server_default='ru', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('nickname'),
    )
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    op.create_table(
        'applications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('main_category', sa.String(length=64), nullable=False),
        sa.Column('blueprint_subcategory', sa.String(length=64), nullable=True),
        sa.Column('skill_category_id', sa.String(length=64), nullable=False),
        sa.Column('skill_category_title', sa.String(length=128), nullable=False),
        sa.Column('subcategories', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('experience_level', sa.String(length=32), nullable=False),
        sa.Column('engine', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('engine_other', sa.Text(), nullable=True),
        sa.Column('tools', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('tools_other', sa.Text(), nullable=True),
        sa.Column('motivations', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('consent_accepted', sa.Boolean(), server_default='1', nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending_review', 'approved', 'rejected', name='applicationstatus', native_enum=False, length=32),
            server_default='pending_review',
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_applications_one_active_per_user',
        'applications',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text("status != 'rejected'"),
        sqlite_where=sa.text("status != 'rejected'"),
    )
    op.create_index(op.f('ix_applications_status'), 'applications', ['status'], unique=False)
    op.create_index(op.f('ix_applications_user_id'), 'applications', ['user_id'], unique=False)

    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=True),
        sa.Column('actor_telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_logs_application_id'), 'logs', ['application_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_logs_application_id'), table_name='logs')
    op.drop_table('logs')
    op.drop_index(op.f('ix_applications_user_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_status'), table_name='applications')
    op.drop_index(
        'ix_applications_one_active_per_user',
        table_name='applications',
        postgresql_where=sa.text("status != 'rejected'"),
        sqlite_where=sa.text("status != 'rejected'"),
    )
    op.drop_table('applications')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_table('users')
