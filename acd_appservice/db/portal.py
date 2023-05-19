from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Dict, List

import asyncpg
from attr import dataclass
from mautrix.types import RoomID, SerializableEnum
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


class PortalState(SerializableEnum):
    INIT = "INIT"
    START = "START"
    PENDING = "PENDING"
    FOLLOWUP = "FOLLOWUP"
    RESOLVED = "RESOLVED"
    ENQUEUED = "ENQUEUED"
    ONMENU = "ONMENU"
    ON_DISTRIBUTION = "ON_DISTRIBUTION"
    ASSIGNED = "ASSIGNED"


@dataclass
class Portal:
    db: ClassVar[Database] = fake_db

    room_id: RoomID
    state: PortalState = PortalState.INIT
    state_date: datetime | None = None
    fk_puppet: int | None = None
    selected_option: RoomID | None = None
    id: int | None = None

    @property
    def _values(self):
        return (
            self.room_id,
            self.selected_option,
            self.state.value,
            self.state_date,
            self.fk_puppet,
        )

    _columns = "room_id, selected_option, state, state_date, fk_puppet"

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Portal:
        """It takes a class and a row from a database,
        and returns an instance of the class with the row's values

        Parameters
        ----------
        row : asyncpg.Record

        Returns
        -------
            A Room object

        """
        data = {**row}
        state = PortalState(data.pop("state"))
        return cls(state=state, **data)

    async def insert(self) -> None:
        """It inserts a new row into the room table"""
        q = f"INSERT INTO portal ({self._columns}) VALUES ($1, $2, $3, $4, $5)"
        await self.db.execute(q, *self._values)

    async def update(self) -> None:
        """It updates the portal's selected_option, state, and fk_puppet in the database"""
        q = (
            "UPDATE portal SET selected_option=$2, state=$3, "
            "state_date=$4, fk_puppet=$5 WHERE room_id=$1"
        )
        await self.db.execute(q, *self._values)

    @classmethod
    async def get_by_room_id(cls, room_id: RoomID) -> Portal | None:
        """Get a room from the database by its room_id

        Parameters
        ----------
        room_id : RoomID
            RoomID

        Returns
        -------
            A Room object

        """
        q = f"SELECT id, {cls._columns} FROM portal WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_rooms_by_state_and_puppet(
        cls, state: PortalState, fk_puppet: int
    ) -> List[Portal] | None:
        q = (
            f"SELECT id, {cls._columns} FROM portal WHERE state=$1 "
            "AND fk_puppet=$2 ORDER BY selected_option ASC, state_date ASC"
        )
        rows = await cls.db.fetch(q, state.value, fk_puppet)
        if not rows:
            return []

        return [cls._from_row(room) for room in rows]

    @classmethod
    async def get_user_selected_menu(cls, room_id: RoomID) -> str | None:
        """Get the selected menu option from the database

        Parameters
        ----------
        room_id : RoomID
            RoomID

        Returns
        -------
            The selected option from the room table.

        """
        q = "SELECT selected_option FROM portal WHERE room_id=$1"
        row = await cls.db.fetchval(q, room_id)
        if not row:
            return None
        return row

    @classmethod
    async def get_rooms_by_puppet(cls, fk_puppet: int) -> Dict[RoomID, None] | None:
        """It returns a dict of rooms

        Parameters
        ----------

        Returns
        -------
            A dict of Room objects

        """
        q = f"SELECT id, {cls._columns} FROM portal WHERE fk_puppet=$1"
        rows = await cls.db.fetch(q, fk_puppet)
        if not rows:
            return None

        return {cls._from_row(room).room_id: None for room in rows}
