from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List, Tuple

from mautrix.api import Method
from mautrix.appservice import IntentAPI
from mautrix.errors.base import IntentError
from mautrix.types import (
    EventType,
    JoinRule,
    PresenceEventContent,
    RoomDirectoryVisibility,
    RoomID,
    UserID,
)
from mautrix.util.logging import TraceLogger

from .config import Config
from .db import Room


class RoomManager:
    config: Config
    log: TraceLogger = logging.getLogger("mau.room_manager")
    ROOMS: dict[RoomID, Dict] = {}
    # list of room_ids to know if distribution process is taking place
    LOCKED_ROOMS = set()

    def __init__(self, config: Config) -> None:
        self.config = config

    async def initialize_room(self, room_id: RoomID, intent: IntentAPI) -> bool:
        """Initializing a room.

        Given a room and an IntentAPI, a room is configured, the room must be a room of a client.
        The acd is given permissions of 100, and a task is run that runs 10 times,
        it tries to add the room to the directory, that the room has a public join,
        and the history of the room is made public.

        Parameters
        ----------
        room_id: RoomID
            Room to initialize.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """

        if not await self.is_customer_room(room_id=room_id, intent=intent):
            return False

        bridge = await self.get_room_bridge(room_id=room_id, intent=intent)

        if not bridge:
            return False

        if bridge.startswith("mautrix"):
            await self.send_cmd_set_pl(
                room_id=room_id,
                intent=intent,
                bridge=bridge,
                user_id=intent.mxid,
                power_level=100,
            )
            await self.send_cmd_set_relay(room_id=room_id, intent=intent, bridge=bridge)

        await asyncio.create_task(self.initial_room_setup(room_id=room_id, intent=intent))

        if not await self.put_name_customer_room(room_id=room_id, intent=intent):
            return False

        self.log.info(f"Room {room_id} initialization is complete")
        return True

    async def initial_room_setup(self, room_id: RoomID, intent: IntentAPI):
        """Initializing a room visibility.

        it tries to add the room to the directory, that the room has a public join,
        and the history of the room is made public.

        Parameters
        ----------
        room_id: RoomID
            Room to initialize.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        """

        for attempt in range(0, 10):
            self.log.debug(f"Attempt # {attempt} of room configuration")
            try:
                await intent.set_room_directory_visibility(
                    room_id=room_id, visibility=RoomDirectoryVisibility.PUBLIC
                )
            except Exception as e:
                self.log.error(e)

            try:
                await intent.set_join_rule(room_id=room_id, join_rule=JoinRule.PUBLIC)
            except Exception as e:
                self.log.error(e)

            try:
                await intent.send_state_event(
                    room_id=room_id,
                    event_type=EventType.ROOM_HISTORY_VISIBILITY,
                    content={"history_visibility": "world_readable"},
                )
            except Exception as e:
                self.log.error(e)

            await asyncio.sleep(1)

    async def put_name_customer_room(self, room_id: RoomID, intent: IntentAPI) -> bool:
        """Name a customer's room.

        Given a room and a matrix client, name the room correctly if needed.

        Parameters
        ----------
        room_id: RoomID
            Room to initialize.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """

        if (
            not await self.is_customer_room(room_id=room_id, intent=intent)
            and not self.config["acd.force_name_change"]
        ):
            return False

        creator = await self.get_room_creator(room_id=room_id, intent=intent)

        new_room_name = await self.get_update_name(creator=creator, intent=intent)
        if not new_room_name:
            return False

        await intent.set_room_name(room_id, new_room_name)
        return True

    async def create_room_name(self, user_id: UserID, intent: IntentAPI) -> str:
        """Given a customer's mxid, pull the phone number and concatenate it to the name.

        Parameters
        ----------
        user_id: UserID
            User to get new name.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        str
            new_name if successful, None otherwise.
        """

        phone_match = re.findall(r"\d+", user_id)
        if phone_match:
            self.log.debug(f"Formatting phone number {phone_match[0]}")

            customer_displayname = await intent.get_displayname(user_id)
            if customer_displayname:
                room_name = f"{customer_displayname}({phone_match[0]})"
            else:
                room_name = f"({phone_match[0]})"

            return room_name

        return None

    async def send_cmd_set_relay(self, room_id: RoomID, intent: IntentAPI, bridge: str) -> None:
        """Given a room, send the command set-relay.

        Parameters
        ----------
        room_id: RoomID
            Room to send command.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        """
        bridge = self.config[f"bridges.{bridge}"]

        cmd = f"{bridge['prefix']} {bridge['set_relay']}"
        try:
            await intent.send_text(room_id=room_id, text=cmd)
        except ValueError as e:
            self.log.error(e)

        self.log.info(f"The command {cmd} has been sent to room {room_id}")

    async def send_cmd_set_pl(
        self,
        room_id: RoomID,
        intent: IntentAPI,
        bridge: str,
        user_id: str,
        power_level: int,
    ) -> None:
        """Given a room, send the command set-pl.

        Parameters
        ----------
        room_id: RoomID
            Room to send command.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        """
        bridge = self.config[f"bridges.{bridge}"]
        cmd = (
            f"{bridge['prefix']} "
            f"{bridge['set_permissions'].format(mxid=user_id, power_level=power_level)}"
        )

        try:
            await intent.send_text(room_id=room_id, text=cmd)
        except ValueError as e:
            self.log.error(e)

        self.log.info(f"The command {cmd} has been sent to room {room_id}")

    # HAY 3 TIPOS DE SALAS
    # SALAS DE GRUPOS (Cuando hay mas de un cliente en la sala)
    # SALAS DE CLIENTE (Cuando cuando el creador de la sala es un cliente)
    # OTRO TIPO DE SALA (Cuando es la sala de control, sala de agentes o de colas)

    async def is_customer_room(self, room_id: RoomID, intent: IntentAPI) -> bool:
        """Given a room, verify that it is a customer's room.

        Parameters
        ----------
        room_id: RoomID
            Room to check.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        bool
            True if it is a customer's room, False otherwise.
        """
        creator = await self.get_room_creator(room_id=room_id, intent=intent)

        try:
            room = self.ROOMS[room_id]
            is_customer_room = room.get("is_customer_room")
            if is_customer_room:
                return is_customer_room
        except KeyError:
            pass

        bridges = self.config["bridges"]
        if creator:
            for bridge in bridges:
                user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
                if creator.startswith(f"@{user_prefix}"):
                    self.ROOMS[room_id]["is_customer_room"] = True
                    return True
        return False

    async def is_mx_whatsapp_status_broadcast(self, room_id: RoomID, intent: IntentAPI) -> bool:
        """Check if a room is whatsapp_status_broadcast.

        Parameters
        ----------
        room_id: RoomID
            Room to check.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        bool
            True if is whatsapp_status_broadcast, False otherwise.
        """
        room_name = None
        try:
            room_name = await self.get_room_name(room_id=room_id, intent=intent)
        except Exception as e:
            self.log.error(e)

        if room_name and room_name == "WhatsApp Status Broadcast":
            return True

        return False

    @classmethod
    def lock_room(cls, room_id: RoomID) -> None:
        """Lock the room."""
        cls.log.debug(f"LOCKING ROOM {room_id}...")
        cls.LOCKED_ROOMS.add(room_id)

    @classmethod
    def unlock_room(cls, room_id: RoomID) -> None:
        """Unlock the room."""
        cls.log.debug(f"UNLOCKING ROOM {room_id}...")
        cls.LOCKED_ROOMS.discard(room_id)

    @classmethod
    def is_room_locked(cls, room_id: RoomID) -> bool:
        """Check if room is locked."""
        return room_id in cls.LOCKED_ROOMS

    @classmethod
    def get_future_key(cls, room_id: RoomID, agent_id: UserID) -> str:
        """Return the key for the dict of futures for a specific agent."""
        return f"{room_id}-{agent_id}"

    async def get_update_name(self, creator: UserID, intent: IntentAPI) -> str:
        """Given a customer's mxid, pull the phone number and concatenate it to the name
        and delete the postfix_template (WA).

        Parameters
        ----------
        creator: UserID
            User to get new name.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        str
            new_name if successful, None otherwise.
        """

        new_room_name = None
        bridges = self.config["bridges"]
        for bridge in bridges:
            user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
            if creator.startswith(f"@{user_prefix}"):
                new_room_name = await self.create_room_name(user_id=creator, intent=intent)
                if new_room_name:
                    postfix_template = self.config[f"bridges.{bridge}.postfix_template"]
                    new_room_name = new_room_name.replace(postfix_template, "")
                break

        return new_room_name

    async def get_user_presence(self, user_id: UserID, intent: IntentAPI) -> PresenceEventContent:
        """Get user presence status."""
        self.log.debug(f"Checking presence for....... [{user_id}]")
        response = None
        try:
            response = await intent.get_presence(user_id=user_id)
        except IntentError as e:
            self.log.error(e)

        return response

    async def is_in_mobile_device(self, user_id: UserID, intent: IntentAPI) -> bool:
        devices = await self.get_user_devices(user_id=user_id, intent=intent)
        device_name_regex = self.config["acd.device_name_regex"]
        if devices:
            for device in devices["devices"]:
                if device.get("display_name") and re.search(
                    device_name_regex, device["display_name"]
                ):
                    return True

    async def get_user_devices(self, user_id: UserID, intent: IntentAPI) -> Dict[str, List[Dict]]:
        """Get devices where agent have sessions"""
        response: Dict[str, List[Dict]] = None
        try:
            response = await intent.api.request(
                method=Method.GET, path=f"/_synapse/admin/v2/users/{user_id}/devices"
            )

        except IntentError as e:
            self.log.error(e)

        return response

    async def get_room_creator(self, room_id: RoomID, intent: IntentAPI) -> str:
        """Given a room, get its creator.

        Parameters
        ----------
        room_id: RoomID
            Room to check.
        intent: IntentAPI
            Matrix client.

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
            room_info = await self.get_room_info(room_id=room_id, intent=intent)
            creator = room_info.get("creator")
        except Exception as e:
            self.log.error(e)

        return creator

    async def kick_menubot(self, room_id: RoomID, reason: str, intent: IntentAPI) -> None:
        """Kick menubot from some room."""
        menubot_id = await self.get_menubot_id(room_id=room_id)
        if menubot_id:
            self.log.debug("Kicking the menubot [{menubot_id}]")
            await self.send_menubot_command(
                menubot_id=menubot_id, command="cancel_task", args=(room_id)
            )
            try:
                await intent.kick_user(room_id=room_id, user_id=menubot_id, reason=reason)
            except IntentError as e:
                self.log.error(e)
            self.log.debug(f"User [{menubot_id}] KICKED from room [{room_id}]")

    async def send_menubot_command(
        self, menubot_id: UserID, command: str, intent: IntentAPI, *args: Tuple
    ) -> None:
        """Send a command to menubot."""
        if menubot_id:
            if self.config["acd.menubot"]:
                prefix = self.config["acd.menubot.command_prefix"]
            else:
                prefix = self.config[f"acd.menubots.[{menubot_id}].command_prefix"]

            cmd = f"{prefix} {command} {' '.join(args)}"

            cmd = cmd.strip()

            self.log.debug(f"Sending command {command} for the menubot [{menubot_id}]")
            await intent.send_text(room_id=self.control_room_id, text=cmd)

    async def get_menubot_id(
        self, intent: IntentAPI, room_id: RoomID = None, user_id: UserID = None
    ) -> UserID:
        """Get menubot_id by room_id or user_id or user_prefix"""

        menubot_id: UserID = None

        if self.config["acd.menubot"]:
            menubot_id = self.config["acd.menubot.user_id"]
            return menubot_id

        if room_id:
            members = await intent.get_joined_members(room_id=room_id)
            if members:
                for user_id in members:
                    if user_id in self.config["acd.menubots"]:
                        menubot_id = user_id
                        break

        if user_id:
            username_regex = self.config["utils.username_regex"]
            user_prefix = re.search(username_regex, user_id).group("user_prefix")
            menubots: Dict[UserID, Dict] = self.config["acd.menubots"]
            for menubot in menubots:
                if user_prefix == self.config[f"acd.menubots{menubot}.user_prefix"]:
                    menubot_id = menubot
                    break

        return menubot_id

    async def get_room_bridge(self, room_id: RoomID, intent: IntentAPI) -> str:
        """Given a room, get its bridge.

        Parameters
        ----------
        room_id: RoomID
            Room to check.
        intent: IntentAPI
            Matrix client.

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

        creator = await self.get_room_creator(room_id=room_id, intent=intent)

        bridges = self.config["bridges"]
        if creator:
            for bridge in bridges:
                user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
                if creator.startswith(f"@{user_prefix}"):
                    self.log.debug(f"The bridge obtained is {bridge}")
                    self.ROOMS[room_id]["bridge"] = bridge
                    return bridge
        return None

    async def get_room_name(self, room_id: RoomID, intent: IntentAPI) -> str:
        """Given a room, get its name.

        Parameters
        ----------
        room_id: RoomID
            Room to check.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        str
            Name if successful, None otherwise.
        """
        room_name = None
        try:
            room_info = await self.get_room_info(room_id=room_id, intent=intent)
            room_name = room_info.get("name")
        except Exception as e:
            self.log.error(e)

        return room_name

    async def get_room_info(self, room_id: RoomID, intent: IntentAPI) -> Dict:
        """Given a room, get its room_info.

        Parameters
        ----------
        room_id: RoomID
            Room to check.
        intent: IntentAPI
            Matrix client.

        Returns
        -------
        Dict
            room_info if successful, None otherwise.
        """
        try:
            room_info = await intent.api.request(
                method=Method.GET, path=f"/_synapse/admin/v1/rooms/{room_id}"
            )
            self.ROOMS[room_id] = room_info
        except Exception as e:
            self.log.error(e)

        return room_info

    @classmethod
    async def set_user_selected_menu(cls, room_id: RoomID, selected_option: str) -> bool:  # ok
        """Sets the customer's menu selection.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        room = await Room.get_by_room_id(room_id)
        if room:
            return await cls.update_room_in_db(room_id=room_id, selected_option=selected_option)
        else:
            return await cls.insert_room_in_db(room_id=room_id, selected_option=selected_option)

    @classmethod
    async def save_pending_room(cls, room_id: RoomID, selected_option: str = None) -> bool:  # ok
        """Save or update a pending room.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        room = await Room.get_by_room_id(room_id)
        if room:
            return await cls.update_room_in_db(
                room_id=room_id, selected_option=selected_option, is_pending_room=True
            )
        else:
            return await cls.insert_room_in_db(
                room_id=room_id, selected_option=selected_option, is_pending_room=True
            )

    @classmethod
    async def remove_pending_room(cls, room_id: RoomID) -> bool:  # ok
        """Update is_pendid_room = False.

        Parameters
        ----------
        room_id: RoomID
            Room to remove data.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        return await Room.update_pending_room_by_room_id(room_id, False)

    @classmethod
    async def insert_room_in_db(
        cls, room_id: RoomID, selected_option: str, is_pending_room: bool = False
    ) -> bool:  # ok
        """Inserts a room in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer.
        is_pending_room: bool
            If it is a pending room.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_by_room_id(room_id)
            if room:
                return False
            else:
                await Room.insert(room_id, selected_option, is_pending_room)
        except Exception as e:
            cls.log.error(e)
            return False

        return True

    @classmethod
    async def update_room_in_db(
        cls, room_id: RoomID, selected_option: str, is_pending_room: bool = False
    ) -> bool:  # ok
        """Updates a room in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer.
        is_pending_room: bool
            If it is a pending room.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_by_room_id(room_id)
            if room:
                await Room.update_by_room_id(room_id, selected_option, is_pending_room)
            else:
                cls.log.error(f"The room {room_id} does not exist so it will not be updated")
        except Exception as e:
            cls.log.error(e)
            return False

        return True

    @classmethod
    async def get_pending_rooms(cls)->List[RoomID]:
        try:
            rooms = await Room.get_pending_rooms()
        except Exception as e:
            cls.log.error(e)

        return [room.room_id for room in rooms]

    @classmethod
    async def get_campaign_of_pending_room(cls, room_id: RoomID)-> RoomID:
        try:
            return await Room.get_user_selected_menu(room_id=room_id)
        except Exception as e:
            cls.log.error(e)


