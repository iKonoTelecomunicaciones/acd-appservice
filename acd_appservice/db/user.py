from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Dict, List

import asyncpg
from attr import dataclass
from mautrix.types import RoomID, SerializableEnum, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


class UserRoles(SerializableEnum):
    SUPERVISOR = "SUPERVISOR"
    AGENT = "AGENT"
    MENU = "MENU"
    CUSTOMER = "CUSTOMER"


@dataclass
class User:
    db: ClassVar[Database] = fake_db

    mxid: UserID
    id: int | None = None
    management_room: RoomID | None = None  # if is admin
    role: UserRoles = None

    # max_chats: int = 0

    _columns = "mxid, management_room, role"

    @property
    def _values(self):
        role = self.role.value if self.role else None
        return (self.mxid, self.management_room, role)

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> User:
        data = dict(row)
        try:
            role = UserRoles(data.pop("role"))
        except ValueError:
            role = None
        return cls(role=role, **data)

    async def insert(self) -> None:
        q = 'INSERT INTO "user" (mxid, management_room, role) VALUES ($1, $2, $3)'
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = 'UPDATE "user" SET management_room=$2, role=$3 WHERE mxid=$1'
        await self.db.execute(q, *self._values)

    async def delete(self) -> None:
        q = 'DELETE FROM "user" WHERE mxid=$1'
        await self.db.execute(q, self.mxid)

    @classmethod
    async def get_by_mxid(cls, user_id: UserID) -> User | None:
        q = f'SELECT id, {cls._columns} FROM "user" WHERE mxid=$1'
        row = await cls.db.fetchrow(q, user_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_id(cls, id: int) -> User | None:
        q = f'SELECT id, {cls._columns} FROM "user" WHERE id=$1'
        row = await cls.db.fetchrow(q, id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_users_by_role(cls, role: str) -> List[Dict]:
        q = f'SELECT id, {cls._columns} FROM "user" WHERE role=$1 ORDER BY mxid'
        rows = await cls.db.fetch(q, role)
        if not rows:
            return None

        return [dict(user) for user in rows]
