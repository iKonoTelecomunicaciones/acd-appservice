from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Dict, Tuple

from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import IntentAPI
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config
from .db.portal import Portal


class RoomManager:
    log: TraceLogger = logging.getLogger("acd.room_manager")
    ROOMS: dict[RoomID, Dict] = {}

    # Listado de salas  en la DB
    by_room_id: dict[RoomID, Portal] = {}

    # list of room_ids to know if distribution process is taking place
    LOCKED_ROOMS = set()

    # rooms that are in offline agent menu
    offline_menu = set()

    # blacklist of rooms
    blacklist_rooms = set()

    def __init__(
        self,
        puppet_pk: int,
        control_room_id: RoomID,
        config: Config,
        bridge: str,
        intent: IntentAPI = None,
    ) -> None:
        self.config = config
        if not intent:
            return
        self.intent = intent
        self.log = self.log.getChild(self.intent.mxid or None)
        self.puppet_pk = puppet_pk
        self.control_room_id = control_room_id
        self.bridge = bridge

    @classmethod
    def _add_to_cache(cls, room_id, room: Portal) -> None:
        cls.by_room_id[room_id] = room

    async def is_guest_room(self, room_id: RoomID) -> bool:
        """If the room is a guest room, return True.
        If not,
        check if any of the room members have a username that matches the regex in the config.
        If so, return True. Otherwise, return False

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to check.

        Returns
        -------
            A boolean value.

        """

        try:
            room = self.ROOMS[room_id]
            is_guest_room = room.get("is_guest_room")
            # Para que ingrese aun si is_guest_room es False
            if is_guest_room is not None:
                return is_guest_room
        except KeyError:
            pass

        members = await self.intent.get_joined_members(room_id=room_id)

        for member in members:
            username_regex = self.config["acd.username_regex_guest"]
            guest_prefix = re.search(username_regex, member)

            if guest_prefix:
                self.ROOMS[room_id]["is_guest_room"] = True
                return True

        self.ROOMS[room_id]["is_guest_room"] = False
        return False

    async def is_mx_whatsapp_status_broadcast(self, room_id: RoomID) -> bool:
        """Check if a room is whatsapp_status_broadcast.

        Parameters
        ----------
        room_id: RoomID
            Portal to check.

        Returns
        -------
        bool
            True if is whatsapp_status_broadcast, False otherwise.
        """
        room_name = None
        try:
            room_name = await self.get_room_name(room_id=room_id)
        except Exception as e:
            self.log.exception(e)

        if room_name and room_name == "WhatsApp Status Broadcast":
            return True

        return False

    @classmethod
    def put_in_offline_menu(cls, room_id):
        """It adds the room ID to the offline menu

        Parameters
        ----------
        room_id
            The room ID of the room you want to put in the offline menu.

        """
        cls.offline_menu.add(room_id)

    @classmethod
    def pull_from_offline_menu(cls, room_id):
        """It removes the room_id from the offline_menu set

        Parameters
        ----------
        room_id
            The room ID of the room you want to add to the offline menu.

        """
        cls.offline_menu.discard(room_id)

    @classmethod
    def in_offline_menu(cls, room_id):
        """If the room ID is in the offline menu, return True. Otherwise, return False

        Parameters
        ----------
        room_id
            The room ID of the room you want to add the offline menu to.

        Returns
        -------
            The room_id is being returned.

        """
        return room_id in cls.offline_menu

    @classmethod
    def put_in_blacklist_rooms(cls, room_id):
        """This function adds the room_id to the blacklist_rooms set

        Parameters
        ----------
        room_id
            The room ID of the room you want to blacklist.

        """
        cls.blacklist_rooms.add(room_id)

    @classmethod
    def in_blacklist_rooms(cls, room_id) -> bool:
        """If the room ID is in the blacklist, return True. Otherwise, return False

        Parameters
        ----------
        room_id
            The room ID of the room you want to blacklist.

        Returns
        -------
            The room_id is being returned.

        """
        return room_id in cls.blacklist_rooms

    async def get_room_creator(self, room_id: RoomID) -> str:
        """Given a room, get its creator.

        Parameters
        ----------
        room_id: RoomID
            Portal to check.

        Returns
        -------
        str
            Creator if successful, None otherwise.
        """
        creator = None

        try:
            room = self.ROOMS[room_id]
            return room.get("creator")
        except KeyError:
            pass

        try:
            room_info = await self.get_room_info(room_id=room_id)
            creator = room_info.get("creator")
        except Exception as e:
            self.log.exception(e)

        return creator

    async def send_menubot_command(
        self,
        menubot_id: UserID,
        command: str,
        *args: Tuple,
    ) -> None:
        """It sends a command to the menubot

        Parameters
        ----------
        menubot_id : UserID
            The user ID of the menubot.
        command : str
            The command to send to the menubot.
        args : Tuple
        menubot_id: The ID of the menubot to send the command to.

        """
        if menubot_id:
            prefix = self.config["acd.menubot_command_prefix"]

            cmd = f"{prefix} {command} {' '.join(args)}"

            cmd = cmd.strip()

            self.log.debug(f"Sending command {command} for the menubot [{menubot_id}]")
            await self.intent.send_text(room_id=self.control_room_id, text=cmd)

    async def get_menubot_id(self) -> UserID | None:
        """It gets the ID of the menubot in the control room

        Returns
        -------
            The user_id of the menubot.

        """

        try:
            room = self.ROOMS[self.control_room_id]
            menubot_id = room.get("menubot_id")
            if menubot_id:
                return menubot_id
        except KeyError:
            pass

        await self.get_room_info(room_id=self.control_room_id)
        members = await self.intent.get_joined_members(room_id=self.control_room_id)

        for user_id in members:
            if user_id.startswith(self.config["acd.menubot_prefix"]):
                self.ROOMS[self.control_room_id]["menubot_id"] = user_id
                return user_id

    async def is_group_room(self, room_id: RoomID) -> bool:
        """It checks if a room has more than one user in it, and if it does, it returns True

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to check.

        Returns
        -------
            True if is_group_room, False otherwise.

        """
        try:
            room = self.ROOMS[room_id]
            return room.get("is_group_room")
        except KeyError:
            pass

        members = await self.intent.get_joined_members(room_id=room_id)

        if not members:
            return False

        clients = 0

        for member in members:
            self.log.debug(f"One of the members of this room {room_id} is {member}")
            customer_user_match = re.search(self.config["utils.username_regex"], member)
            if customer_user_match:
                clients += 1

            if clients >= 2:
                self.ROOMS[room_id]["is_group_room"] = True
                self.log.debug(f"This room {room_id} is a group room, return True")
                return True

        self.log.debug(f"This room {room_id} not is a group room, return False")
        self.ROOMS[room_id]["is_group_room"] = False
        return False

    async def get_room_bridge(self, room_id: RoomID) -> str:
        """Given a room, get its bridge.

        Parameters
        ----------
        room_id: RoomID
            Portal to check.

        Returns
        -------
        str
            Bridge if successful, None otherwise.
        """
        try:
            room = self.ROOMS[room_id]
            bridge = room.get("bridge")
            if bridge:
                return bridge
        except KeyError:
            pass

        creator = await self.get_room_creator(room_id=room_id)

        bridges = self.config["bridges"]
        if creator:
            for bridge in bridges:
                user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
                if creator.startswith(f"@{user_prefix}"):
                    self.log.debug(f"The bridge obtained is {bridge}")
                    self.ROOMS[room_id]["bridge"] = bridge
                    return bridge

        if await self.is_guest_room(room_id=room_id):
            self.ROOMS[room_id]["bridge"] = "chatterbox"
            return "chatterbox"

        return None

    async def get_room_name(self, room_id: RoomID) -> str:
        """Given a room, get its name.

        Parameters
        ----------
        room_id: RoomID
            Portal to check.

        Returns
        -------
        str
            Name if successful, None otherwise.
        """

        room_name = None

        try:
            room = self.ROOMS[room_id]
            room_name = room.get("name")
            if room_name:
                return room_name
        except KeyError:
            pass

        try:
            room_info = await self.get_room_info(room_id=room_id)
            room_name = room_info.get("name")
            self.ROOMS[room_id]["name"] = room_name
        except Exception as e:
            self.log.exception(e)
            return

        return room_name

    async def get_room_info(self, room_id: RoomID) -> Dict:
        """Given a room, get its room_info.

        Parameters
        ----------
        room_id: RoomID
            Portal to check.

        Returns
        -------
        Dict
            room_info if successful, None otherwise.
        """
        try:
            api = self.intent.bot.api if self.intent.bot else self.intent.api
            room_info = await api.request(
                method=Method.GET, path=SynapseAdminPath.v1.rooms[room_id]
            )
            self.ROOMS[room_id] = room_info
        except Exception as e:
            self.log.exception(e)
            return

        return room_info
