from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import asyncpg
from attr import dataclass
from mautrix.types import RoomID, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class User:
    db: ClassVar[Database] = fake_db

    mxid: UserID
    id: int | None = None
    management_room: RoomID | None = None  # if is admin

    # max_chats: int = 0

    _columns = "mxid, management_room"

    @property
    def _values(self):
        return (self.mxid, self.management_room)

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> User:
        return cls(**row)

    async def insert(self) -> None:
        q = 'INSERT INTO "user" (mxid, management_room) VALUES ($1, $2)'
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = 'UPDATE "user" SET management_room=$2 WHERE mxid=$1'
        await self.db.execute(q, *self._values)

    @classmethod
    async def get_by_mxid(cls, user_id: UserID) -> User | None:
        q = f'SELECT id, {cls._columns} FROM "user" WHERE mxid=$1'
        row = await cls.db.fetchrow(q, user_id)
        if not row:
            return None
        return cls._from_row(row)
