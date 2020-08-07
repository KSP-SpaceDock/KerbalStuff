"""Add ondelete='CASCADE' to foreign keys that need it

Revision ID: 7eec82634342
Revises: 73c9d707134b
Create Date: 2020-08-07 11:00:59.835800

"""

# revision identifiers, used by Alembic.
revision = '7eec82634342'
down_revision = '73c9d707134b'

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.drop_constraint('downloadevent_version_id_fkey', 'downloadevent', type_='foreignkey')
    op.create_foreign_key('downloadevent_version_id_fkey', 'downloadevent', 'modversion', ['version_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('downloadevent_mod_id_fkey', 'downloadevent', type_='foreignkey')
    op.create_foreign_key('downloadevent_mod_id_fkey', 'downloadevent', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('featured_mod_id_fkey', 'featured', type_='foreignkey')
    op.create_foreign_key('featured_mod_id_fkey', 'featured', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('followevent_mod_id_fkey', 'followevent', type_='foreignkey')
    op.create_foreign_key('followevent_mod_id_fkey', 'followevent', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('game_publisher_id_fkey', 'game', type_='foreignkey')
    op.create_foreign_key('game_publisher_id_fkey', 'game', 'publisher', ['publisher_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('gameversion_game_id_fkey', 'gameversion', type_='foreignkey')
    op.create_foreign_key('gameversion_game_id_fkey', 'gameversion', 'game', ['game_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('media_mod_id_fkey', 'media', type_='foreignkey')
    op.create_foreign_key('media_mod_id_fkey', 'media', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('mod_game_id_fkey', 'mod', type_='foreignkey')
    op.create_foreign_key('mod_game_id_fkey', 'mod', 'game', ['game_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('mod_user_id_fkey', 'mod', type_='foreignkey')
    op.create_foreign_key('mod_user_id_fkey', 'mod', 'user', ['user_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('modlist_user_id_fkey', 'modlist', type_='foreignkey')
    op.create_foreign_key('modlist_user_id_fkey', 'modlist', 'user', ['user_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('modlist_game_id_fkey', 'modlist', type_='foreignkey')
    op.create_foreign_key('modlist_game_id_fkey', 'modlist', 'game', ['game_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('modlistitem_mod_id_fkey', 'modlistitem', type_='foreignkey')
    op.create_foreign_key('modlistitem_mod_id_fkey', 'modlistitem', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('modlistitem_mod_list_id_fkey', 'modlistitem', type_='foreignkey')
    op.create_foreign_key('modlistitem_mod_list_id_fkey', 'modlistitem', 'modlist', ['mod_list_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('modversion_gameversion_id_fkey', 'modversion', type_='foreignkey')
    op.create_foreign_key('modversion_gameversion_id_fkey', 'modversion', 'gameversion', ['gameversion_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('modversion_mod_id_fkey', 'modversion', type_='foreignkey')
    op.create_foreign_key('modversion_mod_id_fkey', 'modversion', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('referralevent_mod_id_fkey', 'referralevent', type_='foreignkey')
    op.create_foreign_key('referralevent_mod_id_fkey', 'referralevent', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('sharedauthor_mod_id_fkey', 'sharedauthor', type_='foreignkey')
    op.create_foreign_key('sharedauthor_mod_id_fkey', 'sharedauthor', 'mod', ['mod_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint('sharedauthor_user_id_fkey', 'sharedauthor', type_='foreignkey')
    op.create_foreign_key('sharedauthor_user_id_fkey', 'sharedauthor', 'user', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('downloadevent_version_id_fkey', 'downloadevent', type_='foreignkey')
    op.create_foreign_key('downloadevent_version_id_fkey', 'downloadevent', 'modversion', ['version_id'], ['id'])
    op.drop_constraint('downloadevent_mod_id_fkey', 'downloadevent', type_='foreignkey')
    op.create_foreign_key('downloadevent_mod_id_fkey', 'downloadevent', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('featured_mod_id_fkey', 'featured', type_='foreignkey')
    op.create_foreign_key('featured_mod_id_fkey', 'featured', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('followevent_mod_id_fkey', 'followevent', type_='foreignkey')
    op.create_foreign_key('followevent_mod_id_fkey', 'followevent', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('game_publisher_id_fkey', 'game', type_='foreignkey')
    op.create_foreign_key('game_publisher_id_fkey', 'game', 'publisher', ['publisher_id'], ['id'])
    op.drop_constraint('gameversion_game_id_fkey', 'gameversion', type_='foreignkey')
    op.create_foreign_key('gameversion_game_id_fkey', 'gameversion', 'game', ['game_id'], ['id'])
    op.drop_constraint('media_mod_id_fkey', 'media', type_='foreignkey')
    op.create_foreign_key('media_mod_id_fkey', 'media', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('mod_game_id_fkey', 'mod', type_='foreignkey')
    op.create_foreign_key('mod_game_id_fkey', 'mod', 'game', ['game_id'], ['id'])
    op.drop_constraint('mod_user_id_fkey', 'mod', type_='foreignkey')
    op.create_foreign_key('mod_user_id_fkey', 'mod', 'user', ['user_id'], ['id'])
    op.drop_constraint('modlist_user_id_fkey', 'modlist', type_='foreignkey')
    op.create_foreign_key('modlist_user_id_fkey', 'modlist', 'user', ['user_id'], ['id'])
    op.drop_constraint('modlist_game_id_fkey', 'modlist', type_='foreignkey')
    op.create_foreign_key('modlist_game_id_fkey', 'modlist', 'game', ['game_id'], ['id'])
    op.drop_constraint('modlistitem_mod_id_fkey', 'modlistitem', type_='foreignkey')
    op.create_foreign_key('modlistitem_mod_id_fkey', 'modlistitem', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('modlistitem_mod_list_id_fkey', 'modlistitem', type_='foreignkey')
    op.create_foreign_key('modlistitem_mod_list_id_fkey', 'modlistitem', 'modlist', ['mod_list_id'], ['id'])
    op.drop_constraint('modversion_gameversion_id_fkey', 'modversion', type_='foreignkey')
    op.create_foreign_key('modversion_gameversion_id_fkey', 'modversion', 'gameversion', ['gameversion_id'], ['id'])
    op.drop_constraint('modversion_mod_id_fkey', 'modversion', type_='foreignkey')
    op.create_foreign_key('modversion_mod_id_fkey', 'modversion', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('referralevent_mod_id_fkey', 'referralevent', type_='foreignkey')
    op.create_foreign_key('referralevent_mod_id_fkey', 'referralevent', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('sharedauthor_mod_id_fkey', 'sharedauthor', type_='foreignkey')
    op.create_foreign_key('sharedauthor_mod_id_fkey', 'sharedauthor', 'mod', ['mod_id'], ['id'])
    op.drop_constraint('sharedauthor_user_id_fkey', 'sharedauthor', type_='foreignkey')
    op.create_foreign_key('sharedauthor_user_id_fkey', 'sharedauthor', 'user', ['user_id'], ['id'])
