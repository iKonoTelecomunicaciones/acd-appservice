from __future__ import annotations

import logging
from typing import cast

from mautrix.bridge import async_getter_lock
from mautrix.types import EventID, RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config
from .db import Message as DBMessage


class Message(DBMessage):
    """Representa al mensaje en el synapse."""

    log: TraceLogger = logging.getLogger("acd.room_manager")
    by_event_id: dict[str, Message] = {}
    config: Config

    def __init__(
        self,
        event_id: EventID,
        room_id: RoomID,
        sender: UserID,
        receiver: str,
        timestamp_send: int | None,
        timestamp_read: int | None = None,
        was_read: bool = False,
    ):
        super().__init__(
            event_id=event_id,
            room_id=room_id,
            sender=sender,
            receiver=receiver,
            timestamp_send=timestamp_send,
            timestamp_read=timestamp_read,
            was_read=was_read,
        )

    def _add_to_cache(self) -> None:
        self.by_event_id[self.event_id] = self

    def values(self):
        return (
            self.event_id,
            self.room_id,
            self.sender,
            self.receiver,
            self.timestamp_send,
            self.timestamp_read,
            self.was_read,
        )

    @classmethod
    async def insert_msg(
        cls,
        event_id: EventID,
        room_id: RoomID,
        sender: UserID,
        receiver: str,
        timestamp_send: int | None,
        timestamp_read: int | None = None,
        was_read: bool = False,
    ):
        msg = cls(
            event_id=event_id,
            room_id=room_id,
            sender=sender,
            receiver=receiver,
            timestamp_send=timestamp_send,
            timestamp_read=timestamp_read,
            was_read=was_read,
        )
        await msg.insert()
        msg._add_to_cache()

    @classmethod
    async def get_by_event_id(cls, event_id: EventID) -> Message | None:
        try:
            return cls.by_event_id[event_id]
        except KeyError:
            pass

        message = cast(cls, await super().get_by_event_id(event_id))
        if message:
            message._add_to_cache()
            return message

        return None
