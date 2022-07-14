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

from acd_appservice import puppet as pu

from .config import Config
from .db import Room


class RoomManager:
    config: Config
    intent: IntentAPI

    log: TraceLogger = logging.getLogger("acd.room_manager")
    ROOMS: dict[RoomID, Dict] = {}

    # Listado de salas  en la DB
    by_room_id: dict[RoomID, Room] = {}

    CONTROL_ROOMS: List[RoomID] = []

    # list of room_ids to know if distribution process is taking place
    LOCKED_ROOMS = set()

    # rooms that are in offline agent menu
    offline_menu = set()

    def __init__(self, config: Config, intent: IntentAPI = None) -> None:
        self.config = config
        self.intent = intent
        self.log = self.log.getChild(self.intent.mxid)

    @classmethod
    def _add_to_cache(cls, room_id, room: Room) -> None:
        cls.by_room_id[room_id] = room

    async def initialize_room(self, room_id: RoomID) -> bool:
        """Initializing a room.

        Given a room and an IntentAPI, a room is configured, the room must be a room of a client.
        The acd is given permissions of 100, and a task is run that runs 10 times,
        it tries to add the room to the directory, that the room has a public join,
        and the history of the room is made public.

        Parameters
        ----------
        room_id: RoomID
            Room to initialize.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """

        if not await self.is_customer_room(room_id=room_id):
            return False

        bridge = await self.get_room_bridge(room_id=room_id)

        if not bridge:
            return False

        if bridge.startswith("mautrix"):
            await self.send_cmd_set_pl(
                room_id=room_id,
                bridge=bridge,
                user_id=self.intent.mxid,
                power_level=100,
            )
            await self.send_cmd_set_relay(room_id=room_id, bridge=bridge)

        await asyncio.create_task(self.initial_room_setup(room_id=room_id))

        self.log.info(f"Room {room_id} initialization is complete")
        return True

    async def initial_room_setup(self, room_id: RoomID):
        """Initializing a room visibility.

        it tries to add the room to the directory, that the room has a public join,
        and the history of the room is made public.

        Parameters
        ----------
        room_id: RoomID
            Room to initialize.

        Returns
        -------
        """

        for attempt in range(0, 10):
            self.log.debug(f"Attempt # {attempt} of room configuration")
            try:
                await self.intent.set_room_directory_visibility(
                    room_id=room_id, visibility=RoomDirectoryVisibility.PUBLIC
                )
                await self.intent.set_join_rule(room_id=room_id, join_rule=JoinRule.PUBLIC)
                await self.intent.send_state_event(
                    room_id=room_id,
                    event_type=EventType.ROOM_HISTORY_VISIBILITY,
                    content={"history_visibility": "world_readable"},
                )
                break
            except Exception as e:
                self.log.warning(e)

            await asyncio.sleep(1)

    async def put_name_customer_room(self, room_id: RoomID, old_name: str) -> bool:
        """Name a customer's room.

        Given a room and a matrix client, name the room correctly if needed.

        Parameters
        ----------
        room_id: RoomID
            Room to initialize.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        new_room_name = None
        if await self.is_customer_room(room_id=room_id):
            if self.config["acd.keep_room_name"]:

                new_room_name = old_name
            else:

                creator = await self.get_room_creator(room_id=room_id)

                new_room_name = await self.get_update_name(creator=creator)

            if new_room_name:
                await self.intent.set_room_name(room_id, new_room_name)
                return True

        return False

    async def create_room_name(self, user_id: UserID) -> str:
        """Given a customer's mxid, pull the phone number and concatenate it to the name.

        Parameters
        ----------
        user_id: UserID
            User to get new name.

        Returns
        -------
        str
            new_name if successful, None otherwise.
        """

        phone_match = re.findall(r"\d+", user_id)
        if phone_match:
            self.log.debug(f"Formatting phone number {phone_match[0]}")

            customer_displayname = await self.intent.get_displayname(user_id)
            if customer_displayname:
                room_name = f"{customer_displayname.strip()} ({phone_match[0].strip()})"
            else:
                room_name = f"({phone_match[0].strip()})"
            return room_name

        return None

    async def send_cmd_set_relay(self, room_id: RoomID, bridge: str) -> None:
        """Given a room, send the command set-relay.

        Parameters
        ----------
        room_id: RoomID
            Room to send command.

        Returns
        -------
        """
        bridge = self.config[f"bridges.{bridge}"]

        cmd = f"{bridge['prefix']} {bridge['set_relay']}"
        try:
            await self.intent.send_text(room_id=room_id, text=cmd)
        except ValueError as e:
            self.log.exception(e)

        self.log.info(f"The command {cmd} has been sent to room {room_id}")

    async def send_cmd_set_pl(
        self,
        room_id: RoomID,
        bridge: str,
        user_id: str,
        power_level: int,
    ) -> None:
        """Given a room, send the command set-pl.

        Parameters
        ----------
        room_id: RoomID
            Room to send command.

        Returns
        -------
        """
        bridge = self.config[f"bridges.{bridge}"]
        cmd = (
            f"{bridge['prefix']} "
            f"{bridge['set_permissions'].format(mxid=user_id, power_level=power_level)}"
        )

        try:
            await self.intent.send_text(room_id=room_id, text=cmd)
        except ValueError as e:
            self.log.exception(e)

        self.log.info(f"The command {cmd} has been sent to room {room_id}")

    # HAY 3 TIPOS DE SALAS
    # SALAS DE GRUPOS (Cuando hay mas de un cliente en la sala)
    # SALAS DE CLIENTE (Cuando cuando el creador de la sala es un cliente)
    # OTRO TIPO DE SALA (Cuando es la sala de control, sala de agentes o de colas)

    async def is_customer_room(self, room_id: RoomID) -> bool:
        """Given a room, verify that it is a customer's room.

        Parameters
        ----------
        room_id: RoomID
            Room to check.

        Returns
        -------
        bool
            True if it is a customer's room, False otherwise.
        """
        creator = await self.get_room_creator(room_id=room_id)

        try:
            room = self.ROOMS[room_id]
            is_customer_room = room.get("is_customer_room")
            # Para que ingrese aun si is_customer_room es False
            if is_customer_room is not None:
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

        self.ROOMS[room_id]["is_customer_room"] = False
        return False

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
            Room to check.

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
    def lock_room(cls, room_id: RoomID, transfer: bool = False) -> None:
        """This function locks a room by adding it to the `LOCKED_ROOMS` set

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to lock.
        transfer : bool, optional
            If True, the room will be locked for transfer.

        """
        if transfer:
            cls.log.debug(f"[TRANSFER] - LOCKING ROOM {room_id}...")
            room_id = cls.get_room_transfer_key(room_id=room_id)
        else:
            cls.log.debug(f"LOCKING ROOM {room_id}...")
        cls.LOCKED_ROOMS.add(room_id)

    @classmethod
    def unlock_room(cls, room_id: RoomID, transfer: bool = False) -> None:
        """Unlock the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to unlock.
        transfer : bool, optional
            bool = False

        """
        if transfer:
            cls.log.debug(f"[TRANSFER] - UNLOCKING ROOM {room_id}...")
            room_id = cls.get_room_transfer_key(room_id=room_id)
        else:
            cls.log.debug(f"UNLOCKING ROOM {room_id}...")

        cls.LOCKED_ROOMS.discard(room_id)

    @classmethod
    def is_room_locked(cls, room_id: RoomID, transfer: bool = False) -> bool:
        """ "If the room is locked, return True, otherwise return False."

        The first line of the function is a docstring.
        This is a string that describes what the function does.
        It's not required, but it's good practice to include one

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to lock.
        transfer : bool, optional
            If True, the room_id will be converted to a transfer key.

        Returns
        -------
            A boolean value.

        """
        if transfer:
            room_id = cls.get_room_transfer_key(room_id=room_id)
        return room_id in cls.LOCKED_ROOMS

    @classmethod
    def get_room_transfer_key(cls, room_id: RoomID):
        """`get_room_transfer_key` returns a string that is used as a key
        for a Redis hash

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room to transfer.

        Returns
        -------
            A string

        """
        return f"transfer-{room_id}"

    @classmethod
    def get_future_key(cls, room_id: RoomID, agent_id: UserID, transfer: bool = False) -> str:
        """It returns a string that is used as a key to store the future in the cache

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to transfer the user to.
        agent_id : UserID
            The user ID of the agent who is being transferred to.
        transfer : bool, optional
            If True, the key will be for a transfer. If False, the key will be for a future.

        Returns
        -------
            A string

        """
        return f"trasnfer-{room_id}-{agent_id}" if transfer else f"{room_id}-{agent_id}"

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

    async def get_update_name(self, creator: UserID) -> str:
        """Given a customer's mxid, pull the phone number and concatenate it to the name
        and delete the postfix_template (WA).

        Parameters
        ----------
        creator: UserID
            User to get new name.

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
                new_room_name = await self.create_room_name(user_id=creator)
                if new_room_name:
                    postfix_template = self.config[f"bridges.{bridge}.postfix_template"]
                    new_room_name = new_room_name.replace(f" {postfix_template}", "")
                break

        return new_room_name

    async def get_user_presence(self, user_id: UserID) -> PresenceEventContent:
        """This function will return the presence of a user

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to check the presence of.

        Returns
        -------
            PresenceEventContent

        """
        self.log.debug(f"Checking presence for....... [{user_id}]")
        response = None
        try:
            response = await self.intent.get_presence(user_id=user_id)
            self.log.debug(f"Presence for....... [{user_id}] is [{response.presence}]")
        except IntentError as e:
            self.log.exception(e)

        return response

    async def is_in_mobile_device(self, user_id: UserID) -> bool:
        """It checks if the user is in a mobile device

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to check.

        Returns
        -------
            A boolean value.

        """
        devices = await self.get_user_devices(user_id=user_id, intent=self.intent)
        device_name_regex = self.config["acd.device_name_regex"]
        if devices:
            for device in devices["devices"]:
                if device.get("display_name") and re.search(
                    device_name_regex, device["display_name"]
                ):
                    return True

    async def get_user_devices(self, user_id: UserID) -> Dict[str, List[Dict]]:
        """It gets a list of devices for a given user

        Parameters
        ----------
        user_id : UserID
            The user ID of the user whose devices you want to get.

        Returns
        -------
            A dictionary of devices and their information.

        """
        response: Dict[str, List[Dict]] = None
        try:
            api = self.intent.bot.api if self.intent.bot else self.intent.api
            response = await api.request(
                method=Method.GET, path=f"/_synapse/admin/v2/users/{user_id}/devices"
            )

        except IntentError as e:
            self.log.exception(e)

        return response

    async def get_room_creator(self, room_id: RoomID) -> str:
        """Given a room, get its creator.

        Parameters
        ----------
        room_id: RoomID
            Room to check.

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

    async def kick_menubot(self, room_id: RoomID, reason: str, control_room_id: RoomID) -> None:
        """It kicks the menubot out of the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room where the menubot is.
        reason : str
            str
        control_room_id : RoomID
            The room ID of the room where the menubot is running.

        """
        menubot_id = await self.get_menubot_id(room_id=room_id)
        if menubot_id:
            await self.send_menubot_command(menubot_id, "cancel_task", control_room_id, room_id)
            try:
                self.log.debug(f"Kicking the menubot [{menubot_id}]")
                await self.intent.kick_user(room_id=room_id, user_id=menubot_id, reason=reason)
            except Exception as e:
                self.log.warning(
                    str(e) + f":: the user who was going to be kicked out: {menubot_id}"
                )

            self.log.debug(f"User [{menubot_id}] KICKED from room [{room_id}]")

    async def send_menubot_command(
        self,
        menubot_id: UserID,
        command: str,
        control_room_id: RoomID,
        *args: Tuple,
    ) -> None:
        """It sends a command to the menubot

        Parameters
        ----------
        menubot_id : UserID
            The user ID of the menubot.
        command : str
            The command to send to the menubot.
        control_room_id : RoomID
            The room ID of the room where the menubot is running.
        args : Tuple
        menubot_id: The ID of the menubot to send the command to.

        """
        if menubot_id:
            if self.config["acd.menubot"]:
                prefix = self.config["acd.menubot.command_prefix"]
            else:
                prefix = self.config[f"acd.menubots.[{menubot_id}].command_prefix"]

            cmd = f"{prefix} {command} {' '.join(args)}"

            cmd = cmd.strip()

            self.log.debug(f"Sending command {command} for the menubot [{menubot_id}]")
            await self.intent.send_text(room_id=control_room_id, text=cmd)

    async def get_menubot_id(self, room_id: RoomID = None, user_id: UserID = None) -> UserID:
        """It returns the ID of the menubot that is assigned to a given room or user

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room where the user is.
        user_id : UserID
            The user ID of the user who is trying to access the menu.

        Returns
        -------
            The menubot_id

        """

        menubot_id: UserID = None

        if self.config["acd.menubot.active"]:
            menubot_id = self.config["acd.menubot.user_id"]
            return menubot_id

        elif room_id:
            members = await self.intent.get_joined_members(room_id=room_id)
            if members:
                for user_id in members:
                    if user_id in self.config["acd.menubots"]:
                        menubot_id = user_id
                        break

        elif user_id:
            username_regex = self.config["utils.username_regex"]
            user_prefix = re.search(username_regex, user_id)
            menubots: Dict[UserID, Dict] = self.config["acd.menubots"]
            if user_prefix:
                # Llega aquí si es un cliente
                user_prefix = user_prefix.group("user_prefix")
                for menubot in menubots:
                    if user_prefix == self.config[f"acd.menubots.{menubot}.user_prefix"]:
                        menubot_id = menubot
                        break
            else:
                username_regex_guest = self.config[f"acd.username_regex_guest"]
                user_prefix_guest = re.search(username_regex_guest, user_id)
                if user_prefix_guest:
                    # Solo llega aquí si es un usuario tipo guest
                    for menubot in menubots:
                        if self.config[f"acd.menubots.{menubot}.is_guest"]:
                            menubot_id = menubot
                            break

        return menubot_id

    async def has_menubot(self, room_id: RoomID) -> bool:
        """If the room has a menubot, return True. Otherwise, return False

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to check.

        Returns
        -------
            A boolean value.

        """
        members = await self.intent.get_joined_members(room_id=room_id)

        if not members:
            return False

        for member in members:
            if self.config["acd.menubot"]:
                if member == self.config["acd.menubot.user_id"]:
                    return True

            if self.config["acd.menubots"]:
                if member in self.config["acd.menubots"]:
                    return True

        return False

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

    async def invite_menu_bot(self, room_id: RoomID, menubot_id: UserID) -> None:
        """It tries to invite the menubot to the room, and if it fails, it waits a couple of seconds and tries again

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to invite the menubot to.
        menubot_id : UserID
            The user ID of the menubot.

        """
        for attempt in range(10):
            self.log.debug(f"Inviting menubot {menubot_id} to {room_id}...")
            try:
                await self.intent.invite_user(room_id=room_id, user_id=menubot_id)
                self.log.debug("Menubot invite OK")
                break
            except Exception as e:
                self.log.warning(f"Failed to invite menubot attempt {attempt}: {e}")

            await asyncio.sleep(2)

    async def invite_supervisors(self, room_id: RoomID) -> None:
        """It tries to invite the menubot to the room, and if it fails, it waits a couple of seconds and tries again

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to invite the menubot to.

        """

        invitees = self.config["acd.supervisors_to_invite.invitees"]
        for user_id in invitees:
            for attempt in range(10):
                self.log.debug(f"Inviting supervisor {user_id} to {room_id}...")
                try:
                    await self.intent.invite_user(room_id=room_id, user_id=user_id)
                    self.log.debug("Supervisor invite OK")
                    break
                except Exception as e:
                    self.log.warning(f"Failed to invite supervisor attempt {attempt}: {e}")

                await asyncio.sleep(2)

    async def get_room_bridge(self, room_id: RoomID) -> str:
        """Given a room, get its bridge.

        Parameters
        ----------
        room_id: RoomID
            Room to check.

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
            self.ROOMS[room_id]["bridge"] = "plugin"
            return "plugin"

        return None

    async def get_room_name(self, room_id: RoomID) -> str:
        """Given a room, get its name.

        Parameters
        ----------
        room_id: RoomID
            Room to check.

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
            Room to check.

        Returns
        -------
        Dict
            room_info if successful, None otherwise.
        """
        try:
            api = self.intent.bot.api if self.intent.bot else self.intent.api
            room_info = await api.request(
                method=Method.GET, path=f"/_synapse/admin/v1/rooms/{room_id}"
            )
            self.ROOMS[room_id] = room_info
        except Exception as e:
            self.log.exception(e)
            return

        return room_info

    # Seccion DB
    @classmethod
    async def save_pending_room(
        cls, room_id: RoomID, puppet_mxid: str, selected_option: str = None
    ) -> bool:
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
        room = await Room.get_pending_room_by_room_id(room_id)
        if room:
            return await cls.update_pending_room_in_db(
                room_id=room_id, selected_option=selected_option, puppet_mxid=puppet_mxid
            )
        else:
            return await cls.insert_pending_room_in_db(
                room_id=room_id, selected_option=selected_option, puppet_mxid=puppet_mxid
            )

    @classmethod
    async def save_room(
        cls,
        room_id: RoomID,
        selected_option: str,
        puppet_mxid: str,
        change_selected_option: bool = False,
    ) -> bool:
        """Save or update a room.

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
        room = await Room.get_room_by_room_id(room_id)
        if room:
            return await cls.update_room_in_db(
                room_id=room_id,
                selected_option=selected_option,
                puppet_mxid=puppet_mxid,
                change_selected_option=change_selected_option,
            )
        else:
            return await cls.insert_room_in_db(
                room_id=room_id, selected_option=selected_option, puppet_mxid=puppet_mxid
            )

    @classmethod
    async def remove_pending_room(cls, room_id: RoomID) -> bool:
        """Delete the pending room.

        Parameters
        ----------
        room_id: RoomID
            Room to remove data.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_pending_room_by_room_id(room_id)
            if not room:
                return False

            return await Room.remove_pending_room(room_id)
        except Exception as e:
            cls.log.exception(e)
            return False

    @classmethod
    async def insert_room_in_db(
        cls, room_id: RoomID, selected_option: str, puppet_mxid: UserID
    ) -> bool:
        """Inserts a room in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_room_by_room_id(room_id)
            if room:
                return False
            else:
                puppet: pu.Puppet = await pu.Puppet.get_by_custom_mxid(puppet_mxid)
                await Room.insert_room(room_id, selected_option, puppet.pk)
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def insert_pending_room_in_db(
        cls, room_id: RoomID, selected_option: str, puppet_mxid: UserID
    ) -> bool:
        """Inserts a pending_room in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_pending_room_by_room_id(room_id)
            if room:
                return False
            else:
                puppet: pu.Puppet = await pu.Puppet.get_by_custom_mxid(puppet_mxid)
                await Room.insert_pending_room(room_id, selected_option, puppet.pk)
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def update_pending_room_in_db(
        cls, room_id: RoomID, selected_option: str, puppet_mxid: str
    ) -> bool:
        """Updates a pending_room in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_pending_room_by_room_id(room_id)
            if room:
                puppet: pu.Puppet = await pu.Puppet.get_by_custom_mxid(puppet_mxid)
                if not puppet:
                    cls.log.error(f"Puppet not found {puppet_mxid}")
                    return False

                fk_puppet = room.fk_puppet if puppet.pk == room.fk_puppet else puppet.pk
                await Room.update_pending_room_by_room_id(room_id, selected_option, fk_puppet)
            else:
                cls.log.error(f"The room {room_id} does not exist so it will not be updated")
                return False
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def update_room_in_db(
        cls,
        room_id: RoomID,
        selected_option: str,
        puppet_mxid: UserID,
        change_selected_option: bool = False,
    ) -> bool:
        """Updates a room in the database.

        If you want change `selected_option`, you must put `change_selected_option` in `True`.

        Parameters
        ----------
        room_id: RoomID
            Room to save data.
        selected_option: RoomID
            Room selected by the customer.
        change_selected_option : bool
            Flag to change selected_option

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        try:
            room = await Room.get_room_by_room_id(room_id)
            if room:
                if not change_selected_option:
                    selected_option = room.selected_option

                puppet: pu.Puppet = await pu.Puppet.get_by_custom_mxid(puppet_mxid)
                if not puppet:
                    cls.log.error(f"Puppet not found {puppet_mxid}")
                    return False

                fk_puppet = room.fk_puppet if puppet.pk == room.fk_puppet else puppet.pk
                await Room.update_room_by_room_id(room_id, selected_option, fk_puppet)
            else:
                cls.log.error(f"The room {room_id} does not exist so it will not be updated")
                return False
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def get_pending_rooms(cls, fk_puppet: int) -> List[RoomID]:
        """Get a pending rooms in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to query.

        Returns
        -------
        List[RoomID]
            List[RoomID] if successful, None otherwise.
        """
        try:
            rooms = await Room.get_pending_rooms(fk_puppet)
        except Exception as e:
            cls.log.exception(e)
            return

        if not rooms:
            return []

        return [room.room_id for room in rooms]

    @classmethod
    async def get_puppet_rooms(cls, fk_puppet: int) -> Dict[RoomID]:
        """Get a pending rooms in the database.

        Parameters
        ----------
        room_id: RoomID
            Room to query.

        Returns
        -------
        Dict[RoomID]
            Dict[RoomID] if successful, None otherwise.
        """
        try:
            rooms = await Room.get_puppet_rooms(fk_puppet)
        except Exception as e:
            cls.log.exception(e)
            return
        if not rooms:
            return {}

        return rooms

    @classmethod
    async def get_campaign_of_pending_room(cls, room_id: RoomID) -> RoomID:
        """Given a pending room, its selected campaign is obtained.
        Parameters
        ----------
        room_id: RoomID
            Room to query.

        Returns
        -------
        RoomID
            RoomID if successful, None otherwise.
        """
        try:
            return await Room.get_campaign_of_pending_room(room_id=room_id)
        except Exception as e:
            cls.log.exception(e)

    @classmethod
    async def get_campaign_of_room(cls, room_id: RoomID) -> RoomID:
        """Given a room, its selected campaign is obtained.
        Parameters
        ----------
        room_id: RoomID
            Room to query.

        Returns
        -------
        RoomID
            RoomID if successful, None otherwise.
        """
        try:
            return await Room.get_user_selected_menu(room_id=room_id)
        except Exception as e:
            cls.log.exception(e)

    @classmethod
    async def get_room(cls, room_id: RoomID) -> Room:
        """If the room is in the cache, return it.
        If not, get it from the database and add it to the cache.

        The first thing we do is check if the room is in the cache.
        If it is, we return it. If not, we get it from the database

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to get.

        Returns
        -------
            A room object

        """

        try:
            return cls.by_room_id[room_id]
        except KeyError:
            pass
        room = None

        try:
            room = await Room.get_room_by_room_id(room_id=room_id)
        except Exception as e:
            cls.log.exception(e)

        if not room:
            return

        cls._add_to_cache(room_id=room_id, room=room)

        return room

    @classmethod
    async def is_a_control_room(cls, room_id: RoomID) -> bool:
        """If the room ID is in the list of control rooms,
        or if the room ID is in the list of control room IDs,
        then the room is a control room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to check.

        Returns
        -------
            A list of room IDs.

        """
        if room_id in cls.CONTROL_ROOMS:
            return True

        if room_id in await cls.get_control_room_ids():
            return True

        return False

    @classmethod
    async def get_control_room_ids(cls) -> List[RoomID]:
        """This function is used to get the list of control rooms from the pu.Puppet

        Parameters
        ----------

        Returns
        -------
            A list of room ids

        """
        try:
            control_room_ids = await pu.Puppet.get_control_room_ids()
        except Exception as e:
            cls.log.exception(e)
            return []

        if not control_room_ids:
            return []

        cls.CONTROL_ROOMS = control_room_ids
        return control_room_ids
