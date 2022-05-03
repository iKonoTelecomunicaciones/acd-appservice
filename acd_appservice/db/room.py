from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, List

import asyncpg
from attr import dataclass
from mautrix.types import RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Room:
    """Representación en la bd de room y pending_room"""

    db: ClassVar[Database] = fake_db

    id: int | None
    room_id: RoomID
    selected_option: str

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Room:
        return cls(**row)

    @classmethod
    async def insert_room(cls, room_id: RoomID, selected_option: str) -> None:
        q = "INSERT INTO room (room_id, selected_option) VALUES ($1, $2)"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def insert_pending_room(cls, room_id: RoomID, selected_option: RoomID) -> None:
        q = "INSERT INTO pending_room (room_id, selected_option) VALUES ($1, $2)"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def update_room_by_id(cls, id: int, room_id: RoomID, selected_option: str) -> None:
        q = "UPDATE room SET room_id=$2, selected_option=$3 WHERE id=$1"
        await cls.db.execute(q, *(id, room_id, selected_option))

    @classmethod
    async def update_room_by_room_id(cls, room_id: RoomID, selected_option: str) -> None:
        q = "UPDATE room SET selected_option=$2 WHERE room_id=$1"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def update_pending_room_by_id(cls, id: int, room_id: RoomID, selected_option: str) -> None:
        q = "UPDATE pending_room SET room_id=$2, selected_option=$3 WHERE id=$1"
        await cls.db.execute(q, *(id, room_id, selected_option))

    @classmethod
    async def update_pending_room_by_room_id(cls, room_id: RoomID, selected_option: str) -> None:
        q = "UPDATE pending_room SET selected_option=$2 WHERE room_id=$1"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def get_room_by_room_id(cls, room_id: RoomID) -> Room | None:
        q = "SELECT id, room_id, selected_option FROM room WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_pending_room_by_room_id(cls, room_id: RoomID) -> Room | None:
        q = "SELECT id, room_id, selected_option FROM pending_room WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_user_selected_menu(cls, room_id: RoomID) -> str | None:
        q = "SELECT selected_option FROM room WHERE room_id=$1"
        row = await cls.db.fetchval(q, room_id)
        if not row:
            return None
        return row

    @classmethod
    async def get_campaign_of_pending_room(cls, room_id: RoomID) -> str | None:
        q = "SELECT selected_option FROM pending_room WHERE room_id=$1"
        row = await cls.db.fetchval(q, room_id)
        if not row:
            return None
        return row

    @classmethod
    async def get_rooms(cls) -> List[Room] | None:
        q = "SELECT id, room_id, selected_option  FROM room ORDER BY selected_option"
        rows = await cls.db.fetch(q)
        if not rows:
            return None

        return [cls._from_row(room) for room in rows]

    @classmethod
    async def get_pending_rooms(cls) -> List[Room] | None:
        q = "SELECT id, room_id, selected_option  FROM pending_room ORDER BY selected_option"
        rows = await cls.db.fetch(q)
        if not rows:
            return None

        return [cls._from_row(room) for room in rows]

    @classmethod
    async def remove_pending_room(cls, room_id: RoomID) -> None:
        q = "DELETE FROM pending_room FROM room_id=$1"
        await cls.db.execute(q, room_id)
