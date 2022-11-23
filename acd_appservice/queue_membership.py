from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

from mautrix.util.logging import TraceLogger

from .db.queue_membership import QueueMembership as DBMembership
from .db.queue_membership import QueueMembershipState


class QueueMembership(DBMembership):

    fk_user: int
    fk_queue: int
    creation_ts: int
    state_ts: int = 0
    pause_ts: int = 0
    pause_reason: str | None = None
    state: str = QueueMembershipState.Offline.value
    paused: bool = False

    log: TraceLogger = logging.getLogger("acd.queue_membership")

    by_id: dict[int, QueueMembership] = {}
    by_queue_and_user: dict[str, QueueMembership] = {}

    def __init__(
        self,
        fk_user: int,
        fk_queue: int,
        creation_ts: int,
        state_ts: int = 0,
        pause_ts: int = 0,
        pause_reason: str | None = None,
        state: str = QueueMembershipState.Offline.value,
        paused: bool = False,
        id: int | None = None,
    ):
        super().__init__(
            id=id,
            fk_user=fk_user,
            fk_queue=fk_queue,
            creation_ts=creation_ts,
            state_ts=state_ts,
            pause_ts=pause_ts,
            pause_reason=pause_reason,
            state=state,
            paused=paused,
        )

    async def save(self) -> None:
        self._add_to_cache()
        await self.update()

    def _add_to_cache(self) -> None:
        self.by_id[self.id] = self
        self.by_queue_and_user[f"{self.fk_user}-{self.fk_queue}"] = self

    @classmethod
    async def get_by_queue_and_user(
        cls, fk_user: int, fk_queue: int, *, create: bool = True
    ) -> QueueMembership | None:

        try:
            return cls.by_queue_and_user[f"{fk_user}-{fk_queue}"]
        except KeyError:
            pass

        queue_membership = cast(cls, await super().get_by_queue_and_user(fk_user, fk_queue))
        if queue_membership is not None:
            queue_membership._add_to_cache()
            return queue_membership

        if create:
            queue_membership = cls(fk_user, fk_queue, datetime.timestamp(datetime.utcnow()))
            await queue_membership.insert()
            queue_membership._add_to_cache()
            return queue_membership

        return None
