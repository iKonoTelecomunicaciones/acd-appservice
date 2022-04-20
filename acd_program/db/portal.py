from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import asyncpg
from attr import dataclass
from mautrix.types import ContentURI, RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Portal:
    db: ClassVar[Database] = fake_db

    receiver: int
    mxid: RoomID | None
    name: str | None
    avatar_url: ContentURI | None
    name_set: bool
    avatar_set: bool

    @property
    def _values(self):
        return (
            self.receiver,
            self.mxid,
            self.name,
            self.avatar_url,
            self.name_set,
            self.avatar_set,
        )

    async def insert(self) -> None:
        q = (
            "INSERT INTO portal (receiver, mxid, name, avatar_url, "
            "                    name_set, avatar_set) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)"
        )
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = (
            "UPDATE portal SET mxid=$2, name=$3, avatar_url=$4, name_set=$5, avatar_set=$6"
            "WHERE receiver=$1"
        )
        await self.db.execute(q, *self._values)

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Portal:
        return cls(**row)

    @classmethod
    async def get_by_mxid(cls, mxid: RoomID) -> Portal | None:
        q = (
            "SELECT receiver, mxid, name, avatar_url, "
            "       name_set, avatar_set "
            "FROM portal WHERE mxid=$1"
        )
        row = await cls.db.fetchrow(q, mxid)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def all_with_room(cls) -> list[Portal]:
        q = (
            "SELECT receiver, mxid, name, avatar_url, "
            "       name_set, avatar_set "
            "FROM portal WHERE mxid IS NOT NULL"
        )
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]
