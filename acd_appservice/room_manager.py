from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List, Tuple

from markdown import markdown
from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import IntentAPI
from mautrix.errors.base import IntentError
from mautrix.types import (
    EventType,
    Format,
    JoinRule,
    MessageType,
    PowerLevelStateEventContent,
    RoomDirectoryVisibility,
    RoomID,
    TextMessageEventContent,
    UserID,
)
from mautrix.util.logging import TraceLogger

from .config import Config
from .db import Room
from .util import Util


class RoomManager:

    log: TraceLogger = logging.getLogger("acd.room_manager")
    ROOMS: dict[RoomID, Dict] = {}

    # Listado de salas  en la DB
    by_room_id: dict[RoomID, Room] = {}

    # list of room_ids to know if distribution process is taking place
    LOCKED_ROOMS = set()

    # rooms that are in offline agent menu
    offline_menu = set()

    # blacklist of rooms
    blacklist_rooms = set()

    def __init__(
        self, puppet_pk: int, control_room_id: RoomID, config: Config, intent: IntentAPI = None
    ) -> None:
        self.config = config
        if not intent:
            return
        self.intent = intent
        self.log = self.log.getChild(self.intent.mxid or None)
        self.puppet_pk = puppet_pk
        self.control_room_id = control_room_id

    @classmethod
    def _add_to_cache(cls, room_id, room: Room) -> None:
        cls.by_room_id[room_id] = room

    @property
    def power_levels(self) -> PowerLevelStateEventContent:
        levels = PowerLevelStateEventContent()
        levels.events_default = 0
        levels.ban = 99
        levels.kick = 99
        levels.invite = 99
        levels.events[EventType.REACTION] = 0
        levels.events[EventType.ROOM_NAME] = 0
        levels.events[EventType.ROOM_AVATAR] = 0
        levels.events[EventType.ROOM_TOPIC] = 0
        levels.events[EventType.ROOM_TOMBSTONE] = 99
        levels.users_default = 0
        levels.redact = 99

        return levels

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
            self.log.debug(f"Only customer rooms are initialised :: {room_id}")
            return False

        bridge = await self.get_room_bridge(room_id=room_id)
        if bridge and bridge in self.config["bridges"] and bridge != "plugin":
            await self.send_cmd_set_pl(
                room_id=room_id,
                bridge=bridge,
                user_id=self.intent.mxid,
                power_level=100,
            )
            await self.send_cmd_set_relay(room_id=room_id, bridge=bridge)
        else:
            await self.intent.set_power_levels(room_id=room_id, content=self.power_levels)

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

    async def put_name_customer_room(self, room_id: RoomID) -> bool:
        """It sets the room name to the name of the customer

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to change the name of.

        Returns
        -------
            A boolean value.

        """
        if await self.is_customer_room(room_id=room_id):
            if (
                not self.config["acd.keep_room_name"]
                or self.ROOMS.get(room_id).get("name") is None
            ):
                creator = await self.get_room_creator(room_id=room_id)
                new_room_name = await self.get_update_name(creator=creator)
                if new_room_name:
                    self.log.debug(f"Setting the name {new_room_name} to the room {room_id}")
                    for attempt in range(10):
                        try:
                            await self.intent.set_room_name(room_id, new_room_name)
                            break
                        except Exception as e:
                            self.log.warning(f"Failed to set room name attempt {attempt}: {e}")

                        await asyncio.sleep(2)
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

    async def send_formatted_message(
        self,
        room_id: RoomID,
        msg: str,
    ) -> None:
        """It sends a message to a room, and the message is formatted using Markdown

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the message to.
        msg : str
            The message to send.

        """
        html = markdown(msg)
        content = TextMessageEventContent(
            msgtype=MessageType.TEXT,
            body=msg,
            format=Format.HTML,
            formatted_body=html,
        )

        # Remove markdown and html tags if bridge not support formatted messages
        bridge_room = await self.get_room_bridge(room_id=room_id)
        if not self.config[f"bridges.{bridge_room}.format_messages"]:
            new_body = Util.md_to_text(content.get("body"))
            content["body"] = new_body if new_body else msg

        await self.intent.send_message(
            room_id=room_id,
            content=content,
        )

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
        return f"transfer-{room_id}-{agent_id}" if transfer else f"{room_id}-{agent_id}"

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

    async def get_update_name(self, creator: UserID) -> str:
        """It takes a user ID and a puppet ID, and returns a room name

        Parameters
        ----------
        creator : UserID
            The user ID of the user who created the room.

        Returns
        -------
            A string

        """
        new_room_name = None
        emoji_number = ""
        bridges = self.config["bridges"]
        for bridge in bridges:
            user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
            if creator.startswith(f"@{user_prefix}"):
                if bridge == "instagram":
                    new_room_name = await self.intent.get_displayname(user_id=creator)
                else:
                    new_room_name = await self.create_room_name(user_id=creator)
                if new_room_name:
                    postfix_template = self.config[f"bridges.{bridge}.postfix_template"]
                    new_room_name = new_room_name.replace(f" {postfix_template}", "")
                    if self.config["acd.numbers_in_rooms"]:
                        try:

                            emoji_number = self.get_emoji_number(number=str(self.puppet_pk))

                            if emoji_number:
                                new_room_name = f"{new_room_name} {emoji_number}"
                        except AttributeError as e:
                            self.log.error(e)
                break

        return new_room_name

    def get_emoji_number(self, number: str) -> str | None:
        """It takes a string of numbers and returns a string of emoji numbers

        Parameters
        ----------
        number : str
            The number you want to convert to emojis.

        Returns
        -------
            the emoji number.

        """

        emoji_number = (
            number.replace("0", "0️⃣")
            .replace("1", "1️⃣")
            .replace("2", "2️⃣")
            .replace("3", "3️⃣")
            .replace("4", "4️⃣")
            .replace("5", "5️⃣")
            .replace("6", "6️⃣")
            .replace("7", "7️⃣")
            .replace("8", "8️⃣")
            .replace("9", "9️⃣")
        )

        return emoji_number

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
                method=Method.GET, path=SynapseAdminPath.v2.users[user_id].devices
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

    async def menubot_leaves(self, room_id: RoomID, reason: str = None) -> None:
        """It sends a command to the menubot to cancel the task, then it leaves the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room the menubot is in.
        reason : str
            The reason for the user leaving the room.

        """

        menubot_id = await self.get_menubot_id()
        if menubot_id:
            await self.send_menubot_command(menubot_id, "cancel_task", room_id)
            try:

                self.log.debug(f"Menubot [{menubot_id}] is leaving the room {room_id}")
                await self.remove_user_from_room(
                    room_id=room_id, user_id=menubot_id, reason=reason
                )
            except Exception as e:
                self.log.error(str(e))

    async def remove_user_from_room(self, room_id: RoomID, user_id: UserID, reason: str = None):
        """It sends a request to the homeserver to leave a room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to kick the user from.
        user_id : UserID
            The user ID of the user to kick.
        reason : str
            The reason for leaving the room.

        """
        try:
            if self.config["acd.remove_method"] == "leave":
                data = {}
                if reason:
                    data["reason"] = reason

                await self.intent.api.session.post(
                    url=f"{self.intent.api.base_url}/_matrix/client/v3/rooms/{room_id}/leave",
                    headers={"Authorization": f"Bearer {self.intent.api.token}"},
                    json=data,
                    params={"user_id": user_id},
                )
                self.log.debug(f"User {user_id} has left the room {room_id}")
            elif self.config["acd.remove_method"] == "kick":
                self.log.debug(f"User {user_id} has been kicked from the room {room_id}")
                await self.intent.kick_user(room_id=room_id, user_id=user_id, reason=reason)
        except Exception as e:
            self.log.exception(e)

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
            if member == await self.get_menubot_id():
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
        """Invite supervisors to the room, and if it fails,
        it waits a couple of seconds and tries again.

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room to invite supervisors to.

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

    async def get_bridge_by_cmd_prefix(self, cmd_prefix: str) -> str:
        """It takes a command prefix and returns the bridge that it belongs to

        Parameters
        ----------
        cmd_prefix : str
            The command prefix that the user used to call the command.

        Returns
        -------
            The bridge name.

        """

        bridges = self.config["bridges"]

        for bridge in bridges:
            bridge_cmd_prefix = self.config[f"bridges.{bridge}.prefix"]
            if cmd_prefix.startswith(bridge_cmd_prefix):
                return bridge

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
                method=Method.GET, path=SynapseAdminPath.v1.rooms[room_id]
            )
            self.ROOMS[room_id] = room_info
        except Exception as e:
            self.log.exception(e)
            return

        return room_info

    # Seccion DB
    @classmethod
    async def save_pending_room(
        cls, room_id: RoomID, puppet_pk: int, selected_option: str = None
    ) -> bool:
        """> If the room is already in the database, update it, otherwise insert it

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to save.
        puppet_pk : int
            The primary key of the puppet in the database.
        selected_option : str
            The option that the user selected.

        Returns
        -------
            A boolean value.

        """
        room = await Room.get_pending_room_by_room_id(room_id)
        if room:
            return await cls.update_pending_room_in_db(
                room_id=room_id, selected_option=selected_option, puppet_pk=puppet_pk
            )
        else:
            return await cls.insert_pending_room_in_db(
                room_id=room_id, selected_option=selected_option, puppet_pk=puppet_pk
            )

    @classmethod
    async def save_room(
        cls,
        room_id: RoomID,
        selected_option: str,
        puppet_pk: int,
        change_selected_option: bool = False,
    ) -> bool:
        """> It saves the room in the database

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to save.
        selected_option : str
            This is the option that the user has selected.
        puppet_pk : int
            The primary key of the puppet in the database.
        change_selected_option : bool, optional
            bool = False

        Returns
        -------
            A boolean value.

        """

        room = await Room.get_room_by_room_id(room_id)
        cls.log.debug(f"Saving the room {room_id} for the puppet {puppet_pk}")
        if room:
            return await cls.update_room_in_db(
                room_id=room_id,
                selected_option=selected_option,
                puppet_pk=puppet_pk,
                change_selected_option=change_selected_option,
            )
        else:
            return await cls.insert_room_in_db(
                room_id=room_id, selected_option=selected_option, puppet_pk=puppet_pk
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
        cls, room_id: RoomID, selected_option: str, puppet_pk: int
    ) -> bool:
        """> This function inserts a room into the database

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to insert into the database.
        selected_option : str
            The option that the user selected from the menu.
        puppet_pk : int
            The primary key of the puppet in the database.

        Returns
        -------
            A boolean value.

        """
        try:
            room = await Room.get_room_by_room_id(room_id)
            if room:
                return False
            else:
                await Room.insert_room(room_id, selected_option, puppet_pk)
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def insert_pending_room_in_db(
        cls, room_id: RoomID, selected_option: str, puppet_pk: int
    ) -> bool:
        """> Inserts a pending room into the database

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to add to the database.
        selected_option : str
            This is the option that the user selected from the menu.
        puppet_pk : int
            The primary key of the puppet in the database.

        Returns
        -------
            A boolean value.

        """
        try:
            room = await Room.get_pending_room_by_room_id(room_id)
            if room:
                return False
            else:
                await Room.insert_pending_room(room_id, selected_option, puppet_pk)
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def update_pending_room_in_db(
        cls, room_id: RoomID, selected_option: str, puppet_pk: int
    ) -> bool:
        """It updates the selected option and the puppet pk of a pending room in the database

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to update
        selected_option : str
            The option that the user selected.
        puppet_pk : int
            The primary key of the puppet that is being used to create the room.

        Returns
        -------
            A boolean value

        """
        try:
            room = await Room.get_pending_room_by_room_id(room_id)
            if room:
                puppet_pk = room.fk_puppet if puppet_pk == room.fk_puppet else puppet_pk
                await Room.update_pending_room_by_room_id(room_id, selected_option, puppet_pk)
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
        puppet_pk: int,
        change_selected_option: bool = False,
    ) -> bool:
        """It updates the room in the database

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to update
        selected_option : str
            The option that the user has selected.
        puppet_pk : int
            The primary key of the puppet that is currently in the room.
        change_selected_option : bool, optional
            If True, the selected_option will be updated to the new value.
            If False, the selected_option will not be updated.

        Returns
        -------
            A boolean value

        """
        try:
            room = await Room.get_room_by_room_id(room_id)
            if room:
                if not change_selected_option:
                    selected_option = room.selected_option

                puppet_pk = room.fk_puppet if puppet_pk == room.fk_puppet else puppet_pk
                await Room.update_room_by_room_id(room_id, selected_option, puppet_pk)
            else:
                cls.log.error(f"The room {room_id} does not exist so it will not be updated")
                return False
        except Exception as e:
            cls.log.exception(e)
            return False

        return True

    @classmethod
    async def get_pending_rooms(cls, puppet_pk: int) -> List[RoomID]:
        """`get_pending_rooms` returns a list of room IDs that are pending for a given puppet

        Parameters
        ----------
        puppet_pk : int
            The primary key of the puppet.

        Returns
        -------
            A list of room_ids

        """
        try:
            rooms = await Room.get_pending_rooms(puppet_pk)
        except Exception as e:
            cls.log.exception(e)
            return

        if not rooms:
            return []

        return [room.room_id for room in rooms]

    @classmethod
    async def get_puppet_rooms(cls, puppet_pk: int) -> Dict[RoomID]:
        """`get_puppet_rooms` returns a dictionary of rooms that are associated with a puppet

        Parameters
        ----------
        puppet_pk : int
            The primary key of the puppet.

        Returns
        -------
            A dictionary of room ids and room names.

        """
        try:
            rooms = await Room.get_puppet_rooms(puppet_pk)
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
