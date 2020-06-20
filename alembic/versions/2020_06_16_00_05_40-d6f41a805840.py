"""Index columns passed to .order_by()

Revision ID: d6f41a805840
Revises: 7993492be4eb
Create Date: 2020-06-15 22:05:43.130743

"""

# revision identifiers, used by Alembic.
revision = 'd6f41a805840'
down_revision = '7993492be4eb'

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(op.f('ix_blog_created'), 'blog', ['created'], unique=False)
    op.create_index(op.f('ix_downloadevent_created'), 'downloadevent', ['created'], unique=False)
    op.create_index(op.f('ix_featured_created'), 'featured', ['created'], unique=False)
    op.create_index(op.f('ix_followevent_created'), 'followevent', ['created'], unique=False)
    op.create_index(op.f('ix_game_created'), 'game', ['created'], unique=False)
    op.create_index(op.f('ix_game_name'), 'game', ['name'], unique=False)
    op.create_index(op.f('ix_mod_created'), 'mod', ['created'], unique=False)
    op.create_index(op.f('ix_mod_updated'), 'mod', ['updated'], unique=False)
    op.create_index(op.f('ix_referralevent_created'), 'referralevent', ['created'], unique=False)
    op.create_index(op.f('ix_user_created'), 'user', ['created'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_user_created'), table_name='user')
    op.drop_index(op.f('ix_referralevent_created'), table_name='referralevent')
    op.drop_index(op.f('ix_mod_updated'), table_name='mod')
    op.drop_index(op.f('ix_mod_created'), table_name='mod')
    op.drop_index(op.f('ix_game_name'), table_name='game')
    op.drop_index(op.f('ix_game_created'), table_name='game')
    op.drop_index(op.f('ix_followevent_created'), table_name='followevent')
    op.drop_index(op.f('ix_featured_created'), table_name='featured')
    op.drop_index(op.f('ix_downloadevent_created'), table_name='downloadevent')
    op.drop_index(op.f('ix_blog_created'), table_name='blog')
    # ### end Alembic commands ###
