from __future__ import annotations

import logging
from typing import cast

from mautrix.appservice import IntentAPI
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from .db.queue import Queue as DBQueue
from .room import Room


class Queue(DBQueue, Room):

    room_id: RoomID
    name: str = ""
    description: str | None = None

    log: TraceLogger = logging.getLogger("acd.queue")

    by_id: dict[int, Queue] = {}
    by_room_id: dict[RoomID, Queue] = {}

    def __init__(
        self,
        room_id: RoomID,
        name: str = "",
        description: str | None = None,
        id: int = None,
        intent: IntentAPI = None,
    ):
        DBQueue.__init__(self, id=id, name=name, room_id=room_id, description=description)
        Room.__init__(self, room_id=self.room_id, intent=intent)

    async def _add_to_cache(self) -> None:
        self.by_id[self.id] = self
        self.by_room_id[self.room_id] = self
        await self.post_init()

    async def save(self) -> None:
        await self._add_to_cache()
        await self.update()

    async def add_member(self, new_member: UserID):
        """If the config value for `acd.queue.user_add_method` is `join`, then join the user,
        otherwise invite the user

        Parameters
        ----------
        new_member : UserID
            The user ID of the user to add to the queue.

        """
        if self.config["acd.queues.user_add_method"] == "join":
            await self.join_user(user_id=new_member)
        else:
            await self.invite_user(user_id=new_member)

    async def remove_member(self, member: UserID, reason: str = None):
        """If the config value for "acd.remove_method" is "leave", then leave the user,
        otherwise kick the user

        Parameters
        ----------
        member : UserID
            The user ID of the member to remove.
        reason : str
            The reason for the removal.

        """
        if self.config["acd.remove_method"] == "leave":
            await self.leave_user(user_id=member, reason=reason)
        else:
            await self.kick_user(user_id=member, reason=reason)

    @classmethod
    async def get_by_room_id(cls, room_id: RoomID, *, create: bool = True) -> Queue | None:

        try:
            return cls.by_room_id[room_id]
        except KeyError:
            pass

        queue = cast(cls, await super().get_by_room_id(room_id))
        if queue is not None:
            await queue._add_to_cache()
            return queue

        if create:
            queue = cls(room_id)
            await queue.insert()
            queue = await super().get_by_room_id(room_id)
            await queue._add_to_cache()
            return queue

        return None
