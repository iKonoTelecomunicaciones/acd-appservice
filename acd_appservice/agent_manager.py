from __future__ import annotations

import logging
import re
from asyncio import Future, create_task, get_running_loop, sleep
from datetime import datetime
from typing import Dict, List, Tuple

from mautrix.api import Method
from mautrix.appservice import IntentAPI
from mautrix.errors.base import IntentError
from mautrix.types import Member, PresenceEventContent, RoomAlias, RoomID, UserID
from mautrix.util.logging import TraceLogger

from .config import Config
from .room_manager import RoomManager


class AgentManager:
    config: Config
    log: TraceLogger = logging.getLogger("mau.agent_manager")
    intent: IntentAPI

    # last invited agent per control room (i.e. campaigns)
    CURRENT_AGENT = {}

    # Dict of Future objects used to get notified when an agent accepts an invite
    PENDING_INVITES: dict[str, Future] = {}

    control_room_id: RoomID | None = None

    def __init__(
        self,
        intent: IntentAPI,
        config: Config,
        control_room_id: RoomID,
    ) -> None:
        self.intent = intent
        self.config = config
        self.control_room_id = control_room_id

    async def process_distribution(
        self,
        customer_room_id: RoomID,
        campaign_room_id: RoomID = None,
        joined_message: str = None,
    ) -> None:
        """Start distribution process if no online agents in the room.

        This loop is done over agents in campaign_room_id
        """

        if RoomManager.is_room_locked(room_id=customer_room_id):
            self.log.debug(f"Room [{customer_room_id}] LOCKED")
            return

        self.log.debug(f"INIT Process distribution for [{customer_room_id}]")

        # lock the room
        RoomManager.lock_room(room_id=customer_room_id)

        online_agents_in_room = await self.is_a_room_with_online_agents(room_id=customer_room_id)

        if online_agents_in_room == "unlock":
            RoomManager.unlock_room(room_id=customer_room_id)
            return

        if not online_agents_in_room:
            # if a campaign is provided, the loop is done over the agents of that campaign.
            # if campaign is None, the loop is done over the control room

            target_room_id = campaign_room_id if campaign_room_id else self.control_room_id

            # a task is created to not block asyncio loop
            create_task(
                self.loop_agents(
                    customer_room_id=customer_room_id,
                    campaign_room_id=target_room_id,
                    agent_id=self.CURRENT_AGENT.get(target_room_id),
                    joined_message=joined_message,
                )
            )
        else:
            self.log.debug(f"This room [[{customer_room_id}]] doesn't have online agents")
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
        online_agents = 0

        # Number of agents iterated
        agent_count = 0

        self.log.debug(
            f"New agent loop in [{campaign_room_id}] starting with [{agent_id if agent_id else '👻'}]"
        )

        while True:
            agent_id = await self.get_next_agent(agent_id, campaign_room_id)
            if not agent_id:
                self.log.info(f"NO AGENTS IN ROOM [{campaign_room_id}]")

                await self.show_no_agents_message(
                    customer_room_id=customer_room_id, campaign_room_id=campaign_room_id
                )
                RoomManager.unlock_room(room_id=customer_room_id)
                break

            joined_members = await self.intent.get_joined_members(room_id=customer_room_id)
            if not joined_members:
                self.log.debug(f"No joined members in the room [[{customer_room_id}]]")
                RoomManager.unlock_room(customer_room_id)
                break

            if len(joined_members) == 1 and joined_members[0].user_id == self.intent.mxid:
                # customer leaves when trying to connect an agent
                self.log.info("NOBODY IN THIS ROOM, I'M LEAVING")
                await self.intent.leave_room(
                    room_id=customer_room_id, reason="NOBODY IN THIS ROOM, I'M LEAVING"
                )
                RoomManager.unlock_room(customer_room_id)
                break

            if self.config["acd.force_join"] and await self.is_in_mobile_device(agent_id):
                # force agent join to room when agent is in mobile device
                self.log.debug(f"Agent [[{agent_id}]] is in mobile device")
                await self.force_invite_agent(
                    customer_room_id, agent_id, campaign_room_id, joined_message
                )
                break

            presence_response = await self.get_user_presence(agent_id)
            self.log.debug(
                f"PRESENCE RESPONSE: "
                f"[{presence_response.presence if presence_response else None}]"
            )
            if presence_response and presence_response.presence.ONLINE:
                # only invite agents online
                online_agents += 1
                response = await self.invite_agent(
                    customer_room_id, agent_id, campaign_room_id, joined_message
                )
                if response:
                    self.log.debug(f"TRYING [[{agent_id}]] ...")
                    RoomManager.unlock_room(customer_room_id)
                    break

            agent_count += 1

            # if no agents online after cheking them all, break
            if agent_count >= total_agents:
                if online_agents == 0:
                    # there is no available agents
                    self.log.debug("NO ONLINE AGENTS")
                else:
                    self.log.debug("THERE ARE ONLINE AGENTS BUT ERROR ON INVITE")

                await self.show_no_agents_message(
                    customer_room_id=customer_room_id, campaign_room_id=campaign_room_id
                )

                self.log.debug(f"Saving room [[{customer_room_id}]] in pending list")
                # self.bot.store.save_pending_room(customer_room_id, campaign_room_id) # TODO GUARDAR EN BASE DE DATOS

                RoomManager.unlock_room(room_id=customer_room_id)
                break

            self.log.debug(f"agent count: [{agent_count}] online_agents: [{online_agents}]")

    async def invite_agent(
        self,
        customer_room_id: RoomID,
        agent_id: UserID,
        campaign_room_id: RoomID,
        joined_message: str = None,
    ):
        """Invite an agent."""
        self.log.debug(f"Inviting [[{agent_id}]]...")
        try:
            await self.intent.invite_user(room_id=customer_room_id, user_id=agent_id)
        except IntentError as e:
            self.log.error(e)
            return False

        # get the current event loop
        loop = get_running_loop()

        # create a new Future object.
        pending_invite = loop.create_future()
        future_key = self.get_future_key(customer_room_id, agent_id)
        # mantain an array of futures for every invite to get notification of joins
        self.PENDING_INVITES[future_key] = pending_invite
        self.log.debug(f"Futures are... [{self.PENDING_INVITES}]")

        # spawn a task that does not block the asyncio loop
        create_task(
            self.check_agent_joined(
                customer_room_id, pending_invite, agent_id, campaign_room_id, joined_message
            )
        )

        return True

    async def get_user_presence(self, user_id: UserID) -> PresenceEventContent:
        """Get user presence status."""
        self.log.debug(f"Checking presence for....... [{user_id}]")
        response = None
        try:
            response = await self.intent.get_presence(user_id=user_id)
        except IntentError as e:
            self.log.error(e)

        return response

    async def get_next_agent(self, agent_id: UserID, room_id: RoomID) -> UserID:
        """Get next agent in line."""
        members = await self.intent.get_joined_members(room_id)
        # print([member.user_id for member in members])
        if members:
            # remove bots from member list
            members = self.remove_not_agents(members)

            # if members is empty after bots removed, return None
            if not members:
                return None

            # if not reference agent, return first one
            if not agent_id:
                return members[0]

            total = len(members)
            i = 0
            for member in members:
                if member == agent_id:
                    # return next agent after reference agent, or first one
                    # if reference agent is last in line
                    return members[0] if i >= total - 1 else members[i + 1]
                i += 1

            # if member is not in the room anymore, return first agent
            return members[0]

        return None

    async def is_in_mobile_device(self, user_id: UserID) -> bool:
        devices = await self.get_user_devices(user_id=user_id)
        device_name_regex = self.config["acd.device_name_regex"]
        if devices:
            for device in devices["devices"]:
                if device.get("display_name") and re.search(
                    device_name_regex, device["display_name"]
                ):
                    return True

    async def force_invite_agent(
        self,
        room_id: RoomID,
        agent_id: UserID,
        campaign_room_id: RoomID,
        joined_message: str = None,
    ):
        # get the current event loop
        loop = get_running_loop()

        # create a new Future object.
        pending_invite = loop.create_future()
        future_key = AgentManager.get_future_key(room_id, agent_id)
        # mantain an array of futures for every invite to get notification of joins
        self.PENDING_INVITES[future_key] = pending_invite
        self.log.debug(f"Futures are... [{self.PENDING_INVITES}]")

        await self.force_join_agent(room_id, agent_id)

        # spawn a task that does not block the asyncio loop
        create_task(
            self.check_agent_joined(
                room_id, pending_invite, agent_id, campaign_room_id, joined_message
            )
        )

    async def check_agent_joined(
        self,
        customer_room_id: RoomID,
        pending_invite: Future,
        agent_id: UserID,
        campaign_room_id: RoomID,
        joined_message: str = None,
    ):
        """Start a loop of x seconds that is interrupted when the agent accepts the invite."""
        agent_joined = None
        loop = get_running_loop()
        end_time = loop.time() + float(self.config.get("agent_invite_timeout"))
        while True:
            self.log.debug(datetime.now())
            if pending_invite.done():
                # when a join event is received, the Future object is resolved
                self.log.debug("FUTURE IS DONE")
                break
            if (loop.time() + 1.0) >= end_time:
                self.log.debug("TIMEOUT COMPLETED.")
                pending_invite.set_result(False)
                break

            await sleep(1)

        agent_joined = pending_invite.result()
        future_key = AgentManager.get_future_key(customer_room_id, agent_id)
        if future_key in self.PENDING_INVITES:
            del self.PENDING_INVITES[future_key]
        self.log.debug(f"futures left: {self.PENDING_INVITES}")
        if agent_joined:
            self.CURRENT_AGENT[campaign_room_id] = agent_id
            self.log.debug(f"[[{agent_id}]] ACCEPTED the invite. CHAT ASSIGNED.")
            self.log.debug(f"NEW CURRENT_AGENT : [{self.CURRENT_AGENT}]")
            self.log.debug(f"======> [{customer_room_id}] selected [{campaign_room_id}]")
            self.bot.store.set_user_selected_menu(customer_room_id, campaign_room_id)

            self.log.debug(f"Removing room [{customer_room_id}] from pending list")
            # self.bot.store.remove_pending_room(customer_room_id) # TODO BASE DE DATOS

            # kick menu bot
            await self.kick_menubot(
                room_id=customer_room_id, reason=f"agent [{agent_id}] accepted invite"
            )

            displayname = await self.intent.get_displayname(user_id=agent_id)
            msg = ""
            if joined_message:
                msg = joined_message.format(agentname=displayname)
            else:
                msg = self.config.get("joined_agent_message").format(agentname=displayname)

            if msg:
                await self.intent.send_text(room_id=customer_room_id, text=msg)

            # signaling = Signaling(self.bot)

            # set chat status to pending when the agent is asigned to the chat
            # await signaling.set_chat_status(
            #     room_id=room_id,
            #     status=Signaling.PENDING,
            #     campaign_room_id=campaign_room_id,
            #     agent=agent_id,
            # )

            # send campaign selection event
            # await signaling.set_selected_campaign(
            #     room_id=room_id, campaign_room_id=campaign_room_id
            # )

            # send agent chat connect
            # await signaling.set_chat_connect_agent(
            #     room_id=room_id, agent=agent_id, source="auto", campaign_room_id=campaign_room_id
            # )

            RoomManager.unlock_room(room_id=customer_room_id)
        else:
            self.log.debug(f"[{agent_id}] DID NOT ACCEPT the invite. Inviting next agent ...")
            await self.intent.kick_user(
                room_id=customer_room_id,
                user_id=agent_id,
                reason="Tiempo de espera cumplido para unirse a la conversación",
            )
            await self.loop_agents(
                customer_room_id=customer_room_id,
                campaign_room_id=campaign_room_id,
                agent_id=agent_id,
                joined_message=joined_message,
            )

    @classmethod
    def get_future_key(cls, room_id: RoomID, agent_id: UserID) -> str:
        """Return the key for the dict of futures for a specific agent."""
        return f"[{room_id}]-[{agent_id}]"

    async def get_user_devices(self, user_id: UserID) -> Dict[str, List[Dict]]:
        """Get devices where agent have sessions"""
        response = None
        try:
            response = await self.intent.api.request(
                method=Method.GET, path=f"/_synapse/admin/v2/users/{user_id}/devices"
            )

        except IntentError as e:
            self.log.error(e)

        return response

    async def force_join_agent(
        self, room_id: RoomID, agent_id: UserID, room_alias: RoomAlias = None
    ) -> None:
        """Force agent join to room"""

        data = {"user_id": agent_id}
        try:
            response = await self.intent.api.request(
                method=Method.POST,
                path=f"/_synapse/admin/v1/join/{room_alias if room_alias else room_id}",
                content=data,
            )
            self.log.debug(response)
        except IntentError as e:
            self.log.error(e)

    async def show_no_agents_message(self, customer_room_id, campaign_room_id):
        """Ask menubot to show no-agents message for the given room."""
        menubot_id = await self.get_menubot_id(room_id=customer_room_id)
        if menubot_id:
            await self.send_menubot_command(
                menubot_id=menubot_id,
                command="no_agents_message",
                args=(customer_room_id, campaign_room_id),
            )

    async def kick_menubot(self, room_id: RoomID, reason: str) -> None:
        """Kick menubot from some room."""
        menubot_id = await self.get_menubot_id(room_id=room_id)
        if menubot_id:
            self.log.debug("Kicking the menubot [{menubot_id}]")
            await self.send_menubot_command(
                menubot_id=menubot_id, command="cancel_task", args=(room_id)
            )
            try:
                await self.intent.kick_user(room_id=room_id, user_id=menubot_id, reason=reason)
            except IntentError as e:
                self.log.error(e)
            self.log.debug(f"User [{menubot_id}] KICKED from room [{room_id}]")

    async def send_menubot_command(self, menubot_id: UserID, command: str, *args: Tuple):
        """Send a command to menubot."""
        if menubot_id:
            if self.config["acd.menubot"]:
                prefix = self.config["acd.menubot.command_prefix"]
            else:
                prefix = self.config[f"acd.menubots.[{menubot_id}].command_prefix"]

            cmd = f"{prefix} {command} {' '.join(args)}"

            cmd = cmd.strip()

            self.log.debug(f"Sending command {command} for the menubot [{menubot_id}]")
            await self.intent.send_text(room_id=self.control_room_id, text=cmd)

    async def get_menubot_id(self, room_id: RoomID = None, user_id: UserID = None) -> UserID:
        """Get menubot_id by room_id or user_id or user_prefix"""

        menubot_id = None

        if self.config["acd.menubot"]:
            menubot_id = self.config["acd.menubot.user_id"]
            return menubot_id

        if room_id:
            members = await self.intent.get_joined_members(room_id=room_id)
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

    async def get_agent_count(self, room_id: RoomID):
        """Get a room agent count."""
        total = 0
        agents = await self.get_agents(room_id=room_id)
        if agents:
            total = len(agents)
        return total

    async def is_a_room_with_online_agents(self, room_id: RoomID) -> bool:
        """Check if there is an online agent in the room."""
        members = await self.intent.get_joined_members(room_id=room_id)
        if not members:
            # probably an error has occurred
            self.log.debug(f"No joined members in the room [{room_id}]")
            return "unlock"

        for user_id in members:
            member_is_agent = self.is_agent(user_id)
            if not member_is_agent:
                # count only agents, not customers
                continue
            response = await self.intent.get_presence(user_id)
            if response.presence.ONLINE:
                self.log.debug(f"Online agent {user_id} in the room [{room_id}]")
                return True

        return False

    async def get_agents(self, room_id: RoomID) -> List[UserID]:
        """Get a room agent list."""
        members = None
        try:
            members = await self.intent.get_joined_members(room_id=room_id)
        except IntentError as e:
            self.log.error(e)

        if members:
            # remove bots from member list
            agents_id = self.remove_not_agents(members)
            return agents_id

        return None

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

    def is_agent(self, agent_id: UserID) -> bool:
        """Check if user_id is agent."""
        return True if agent_id.startswith(self.config["acd.agent_prefix"]) else False
