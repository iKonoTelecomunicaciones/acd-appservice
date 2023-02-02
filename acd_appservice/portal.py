from __future__ import annotations

import logging
import re
from enum import Enum
from typing import cast

from mautrix.appservice import IntentAPI
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config
from .db.portal import Portal as DBPortal
from .db.portal import PortalState
from .matrix_room import MatrixRoom
from .util import Util


class LockedReason(Enum):
    GENERAL = "{room_id}"
    TRANSFER = "TRANSFER-{room_id}"


class Portal(DBPortal, MatrixRoom):

    log: TraceLogger = logging.getLogger("acd.message")
    config: Config

    room_id: RoomID
    creator: UserID
    bridge: str
    state: PortalState

    by_id: dict[int, Portal] = {}
    by_room_id: dict[RoomID, Portal] = {}

    LOCKED_PORTALS: set = set()

    def _init_(
        self, room_id: RoomID, id: int = None, intent: IntentAPI = None, fk_puppet: int = None
    ):
        DBPortal.__init__(self, id=id, room_id=room_id, fk_puppet=fk_puppet)
        MatrixRoom.__init__(self, room_id=room_id, intent=intent)

    async def _add_to_cache(self) -> None:
        self.by_id[self.id] = self
        self.by_room_id[self.room_id] = self

    async def update_state(self, state: PortalState):
        self.log.debug(f"Updating state [{self.state}] to [{state.value}]")
        self.state = state.value
        await self.save()

    async def update_room_name(self) -> None:
        """If the room name is not set to be kept, get the updated name and set it

        Returns
        -------
            The updated room name.

        """

        if self.config["acd.keep_room_name"]:
            self.log.debug(
                f"The portal {self.room_id} name hasn't been updated because keep_room_name is true."
            )
            return

        updated_room_name = await self.get_update_name()

        if not updated_room_name:
            return

        await self.main_intent.set_room_name(room_id=self.room_id, name=updated_room_name)

    async def get_update_name(self) -> str:
        """It gets the room name from the creator's display name,
        and adds an emoji number to the end of the room name if the config option is enabled

        Returns
        -------
            The new room name.

        """
        new_room_name = None
        emoji_number = ""
        bridges = self.config["bridges"]
        for bridge in bridges:
            user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
            if self.creator.startswith(f"@{user_prefix}"):
                if bridge == "instagram":
                    new_room_name = await self.main_intent.get_displayname(user_id=self.creator)
                else:
                    new_room_name = await self.room_name_custom_by_creator()

                if new_room_name:
                    postfix_template = self.config[f"bridges.{bridge}.postfix_template"]
                    new_room_name = new_room_name.replace(f" {postfix_template}", "")
                    if self.config["acd.numbers_in_rooms"]:
                        try:

                            emoji_number = Util.get_emoji_number(number=str(self.fk_puppet))

                            if emoji_number:
                                new_room_name = f"{new_room_name} {emoji_number}"
                        except AttributeError as e:
                            self.log.error(e)
                break

        return new_room_name

    async def room_name_custom_by_creator(self) -> str:
        """If the creator of the room is a phone number,
        then return the displayname of the creator, or if that's not available,
        just return the phone number

        Returns
        -------
            A string

        """
        phone_match = re.findall(r"\d+", self.creator)
        if phone_match:
            self.log.debug(f"Formatting phone number {phone_match[0]}")

            customer_displayname = await self.main_intent.get_displayname(self.creator)
            if customer_displayname:
                room_name = f"{customer_displayname.strip()} ({phone_match[0].strip()})"
            else:
                room_name = f"({phone_match[0].strip()})"
            return room_name

        return None

    @property
    def is_locked(self) -> bool:
        return self.room_id in self.LOCKED_PORTALS

    def lock(self, transfer: bool = False):
        """If the room is already locked, return.
        If the room is being locked for a transfer,
        add the room to the set of locked rooms with the reason being "TRANSFER".
        Otherwise, add the room to the set of locked rooms with the reason being "GENERAL"

        Parameters
        ----------
        transfer : bool, optional
            bool = False

        Returns
        -------
            A set of strings.

        """
        if self.is_lock:
            self.log.debug(f"The room {self.room_id} already locked")
            return

        if transfer:
            self.log.debug(f"[TRANSFER] - LOCKING PORTAL {self.room_id}...")
            self.LOCKED_PORTALS.add(LockedReason.TRANSFER.value.format(room_id=self.room_id))
        else:
            self.log.debug(f"LOCKING PORTAL {self.room_id}...")
            self.LOCKED_PORTALS.add(LockedReason.GENERAL.value.format(room_id=self.room_id))

    def unlock(self, transfer: bool = False):
        """If the room is locked, remove the lock from the list of locked rooms

        Parameters
        ----------
        transfer : bool, optional
            bool = False

        Returns
        -------
            The room_id

        """

        if not self.is_lock:
            self.log.debug(f"The room {self.room_id} already unlocked")
            return

        if transfer:
            self.log.debug(f"[TRANSFER] - UNLOCKING PORTAL {self.room_id}...")
            self.LOCKED_PORTALS.remove(
                LockedReason.TRANSFER.value.replace("room_id", self.room_id)
            )
        else:
            self.log.debug(f"UNLOCKING PORTAL {self.room_id}...")
            self.LOCKED_PORTALS.remove(LockedReason.GENERAL.value.replace("room_id", self.room_id))

    async def save(self) -> None:
        await self._add_to_cache()
        await self.update()

    @classmethod
    async def get_by_room_id(
        cls,
        room_id: RoomID,
        *,
        create: bool = True,
        fk_puppet: int = None,
        intent: IntentAPI = None,
    ) -> Portal | None:

        try:
            return cls.by_room_id[room_id]
        except KeyError:
            pass

        portal = cast(cls, await super().get_by_room_id(room_id))
        if portal is not None:

            if fk_puppet:
                portal.fk_puppet = fk_puppet

            if intent:
                portal.main_intent = intent

            await portal._add_to_cache()
            await portal.post_init()
            return portal

        if create:
            portal = cls(room_id)

            if fk_puppet:
                portal.fk_puppet = fk_puppet

            if intent:
                portal.main_intent = intent

            await portal.insert()
            portal = cast(cls, await super().get_by_room_id(room_id))
            await portal._add_to_cache()
            await portal.post_init()
            return portal

        return None
