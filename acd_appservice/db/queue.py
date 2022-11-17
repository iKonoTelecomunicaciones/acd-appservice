from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import asyncpg
from attr import dataclass
from mautrix.types import RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Queue:
    db: ClassVar[Database] = fake_db

    id: int | None
    room_id: RoomID
    name: str | None = ""

    # strategy: str = "roundrobin"
    # timeout: int = 0  # in sec

    _columns = "room_id, name"

    @property
    def _values(self):
        return (
            self.room_id,
            self.name,
        )

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Queue:
        return cls(**row)

    async def insert(self) -> None:
        q = "INSERT INTO queue (room_id, name) VALUES ($1, $2)"
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = "UPDATE queue SET name=$2 WHERE room_id=$1"
        await self.db.execute(q, *self._values)

    @classmethod
    async def get_by_room_id(cls, room_id: RoomID) -> Queue | None:
        q = f"SELECT id, {cls._columns} FROM queue WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)
