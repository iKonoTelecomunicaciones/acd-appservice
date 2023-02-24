from __future__ import annotations

import logging
from asyncio import Future, create_task, get_running_loop, sleep
from datetime import datetime
from typing import Dict, List, Optional

from mautrix.api import Method, SynapseAdminPath
from mautrix.appservice import IntentAPI
from mautrix.types import Member, RoomAlias, RoomID, UserID
from mautrix.util.logging import TraceLogger

from .commands.handler import CommandProcessor
from .config import Config
from .portal import Portal, PortalState
from .queue import Queue
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
        self, portal: Portal, queue: Queue = None, joined_message: str = None
    ) -> None:
        """If there are no online agents in the room, then loop over the agents in the campaign room
        (or control room if no campaign is provided) and invite them to the customer room

        Parameters
        ----------
        portal : Portal
            The room where the customer is.
        queue : Queue
            The queue that the customer is being distributed to.
        joined_message : str
            The message that will be sent to the customer when the agent joins the room.

        """
        json_response: Dict = {
            "data": {
                "detail": "",
                "room_id": portal.room_id,
            },
            "status": 0,
        }

        if RoomManager.is_room_locked(room_id=portal.room_id):
            self.log.debug(f"Room [{portal.room_id}] LOCKED")
            json_response["data"]["detail"] = f"Room [{portal.room_id}] LOCKED"
            json_response["status"] = 409
            return json_response

        # Send an informative message if the conversation started no within the business hour
        if await self.business_hours.is_not_business_hour():
            await self.business_hours.send_business_hours_message(room_id=portal.room_id)
            self.log.debug(f"Saving room {portal.room_id} in pending list")
            await portal.update_state(state=PortalState.ENQUEUED)
            portal.selected_option = queue.room_id
            await portal.update()

            json_response["data"]["detail"] = f"Message out of business hours"
            json_response["status"] = 409
            return json_response

        self.log.debug(f"Init process distribution for [{portal.room_id}]")

        # lock the room
        RoomManager.lock_room(room_id=portal.room_id)

        online_agents_in_room = await portal.has_online_agents()

        if online_agents_in_room == "unlock":
            RoomManager.unlock_room(room_id=portal.room_id)
            json_response["data"]["detail"] = f"No joined members in the room [{portal.room_id}]"
            json_response["status"] = 409
            return json_response

        if not online_agents_in_room:
            # if a campaign is provided, the loop is done over the agents of that campaign.
            # if campaign is None, the loop is done over the control room

            target_room_id = queue.room_id if queue else self.config["acd.available_agents_room"]

            queue: Queue = await Queue.get_by_room_id(room_id=target_room_id)

            # a task is created to not block asyncio loop
            return await self.loop_agents(
                portal=portal,
                queue=queue,
                agent_id=self.CURRENT_AGENT.get(queue.room_id),
                joined_message=joined_message,
            )
        else:
            self.log.debug(f"This room [{portal.room_id}] has online agents")
            RoomManager.unlock_room(room_id=portal.room_id)
            json_response["data"]["detail"] = f"This room [{portal.room_id}] has online agents"
            json_response["status"] = 409
            return json_response

    async def process_enqueued_rooms(self) -> None:
        """Task to run every X second looking for enqueued rooms

        Every X seconds, check if there are enqueued rooms, if there are,
        check if there are online agents in the campaign room, if there are,
        assign the agent to the enqueued room
        """
        try:
            while True:
                # Stop process enqueued rooms if the conversation is not within the business hour
                if await self.business_hours.is_not_business_hour():
                    self.log.debug(
                        (
                            f"[{PortalState.ENQUEUED.value}] rooms process is stopped,"
                            " the conversation is not within the business hour"
                        )
                    )
                    await sleep(self.config["acd.search_pending_rooms_interval"])
                    continue

                self.log.debug(f"Searching for [{PortalState.ENQUEUED.value}] rooms...")
                enqueued_portals: List[Portal] = await Portal.get_rooms_by_state_and_puppet(
                    state=PortalState.ENQUEUED, fk_puppet=self.puppet_pk
                )

                if len(enqueued_portals) > 0:
                    last_campaign_room_id = None
                    first_online_agent = None

                    for portal in enqueued_portals:
                        portal.main_intent = self.intent
                        # Se actualiza el puppet dada la sala que se tenga en pending_rooms :)
                        # que bug tan maluco le digo
                        result = await portal.get_current_agent()
                        if result:
                            self.log.debug(
                                (
                                    f"Room {portal.room_id} has already an agent, "
                                    f"removing from [{PortalState.ENQUEUED.value}] rooms..."
                                )
                            )
                            await portal.update_state(state=PortalState.PENDING)

                        else:
                            queue: Queue = await Queue.get_by_room_id(
                                room_id=portal.selected_option
                            )

                            self.log.debug(
                                "Searching for online agent in campaign "
                                f"{queue.room_id if queue else '👻'} "
                                f"to room: {portal.room_id}"
                            )

                            if queue.room_id != last_campaign_room_id:
                                first_online_agent = await queue.get_first_online_agent()
                            else:
                                self.log.debug(
                                    f"Same campaign, continue with other room waiting "
                                    "for other online agent different than last one"
                                )
                                continue

                            if first_online_agent:
                                self.log.debug(
                                    f"The agent {first_online_agent.mxid} is online to join "
                                    f"room: {portal.room_id}"
                                )
                                try:
                                    await self.process_distribution(portal, queue)
                                except Exception as e:
                                    self.log.exception(e)

                            else:
                                self.log.debug("There's no online agents yet")

                            last_campaign_room_id = queue.room_id

                else:
                    self.log.debug(f"There's no [{PortalState.ENQUEUED.value}] rooms")

                await sleep(self.config["acd.search_pending_rooms_interval"])
        except Exception as e:
            self.log.exception(e)

    async def loop_agents(
        self,
        portal: Portal,
        queue: Queue,
        agent_id: UserID,
        joined_message: str | None = None,
        transfer_author: Optional[User] = None,
    ) -> Dict:
        """It loops through all the agents in a queue, and if it finds one that is online,
        it invites them to the room

        Parameters
        ----------
        portal : Portal
            Portal = Portal
        queue : Queue
            Queue
        agent_id : UserID
            The ID of the agent to invite to the room.
        joined_message : str | None
            str | None = None
        transfer_author : Optional[User]
            The user who initiated the transfer.

        """

        json_response: Dict = {
            "data": {
                "detail": "",
                "room_id": portal.room_id,
            },
            "status": 0,
        }

        total_agents = await queue.get_agent_count()
        online_agents = 0

        # Number of agents iterated
        agent_count = 0

        self.log.debug(
            f"New agent loop in [{queue.room_id}] starting with [{agent_id if agent_id else '👻'}]"
        )

        transfer = True if transfer_author else False

        # Trying to find an agent to invite to the room.
        while True:
            agent_id = await self.get_next_agent(agent_id, queue.room_id)
            if not agent_id:
                self.log.info(f"NO AGENTS IN ROOM [{queue.room_id}]")

                if transfer_author:
                    msg = (
                        f"The room [{portal.room_id}] tried to be transferred to "
                        f"[{queue.room_id}] but it has no agents"
                    )
                    await self.intent.send_notice(room_id=portal.room_id, text=msg)
                    json_response["data"]["detail"] = msg
                else:
                    await self.show_no_agents_message(
                        customer_room_id=portal.room_id, campaign_room_id=queue.room_id
                    )
                    json_response["data"]["detail"] = "There are no agents in queue room"

                json_response["status"] = 404
                RoomManager.unlock_room(room_id=portal.room_id, transfer=transfer)
                break

            agent: User = await User.get_by_mxid(mxid=agent_id)

            # Usar get_room_members porque regresa solo una lista de UserIDs
            joined_members = await portal.get_joined_users()
            if not joined_members:
                self.log.debug(f"No joined members in the room [{portal.room_id}]")
                RoomManager.unlock_room(room_id=portal.room_id, transfer=transfer)
                break

            if len(joined_members) == 1 and joined_members[0].mxid == self.intent.mxid:
                # customer leaves when trying to connect an agent
                self.log.info("NOBODY IN THIS ROOM, I'M LEAVING")

                await portal.leave(reason="NOBODY IN THIS ROOM, I'M LEAVING")

                RoomManager.unlock_room(room_id=portal.room_id, transfer=transfer)
                break

            aux_transfer_author_mxid = transfer_author.mxid if transfer_author else ""

            if agent.mxid != aux_transfer_author_mxid:
                # Switch between presence and agent operation login using config parameter
                # to verify if agent is available to be assigned to the chat

                is_agent_available_for_assignment = await agent.is_online(queue_id=queue.id)

                if not self.config["acd.use_presence"]:
                    membership = await queue.get_membership(agent)

                    if is_agent_available_for_assignment:
                        is_agent_available_for_assignment = (
                            not membership.paused
                        ) and is_agent_available_for_assignment

                if is_agent_available_for_assignment:
                    online_agents += 1

                    await self.force_invite_agent(
                        agent_id=agent.mxid,
                        portal=portal,
                        queue=queue,
                        joined_message=joined_message,
                        transfer_author=transfer_author,
                    )
                    json_response.get("data")["detail"] = "Chat distribute successfully"
                    json_response["status"] = 200
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
                    json_response["status"] = 404
                    await self.intent.send_notice(room_id=portal.room_id, text=msg)
                else:
                    msg = (
                        "The chat could not be distributed, however, it was saved in pending rooms"
                    )
                    json_response["status"] = 202
                    await self.show_no_agents_message(
                        customer_room_id=portal.room_id, campaign_room_id=queue.room_id
                    )
                    self.log.debug(f"Saving room [{portal.room_id}] in pending list")
                    await portal.update_state(state=PortalState.ENQUEUED)

                    portal.selected_option = queue.room_id
                    await portal.update()

                RoomManager.unlock_room(room_id=portal.room_id, transfer=transfer)
                json_response["data"]["detail"] = msg
                break

            self.log.debug(f"Agent count: [{agent_count}] online_agents: [{online_agents}]")

        return json_response

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
        portal: Portal,
        agent_id: UserID,
        queue: Queue = None,
        joined_message: str = None,
        transfer_author: User = None,
    ) -> None:
        """Given the portal and the queue have the agent forcibly join the portal.

        Parameters
        ----------
        portal : Portal
            Customer room
        agent_id : UserID
            The user ID of the agent to invite
        queue : Queue
            Queue room
        joined_message : str
            When the agent enters the room, send this message
        transfer_author : User
            Who sends the transfer

        """
        # get the current event loop
        loop = get_running_loop()

        # create a new Future object.
        pending_invite = loop.create_future()

        transfer = True if transfer_author else False

        future_key = RoomManager.get_future_key(
            room_id=portal.room_id, agent_id=agent_id, transfer=transfer
        )
        # mantain an array of futures for every invite to get notification of joins
        self.PENDING_INVITES[future_key] = pending_invite
        self.log.debug(f"Futures are... [{self.PENDING_INVITES}]")

        create_task(
            self.check_agent_joined(
                portal=portal,
                queue=queue,
                pending_invite=pending_invite,
                agent_id=agent_id,
                joined_message=joined_message,
                transfer_author=transfer_author,
            )
        )

        await self.force_join_agent(portal.room_id, agent_id)

    async def check_agent_joined(
        self,
        portal: Portal,
        pending_invite: Future,
        agent_id: UserID,
        queue: Queue = None,
        joined_message: str = None,
        transfer_author: Optional[User] = None,
    ) -> None:
        """It checks if the agent has joined the room, if not,
        it kicks the agent out of the room and tries to invite the next agent

        Parameters
        ----------
        portal : Portal
            The room where the customer is waiting for an agent to join.
        pending_invite : Future
            Future object that is resolved when the agent accepts the invite.
        agent_id : UserID
            The user ID of the agent to invite.
        queue : Queue
            The queue object that the agent is being invited to.
        joined_message : str
            This is the message that will be sent to the customer when the agent joins the room.
        transfer_author : Optional[User]
            The user who transferred the chat.

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
        future_key = RoomManager.get_future_key(portal.room_id, agent_id, transfer)
        if future_key in self.PENDING_INVITES:
            del self.PENDING_INVITES[future_key]
        self.log.debug(f"futures left: {self.PENDING_INVITES}")

        self.signaling.intent = portal.main_intent
        if agent_joined:
            if queue and queue.room_id:
                self.CURRENT_AGENT[queue.room_id] = agent_id
                self.log.debug(f"[{agent_id}] ACCEPTED the invite. CHAT ASSIGNED.")
                self.log.debug(f"NEW CURRENT_AGENT : [{self.CURRENT_AGENT}]")
                self.log.debug(f"======> [{portal.room_id}] selected [{queue.room_id}]")

            # Setting the selected menu option for the customer.
            self.log.debug(f"Saving room [{portal.room_id}]")

            if queue:
                portal.selected_option = queue.room_id
                await portal.save()

            self.log.debug(f"Removing room [{portal.room_id}] from pending list")
            await portal.update_state(PortalState.PENDING)

            agent_displayname = await self.intent.get_displayname(user_id=agent_id)
            detail = ""
            if transfer_author:
                detail = f"{transfer_author.mxid} transferred {portal.room_id} to {agent_id}"

            # transfer_author can be a supervisor or admin when an open chat is transferred.
            if transfer_author is not None and transfer_author.is_agent:
                await self.room_manager.remove_user_from_room(
                    room_id=portal.room_id,
                    user_id=transfer_author.mxid,
                    reason=self.config["acd.transfer_message"].format(agentname=agent_displayname),
                )
            else:
                # kick menu bot
                self.log.debug(f"Kicking the menubot out of the room {portal.room_id}")
                try:
                    await self.room_manager.menubot_leaves(
                        room_id=portal.room_id,
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
                    await self.room_manager.send_formatted_message(room_id=portal.room_id, msg=msg)

            except Exception as e:
                self.log.exception(e)

            # set chat status to pending when the agent is asigned to the chat
            if transfer_author:
                await self.signaling.set_chat_status(
                    room_id=portal.room_id,
                    status=Signaling.PENDING,
                    campaign_room_id=queue.room_id if queue else None,
                    agent=agent_id,
                    keep_agent=False,
                )
            else:
                await self.signaling.set_chat_status(
                    room_id=portal.room_id,
                    status=Signaling.PENDING,
                    campaign_room_id=queue.room_id if queue else None,
                    agent=agent_id,
                )

            # send campaign selection event
            await self.signaling.set_selected_campaign(
                room_id=portal.room_id, campaign_room_id=queue.room_id if queue else None
            )

            # send agent chat connect
            if transfer_author:
                await self.signaling.set_chat_connect_agent(
                    room_id=portal.room_id,
                    agent=agent_id,
                    source="transfer_user" if not queue else "transfer_room",
                    campaign_room_id=queue.room_id if queue else None,
                    previous_agent=transfer_author.mxid if transfer_author.is_agent else None,
                )
            else:
                await self.signaling.set_chat_connect_agent(
                    room_id=portal.room_id,
                    agent=agent_id,
                    source="auto",
                    campaign_room_id=queue.room_id if queue else None,
                )

            RoomManager.unlock_room(room_id=portal.room_id, transfer=transfer)

        elif await portal.get_current_agent() and transfer_author is None:
            RoomManager.unlock_room(room_id=portal.room_id)
            self.log.debug(f"Unlocking room {portal.room_id}..., agent {agent_id} already in room")
        else:
            self.log.debug(f"[{agent_id}] DID NOT ACCEPT the invite. Inviting next agent ...")
            await portal.kick_user(
                user_id=agent_id,
                reason="Tiempo de espera cumplido para unirse a la conversación",
            )
            if queue:
                await self.loop_agents(
                    portal=portal,
                    queue=queue,
                    agent_id=agent_id,
                    joined_message=joined_message,
                    transfer_author=transfer_author,
                )
            else:
                # if it is a direct transfer, unlock the room
                msg = f"{agent_id} no aceptó la transferencia."
                await portal.send_notice(text=msg)
                RoomManager.unlock_room(room_id=portal.room_id, transfer=transfer)

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

    async def process_offline_selection(self, portal: Portal, msg: str):
        """If the user selects option 1, the bot will transfer the user to another agent
        in the same campaign. If the user selects option 2,
        the bot will kick the current offline agent and show the main menu

        Parameters
        ----------
        portal : Portal
            The room where the user is.
        msg : str
            The message that the user sent.

        Returns
        -------
            The return value is a boolean.
        """

        offline_menu_option = msg.split()[0]

        room_agent: User = await portal.get_current_agent()

        if offline_menu_option == "1":
            # user selected transfer to another agent in same campaign
            selected_queue = await Queue.get_by_room_id(portal.selected_option)

            if not selected_queue:
                # this can happen if the database is deleted
                selected_queue = await Queue.get_by_room_id(
                    self.config["acd.available_agents_room"]
                )

            # check if that campaign has online agents
            campaign_has_online_agent = await selected_queue.get_first_online_agent()
            if not campaign_has_online_agent:
                msg = self.config["acd.no_agents_for_transfer"]
                if msg:
                    await portal.send_formatted_message(text=msg)
                return True

            self.log.debug(f"Transferring to {selected_queue.room_id}")

            await self.commands.handle(
                room_id=portal.room_id,
                sender=room_agent,
                command="transfer",
                args_list=f"{portal.room_id} {selected_queue.room_id}".split(),
                intent=self.intent,
                is_management=portal == room_agent.management_room,
            )

        elif offline_menu_option == "2":
            # user selected kick current offline agent and see the main menu
            await self.room_manager.remove_user_from_room(
                room_id=portal.room_id,
                user_id=room_agent.mxid,
                reason=self.config["acd.offline.menu_user_selection"],
            )
            await self.signaling.set_chat_status(portal.room_id, Signaling.OPEN)
            # clear campaign in the ik.chat.campaign_selection state event
            await self.signaling.set_selected_campaign(
                room_id=portal.room_id, campaign_room_id=None
            )

            menubot_id = await self.room_manager.get_menubot_id()
            await self.room_manager.invite_menu_bot(room_id=portal.room_id, menubot_id=menubot_id)

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
