from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, List

import asyncpg
from attr import dataclass
from mautrix.types import RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Room:
    """Representación en la bd de Room"""

    db: ClassVar[Database] = fake_db

    id: int | None
    room_id: RoomID
    is_pending_room: bool | None
    selected_option: str

    @property
    def _values(self):
        return (
            self.id,
            self.room_id,
            self.is_pending_room,
            self.selected_option,
        )

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Room:
        return cls(**row)

    @classmethod
    async def insert(
        cls, room_id: RoomID, selected_option: str, is_pending_room: bool = False
    ) -> None:
        q = "INSERT INTO room (room_id, is_pending_room, selected_option) VALUES ($1, $2, $3)"
        await cls.db.execute(
            q,
            *(
                room_id,
                is_pending_room,
                selected_option,
            ),
        )

    async def update_by_id(self) -> None:
        q = "UPDATE room SET room_id=$2, is_pending_room=$3, selected_option=$4 WHERE id=$1"
        await self.db.execute(q, *self._values)

    @classmethod
    async def update_by_room_id(
        cls, room_id: RoomID, selected_option: str, is_pending_room: bool = False
    ) -> None:
        q = "UPDATE room SET is_pending_room=$2, selected_option=$3 WHERE room_id=$1"
        await cls.db.execute(
            q,
            *(
                room_id,
                is_pending_room,
                selected_option,
            ),
        )

    @classmethod
    async def update_pending_room_by_room_id(cls, room_id: RoomID, is_pending_room: bool) -> None:
        q = "UPDATE room SET is_pending_room=$2 WHERE room_id=$1"
        await cls.db.execute(
            q,
            *(
                room_id,
                is_pending_room,
            ),
        )

    @classmethod
    async def get_by_room_id(cls, room_id: RoomID) -> Room | None:
        q = "SELECT id, room_id, is_pending_room, selected_option FROM room WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_pending_rooms(cls) -> List[Room] | None:
        q = (
            "SELECT id, room_id, is_pending_room, selected_option FROM room "
            "WHERE is_pending_room='t' ORDER BY selected_option"
        )
        rows = await cls.db.fetch(q)
        if not rows:
            return None

        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_user_selected_menu(cls, room_id: RoomID) -> str | None:
        q = "SELECT selected_option FROM room WHERE room_id=$1"
        row = await cls.db.fetchval(q, room_id)
        if not row:
            return None

        return row
