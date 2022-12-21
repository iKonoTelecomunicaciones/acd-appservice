from __future__ import annotations

import logging
from asyncio import Future, create_task, get_running_loop, sleep
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import IntentAPI
from mautrix.errors.base import IntentError
from mautrix.types import Member, PresenceState, RoomAlias, RoomID, UserID
from mautrix.util.logging import TraceLogger

from .commands.handler import CommandProcessor
from .config import Config
from .queue import Queue
from .queue_membership import QueueMembership, QueueMembershipState
from .room_manager import RoomManager
from .signaling import Signaling
from .user import User
from .util import BusinessHour


class AgentManager:
    log: TraceLogger = logging.getLogger("acd.agent_manager")
    # last invited agent per control room (i.e. campaigns)
    CURRENT_AGENT = {}

    # Dict of Future objects used to get notified when an agent accepts an invite
    PENDING_INVITES: dict[str, Future] = {}

    def __init__(
        self,
        puppet_pk: int,
        control_room_id: RoomID,
        intent: IntentAPI,
        config: Config,
        room_manager: RoomManager,
    ) -> None:
        self.intent = intent
        self.config = config
        self.puppet_pk = puppet_pk
        self.control_room_id = control_room_id
        self.signaling = Signaling(intent=self.intent, config=self.config)
        self.business_hours = BusinessHour(
            intent=self.intent.bot, config=self.config, room_manager=room_manager
        )
        self.log = self.log.getChild(self.intent.mxid)
        self.room_manager = room_manager
        self.commands = CommandProcessor(config=self.config)

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

        # Send an informative message if the conversation started no within the business hour
        if await self.business_hours.is_not_business_hour():
            await self.business_hours.send_business_hours_message(room_id=customer_room_id)
            self.log.debug(f"Saving room {customer_room_id} in pending list")
            await RoomManager.save_pending_room(
                room_id=customer_room_id,
                selected_option=campaign_room_id,
                puppet_pk=self.puppet_pk,
            )
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

            target_room_id = (
                campaign_room_id if campaign_room_id else self.config["acd.available_agents_room"]
            )

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
            self.log.debug(f"This room [{customer_room_id}] have online agents")
            RoomManager.unlock_room(room_id=customer_room_id)

    async def process_pending_rooms(self) -> None:
        """Task to run every X second looking for pending rooms

        Every X seconds, check if there are pending rooms, if there are,
        check if there are online agents in the campaign room, if there are,
        assign the agent to the pending room
        """
        while True:

            # Stop process pending rooms if the conversation is not within the business hour
            if await self.business_hours.is_not_business_hour():
                self.log.debug(
                    "Pending rooms process is stopped, the conversation is not within the business hour"
                )
                await sleep(self.config["acd.search_pending_rooms_interval"])
                continue

            self.log.debug("Searching for pending rooms...")
            customer_room_ids = await RoomManager.get_pending_rooms(puppet_pk=self.puppet_pk)

            if len(customer_room_ids) > 0:
                last_campaign_room_id = None
                online_agent = None

                for customer_room_id in customer_room_ids:
                    # Se actualiza el puppet dada la sala que se tenga en pending_rooms :)
                    # que bug tan maluco le digo
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

            await sleep(self.config["acd.search_pending_rooms_interval"])

    async def loop_agents(
        self,
        customer_room_id: RoomID,
        campaign_room_id: RoomID,
        agent_id: UserID,
        joined_message: str | None = None,
        transfer_author: Optional[UserID] = None,
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
            Agent join message to be displayed in the room
        transfer_author: UserID
            if it is a transfer, then it will be the author of this
        """
        total_agents = await self.get_agent_count(room_id=campaign_room_id)
        online_agents = 0

        # Number of agents iterated
        agent_count = 0

        self.log.debug(
            f"New agent loop in [{campaign_room_id}] starting with [{agent_id if agent_id else '👻'}]"
        )

        transfer = True if transfer_author else False

        # Trying to find an agent to invite to the room.
        while True:
            agent_id = await self.get_next_agent(agent_id, campaign_room_id)
            if not agent_id:
                self.log.info(f"NO AGENTS IN ROOM [{campaign_room_id}]")

                if transfer_author:
                    msg = (
                        f"The room [{customer_room_id}] tried to be transferred to "
                        f"[{campaign_room_id}] but it has no agents"
                    )
                    await self.intent.send_notice(room_id=customer_room_id, text=msg)
                else:
                    await self.show_no_agents_message(
                        customer_room_id=customer_room_id, campaign_room_id=campaign_room_id
                    )

                RoomManager.unlock_room(room_id=customer_room_id, transfer=transfer)
                break

            # Usar get_room_members porque regresa solo una lista de UserIDs
            joined_members = await self.intent.get_room_members(room_id=customer_room_id)
            if not joined_members:
                self.log.debug(f"No joined members in the room [{customer_room_id}]")
                RoomManager.unlock_room(room_id=customer_room_id, transfer=transfer)
                break

            if len(joined_members) == 1 and joined_members[0] == self.intent.mxid:
                # customer leaves when trying to connect an agent
                self.log.info("NOBODY IN THIS ROOM, I'M LEAVING")
                await self.intent.leave_room(
                    room_id=customer_room_id, reason="NOBODY IN THIS ROOM, I'M LEAVING"
                )
                RoomManager.unlock_room(room_id=customer_room_id, transfer=transfer)
                break

            if agent_id != transfer_author:
                # Switch between presence and agent operation login using config parameter
                # to verify if agent is available to be assigned to the chat
                is_agent_available_for_assignment: bool = False
                if self.config["acd.use_presence"]:
                    presence_response = await self.get_agent_presence(agent_id=agent_id)
                    is_agent_available_for_assignment = (
                        presence_response and presence_response.presence == PresenceState.ONLINE
                    )
                else:
                    presence_response = await self.get_agent_status(
                        queue_room_id=campaign_room_id, agent_id=agent_id
                    )

                    if (
                        presence_response
                        and presence_response.get("presence") == QueueMembershipState.Online.value
                    ):
                        paused_response = await self.get_agent_pause_status(
                            queue_room_id=campaign_room_id, agent_id=agent_id
                        )
                        is_agent_available_for_assignment = not paused_response.get("paused")
                        self.log.debug(
                            "PAUSE STATE: "
                            f"[{agent_id}] -> "
                            f"[{'paused' if paused_response.get('paused') else 'unpause'}]"
                        )

                self.log.debug(
                    f"PRESENCE RESPONSE: "
                    f"[{agent_id}] -> "
                    f"""[{presence_response.get('presence') or presence_response.presence
                    if presence_response else None}]"""
                )

                if is_agent_available_for_assignment:
                    online_agents += 1

                    await self.force_invite_agent(
                        room_id=customer_room_id,
                        agent_id=agent_id,
                        campaign_room_id=campaign_room_id,
                        joined_message=joined_message,
                        transfer_author=transfer_author,
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

                if transfer_author:
                    msg = self.config["acd.no_agents_for_transfer"]
                    await self.intent.send_notice(room_id=customer_room_id, text=msg)
                else:
                    await self.show_no_agents_message(
                        customer_room_id=customer_room_id, campaign_room_id=campaign_room_id
                    )

                if not transfer_author:
                    self.log.debug(f"Saving room [{customer_room_id}] in pending list")
                    await RoomManager.save_pending_room(
                        room_id=customer_room_id,
                        selected_option=campaign_room_id,
                        puppet_pk=self.puppet_pk,
                    )

                RoomManager.unlock_room(room_id=customer_room_id, transfer=transfer)
                break

            self.log.debug(f"Agent count: [{agent_count}] online_agents: [{online_agents}]")

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
        try:
            members = await self.intent.bot.get_joined_members(room_id)
        except Exception as e:
            self.log.error(e)
            return

        # print([member.user_id for member in members])
        if members:
            # remove bots from member list
            members = self.remove_not_agents(members)

            # if members is empty after bots removed, return None
            if not members:
                return

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

        return

    async def force_invite_agent(
        self,
        room_id: RoomID,
        agent_id: UserID,
        campaign_room_id: RoomID = None,
        joined_message: str = None,
        transfer_author: UserID = None,
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
            Agent join message to be displayed in the room
        transfer_author: UserID
            if it is a transfer, then it will be the author of this

        """
        # get the current event loop
        loop = get_running_loop()

        # create a new Future object.
        pending_invite = loop.create_future()

        transfer = True if transfer_author else False

        future_key = RoomManager.get_future_key(
            room_id=room_id, agent_id=agent_id, transfer=transfer
        )
        # mantain an array of futures for every invite to get notification of joins
        self.PENDING_INVITES[future_key] = pending_invite
        self.log.debug(f"Futures are... [{self.PENDING_INVITES}]")

        create_task(
            self.check_agent_joined(
                customer_room_id=room_id,
                pending_invite=pending_invite,
                agent_id=agent_id,
                campaign_room_id=campaign_room_id,
                joined_message=joined_message,
                transfer_author=transfer_author,
            )
        )

        await self.force_join_agent(room_id, agent_id)

    async def check_agent_joined(
        self,
        customer_room_id: RoomID,
        pending_invite: Future,
        agent_id: UserID,
        campaign_room_id: RoomID = None,
        joined_message: str = None,
        transfer_author: Optional[UserID] = None,
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

        transfer = True if transfer_author else False

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
        future_key = RoomManager.get_future_key(customer_room_id, agent_id, transfer)
        if future_key in self.PENDING_INVITES:
            del self.PENDING_INVITES[future_key]
        self.log.debug(f"futures left: {self.PENDING_INVITES}")

        self.signaling.intent = self.intent
        if agent_joined:
            if campaign_room_id:
                self.CURRENT_AGENT[campaign_room_id] = agent_id
                self.log.debug(f"[{agent_id}] ACCEPTED the invite. CHAT ASSIGNED.")
                self.log.debug(f"NEW CURRENT_AGENT : [{self.CURRENT_AGENT}]")
                self.log.debug(f"======> [{customer_room_id}] selected [{campaign_room_id}]")

            # Setting the selected menu option for the customer.
            self.log.debug(f"Saving room [{customer_room_id}]")
            await RoomManager.save_room(
                room_id=customer_room_id,
                selected_option=campaign_room_id,
                puppet_pk=self.puppet_pk,
                change_selected_option=True if campaign_room_id else False,
            )
            self.log.debug(f"Removing room [{customer_room_id}] from pending list")
            await RoomManager.remove_pending_room(
                room_id=customer_room_id,
            )

            agent_displayname = await self.intent.get_displayname(user_id=agent_id)
            detail = ""
            if transfer_author:
                detail = f"{transfer_author} transferred {customer_room_id} to {agent_id}"

            # transfer_author can be a supervisor or admin when an open chat is transferred.
            if transfer_author is not None and self.is_agent(transfer_author):
                await self.room_manager.remove_user_from_room(
                    room_id=customer_room_id,
                    user_id=transfer_author,
                    reason=self.config["acd.transfer_message"].format(agentname=agent_displayname),
                )
            else:
                # kick menu bot
                self.log.debug(f"Kicking the menubot out of the room {customer_room_id}")
                try:
                    await self.room_manager.menubot_leaves(
                        room_id=customer_room_id,
                        reason=detail if detail else f"agent [{agent_id}] accepted invite",
                    )
                except Exception as e:
                    self.log.exception(e)
            try:
                msg = ""
                if transfer_author:
                    msg = self.config["acd.transfer_message"].format(agentname=agent_displayname)
                elif joined_message:
                    msg = joined_message.format(agentname=agent_displayname)
                else:
                    msg = self.config["acd.joined_agent_message"].format(
                        agentname=agent_displayname
                    )

                if msg:
                    await self.room_manager.send_formatted_message(
                        room_id=customer_room_id, msg=msg
                    )

            except Exception as e:
                self.log.exception(e)

            # set chat status to pending when the agent is asigned to the chat
            if transfer_author:
                await self.signaling.set_chat_status(
                    room_id=customer_room_id,
                    status=Signaling.PENDING,
                    campaign_room_id=campaign_room_id,
                    agent=agent_id,
                    keep_agent=False,
                )
            else:
                await self.signaling.set_chat_status(
                    room_id=customer_room_id,
                    status=Signaling.PENDING,
                    campaign_room_id=campaign_room_id,
                    agent=agent_id,
                )

            # send campaign selection event
            await self.signaling.set_selected_campaign(
                room_id=customer_room_id, campaign_room_id=campaign_room_id
            )

            # send agent chat connect
            if transfer_author:
                await self.signaling.set_chat_connect_agent(
                    room_id=customer_room_id,
                    agent=agent_id,
                    source="transfer_user" if not campaign_room_id else "transfer_room",
                    campaign_room_id=campaign_room_id,
                    previous_agent=transfer_author if self.is_agent(transfer_author) else None,
                )
            else:
                await self.signaling.set_chat_connect_agent(
                    room_id=customer_room_id,
                    agent=agent_id,
                    source="auto",
                    campaign_room_id=campaign_room_id,
                )

            RoomManager.unlock_room(room_id=customer_room_id, transfer=transfer)

        elif await self.get_room_agent(room_id=customer_room_id) and transfer_author is None:
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
            if campaign_room_id:
                await self.loop_agents(
                    customer_room_id=customer_room_id,
                    campaign_room_id=campaign_room_id,
                    agent_id=agent_id,
                    joined_message=joined_message,
                    transfer_author=transfer_author,
                )
            else:
                # if it is a direct transfer, unlock the room
                msg = f"{agent_displayname} no aceptó la transferencia."
                await self.intent.send_notice(room_id=customer_room_id, text=msg)
                RoomManager.unlock_room(room_id=customer_room_id, transfer=transfer)

    async def force_join_agent(
        self, room_id: RoomID, agent_id: UserID, room_alias: RoomAlias = None
    ) -> None:
        """It takes a room ID, an agent ID, and a room alias (optional) and
        forces the agent to join the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to join.
        agent_id : UserID
            The user ID of the agent you want to force join the room.
        room_alias : RoomAlias
            The alias of the room to join.

        """
        api = self.intent.bot.api if self.intent.bot else self.intent.api
        # Trying to join a room.
        for attempt in range(0, 10):
            self.log.debug(
                f"Attempt # {attempt} trying the force join room: {room_id} :: agent: {agent_id}"
            )
            try:
                await api.request(
                    method=Method.POST,
                    path=SynapseAdminPath.v1.join[room_alias if room_alias else room_id],
                    content={"user_id": agent_id},
                )
                break
            except Exception as e:
                self.log.warning(e)

            await sleep(1)

    async def show_no_agents_message(self, customer_room_id, campaign_room_id) -> None:
        """It asks the menubot to show a message to the customer saying that there are no agents available

        Parameters
        ----------
        customer_room_id
            The room ID of the customer's room.
        campaign_room_id
            The room ID of the campaign room.

        """
        menubot_id = await self.room_manager.get_menubot_id()
        if menubot_id:
            await self.room_manager.send_menubot_command(
                menubot_id,
                "no_agents_message",
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

            # Switch between presence and agent operation login using config parameter
            # to verify if someone agent are online into room
            if self.config["acd.use_presence"]:
                presence_response = await self.get_agent_presence(agent_id=user_id)
                is_agent_online = (
                    presence_response and presence_response.presence == PresenceState.ONLINE
                )
            else:
                login_response = await self.get_agent_status(agent_id=user_id)
                is_agent_online = (
                    login_response.get("presence") == QueueMembershipState.Online.value
                )

            if is_agent_online:
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

    async def get_agent_presence(self, agent_id: UserID) -> PresenceState:
        """Returns the presence state of the agent with the given ID

        Parameters
        ----------
        agent_id : UserID
            The ID of the agent you want to get the presence of.

        Returns
        -------
            PresenceState

        """
        self.log.debug(f"Checking presence for....... [{agent_id}]")
        response = None
        try:
            response = await self.intent.bot.get_presence(agent_id)
            self.log.debug(f"Presence for....... [{agent_id}] is [{response.presence}]")
        except Exception as e:
            self.log.exception(e)

        return response

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
            # Switch between presence and agent operation login using config parameter
            # to verify if agent is logged in
            if self.config["acd.use_presence"]:
                presence_response = await self.get_agent_presence(agent_id=agent_id)
                is_agent_online = (
                    presence_response and presence_response.presence == PresenceState.ONLINE
                )
            else:
                login_response = await self.get_agent_status(
                    queue_room_id=room_id, agent_id=agent_id
                )

                paused_response = await self.get_agent_pause_status(
                    queue_room_id=room_id, agent_id=agent_id
                )
                is_agent_online = login_response.get(
                    "presence"
                ) == QueueMembershipState.Online.value and not paused_response.get("paused")

            if is_agent_online:
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
            members = await self.intent.bot.get_joined_members(room_id=room_id)
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

    async def process_offline_selection(self, room_id: RoomID, msg: str):
        """If the user selects option 1, the bot will transfer the user to another agent
        in the same campaign. If the user selects option 2,
        the bot will kick the current offline agent and show the main menu

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room where the user is.
        msg : str
            The message that the user sent.

        Returns
        -------
            The return value is a boolean.
        """

        offline_menu_option = msg.split()[0]
        room_agent = await self.get_room_agent(room_id=room_id)
        if offline_menu_option == "1":
            # user selected transfer to another agent in same campaign

            user_selected_campaign = await self.room_manager.get_campaign_of_room(room_id=room_id)

            if not user_selected_campaign:
                # this can happen if the database is deleted
                user_selected_campaign = self.config["acd.available_agents_room"]

            # check if that campaign has online agents
            campaign_has_online_agent = await self.get_online_agent_in_room(
                room_id=user_selected_campaign
            )
            if not campaign_has_online_agent:
                msg = self.config["acd.no_agents_for_transfer"]
                if msg:
                    await self.room_manager.send_formatted_message(room_id=room_id, msg=msg)
                return True

            self.log.debug(f"Transferring to {user_selected_campaign}")

            user: User = await User.get_by_mxid(room_agent)

            await self.commands.handle(
                room_id=room_id,
                sender=user,
                command="transfer",
                args_list=f"{room_id} {user_selected_campaign}".split(),
                intent=self.intent,
                is_management=room_id == user.management_room,
            )

        elif offline_menu_option == "2":
            # user selected kick current offline agent and see the main menu
            await self.room_manager.remove_user_from_room(
                room_id=room_id,
                user_id=room_agent,
                reason=self.config["acd.offline.menu_user_selection"],
            )
            await self.signaling.set_chat_status(room_id, Signaling.OPEN)
            # clear campaign in the ik.chat.campaign_selection state event
            await self.signaling.set_selected_campaign(room_id=room_id, campaign_room_id=None)

            menubot_id = await self.room_manager.get_menubot_id()
            await self.room_manager.invite_menu_bot(room_id=room_id, menubot_id=menubot_id)

        else:
            # if user enters an invalid option, shows offline menu again
            return False

        return True

    async def process_offline_agent(self, room_id: RoomID, room_agent: UserID):
        """If the agent is offline, the bot will send a message to the user and then either
        transfer the user to another agent in the same campaign or put the user in the offline menu

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room where the agent is offline.
        room_agent : UserID
            The user ID of the agent who is offline
        last_active_ago : int
            The time in milliseconds since the agent was last active in the room.

        Returns
        -------
            The return value of the function is the return value of the last expression
            evaluated in the function.

        """

        action = self.config["acd.offline.agent_action"]
        self.log.debug(f"Agent {room_agent} OFFLINE in {room_id} --> {action}")

        agent_displayname = await self.intent.get_displayname(user_id=room_agent)
        msg = self.config["acd.offline.agent_message"].format(agentname=agent_displayname)
        if msg:
            await self.room_manager.send_formatted_message(room_id=room_id, msg=msg)

        if action == "keep":
            return
        elif action == "transfer":
            # transfer to another agent in same campaign
            user_selected_campaign = await self.room_manager.get_campaign_of_room(room_id=room_id)
            if not user_selected_campaign:
                # this can happen if the database is deleted
                user_selected_campaign = self.config["acd.available_agents_room"]
            self.log.debug(f"Transferring to {user_selected_campaign}")

            user: User = await User.get_by_mxid(room_agent)

            await self.commands.handle(
                room_id=room_id,
                sender=user,
                command="transfer",
                args_list=f"{room_id} {user_selected_campaign}".split(),
                intent=self.intent,
                is_management=room_id == user.management_room,
            )

        elif action == "menu":
            self.room_manager.put_in_offline_menu(room_id)
            await self.show_offline_menu(agent_displayname=agent_displayname, room_id=room_id)

    async def show_offline_menu(self, agent_displayname: str, room_id: RoomID):
        """It takes the agent's display name and returns a formatted string containing the offline menu

        Parameters
        ----------
        agent_displayname : str
            The name of the agent that the user is chatting with.
        room_id: RoomID
            The room where will be send the offline menu

        Returns
        -------
            A string with the formatted offline menu.

        """

        menu = self.config["acd.offline.menu.header"].format(agentname=agent_displayname)
        menu_options = self.config["acd.offline.menu.options"]
        for key, value in menu_options.items():
            menu += f"<b>{key}</b>. "
            menu += f"{value['text']}<br>"

        await self.room_manager.send_formatted_message(room_id=room_id, msg=menu)

    async def get_agent_status(
        self, agent_id: UserID, queue_room_id: Optional[RoomID] = None
    ) -> Dict:
        """> This function checks if the agent is logged in to the queue

        Parameters
        ----------
        agent_id : UserID
            The Matrix ID of the agent you want to check.
        queue_room_id : Optional[RoomID]
            The room ID of the room the user is in.

        Returns
        -------
            A Dict.

        """

        agent_user: User = await User.get_by_mxid(agent_id, create=False)
        response = {
            "presence": QueueMembershipState.Offline.value,
            "state_date": datetime.now().timestamp(),
        }
        if not agent_user:
            self.log.debug(
                f"Agent {agent_id} does not exist as acd-user. "
                "Check that agent is member of a queue room"
            )
            return response

        if queue_room_id:
            queue: Queue = await Queue.get_by_room_id(queue_room_id, create=False)
            if not queue:
                return response

            membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
                fk_user=agent_user.id, fk_queue=queue.id, create=False
            )

            if membership:
                state_date = (
                    datetime.timestamp(membership.state_date) if membership.state_date else None
                )

                response = {
                    "presence": membership.state,
                    "state_date": state_date,
                }
        else:
            memberships: List[dict] = await QueueMembership.get_user_memberships(
                fk_user=agent_user.id
            )
            if memberships:
                for membership in memberships:
                    if membership.get("state") == QueueMembershipState.Online.value:
                        state_date = (
                            datetime.timestamp(membership.get("state_date"))
                            if membership.get("state_date")
                            else None
                        )
                        response = {
                            "presence": membership.get("state"),
                            "state_date": state_date,
                        }
                        break

        return response

    async def get_agent_pause_status(self, agent_id: UserID, queue_room_id: RoomID) -> Dict:
        """> This function returns a dictionary with the pause status of an agent in a queue

        Parameters
        ----------
        agent_id : UserID
            The Matrix ID of the agent
        queue_room_id : RoomID
            The room ID of the queue you want to get the pause status of.

        Returns
        -------
            A dictionary with the pause status and the pause date.

        """

        response = {
            "paused": False,
            "pause_date": datetime.now().timestamp(),
        }
        agent_user: User = await User.get_by_mxid(agent_id, create=False)
        queue: Queue = await Queue.get_by_room_id(queue_room_id, create=False)
        if not agent_user or not queue:
            self.log.debug(
                f"Agent {agent_id} does not exist as acd-user "
                f"or queue {queue_room_id} does not exists"
            )
            return response

        membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
            fk_user=agent_user.id, fk_queue=queue.id, create=False
        )
        if membership:
            ts_pause_date = (
                datetime.timestamp(membership.pause_date) if membership.pause_date else None
            )
            response["paused"] = membership.paused
            response["pause_date"] = ts_pause_date

        return response
