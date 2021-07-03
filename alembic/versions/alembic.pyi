"""
    This is a stub file so mypy can catch issues in our usage of Alembic.
    - https://mypy.readthedocs.io/en/stable/stubs.html
    - https://alembic.sqlalchemy.org/en/latest/ops.html

    The main goal is to throw an error if we pass None as the first param of
    create_foreign_key or drop_constraint, see:
    - https://github.com/miguelgrinberg/Flask-Migrate/issues/155
"""

from typing import List, Optional

import sqlalchemy.sql.type_api
import sqlalchemy as sa


class op:

    @classmethod
    def get_bind(cls) -> sa.engine.Connection: ...

    @classmethod
    def f(cls,
          s: str) -> str: ...

    @classmethod
    def add_column(cls,
                   table_name: str,
                   column: sa.Column) -> None: ...

    @classmethod
    def drop_column(cls,
                    table_name: str,
                    column: str) -> None: ...

    @classmethod
    def alter_column(cls,
                    table_name: str,
                    column_name: str,
                    existing_type: Optional[sa.sql.type_api.TypeEngine] = None,
                    nullable: Optional[bool] = None) -> None: ...

    @classmethod
    def create_index(cls,
                     index_name: str,
                     table_name: str,
                     columns: List[str],
                     unique: Optional[bool] = False) -> None: ...

    @classmethod
    def drop_index(cls,
                   index_name: str,
                   table_name: Optional[str] = None) -> None: ...

    @classmethod
    def create_foreign_key(cls,
                           constraint_name: str,
                           source_table: str,
                           referent_table: str,
                           local_cols: List[str],
                           remote_cols: List[str],
                           onupdate: Optional[str] = None,
                           ondelete: Optional[str] = None) -> None: ...

    @classmethod
    def create_primary_key(cls,
                           constraint_name: str,
                           table_name: str,
                           columns: List[str]) -> None: ...

    @classmethod
    def drop_constraint(cls,
                        constraint_name: str,
                        table_name: str,
                        type_: Optional[str] = None) -> None: ...

    @classmethod
    def execute(cls,
                sqltext: str) -> None: ...
