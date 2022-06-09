from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from attr import dataclass
from mautrix.types import EventID, RoomID, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Message:
    db: ClassVar[Database] = fake_db

    event_id: EventID
    room_id: RoomID
    sender: UserID
    receiver: str
    timestamp: int
    was_read: bool

    @property
    def _values(self):
        return (
            self.event_id,
            self.room_id,
            self.sender,
            self.receiver,
            self.timestamp,
            self.was_read,
        )

    async def insert(self) -> None:
        q = """
            INSERT INTO message (event_id, room_id, sender, receiver, timestamp, was_read)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        await self.db.execute(q, *self._values)

    @classmethod
    async def get_by_event_id(cls, event_id: EventID, room_id: RoomID) -> Message | None:
        q = (
            f"SELECT event_id, room_id, sender, receiver, timestamp, was_read"
            "FROM message WHERE event_id=$1 AND room_id=$2"
        )
        row = await cls.db.fetchrow(q, event_id, room_id)
        if not row:
            return None
        return cls(**row)
