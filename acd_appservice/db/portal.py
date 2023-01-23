from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Dict, List

import asyncpg
from attr import dataclass
from mautrix.types import RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


class PortalState(Enum):
    INIT = "INIT"
    PENDING = "PENDING"
    FOLLOWUP = "FOLLOWUP"
    RESOLVED = "RESOLVED"
    ENQUEUED = "ENQUEUED"
    ONMENU = "ONMENU"


@dataclass
class Portal:

    db: ClassVar[Database] = fake_db

    id: int | None
    room_id: RoomID
    selected_option: str | None
    state: PortalState = None
    fk_puppet: int | None = None

    @property
    def _values(self):
        return (
            self.room_id,
            self.selected_option,
            self.state,
            self.fk_puppet,
        )

    _columns = "room_id, selected_option, state, fk_puppet"

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
        return cls(**row)

    @classmethod
    async def insert(cls, room_id: RoomID, selected_option: str, fk_puppet: int) -> None:
        """It inserts a new row into the room table

        Parameters
        ----------
        room_id : RoomID
            RoomID
        selected_option : str
            The option that the user has selected.
        fk_puppet : int
            The puppet foregin key.

        """
        q = f"INSERT INTO portal ({cls._columns}) VALUES ($1, $2, $3, $4)"
        await cls.db.execute(q, *(room_id, selected_option, fk_puppet))

    @classmethod
    async def insert_pending_room(
        cls, room_id: RoomID, selected_option: RoomID, fk_puppet: int
    ) -> None:
        """It inserts a row into the pending_room table

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room that the user is in.
        selected_option : RoomID
            The room ID of the room that the user selected.

        """
        q = "INSERT INTO pending_room (room_id, selected_option, fk_puppet) VALUES ($1, $2, $3)"
        await cls.db.execute(q, *(room_id, selected_option, fk_puppet))

    @classmethod
    async def update(cls, room_id: RoomID, selected_option: str, fk_puppet: int) -> None:
        """Update the selected_option column of the room table with the given room_id

        Parameters
        ----------
        room_id : RoomID
            RoomID
        selected_option : str
            str
        fk_puppet : int
            The puppet foregin key.

        """
        q = "UPDATE portal SET selected_option=$2, fk_puppet=$3 WHERE room_id=$1"
        await cls.db.execute(q, *(room_id, selected_option, fk_puppet))

    @classmethod
    async def update_pending_room_by_room_id(
        cls, room_id: RoomID, selected_option: str, fk_puppet: int
    ) -> None:
        """Update the selected_option column of the pending_room table with the selected_option
        parameter WHERE the room_id column is equal to the room_id parameter

        Parameters
        ----------
        room_id : RoomID
            RoomID
        selected_option : str
            The option that the user selected.

        """
        q = "UPDATE pending_room SET selected_option=$2, fk_puppet=$3 WHERE room_id=$1"
        await cls.db.execute(q, *(room_id, selected_option, fk_puppet))

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
    async def get_pending_room_by_room_id(cls, room_id: RoomID) -> Portal | None:
        """This function returns a room object if the room_id is found in the database, otherwise it returns None

        Parameters
        ----------
        room_id : RoomID
            RoomID

        Returns
        -------
            A Room object

        """
        q = "SELECT id, room_id, selected_option FROM pending_room WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

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
    async def get_campaign_of_pending_room(cls, room_id: RoomID) -> str | None:
        """ "Get the campaign of a pending room."

        Parameters
        ----------
        room_id : RoomID
            RoomID

        Returns
        -------
            The campaign name

        """
        q = "SELECT selected_option FROM pending_room WHERE room_id=$1"
        row = await cls.db.fetchval(q, room_id)
        if not row:
            return None
        return row

    @classmethod
    async def get_pending_rooms(cls, fk_puppet: int) -> List[Portal] | None:
        """It returns a list of rooms that are pending

        Parameters
        ----------

        Returns
        -------
            A list of Room objects

        """
        q = (
            "SELECT id, room_id, selected_option, fk_puppet FROM "
            "pending_room WHERE fk_puppet=$1 ORDER BY selected_option"
        )
        rows = await cls.db.fetch(q, fk_puppet)
        if not rows:
            return None

        return [cls._from_row(room) for room in rows]

    @classmethod
    async def get_rooms_by_puppet(cls, fk_puppet: int) -> Dict[Portal] | None:
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

    @classmethod
    async def remove_pending_room(cls, room_id: RoomID) -> None:
        """Remove the room from the pending room table.

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room to be removed from the pending room list.

        """
        q = "DELETE FROM pending_room WHERE room_id=$1"
        await cls.db.execute(q, room_id)
