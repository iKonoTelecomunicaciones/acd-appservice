from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Dict

import asyncpg
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
    timestamp_send: int | None
    timestamp_read: int | None = None
    was_read: bool = False

    @property
    def _values(self):
        return (
            self.event_id,
            self.room_id,
            self.sender,
            self.receiver,
            self.timestamp_send,
            self.timestamp_read,
            self.was_read,
        )

    async def insert(self) -> None:
        q = (
            "INSERT INTO message (event_id, room_id, sender, receiver, timestamp_send, "
            "                     timestamp_read, was_read) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)"
        )
        await self.db.execute(q, *self._values)

    async def update(
        self, receiver: str, event_id: EventID, timestamp_read: int, was_read: bool
    ) -> None:
        q = "UPDATE message SET timestamp_read=$2, was_read=$3 WHERE event_id=$1"
        await self.db.execute(q, event_id, timestamp_read, was_read)

        # El bridge de wpp solo nos envía la verificación de lectura del último mensaje enviado
        # entonces podemos suponer que los mensajes previos ya han sido leídos, realizamos una
        # corrección de los datos.
        await self.fix_message_read_events(receiver=receiver, timestamp_read=timestamp_read)

    async def fix_message_read_events(self, receiver: str, timestamp_read: int) -> None:
        q = "UPDATE message SET timestamp_read=$2, was_read='t' WHERE receiver=$1 AND was_read='f'"
        await self.db.execute(q, receiver, timestamp_read)

    @classmethod
    async def get_by_event_id(cls, event_id: EventID) -> Message | None:
        q = (
            "SELECT event_id, room_id, sender, receiver, timestamp_send, timestamp_read, was_read "
            "FROM message WHERE event_id=$1"
        )
        row = await cls.db.fetchrow(q, event_id)
        if not row:
            return None
        return cls(**row)
