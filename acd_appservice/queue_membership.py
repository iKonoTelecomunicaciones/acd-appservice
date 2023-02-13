from __future__ import annotations

import logging
from datetime import datetime
from datetime import datetime as dt
from typing import cast

from mautrix.util.logging import TraceLogger

from .db.queue_membership import QueueMembership as DBMembership
from .db.queue_membership import QueueMembershipState


class QueueMembership(DBMembership):
    fk_user: int
    fk_queue: int
    creation_date: datetime
    state_date: datetime | None = None
    pause_date: datetime | None = None
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
        creation_date: datetime,
        state_date: datetime | None = None,
        pause_date: datetime | None = None,
        pause_reason: str | None = None,
        state: str = QueueMembershipState.Offline.value,
        paused: bool = False,
        id: int | None = None,
    ):
        super().__init__(
            id=id,
            fk_user=fk_user,
            fk_queue=fk_queue,
            creation_date=creation_date,
            state_date=state_date,
            pause_date=pause_date,
            pause_reason=pause_reason,
            state=state,
            paused=paused,
        )

    @classmethod
    def now(cls) -> str:
        return dt.utcnow()

    async def save(self) -> None:
        self._add_to_cache()
        await self.update()

    async def _delete(self):
        del self.by_queue_and_user[f"{self.fk_user}-{self.fk_queue}"]
        await self.delete()

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
            prev_membership = await QueueMembership.get_serialized_memberships(fk_user=fk_user)
            queue_membership = cls(fk_user, fk_queue, cls.now())
            if prev_membership:
                queue_membership.state = prev_membership[0]["state"]
                queue_membership.paused = prev_membership[0]["paused"]
                queue_membership.pause_reason = prev_membership[0]["pause_reason"]
                queue_membership.state_date = (
                    cls.now() if prev_membership[0]["state_date"] else None
                )
                queue_membership.pause_date = (
                    cls.now() if prev_membership[0]["pause_date"] else None
                )

            await queue_membership.insert()
            queue_membership._add_to_cache()
            return queue_membership

        return None

    @classmethod
    async def get_serialized_memberships(cls, fk_user: int) -> list[dict] | None:
        """Get all user serialized memberships and formatted date

        Parameters
        ----------
        fk_user : int
            The user's ID

        Returns
        -------
            A list of dictionaries with memberships data of the user.

        """
        memberships = []
        dt_format = "%Y-%m-%d %H:%M:%S%z"
        user_memberships = await cls.get_user_memberships(fk_user)
        if user_memberships:
            for membership in user_memberships:
                membership = dict(membership)
                state_date: datetime = membership.get("state_date")
                pause_date: datetime = membership.get("pause_date")
                membership["state_date"] = state_date.strftime(dt_format) if state_date else None
                membership["pause_date"] = pause_date.strftime(dt_format) if pause_date else None
                memberships.append(membership)
            return memberships

        return None
