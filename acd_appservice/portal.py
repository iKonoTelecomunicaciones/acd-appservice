from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Dict, List, cast

from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import IntentAPI
from mautrix.types import (
    EventType,
    JoinRule,
    PowerLevelStateEventContent,
    RoomDirectoryVisibility,
    RoomID,
    UserID,
)
from mautrix.util.logging import TraceLogger

from .config import Config
from .db.portal import Portal as DBPortal
from .db.portal import PortalState
from .matrix_room import MatrixRoom
from .user import User
from .util import ACDEventsType, ACDPortalEvents, CreateEvent, Util


class Portal(DBPortal, MatrixRoom):
    log: TraceLogger = logging.getLogger("acd.portal")
    config: Config

    room_id: RoomID
    creator: UserID
    bridge: str
    state: PortalState = PortalState.INIT

    by_id: dict[int, Portal] = {}
    by_room_id: dict[RoomID, Portal] = {}

    LOCKED_PORTALS: set = set()

    def _init_(
        self, room_id: RoomID, id: int = None, intent: IntentAPI = None, fk_puppet: int = None
    ):
        DBPortal.__init__(self, id=id, room_id=room_id, fk_puppet=fk_puppet)
        MatrixRoom.__init__(self, room_id=room_id, intent=intent)
        self.log = self.log.getChild(room_id)

    async def _add_to_cache(self) -> None:
        self.by_id[self.id] = self
        self.by_room_id[self.room_id] = self

    async def update_state(self, state: PortalState):
        self.log.debug(
            f"Updating room [{self.room_id}] state [{self.state.value}] to [{state.value}]"
        )
        self.state = state
        await self.save()

    async def update_room_name(self) -> None:
        """If the room name is not set to be kept, get the updated name and set it

        Returns
        -------
            The updated room name.

        """

        updated_room_name = await self.get_update_name()

        if not updated_room_name:
            return

        await self.main_intent.set_room_name(room_id=self.room_id, name=updated_room_name)

    async def get_current_agent(self) -> User | None:
        """Get the current agent, if there is one.

        Returns
        -------
            A User object

        """
        users: List[User] = await self.get_joined_users()

        # If it is None, it is because something has gone wrong.
        if not users:
            return False

        for user in users:
            if user.is_agent:
                return user

    async def get_current_menubot(self) -> User | None:
        """Get the current menu, if there is one.

        Returns
        -------
            A User object

        """
        users: List[User] = await self.get_joined_users()

        # If it is None, it is because something has gone wrong.
        if not users:
            return False

        for user in users:
            if user.is_menubot:
                return user

    async def has_online_agents(self) -> bool | str:
        """It checks if the agent is online

        Returns
        -------
            A boolean value.

        """

        agent = await self.get_current_agent()

        if agent == False:
            return "unlock"

        if agent is None:
            return False

        state = await agent.is_online()

        self.log.debug(
            f"Agent {agent.mxid} in the room [{self.room_id}] is [{'online' if state else 'offline'}]"
        )

        return state

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

            customer_displayname = await self.creator_displayname()
            if customer_displayname:
                room_name = f"{customer_displayname.strip()} ({phone_match[0].strip()})"
            else:
                room_name = f"({phone_match[0].strip()})"
            return room_name

        return None

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
        if self.is_locked:
            self.log.debug(f"The room {self.room_id} already locked")
            return

        if transfer:
            self.log.debug(f"[TRANSFER] - LOCKING PORTAL {self.room_id}...")
        else:
            self.log.debug(f"LOCKING PORTAL {self.room_id}...")

        self.LOCKED_PORTALS.add(self.room_id)

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

        if not self.is_locked:
            self.log.debug(f"The room {self.room_id} already unlocked")
            return

        if transfer:
            self.log.debug(f"[TRANSFER] - UNLOCKING PORTAL {self.room_id}...")
        else:
            self.log.debug(f"UNLOCKING PORTAL {self.room_id}...")

        self.LOCKED_PORTALS.remove(self.room_id)

    async def save(self) -> None:
        await self._add_to_cache()
        await self.update()

    async def set_relay(self) -> None:
        """Send the command set-relay to a portal."""

        bridge = self.config[f"bridges.{self.bridge}"]

        cmd = f"{bridge['prefix']} {bridge['set_relay']}"
        try:
            await self.send_text(text=cmd)
        except ValueError as e:
            self.log.exception(e)

        self.log.info(f"The command {cmd} has been sent to room {self.room_id}")

    async def set_pl(self, user_id: UserID, power_level: int) -> None:
        """Send the command set-pl to a portal

        Parameters
        ----------
        user_id: UserID
            Target user to set power level.
        power_level: int
            Power level

        Returns
        -------
        """

        bridge = self.config[f"bridges.{self.bridge}"]
        cmd = (
            f"{bridge['prefix']} "
            f"{bridge['set_permissions'].format(mxid=user_id, power_level=power_level)}"
        )

        try:
            await self.send_text(text=cmd)
        except ValueError as e:
            self.log.exception(e)

        self.log.info(f"The command {cmd} has been sent to room {self.room_id}")

    async def initialize_room(self) -> bool:
        """Initializing a room.

        A room is configured, the room must be a room of a client.
        The acd is given permissions of 100, and a task is run that runs 10 times,
        it tries to add the room to the directory, that the room has a public join,
        and the history of the room is made public.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """

        self.log.debug(f"This room will be set up :: {self.room_id}")
        await self.send_create_portal_event()
        await self.update_state(PortalState.INIT)

        bridge = self.bridge
        if bridge and bridge in self.config["bridges"] and bridge != "chatterbox":
            self.log.debug(f"Sending set-relay, set-pl commands to the room :: {self.room_id}")
            await self.set_pl(
                user_id=self.main_intent.mxid,
                power_level=100,
            )
            await self.set_relay()

        await asyncio.create_task(self.initial_room_setup())

        self.log.info(f"Portal {self.room_id} initialization is complete")
        return True

    async def initial_room_setup(self):
        """Initializing a room visibility.

        it tries to add the room to the directory, that the room has a public join,
        and the history of the room is made public.

        Returns
        -------
        """

        for attempt in range(0, 10):
            self.log.debug(f"Attempt # {attempt} of room configuration")
            try:
                bridge = self.bridge
                if self.config[f"bridges.{bridge}.initial_state.enabled"]:
                    await self.set_portal_default_power_levels()

                await self.main_intent.set_room_directory_visibility(
                    room_id=self.room_id, visibility=RoomDirectoryVisibility.PUBLIC
                )

                await self.main_intent.set_join_rule(
                    room_id=self.room_id, join_rule=JoinRule.PUBLIC
                )

                await self.main_intent.send_state_event(
                    room_id=self.room_id,
                    event_type=EventType.ROOM_HISTORY_VISIBILITY,
                    content={"history_visibility": "world_readable"},
                )

                break
            except Exception as e:
                self.log.warning(e)

            await asyncio.sleep(1)

    async def set_portal_default_power_levels(self) -> None:
        """This function sets the default power levels for the portal"""

        self.log.debug(f"Setting the default power levels in the room :: {self.room_id}")
        levels = await self.main_intent.get_power_levels(room_id=self.room_id)
        current_levels: Dict = levels.serialize()
        current_levels.update(
            json.loads(
                json.dumps(self.config[f"bridges.{self.bridge}.initial_state.power_levels"])
            )
        )
        content_current_levels = PowerLevelStateEventContent.deserialize(current_levels)
        await self.main_intent.set_power_levels(
            room_id=self.room_id, content=content_current_levels
        )

    async def invite_supervisors(self) -> None:
        """Invite supervisors to the room, and if it fails,
        it waits a couple of seconds and tries again.
        """

        invitees = self.config["acd.supervisors_to_invite.invitees"]
        for user_id in invitees:
            for attempt in range(10):
                self.log.debug(f"Inviting supervisor {user_id} to {self.room_id}...")
                try:
                    await self.add_member(new_member=user_id)
                    self.log.debug(f"Supervisor {user_id} invited OK to room {self.room_id}")
                    break
                except Exception as e:
                    self.log.error(
                        f"Failed to invite supervisor {user_id} "
                        f"to room {self.room_id} attempt {attempt}: {e}"
                    )

                await asyncio.sleep(2)

    async def add_menubot(self, menubot_mxid: UserID):
        """It tries to invite the menubot to the portal, and if it fails,
        it waits a couple of seconds and tries again

        Parameters
        ----------
        menubot_id : UserID
            The user ID of the menubot.

        """
        for attempt in range(10):
            self.log.debug(f"Inviting menubot {menubot_mxid} to {self.room_id}...")
            try:
                await self.invite_user(menubot_mxid)
                # When menubot enters to the portal, set the portal state in ONMENU
                await self.update_state(PortalState.ONMENU)
                self.log.debug(f"Menubot {menubot_mxid} invited OK to room {self.room_id}")
                break
            except Exception as e:
                self.log.warning(
                    f"Failed to invite menubot {menubot_mxid} "
                    f"to room {self.room_id} attempt {attempt}: {e}"
                )

            await asyncio.sleep(2)

    async def remove_menubot(self, reason):
        """It removes the current menubot from the room"""
        current_menubot: User = await self.get_current_menubot()
        if current_menubot:
            await self.remove_member(current_menubot.mxid, reason=reason)

    async def creator_displayname(self) -> str | None:
        """It returns the display name of the creator of the portal

        Returns
        -------
            The displayname of the creator of the question.

        """
        return await self.main_intent.get_displayname(self.creator)

    def creator_identifier(self) -> str | None:
        """The function takes a creator mxid and returns the his identifier

        Returns
        -------
            The creator's identifier.

        """
        creator_identifier = re.findall(r"\d+", self.creator)
        if not creator_identifier:
            return

        return creator_identifier[0]

    async def send_create_portal_event(self):
        customer = {
            "mxid": self.creator,
            "account_id": self.creator_identifier(),
            "name": await self.creator_displayname(),
            "username": None,
        }
        create_event = CreateEvent(
            type=ACDEventsType.PORTAL,
            event=ACDPortalEvents.Create,
            state=PortalState.INIT,
            prev_state=None,
            sender=self.creator,
            room_id=self.room_id,
            acd=self.main_intent.mxid,
            customer=customer,
            bridge=self.bridge,
        )

        await create_event.send()

    @classmethod
    async def is_portal(cls, room_id: RoomID) -> bool:
        """It checks if the room is a portal by checking if the creator of the room is a
        user with a user ID that starts with the user prefix of any of the bridges

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to check.

        Returns
        -------
            A boolean value.

        """
        try:
            response = await cls.az.intent.api.request(
                method=Method.GET, path=SynapseAdminPath.v1.rooms[room_id]
            )
        except Exception as e:
            cls.log.exception(e)
            return False

        creator: UserID = response.get("creator", "")

        if not creator:
            return False

        is_customer_guest = re.search(cls.config[f"acd.username_regex_guest"], creator)

        if is_customer_guest:
            return True

        bridges = cls.config["bridges"]

        for bridge in bridges:
            user_prefix = cls.config[f"bridges.{bridge}.user_prefix"]
            if creator.startswith(f"@{user_prefix}"):
                return True

        return False

    @classmethod
    async def get_by_room_id(
        cls,
        room_id: RoomID,
        *,
        create: bool = True,
        fk_puppet: int = None,
        intent: IntentAPI = None,
        bridge: str = None,
    ) -> Portal | None:
        try:
            portal = cls.by_room_id[room_id]
            if intent:
                portal.main_intent = intent

            if bridge:
                portal.bridge = bridge
            return portal
        except KeyError:
            pass

        portal = cast(cls, await super().get_by_room_id(room_id))
        if portal is not None:
            if fk_puppet:
                portal.fk_puppet = fk_puppet

            portal.bridge = bridge

            await portal._add_to_cache()
            await portal.post_init()

            if intent:
                portal.main_intent = intent

            return portal

        if create:
            portal = cls(room_id)

            if fk_puppet:
                portal.fk_puppet = fk_puppet

            await portal.insert()
            portal = cast(cls, await super().get_by_room_id(room_id))
            portal.bridge = bridge
            await portal._add_to_cache()
            await portal.post_init()

            if intent:
                portal.main_intent = intent

            return portal

    @property
    def is_locked(self) -> bool:
        return self.room_id in self.LOCKED_PORTALS
