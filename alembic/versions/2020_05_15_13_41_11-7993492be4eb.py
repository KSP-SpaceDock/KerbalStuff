"""Add locked, lock_reason, locked_by and locked_by_id to mod

Revision ID: 7993492be4eb
Revises: 77f76102f99c
Create Date: 2020-05-15 11:41:13.520468

"""

# revision identifiers, used by Alembic.
revision = '7993492be4eb'
down_revision = '77f76102f99c'

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # Autogenerated, hope it's fine.
    op.add_column('mod', sa.Column('lock_reason', sa.Unicode(length=1024), nullable=True))
    op.add_column('mod', sa.Column('locked', sa.Boolean(), nullable=True))
    op.add_column('mod', sa.Column('locked_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'mod', 'user', ['locked_by_id'], ['id'])
    op.drop_column('mod', 'approved')


def downgrade() -> None:
    # Autogenerated, hope it's fine.
    op.add_column('mod', sa.Column('approved', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.drop_constraint(None, 'mod', type_='foreignkey')
    op.drop_column('mod', 'locked_by_id')
    op.drop_column('mod', 'locked')
    op.drop_column('mod', 'lock_reason')
