from __future__ import annotations

import asyncio
import logging

from mautrix.appservice import IntentAPI
from mautrix.types import EventType, JoinRule, RoomDirectoryVisibility, RoomID
from mautrix.util.logging import TraceLogger

from .config import Config

# from acd_program.puppet import Puppet


class RoomManager:
    config: Config
    log: TraceLogger = logging.getLogger("mau.room_manager")

    def __init__(self, config: Config) -> None:
        self.config = config

    async def initialize_room(self, room_id: RoomID, intent: IntentAPI) -> bool:

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

        self.log.info(f"Room {room_id} initialization is complete")
        return True

    async def initial_room_setup(self, room_id: RoomID, intent: IntentAPI):

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

    async def send_cmd_set_relay(self, room_id: RoomID, intent: IntentAPI, bridge: str) -> bool:
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
    ) -> bool:
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
        creator = await RoomManager.get_room_creator(room_id=room_id, intent=intent)
        bridges = self.config["bridges"]
        if creator:
            for bridge in bridges:
                user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
                if creator.startswith(f"@{user_prefix}"):
                    return True
        return False

    @classmethod
    async def get_room_creator(cls, room_id: RoomID, intent: IntentAPI) -> str:
        try:
            events = await intent.get_state(room_id=room_id)
        except Exception as e:
            cls.log.error(e)

        creator = None
        for event in events:
            if event.type.ROOM_CREATE:
                creator = event.sender
                cls.log.debug(f"The creator of the room {room_id} is {creator} ")
                break

        return creator

    async def get_room_bridge(self, room_id: RoomID, intent: IntentAPI) -> str:
        creator = await RoomManager.get_room_creator(room_id=room_id, intent=intent)
        bridges = self.config["bridges"]
        if creator:
            for bridge in bridges:
                user_prefix = self.config[f"bridges.{bridge}.user_prefix"]
                if creator.startswith(f"@{user_prefix}"):
                    self.log.debug(f"The bridge obtained is {bridge}")
                    return bridge
        return None
