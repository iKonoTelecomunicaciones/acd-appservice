from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import asyncpg
from attr import dataclass
from mautrix.types import ContentURI, SyncToken, UserID
from mautrix.util.async_db import Database
from yarl import URL

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Puppet:
    """Representación en la bd de Puppet"""

    db: ClassVar[Database] = fake_db

    name: str | None
    username: str | None
    photo_id: str | None
    photo_mxc: ContentURI | None
    name_set: bool
    avatar_set: bool

    is_registered: bool

    custom_mxid: UserID | None
    access_token: str | None
    next_batch: SyncToken | None
    base_url: URL | None

    @property
    def _values(self):
        return (
            self.custom_mxid,
            self.name,
            self.username,
            self.photo_id,
            self.photo_mxc,
            self.name_set,
            self.avatar_set,
            self.is_registered,
            self.access_token,
            self.next_batch,
            str(self.base_url) if self.base_url else None,
        )

    async def insert(self) -> None:
        q = (
            "INSERT INTO puppet (custom_mxid, name, username, photo_id, photo_mxc, name_set, avatar_set,"
            "                    is_registered, access_token, next_batch, base_url) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)"
        )
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = (
            "UPDATE puppet SET name=$2, username=$3, photo_id=$4, photo_mxc=$5, name_set=$6,"
            "                  avatar_set=$7, is_registered=$8, access_token=$9,"
            "                  next_batch=$10, base_url=$11 "
            "WHERE custom_mxid=$1"
        )
        await self.db.execute(q, *self._values)

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Puppet:
        data = {**row}
        base_url_str = data.pop("base_url")
        base_url = URL(base_url_str) if base_url_str is not None else None
        return cls(base_url=base_url, **data)

    @classmethod
    async def get_by_custom_mxid(cls, mxid: UserID) -> Puppet | None:
        q = (
            "SELECT name, username, photo_id, photo_mxc, name_set, avatar_set, is_registered,"
            "       custom_mxid, access_token, next_batch, base_url "
            "FROM puppet WHERE custom_mxid=$1"
        )
        row = await cls.db.fetchrow(q, mxid)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def all_with_custom_mxid(cls) -> list[Puppet]:
        q = (
            "SELECT name, username, photo_id, photo_mxc, name_set, avatar_set, is_registered,"
            "       custom_mxid, access_token, next_batch, base_url "
            "FROM puppet WHERE custom_mxid IS NOT NULL"
        )
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]
