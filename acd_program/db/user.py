from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import asyncpg
from attr import dataclass
from mautrix.types import RoomID, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class User:
    """Representación en la bd de User"""

    db: ClassVar[Database] = fake_db

    mxid: UserID
    email: str | None
    room_id: RoomID | None

    async def insert(self) -> None:
        q = 'INSERT INTO "user" (mxid, email, room_id) VALUES ($1, $2, $3)'
        await self.db.execute(q, self.mxid, self.email, self.room_id)

    async def update(self) -> None:
        q = 'UPDATE "user" SET email=$2, room_id=$3 WHERE mxid=$1'
        await self.db.execute(q, self.mxid, self.email, self.room_id)

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> User:
        data = {**row}
        return cls(**data)

    @classmethod
    async def get_by_mxid(cls, mxid: UserID) -> User | None:
        q = 'SELECT mxid, email, room_id FROM "user" WHERE mxid=$1'
        row = await cls.db.fetchrow(q, mxid)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_room_id(cls, room_id: str) -> User | None:
        q = 'SELECT mxid, email, room_id FROM "user" WHERE room_id=$1'
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_email(cls, email: str) -> User | None:
        q = 'SELECT mxid, email, room_id FROM "user" WHERE email=$1'
        row = await cls.db.fetchrow(q, email)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def all_logged_in(cls) -> list[User]:
        q = 'SELECT mxid, email, room_id  FROM "user"'
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]
