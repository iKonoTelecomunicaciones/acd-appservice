from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from attr import dataclass

# from mautrix.types import RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None

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
    creation_ts: int  # Date of queue_membership creation
    state_ts: int = 0  # Last change of state
    pause_ts: int = 0  # Last pause record
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
            self.creation_ts,
            self.state_ts,
            self.pause_ts,
            self.pause_reason,
            self.state,
            self.paused,
        )

    _columns = "fk_user, fk_queue, creation_ts, state_ts, pause_ts, pause_reason, state, paused"

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> QueueMembership:
        return cls(**row)

    async def insert(self) -> None:
        q = f"INSERT INTO queue_membership ({self._columns}) VALUES ($1, $2, $3, $4, $5, $6, $7, $8);"
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = "UPDATE queue_membership SET creation_ts=$3, state_ts=$4, pause_ts=$5, pause_reason=$6, state=$7, paused=$8 WHERE fk_user=$1 AND fk_queue=$2;"
        await self.db.execute(q, *self._values)

    @classmethod
    async def get_by_queue_and_user(cls, fk_user: int, fk_queue: int) -> QueueMembership | None:
        q = f"SELECT id, {cls._columns} FROM queue_membership WHERE fk_user=$1 AND fk_queue=$2;"
        row = await cls.db.fetchrow(q, fk_user, fk_queue)
        if not row:
            return None
        return cls._from_row(row)
