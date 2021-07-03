"""Add indexes and new columns to mod_followers

Revision ID: 17fbd4ff8193
Revises: 426e0b848d77
Create Date: 2021-06-28 19:00:00

"""

# revision identifiers, used by Alembic.
revision = '17fbd4ff8193'
down_revision = '426e0b848d77'

from alembic import op
import sqlalchemy as sa

Base = sa.ext.declarative.declarative_base()


class User(Base):  # type: ignore
    __tablename__ = 'user'
    id = sa.Column(sa.Integer, primary_key=True)


class Mod(Base):  # type: ignore
    __tablename__ = 'mod'
    id = sa.Column(sa.Integer, primary_key=True)


class Following(Base):  # type: ignore
    __tablename__ = 'mod_followers'
    __table_args__ = (sa.PrimaryKeyConstraint('user_id', 'mod_id'), )
    mod_id = sa.Column(sa.Integer, sa.ForeignKey('mod.id'))
    user_id = sa.Column(sa.Integer, sa.ForeignKey('user.id'))
    send_update = sa.Column(sa.Boolean(), default=True)
    send_autoupdate = sa.Column(sa.Boolean(), default=True)


def upgrade() -> None:
    # Remove any broken rows
    op.execute("DELETE FROM mod_followers WHERE mod_id is NULL OR user_id is NULL")
    # Make new primary key columns non-nullable
    op.alter_column('mod_followers', 'mod_id',  existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('mod_followers', 'user_id', existing_type=sa.INTEGER(), nullable=False)

    # Create indices
    op.create_index(op.f('ix_mod_followers_mod_id'), 'mod_followers', ['mod_id'], unique=False)
    op.create_index(op.f('ix_mod_followers_user_id'), 'mod_followers', ['user_id'], unique=False)
    op.create_primary_key('pk_mod_followers', 'mod_followers', ['mod_id', 'user_id'])

    # Add new columns, nullable
    op.add_column('mod_followers', sa.Column('send_update', sa.Boolean()))
    op.add_column('mod_followers', sa.Column('send_autoupdate', sa.Boolean()))

    bind = op.get_bind()
    session = sa.orm.Session(bind=bind)
    for following in session.query(Following).all():
        following.send_update = True
        following.send_autoupdate = True
    session.commit()

    # Make new columns non-nullable
    op.alter_column('mod_followers', 'send_update',     existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('mod_followers', 'send_autoupdate', existing_type=sa.INTEGER(), nullable=False)


def downgrade() -> None:
    op.drop_column('mod_followers', 'send_update')
    op.drop_column('mod_followers', 'send_autoupdate')
    op.drop_index(op.f('ix_mod_followers_user_id'), table_name='mod_followers')
    op.drop_index(op.f('ix_mod_followers_mod_id'), table_name='mod_followers')
    op.drop_constraint('pk_mod_followers', 'mod_followers')
    op.alter_column('mod_followers', 'mod_id',  existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('mod_followers', 'user_id', existing_type=sa.INTEGER(), nullable=True)
