from __future__ import annotations

import logging
from typing import cast

from mautrix.types import RoomID
from mautrix.util.logging import TraceLogger

from .db.queue import Queue as DBQueue


class Queue(DBQueue):

    room_id: RoomID
    name: str = ""

    log: TraceLogger = logging.getLogger("acd.queue")

    by_id: dict[int, Queue] = {}
    by_room_id: dict[RoomID, Queue] = {}

    def __init__(self, room_id: RoomID, name: str = "", id: int = None):
        super().__init__(id=id, name=name, room_id=room_id)
        self.log = self.log.getChild(room_id)

    def _add_to_cache(self) -> None:
        self.by_id[self.id] = self
        self.by_room_id[self.room_id] = self

    async def save(self) -> None:
        self._add_to_cache()
        await self.update()

    @classmethod
    async def get_by_room_id(cls, room_id: RoomID, *, create: bool = True) -> Queue | None:

        try:
            return cls.by_room_id[room_id]
        except KeyError:
            pass

        queue = cast(cls, await super().get_by_room_id(room_id))
        if queue is not None:
            queue._add_to_cache()
            return queue

        if create:
            queue = cls(room_id)
            await queue.insert()
            queue = await super().get_by_room_id(room_id)
            queue._add_to_cache()
            return queue

        return None
