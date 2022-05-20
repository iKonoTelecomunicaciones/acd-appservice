from __future__ import annotations

import logging
from asyncio import Future, create_task, get_running_loop, sleep
from datetime import datetime
from typing import List

from mautrix.api import Method
from mautrix.appservice import IntentAPI
from mautrix.errors.base import IntentError
from mautrix.types import Member, PresenceState, RoomAlias, RoomID, UserID
from mautrix.util.logging import TraceLogger

from acd_appservice.puppet import Puppet

from .room_manager import RoomManager


class AgentManager:
    log: TraceLogger = logging.getLogger("acd.agent_manager")
    intent: IntentAPI
    room_manager: RoomManager
    # last invited agent per control room (i.e. campaigns)
    CURRENT_AGENT = {}

    # Dict of Future objects used to get notified when an agent accepts an invite
    PENDING_INVITES: dict[str, Future] = {}

    control_room_id: RoomID | None = None

    def __init__(
        self, intent: IntentAPI, control_room_id: RoomID, room_manager: RoomManager
    ) -> None:
        self.intent = intent
        self.config = room_manager.config
        self.room_manager = room_manager
        self.control_room_id = control_room_id
        self.room_manager = room_manager

    async def process_distribution(
        self, customer_room_id: RoomID, campaign_room_id: RoomID = None, joined_message: str = None
    ) -> None:
        """Start distribution process if no online agents in the room.

        If the room is locked, return. If the room is not locked, lock it.
        If there are no online agents in the room, create a task to loop over the agents in the campaign room.
        If there are online agents in the room, unlock the room

        Parameters
        ----------
        customer_room_id : RoomID
            RoomID
        campaign_room_id : RoomID
            RoomID = None
        joined_message : str
            str = None

        Returns
        -------
            The return value is a list of tuples.

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
            self.log.debug(f"This room [{customer_room_id}] doesn't have online agents")
            RoomManager.unlock_room(room_id=customer_room_id)

    async def process_pending_rooms(self) -> None:
        """Task to run every X second looking for pending rooms

        Every X seconds, check if there are pending rooms, if there are,
        check if there are online agents in the campaign room, if there are,
        assign the agent to the pending room
        """

        while True:

            self.log.debug("Searching for pending rooms...")
            # room_ids = self.bot.store.get_pending_rooms()
            customer_room_ids = await RoomManager.get_pending_rooms()

            if len(customer_room_ids) > 0:
                last_campaign_room_id = None
                online_agent = None

                for customer_room_id in customer_room_ids:
                    # Se actualiza el puppet dada la sala que se tenga en pending_rooms :)
                    # que bug tan maluco le digo
                    puppet: Puppet = await Puppet.get_customer_room_puppet(
                        room_id=customer_room_id
                    )
                    self.intent = puppet.intent
                    result = await self.get_room_agent(room_id=customer_room_id)
                    if result:
                        self.log.debug(
                            f"Room {customer_room_id} has already an agent, removing from pending rooms..."
                        )
                        # self.bot.store.remove_pending_room(room_id)
                        await RoomManager.remove_pending_room(room_id=customer_room_id)

                    else:
                        # campaign_room_id = self.bot.store.get_campaign_of_pending_room(room_id)
                        campaign_room_id = await RoomManager.get_campaign_of_pending_room(
                            customer_room_id
                        )

                        self.log.debug(
                            "Searching for online agent in campaign "
                            f"{campaign_room_id if campaign_room_id else '👻'} "
                            f"to room: {customer_room_id}"
                        )

                        if campaign_room_id != last_campaign_room_id:
                            online_agent = await self.get_online_agent_in_room(campaign_room_id)
                        else:
                            self.log.debug(
                                f"Same campaign, continue with other room waiting "
                                "for other online agent different than last one"
                            )
                            continue

                        if online_agent:
                            self.log.debug(
                                f"The agent {online_agent} is online to join "
                                f"room: {customer_room_id}"
                            )
                            try:
                                await self.process_distribution(customer_room_id, campaign_room_id)
                            except Exception as e:
                                self.log.exception(e)

                        else:
                            self.log.debug("There's no online agents yet")

                        last_campaign_room_id = campaign_room_id

            else:
                self.log.debug("There's no pending rooms")

            self.log.debug("\n")
            await sleep(self.config["acd.search_pending_rooms_interval"])

    async def loop_agents(
        self,
        customer_room_id: RoomID,
        campaign_room_id: RoomID,
        agent_id: UserID,
        joined_message: str,
    ) -> None:
        """It loops through a list of agents and tries to invite them to a room

        Parameters
        ----------
        customer_room_id : RoomID
            The room ID of the customer.
        campaign_room_id : RoomID
            The room ID of the campaign room.
        agent_id : UserID
            The ID of the agent to start the loop with.
        joined_message : str
            str
        """
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

            # Usar get_room_members porque regresa solo una lista de UserIDs
            joined_members = await self.intent.get_room_members(room_id=customer_room_id)
            if not joined_members:
                self.log.debug(f"No joined members in the room [{customer_room_id}]")
                RoomManager.unlock_room(customer_room_id)
                break

            if len(joined_members) == 1 and joined_members[0] == self.intent.mxid:
                # customer leaves when trying to connect an agent
                self.log.info("NOBODY IN THIS ROOM, I'M LEAVING")
                await self.intent.leave_room(
                    room_id=customer_room_id, reason="NOBODY IN THIS ROOM, I'M LEAVING"
                )
                RoomManager.unlock_room(customer_room_id)
                break

            if self.config["acd.force_join"] and await self.room_manager.is_in_mobile_device(
                user_id=agent_id, intent=self.intent
            ):
                # force agent join to room when agent is in mobile device
                self.log.debug(f"Agent [{agent_id}] is in mobile device")
                await self.force_invite_agent(
                    customer_room_id, agent_id, campaign_room_id, joined_message
                )
                break

            presence_response = await self.room_manager.get_user_presence(
                user_id=agent_id, intent=self.intent
            )
            self.log.debug(
                f"PRESENCE RESPONSE: "
                f"[{agent_id}] -> [{presence_response.presence if presence_response else None}]"
            )
            if presence_response and presence_response.presence == PresenceState.ONLINE:
                online_agents += 1

                await self.force_invite_agent(
                    customer_room_id, agent_id, campaign_room_id, joined_message
                )
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

                self.log.debug(f"Saving room [{customer_room_id}] in pending list")
                # self.bot.store.save_pending_room(customer_room_id, campaign_room_id) # TODO GUARDAR EN BASE DE DATOS
                await RoomManager.save_pending_room(
                    room_id=customer_room_id,
                    selected_option=campaign_room_id,
                )

                RoomManager.unlock_room(room_id=customer_room_id)
                break

            self.log.debug(f"agent count: [{agent_count}] online_agents: [{online_agents}]")

    async def get_next_agent(self, agent_id: UserID, room_id: RoomID) -> UserID:
        """It takes a room ID and an agent ID, and returns the next agent in the room

        Parameters
        ----------
        agent_id : UserID
            UserID
        room_id : RoomID
            The room ID of the room you want to get the next agent from.

        Returns
        -------
            The next agent in line.

        """
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

    async def force_invite_agent(
        self,
        room_id: RoomID,
        agent_id: UserID,
        campaign_room_id: RoomID,
        joined_message: str = None,
    ) -> None:
        """It creates a new Future object, adds it to a dictionary, and then spawns a task that waits for the Future to be set

        Parameters
        ----------
        room_id : RoomID
            RoomID
        agent_id : UserID
            UserID
        campaign_room_id : RoomID
            RoomID
        joined_message : str
            str = None,

        """
        # get the current event loop
        loop = get_running_loop()

        # create a new Future object.
        pending_invite = loop.create_future()
        future_key = RoomManager.get_future_key(room_id, agent_id)
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
    ) -> None:
        """Start a loop of x seconds that is interrupted when the agent accepts the invite.

        It checks if an agent has joined a room within a certain amount of time.
        If the agent has joined, it sets the agent as the current agent for the room,
        and if the agent has not joined, it kicks the agent and invites the next agent in the list

        Parameters
        ----------
        customer_room_id : RoomID
            The room ID of the customer.
        pending_invite : Future
            Future object that is resolved when the agent accepts the invite.
        agent_id : UserID
            The user ID of the agent to invite.
        campaign_room_id : RoomID
            The room ID of the campaign that the customer has selected.
        joined_message : str
            The message to send to the customer when the agent joins the room.

        """
        loop = get_running_loop()
        end_time = loop.time() + float(self.config["acd.agent_invite_timeout"])

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
        future_key = RoomManager.get_future_key(customer_room_id, agent_id)
        if future_key in self.PENDING_INVITES:
            del self.PENDING_INVITES[future_key]
        self.log.debug(f"futures left: {self.PENDING_INVITES}")
        if agent_joined:
            self.CURRENT_AGENT[campaign_room_id] = agent_id
            self.log.debug(f"[{agent_id}] ACCEPTED the invite. CHAT ASSIGNED.")
            self.log.debug(f"NEW CURRENT_AGENT : [{self.CURRENT_AGENT}]")
            self.log.debug(f"======> [{customer_room_id}] selected [{campaign_room_id}]")
            # self.bot.store.set_user_selected_menu(customer_room_id, campaign_room_id)
            # Setting the selected menu option for the customer.
            await RoomManager.save_room(
                room_id=customer_room_id,
                selected_option=campaign_room_id,
                puppet_mxid=self.intent.mxid,
            )

            self.log.debug(f"Removing room [{customer_room_id}] from pending list")
            # self.bot.store.remove_pending_room(customer_room_id) # TODO BASE DE DATOS
            await RoomManager.remove_pending_room(
                room_id=customer_room_id,
            )

            # kick menu bot
            await self.room_manager.kick_menubot(
                room_id=customer_room_id,
                reason=f"agent [{agent_id}] accepted invite",
                intent=self.intent,
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

        elif await self.get_room_agent(room_id=customer_room_id):
            RoomManager.unlock_room(room_id=customer_room_id)
            self.log.debug(
                f"Unlocking room {customer_room_id}..., agent {agent_id} already in room"
            )
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

    async def force_join_agent(
        self, room_id: RoomID, agent_id: UserID, room_alias: RoomAlias = None
    ) -> None:
        """It takes a room ID, an agent ID, and a room alias (optional) and forces the agent to join the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to join.
        agent_id : UserID
            The user ID of the agent you want to force join the room.
        room_alias : RoomAlias
            The alias of the room to join.

        """
        data = {"user_id": agent_id}
        try:
            api = self.intent.bot.api if self.intent.bot else self.intent.api
            await api.request(
                method=Method.POST,
                path=f"/_synapse/admin/v1/join/{room_alias if room_alias else room_id}",
                content=data,
            )
        except IntentError as e:
            self.log.error(e)

    async def show_no_agents_message(self, customer_room_id, campaign_room_id) -> None:
        """It asks the menubot to show a message to the customer saying that there are no agents available

        Parameters
        ----------
        customer_room_id
            The room ID of the customer's room.
        campaign_room_id
            The room ID of the campaign room.

        """
        menubot_id = await self.room_manager.get_menubot_id(
            intent=self.intent, room_id=customer_room_id
        )
        if menubot_id:
            await self.room_manager.send_menubot_command(
                menubot_id,
                "no_agents_message",
                self.control_room_id,
                self.intent,
                customer_room_id,
                campaign_room_id,
            )

    async def get_agent_count(self, room_id: RoomID) -> int:
        """Get a room agent count

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to get the agent count from.

        Returns
        -------
            The number of agents in the room.

        """
        total = 0
        agents = await self.get_agents(room_id=room_id)
        if agents:
            total = len(agents)
        return total

    async def is_a_room_with_online_agents(self, room_id: RoomID) -> bool:
        """It checks if there is an online agent in the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room to check.

        Returns
        -------
            A boolean value.
        """
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
            presence_response = await self.intent.get_presence(user_id)
            if presence_response.presence == PresenceState.ONLINE:
                self.log.debug(f"Online agent {user_id} in the room [{room_id}]")
                return True

        return False

    async def get_room_agent(self, room_id: RoomID) -> UserID:
        """Return the room's assigned agent

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to get the agent for.

        Returns
        -------
            The user_id of the agent assigned to the room.

        """
        agents = await self.intent.get_joined_members(room_id=room_id)
        if agents:
            for user_id in agents:
                member_is_agent = self.is_agent(agent_id=user_id)
                if member_is_agent:
                    return user_id

        return None

    async def get_online_agent_in_room(self, room_id: RoomID) -> UserID:
        """ "Return online agent from room_id."

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to get the agent from.

        Returns
        -------
            The user_id of the agent that is online.

        """
        agents = await self.get_agents(room_id)
        if not agents:
            self.log.debug(f"There's no agent in room: {room_id}")
            return None

        for agent_id in agents:
            presence_response = await self.intent.get_presence(agent_id)
            if presence_response and presence_response.presence == PresenceState.ONLINE:
                return agent_id

        return None

    async def get_agents(self, room_id: RoomID) -> List[UserID]:
        """Get a room agent list

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to get the agent list from.

        Returns
        -------
            A list of user IDs.

        """
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
        """Removes non-agents from the list of members in a room

        Parameters
        ----------
        members : dict[UserID, Member]
            dict[UserID, Member]

        Returns
        -------
            A list of user_ids that start with the agent_prefix.

        """

        only_agents: List[UserID] = []
        if members:
            # Removes non-agents
            only_agents = [
                user_id
                for user_id in members
                if user_id.startswith(self.config["acd.agent_prefix"])
            ]
        return only_agents

    def is_agent(self, agent_id: UserID) -> bool:
        """`Check if user_id is agent.`

        Parameters
        ----------
        agent_id : UserID
            The agent's ID.

        Returns
        -------
            True or False

        """
        return True if agent_id.startswith(self.config["acd.agent_prefix"]) else False
