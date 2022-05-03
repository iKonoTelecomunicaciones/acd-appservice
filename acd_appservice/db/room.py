from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, List

import asyncpg
from attr import dataclass
from mautrix.types import RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Room:
    """Representación en la bd de room y pending_room"""

    db: ClassVar[Database] = fake_db

    id: int | None
    room_id: RoomID
    selected_option: str

    @classmethod
    def _from_row(cls, row: asyncpg.Record) -> Room:
        """It takes a class and a row from a database, and returns an instance of the class with the row's values

        Parameters
        ----------
        row : asyncpg.Record
            asyncpg.Record

        Returns
        -------
            A Room object

        """
        return cls(**row)

    @classmethod
    async def insert_room(cls, room_id: RoomID, selected_option: str) -> None:
        """It inserts a new row into the room table

        Parameters
        ----------
        room_id : RoomID
            RoomID
        selected_option : str
            The option that the user has selected.

        """
        q = "INSERT INTO room (room_id, selected_option) VALUES ($1, $2)"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def insert_pending_room(cls, room_id: RoomID, selected_option: RoomID) -> None:
        """It inserts a row into the pending_room table

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room that the user is in.
        selected_option : RoomID
            The room ID of the room that the user selected.

        """
        q = "INSERT INTO pending_room (room_id, selected_option) VALUES ($1, $2)"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def update_room_by_id(cls, id: int, room_id: RoomID, selected_option: str) -> None:
        """Update the room with the given id, setting the room_id to the given room_id and the selected_option to the given selected_option

        Parameters
        ----------
        id : int
            int - The id of the room to update
        room_id : RoomID
            RoomID = RoomID.from_string(room_id)
        selected_option : str
            This is the option that the user has selected.

        """
        q = "UPDATE room SET room_id=$2, selected_option=$3 WHERE id=$1"
        await cls.db.execute(q, *(id, room_id, selected_option))

    @classmethod
    async def update_room_by_room_id(cls, room_id: RoomID, selected_option: str) -> None:
        """Update the selected_option column of the room table with the given room_id

        Parameters
        ----------
        room_id : RoomID
            RoomID
        selected_option : str
            str

        """
        q = "UPDATE room SET selected_option=$2 WHERE room_id=$1"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def update_pending_room_by_id(
        cls, id: int, room_id: RoomID, selected_option: str
    ) -> None:
        """It updates the pending_room table with the room_id and selected_option

        Parameters
        ----------
        id : int
            The id of the pending room.
        room_id : RoomID
            The room ID of the room that the user is in.
        selected_option : str
            The option that the user selected.

        """
        q = "UPDATE pending_room SET room_id=$2, selected_option=$3 WHERE id=$1"
        await cls.db.execute(q, *(id, room_id, selected_option))

    @classmethod
    async def update_pending_room_by_room_id(cls, room_id: RoomID, selected_option: str) -> None:
        """Update the selected_option column of the pending_room table with the selected_option
        parameter where the room_id column is equal to the room_id parameter

        Parameters
        ----------
        room_id : RoomID
            RoomID
        selected_option : str
            The option that the user selected.

        """
        q = "UPDATE pending_room SET selected_option=$2 WHERE room_id=$1"
        await cls.db.execute(q, *(room_id, selected_option))

    @classmethod
    async def get_room_by_room_id(cls, room_id: RoomID) -> Room | None:
        """Get a room from the database by its room_id

        Parameters
        ----------
        room_id : RoomID
            RoomID

        Returns
        -------
            A Room object

        """
        q = "SELECT id, room_id, selected_option FROM room WHERE room_id=$1"
        row = await cls.db.fetchrow(q, room_id)
        if not row:
            return None
        return cls._from_row(row)

    @classmethod
    async def get_pending_room_by_room_id(cls, room_id: RoomID) -> Room | None:
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
        q = "SELECT selected_option FROM room WHERE room_id=$1"
        row = await cls.db.fetchval(q, room_id)
        if not row:
            return None
        return row

    @classmethod
    async def get_campaign_of_pending_room(cls, room_id: RoomID) -> str | None:
        """ "Get the campaign of a pending room."

        The first line is a docstring. It's a good idea to write docstrings for all your functions

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
    async def get_rooms(cls) -> List[Room] | None:
        """It returns a list of Room objects, or None if there are no rooms in the database

        Parameters
        ----------

        Returns
        -------
            A list of Room objects

        """
        q = "SELECT id, room_id, selected_option  FROM room ORDER BY selected_option"
        rows = await cls.db.fetch(q)
        if not rows:
            return None

        return [cls._from_row(room) for room in rows]

    @classmethod
    async def get_pending_rooms(cls) -> List[Room] | None:
        """It returns a list of rooms that are pending

        Parameters
        ----------

        Returns
        -------
            A list of Room objects

        """
        q = "SELECT id, room_id, selected_option  FROM pending_room ORDER BY selected_option"
        rows = await cls.db.fetch(q)
        if not rows:
            return None

        return [cls._from_row(room) for room in rows]

    @classmethod
    async def remove_pending_room(cls, room_id: RoomID) -> None:
        """Remove the room from the pending room table.

        The first line is a docstring. It's a string that describes what the function does. It's a good idea to write a docstring for every function you write

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room to be removed from the pending room list.

        """
        q = "DELETE FROM pending_room FROM room_id=$1"
        await cls.db.execute(q, room_id)
