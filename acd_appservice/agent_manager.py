from __future__ import annotations

import asyncio
import logging
from ast import Dict
from typing import List

from mautrix.appservice import AppService, IntentAPI
from mautrix.types import Member, RoomID, UserID
from mautrix.util.logging import TraceLogger

from acd_appservice.puppet import Puppet

from .config import Config
from .room_manager import RoomManager


class AgentManager:
    config: Config
    log: TraceLogger = logging.getLogger("mau.agent_manager")
    intent: IntentAPI

    GROUP_ROOM: dict[RoomID, Dict] = {}
    control_room_id: RoomID | None = None

    def __init__(
        self,
        intent: IntentAPI,
        config: Config,
    ) -> None:
        self.intent = intent
        self.config = config
        self.control_room_id = self.config["acd.control_room_id"]

    async def process_distribution(
        self,
        initializer_id: UserID,
        customer_room_id: RoomID,
        campaign_room_id: RoomID = None,
        joined_message: str = None,
    ):
        """Start distribution process if no online agents in the room.

        This loop is done over agents in campaign_room_id
        """
        if RoomManager.is_room_locked(room_id=customer_room_id):
            self.log.debug(f"Room {customer_room_id} LOCKED")
            return

        self.log.debug(f"INIT Process distribution for {customer_room_id}")

        # lock the room
        RoomManager.lock_room(room_id=customer_room_id)

        online_agents_in_room = await self.is_a_room_with_online_agents(room_id=customer_room_id)

        if online_agents_in_room == "unlock":
            RoomManager.unlock_room(room_id=customer_room_id)
            return

        if not online_agents_in_room:
            # if a campaign is provided, the loop is done over the agents of that campaign.
            # if campaign is None, the loop is done over the control room
            if initializer_id and initializer_id != self.intent.bot.mxid:
                puppet: Puppet = await Puppet.get_puppet_by_mxid(initializer_id) # TODO quedamos aqui
                control_room_id = puppet.control_room_id
            else:
                control_room_id = self.control_room_id

            target_room_id = campaign_room_id if campaign_room_id else control_room_id

            if not target_room_id in self.GROUP_ROOM:
                if not await self.load_campaign_room(room_id=customer_room_id):
                    RoomManager.unlock_room(room_id=customer_room_id)
                    return

            # a task is created to not block asyncio loop
            asyncio.create_task(
                self.loop_agents(
                    customer_room_id=customer_room_id,
                    campaign_room_id=target_room_id,
                    agent_id=self.GROUP_ROOM[target_room_id]["next_agent"],
                    joined_message=joined_message,
                )
            )
        else:
            self.log.debug(f"This room {target_room_id} doesn't have online agents")
            RoomManager.unlock_room(room_id=customer_room_id)

    async def loop_agents(
        self,
        customer_room_id: RoomID,
        campaign_room_id: RoomID,
        agent_id: UserID,
        joined_message: str,
    ) -> None:
        """Loop through agents to assign one to the chat."""
        total_agents = await self.get_agent_count(room_id=campaign_room_id)

        self.log.debug(f"New agent loop in {campaign_room_id} starting with {agent_id}")

        while True:
            agent_id = await self.GROUP_ROOM.get(campaign_room_id).get("next_agent")
            if not agent_id:
                self.log.info(f"NO AGENTS IN ROOM {campaign_room_id}")

                await offline_handler.show_no_agents_message(room_id, campaign_room_id)
                ACD.unlock_room(room_id)
                break

    async def load_campaign_room(self, room_id: RoomID) -> bool:
        agents = await self.get_agents(room_id=room_id)
        if not agents:
            return False

        # NOTA: Como es la primer carga de la sala, el ultimo y el primer agente
        # es el primer encontrado

        # Registramos el último agente en la cola
        if self.GROUP_ROOM[room_id].get("last_agent") is None:
            self.GROUP_ROOM[room_id]["last_agent"] = agents[0]

        # Registramos el siguiente agente en la cola
        if self.GROUP_ROOM[room_id].get("next_agent") is None:
            self.GROUP_ROOM[room_id]["next_agent"] = agents[0]

        return True

    async def send_menubot_command(self, menubot_id: UserID, command: str, *args):
        """Send a command to menubot."""
        if menubot_id:
            if self.config["acd.menubot"]:
                prefix = self.config["acd.menubot.command_prefix"]
            else:
                prefix = self.config[f"acd.menubots.{menubot_id}.command_prefix"]

            cmd = f"{prefix} {command} {' '.join(args)}"

            cmd = cmd.strip()

            control_room_id = (
                self.control_room_id
                if self.control_room_id
                else self.config["acd.control_room_id"]
            )  # TODO esta sala de control depende del puppet este manejando en un instante x el algorimo de asignación, cada puppet tiene salas de control independiente.
            self.log.debug(f"Sending command {command} for the menubot {menubot_id}")
            await self.intent.send_text(room_id=control_room_id, text=cmd)

    async def get_agent_count(self, room_id: RoomID):
        """Get a room agent count."""
        total = 0
        agents = await self.get_agents(room_id=room_id)
        if agents:
            total = len(agents)
        return total

    async def is_a_room_with_online_agents(self, room_id: RoomID) -> bool:
        """Check if there is an online agent in the room."""
        agents = await self.get_agents(room_id=room_id)
        if not agents:
            # probably an error has occurred
            self.log.debug(f"No joined members in the room {room_id}")
            return "unlock"

        for user_id in agents:
            response = await self.intent.get_presence(user_id)
            if response.presence.ONLINE:
                self.log.debug(f"Online agent {user_id} in the room {room_id}")
                self.GROUP_ROOM[room_id]["next_agent"] = user_id
                return True

        return False

    async def get_agents(self, room_id: RoomID) -> List[UserID]:
        """Get a room agent list."""

        members = await self.intent.get_joined_members(room_id=room_id)
        if members:
            # remove bots from member list
            agents_id = self.remove_not_agents(members)
        return agents_id

    def remove_not_agents(self, members: dict[UserID, Member]) -> List[UserID]:
        """Remove other users like bots from room members."""

        only_agents = []

        if members:
            # Removes non-agents
            only_agents = [
                user_id
                for user_id in members
                if user_id.startswith(self.config["acd.agent_prefix"])
            ]
        return only_agents

    @classmethod
    def is_agent(cls, agent_id: UserID) -> bool:
        """Check if userid is agent."""
        return True if agent_id.startswith(cls.config["acd.agent_prefix"]) else False
