from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Dict, List

import asyncpg
from attr import dataclass
from mautrix.types import ContentURI, RoomID, SyncToken, UserID
from mautrix.util.async_db import Database
from yarl import URL

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Puppet:
    """Puppet representation in the db"""

    db: ClassVar[Database] = fake_db

    pk: int | None
    email: str | None
    phone: str | None
    bridge: str | None
    destination: str | None
    photo_mxc: ContentURI | None
    name_set: bool
    avatar_set: bool

    is_registered: bool

    custom_mxid: UserID | None
    access_token: str | None
    next_batch: SyncToken | None
    base_url: URL | None
    control_room_id: RoomID

    @property
    def _values(self):
        return (
            self.email,
            self.phone,
            self.bridge,
            self.destination,
            self.photo_mxc,
            self.name_set,
            self.avatar_set,
            self.is_registered,
            self.custom_mxid,
            self.access_token,
            self.next_batch,
            str(self.base_url) if self.base_url else None,
            self.control_room_id,
        )

    _columns = (
        "email, phone, bridge, destination, photo_mxc, name_set, avatar_set, is_registered,"
        "custom_mxid, access_token, next_batch, base_url, control_room_id"
    )

    async def insert(self) -> None:
        q = (
            f"INSERT INTO puppet ({self._columns}) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)"
        )
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        q = (
            "UPDATE puppet SET email=$1, phone=$2, bridge=$3, destination=$4, photo_mxc=$5, name_set=$6,"
            "                  avatar_set=$7, is_registered=$8, custom_mxid=$9, access_token=$10,"
            "                  next_batch=$11, base_url=$12, control_room_id=$13 "
            "WHERE custom_mxid=$9"
        )
        await self.db.execute(q, *self._values)

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Puppet:
        data = {**row}
        base_url_str = data.pop("base_url")
        base_url = URL(base_url_str) if base_url_str is not None else None
        return cls(base_url=base_url, **data)

    @classmethod
    @property
    def query(cls) -> str:
        return f"SELECT pk, {cls._columns} FROM puppet WHERE"

    @classmethod
    async def get_by_pk(cls, pk: int) -> Puppet | None:
        q = f"{cls.query} pk=$1"
        row = await cls.db.fetchrow(q, pk)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_custom_mxid(cls, mxid: UserID) -> Puppet | None:
        q = f"{cls.query} custom_mxid=$1"
        row = await cls.db.fetchrow(q, mxid)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_info_by_custom_mxid(cls, mxid: UserID) -> Dict | None:
        columns_to_remove = ["access_token", "next_batch", "base_url"]
        q = f"{cls.query} custom_mxid=$1"
        row = await cls.db.fetchrow(q, mxid)
        if not row:
            return None

        data = dict(row)
        for column in columns_to_remove:
            del data[column]

        return data

    @classmethod
    async def get_by_email(cls, email: str) -> Puppet | None:
        q = f"{cls.query} email=$1"
        row = await cls.db.fetchrow(q, email)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_phone(cls, phone: str) -> Puppet | None:
        q = f"{cls.query} phone=$1"
        row = await cls.db.fetchrow(q, phone)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_by_control_room_id(cls, control_room_id: RoomID) -> Puppet | None:
        q = f"{cls.query} control_room_id=$1"
        row = await cls.db.fetchrow(q, control_room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_all_puppets(cls) -> list[UserID]:
        q = "SELECT * FROM puppet WHERE custom_mxid IS NOT NULL"
        rows = await cls.db.fetch(q)

        if not rows:
            return []

        return [cls._from_row(row).custom_mxid for row in rows]

    @classmethod
    async def get_next_puppet_id(cls) -> int | None:
        """Get the next puppet id using the custom_mxid and filtering with username_template"""
        username_template = cls.config["bridge.username_template"].format(userid="")
        q = f"""
            SELECT MAX(TO_NUMBER(SUBSTRING(custom_mxid
            FROM '@{username_template}#"[0-9]+#":%' FOR '#'), '999')) + 1
            AS next_mxid
            FROM puppet
            WHERE custom_mxid IS NOT NULL;
        """
        result = await cls.db.fetchval(q)

        return result if result else None

    @classmethod
    async def get_all_puppets_from_mautrix(cls) -> list[UserID]:
        q = "SELECT * FROM puppet WHERE custom_mxid IS NOT NULL AND bridge = 'mautrix'"
        rows = await cls.db.fetch(q)

        if not rows:
            return []

        return [cls._from_row(row).custom_mxid for row in rows]

    @classmethod
    async def get_control_room_ids(cls) -> list[RoomID]:
        q = "SELECT control_room_id FROM puppet WHERE control_room_id IS NOT NULL"
        rows: List[RoomID] = await cls.db.fetch(q)
        if not rows:
            return None
        control_room_ids = [control_room_id.get("control_room_id") for control_room_id in rows]
        return control_room_ids

    @classmethod
    async def all_with_custom_mxid(cls) -> list[Puppet]:
        q = f"{cls.query} custom_mxid IS NOT NULL"
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]
