from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, List

from attr import dataclass
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None

from datetime import datetime
from enum import Enum

import asyncpg


class QueueMembershipState(Enum):
    Online = "online"
    Offline = "offline"


# @dataclass
# class PauseReason:
#     db: ClassVar[Database] = fake_db
#     id: int
#     reason: str
#     enable: bool


@dataclass
class QueueMembership:
    db: ClassVar[Database] = fake_db

    id: int
    fk_user: int
    fk_queue: int
    creation_date: datetime  # Date of queue_membership creation
    state_date: datetime | None = None  # Last change of state
    pause_date: datetime | None = None  # Last pause record
    pause_reason: str = None
    state: str = QueueMembershipState.Offline.value
    paused: bool = False

    # penalty: int = 0
    # max_chats: int = 0
    # last_chat: RoomID # last chat received

    @property
    def _values(self):
        return (
            self.fk_user,
            self.fk_queue,
            self.creation_date,
            self.state_date,
            self.pause_date,
            self.pause_reason,
            self.state,
            self.paused,
        )

    _columns = (
        "fk_user, fk_queue, creation_date, state_date, pause_date, pause_reason, state, paused"
    )

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> QueueMembership:
        return cls(**row)

    async def insert(self) -> None:
        q = f"""INSERT INTO queue_membership ({self._columns})
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"""
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = """UPDATE queue_membership
        SET creation_date=$3, state_date=$4, pause_date=$5, pause_reason=$6,
        state=$7, paused=$8 WHERE fk_user=$1 AND fk_queue=$2"""
        await self.db.execute(q, *self._values)

    async def delete(self) -> None:
        q = 'DELETE FROM "queue_membership" WHERE fk_user=$1 AND fk_queue=$2'
        await self.db.execute(q, self.fk_user, self.fk_queue)

    @classmethod
    async def get_by_queue_and_user(cls, fk_user: int, fk_queue: int) -> QueueMembership | None:
        """Get a queue membership by user and queue."

        Parameters
        ----------
        fk_user : int
            int
        fk_queue : int
            int

        Returns
        -------
            A QueueMembership object

        """

        q = f"SELECT id, {cls._columns} FROM queue_membership WHERE fk_user=$1 AND fk_queue=$2"
        row = await cls.db.fetchrow(q, fk_user, fk_queue)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_queue(cls, fk_queue: int) -> List[QueueMembership] | None:
        """Get a queue membership by queue."

        Parameters
        ----------
        fk_user : int
            int
        fk_queue : int
            int

        Returns
        -------
            A QueueMembership object

        """

        q = f"SELECT id, {cls._columns} FROM queue_membership WHERE fk_queue=$1"
        rows = await cls.db.fetch(q, fk_queue)
        if not rows:
            return None
        return [cls._from_row(queue_membership) for queue_membership in rows]

    @classmethod
    async def get_user_memberships(cls, fk_user: int) -> List[dict] | None:
        """Get all user memberships

        Parameters
        ----------
        fk_user : int
            The user's ID

        Returns
        -------
            A list of dictionaries with memberships data of the user.

        """

        q = """
            SELECT
                queue.room_id,
                queue.name,
                queue.description,
                queue_membership.state_date,
                queue_membership.pause_date,
                queue_membership.pause_reason,
                queue_membership.state,
                queue_membership.paused
            FROM queue
            JOIN queue_membership ON queue_membership.fk_queue = queue.id
            WHERE queue_membership.fk_user = $1
        """

        result = await cls.db.fetch(q, fk_user)
        if not result:
            return None

        memberships = []
        dt_format = "%Y-%m-%d %H:%M:%S%z"
        for user in result:
            state_date = user.get("state_date")
            pause_date = user.get("pause_date")
            memberships.append(
                {
                    "room_id": user.get("room_id"),
                    "room_name": user.get("name"),
                    "description": user.get("description"),
                    "state_date": datetime.strftime(state_date, dt_format) if state_date else None,
                    "pause_date": datetime.strftime(pause_date, dt_format) if pause_date else None,
                    "pause_reason": user.get("pause_reason"),
                    "state": user.get("state"),
                    "paused": user.get("paused"),
                }
            )

        return memberships

    @classmethod
    async def get_users(cls) -> List[dict] | None:
        """Get all users with memberships

        Returns
        -------
            A list of dictionaries with id and mxid of each user.

        """

        q = """
            SELECT DISTINCT "user".id, "user".mxid
            FROM "user"
            JOIN queue_membership ON queue_membership.fk_user = "user".id
        """

        results = await cls.db.fetch(q)

        return [{"id": id, "user_id": mxid} for id, mxid in results if results]
