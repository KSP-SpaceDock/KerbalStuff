"""
    This is a stub file so mypy can catch issues in our usage of Alembic.
    - https://mypy.readthedocs.io/en/stable/stubs.html
    - https://alembic.sqlalchemy.org/en/latest/ops.html

    The main goal is to throw an error if we pass None as the first param of
    create_foreign_key or drop_constraint, see:
    - https://github.com/miguelgrinberg/Flask-Migrate/issues/155
"""

import sqlalchemy as sa
from typing import List, Optional


class op:

    @classmethod
    def get_bind(cls) -> None: ...

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
                           **kwargs: str) -> None: ...

    @classmethod
    def drop_constraint(cls,
                        constraint_name: str,
                        table_name: str,
                        type_: Optional[str] = None) -> None: ...
