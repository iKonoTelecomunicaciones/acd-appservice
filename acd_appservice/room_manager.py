from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict

from mautrix.api import Method
from mautrix.appservice import IntentAPI
from mautrix.types import EventType, JoinRule, RoomDirectoryVisibility, RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config


class RoomManager:
    config: Config
    log: TraceLogger = logging.getLogger("mau.room_manager")
    ROOMS: dict[RoomID, Dict] = {}

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

        creator = await RoomManager.get_room_creator(room_id=room_id, intent=intent)

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
