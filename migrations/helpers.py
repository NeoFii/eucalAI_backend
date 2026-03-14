"""Helpers shared by service-local Alembic revisions."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import MetaData
from sqlalchemy.engine import Connection
from sqlalchemy.schema import Table


def iter_metadata_tables(metadata: MetaData, *, reverse: bool = False) -> Iterable[Table]:
    tables = [table for table in metadata.sorted_tables if not table.info.get("is_view")]
    if reverse:
        tables.reverse()
    return tables


def create_metadata_objects(bind: Connection, metadata: MetaData) -> None:
    for table in iter_metadata_tables(metadata):
        table.create(bind=bind, checkfirst=True)


def drop_metadata_objects(bind: Connection, metadata: MetaData) -> None:
    for table in iter_metadata_tables(metadata, reverse=True):
        table.drop(bind=bind, checkfirst=True)


def create_or_replace_view(bind: Connection, name: str, select_sql: str) -> None:
    bind.exec_driver_sql(f"CREATE OR REPLACE VIEW `{name}` AS\n{select_sql.strip()}")


def drop_view(bind: Connection, name: str) -> None:
    bind.exec_driver_sql(f"DROP VIEW IF EXISTS `{name}`")
