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
from .util import BusinessHour, Util


class AgentManager:
    log: TraceLogger = logging.getLogger("acd.agent_manager")
    # last invited agent per control room (i.e. campaigns)
    CURRENT_AGENT = {}

    # Dict of Future objects used to get notified when an agent accepts an invite
    PENDING_INVITES: dict[str, Future] = {}

    def __init__(
        self,
        puppet_pk: int,
        bridge: str,
        control_room_id: RoomID,
        intent: IntentAPI,
        config: Config,
        room_manager: RoomManager,
    ) -> None:
        self.intent = intent
        self.config = config
        self.puppet_pk = puppet_pk
        self.bridge = bridge
        self.control_room_id = control_room_id
        self.signaling = Signaling(intent=self.intent, config=self.config)
        self.business_hours = BusinessHour(intent=self.intent.bot, config=self.config)
        self.log = self.log.getChild(self.intent.mxid)
        self.room_manager = room_manager
        self.commands = CommandProcessor(config=self.config)

    async def process_distribution(
        self,
        portal: Portal,
        destination: RoomID | UserID = None,
        joined_message: str = None,
        put_enqueued_portal: bool = True,
        force_distribution: bool = False,
    ) -> None:
        """This function init the process distribution of a portal to either a queue or an agent based on the given parameters.

        Parameters
        ----------
        portal : Portal
            The room where the customer is.
        destination : RoomID | UserID
            Queue room id or agent mxid where chat will be distributed
        joined_message : str
            The message that will be sent to the customer when the agent joins the room.
        put_enqueued_portal : bool
            If the chat was not distributed, should the portal be enqueued?
        force_distribution : bool
            "You want to force the agent distribution?

        Returns
        -------
            a JSON response with details about the distribution process.

        """
        if portal.is_locked:
            self.log.debug(f"Room [{portal.room_id}] LOCKED")
            json_response = Util.create_response_data(
                detail=f"Room [{portal.room_id}] LOCKED", room_id=portal.room_id, status=409
            )
            return json_response

        # TODO remove when decide what to do with business hours
        # Send an informative message if the conversation started no within the business hour
        if await self.business_hours.is_not_business_hour():
            await self.business_hours.send_business_hours_message(portal=portal)
            if Util.is_room_id(destination):
                if put_enqueued_portal:
                    self.log.debug(f"Portal [{portal.room_id}] state has been changed to ENQUEUED")
                    await portal.update_state(state=PortalState.ENQUEUED)
                portal.selected_option = destination
                await portal.update()

            json_response = Util.create_response_data(
                detail=f"Message out of business hours", room_id=portal.room_id, status=409
            )
            return json_response

        self.log.debug(f"Init process distribution for [{portal.room_id}]")

        # lock the room
        portal.lock()

        if Util.is_room_id(destination):
            queue: Queue = await Queue.get_by_room_id(destination, create=False)
            return await self.distribute_to_queue(
                portal, queue, joined_message, put_enqueued_portal
            )
        elif Util.is_user_id(destination):
            user: User = await User.get_by_mxid(destination, create=False)
            return await self.distribute_to_agent(
                portal=portal,
                agent=user,
                joined_message=joined_message,
                force_distribution=force_distribution,
            )

    async def distribute_to_agent(
        self, portal: Portal, agent: User, joined_message: str, force_distribution: bool = False
    ):
        # Check that the agent is online and unpaused.
        is_agent_available = await agent.is_available()

        if not is_agent_available and not force_distribution:
            portal.unlock()
            json_response = Util.create_response_data(
                detail=f"Agent {agent.mxid} is not available to be assigned",
                room_id=portal.room_id,
                status=409,
            )
            return json_response

        await portal.join_user(agent.mxid)
        if joined_message:
            msg = joined_message.format(agentname=await agent.get_displayname())
        else:
            msg = self.config["acd.joined_agent_message"].format(
                agentname=await agent.get_displayname()
            )
        await portal.send_formatted_message(msg)
        # set chat status to pending when the agent is asigned to the chat
        await portal.update_state(PortalState.PENDING)
        portal.unlock()

        self.log.debug(f"Kicking the menubot out of the room {portal.room_id}")
        try:
            # TODO remove this code when all clients have menuflow implemented
            menubot = await portal.get_current_menubot()
            if menubot:
                await self.room_manager.send_menubot_command(
                    menubot.mxid, "cancel_task", portal.room_id
                )
                # --------- end remove -----------
                await portal.remove_menubot(reason=f"agent [{agent.mxid}] accepted invite")
        except Exception as e:
            self.log.exception(e)

        json_response = Util.create_response_data(
            detail="Chat distribute successfully", room_id=portal.room_id, status=200
        )
        return json_response

    async def distribute_to_queue(
        self,
        portal: Portal,
        queue: Queue,
        joined_message: str = None,
        put_enqueued_portal: bool = True,
    ):
        online_agents_in_room = await portal.has_online_agents()

        if online_agents_in_room == "unlock":
            portal.unlock()
            json_response = Util.create_response_data(
                detail=f"No joined members in the room [{portal.room_id}]",
                room_id=portal.room_id,
                status=409,
            )
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
                put_enqueued_portal=put_enqueued_portal,
            )
        else:
            self.log.debug(f"This room [{portal.room_id}] has online agents")
            portal.unlock()
            json_response = Util.create_response_data(
                detail=f"This room [{portal.room_id}] has online agents",
                room_id=portal.room_id,
                status=409,
            )
            return json_response

    async def loop_agents(
        self,
        portal: Portal,
        queue: Queue,
        agent_id: UserID,
        joined_message: str | None = None,
        transfer_author: Optional[User] = None,
        put_enqueued_portal: bool = True,
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
        put_enqueued_portal : bool
            If the chat was not distributed, should the portal be enqueued?

        """

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
                    await portal.send_notice(text=msg)
                else:
                    await self.show_no_agents_message(portal=portal, queue=queue)
                    msg = "There are no agents in queue room"

                json_response = Util.create_response_data(
                    detail=msg, room_id=portal.room_id, status=404
                )
                portal.unlock(transfer)
                break

            agent: User = await User.get_by_mxid(mxid=agent_id)

            joined_members = await portal.get_joined_users()
            if not joined_members:
                self.log.debug(f"No joined members in the room [{portal.room_id}]")
                portal.unlock(transfer)
                break

            if len(joined_members) == 1 and joined_members[0].mxid == self.intent.mxid:
                # customer leaves when trying to connect an agent
                self.log.info("NOBODY IN THIS ROOM, I'M LEAVING")

                await portal.leave(reason="NOBODY IN THIS ROOM, I'M LEAVING")

                portal.unlock(transfer)
                break

            transfer_author_mxid = transfer_author.mxid if transfer_author else ""
            if agent.mxid != transfer_author_mxid:
                # Switch between presence and agent operation login using config parameter
                # to verify if agent is available to be assigned to the chat
                if self.config["acd.use_presence"]:
                    is_agent_available_for_assignment = await agent.is_online(queue_id=queue.id)
                else:
                    is_agent_available_for_assignment = await agent.is_online(
                        queue_id=queue.id
                    ) and not await agent.is_paused(queue_id=queue.id)

                    self.log.debug(
                        (
                            f"The agent {agent.mxid} is paused "
                            f"[{await agent.is_paused(queue_id=queue.id)}] in the queue "
                            f"[{queue.room_id}]"
                        )
                    )

                if is_agent_available_for_assignment:
                    online_agents += 1

                    await self.force_invite_agent(
                        agent_id=agent.mxid,
                        portal=portal,
                        queue=queue,
                        joined_message=joined_message,
                        transfer_author=transfer_author,
                    )

                    # Set current agent in queue to avoid distribute
                    # two chats to the same agent in distribution process,
                    # it is useful in enqueued portals to have a clean distribution
                    if not transfer:
                        self.CURRENT_AGENT[queue.room_id] = agent_id

                    json_response = Util.create_response_data(
                        detail="Chat distribute successfully", room_id=portal.room_id, status=200
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
                    status = 404
                    await portal.send_notice(text=msg)
                else:
                    msg = "The chat could not be distributed"
                    status = 202
                    await self.show_no_agents_message(portal=portal, queue=queue)
                    if put_enqueued_portal:
                        msg = f"{msg}, however, it was enqueued"
                        self.log.debug(
                            f"Portal [{portal.room_id}] state has been changed to ENQUEUED"
                        )
                        await portal.update_state(state=PortalState.ENQUEUED)

                    portal.selected_option = queue.room_id
                    await portal.update()

                portal.unlock(transfer)
                json_response = Util.create_response_data(
                    detail=msg, room_id=portal.room_id, status=status
                )
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

        future_key = Util.get_future_key(
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
        future_key = Util.get_future_key(portal.room_id, agent_id, transfer)
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
                await portal.remove_member(
                    member=transfer_author.mxid,
                    reason=self.config["acd.transfer_message"].format(agentname=agent_displayname),
                )
            else:
                # kick menu bot
                self.log.debug(f"Kicking the menubot out of the room {portal.room_id}")
                try:
                    # TODO remove this code when all clients have menuflow implemented
                    menubot = await portal.get_current_menubot()
                    if menubot:
                        await self.room_manager.send_menubot_command(
                            menubot.mxid, "cancel_task", portal.room_id
                        )
                        # --------- end remove -----------
                        await portal.remove_menubot(
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
                    await portal.send_formatted_message(text=msg)

            except Exception as e:
                self.log.exception(e)

            # set chat status to pending when the agent is asigned to the chat
            await portal.update_state(PortalState.PENDING)
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

            portal.unlock(transfer)

        elif await portal.get_current_agent() and transfer_author is None:
            portal.unlock(transfer)
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
                portal.unlock(transfer)

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

    # TODO remove this code when all clients have menuflow implemented
    async def show_no_agents_message(self, portal: Portal, queue: Queue) -> None:
        """It asks the menubot to show a message to the customer saying that there are no agents available

        Parameters
        ----------
        customer_room_id
            The room ID of the customer's room.
        campaign_room_id
            The room ID of the campaign room.

        """
        menubot = await portal.get_current_menubot()
        if menubot:
            await self.room_manager.send_menubot_command(
                menubot.mxid,
                "no_agents_message",
                portal.room_id,
                queue.room_id,
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
                is_management=portal.room_id == room_agent.management_room,
            )

        elif offline_menu_option == "2":
            # user selected kick current offline agent and see the main menu
            await portal.remove_member(
                member=room_agent.mxid,
                reason=self.config["acd.offline.menu_user_selection"],
            )
            await self.signaling.set_chat_status(portal.room_id, Signaling.OPEN)
            # clear campaign in the ik.chat.campaign_selection state event
            await self.signaling.set_selected_campaign(
                room_id=portal.room_id, campaign_room_id=None
            )

            menubot_id = await self.room_manager.get_menubot_id()
            await portal.add_menubot(menubot_id)
        else:
            # if user enters an invalid option, shows offline menu again
            return False

        return True

    async def process_offline_agent(self, portal: Portal, room_agent: User):
        """If the agent is offline, the bot will send a message to the user and then either
        transfer the user to another agent in the same campaign or put the user in the offline menu

        Parameters
        ----------
        portal : Portal
            The room of the room where the agent is offline.
        room_agent : User
            The user of the agent who is offline
        last_active_ago : int
            The time in milliseconds since the agent was last active in the room.

        Returns
        -------
            The return value of the function is the return value of the last expression
            evaluated in the function.

        """

        action = self.config["acd.offline.agent_action"]
        self.log.debug(f"Agent {room_agent.mxid} OFFLINE in {portal.room_id} --> {action}")

        agent_displayname = await room_agent.get_displayname()
        msg = self.config["acd.offline.agent_message"].format(agentname=agent_displayname)
        if msg:
            await portal.send_formatted_message(text=msg)

        if action == "keep":
            return
        elif action == "transfer":
            # transfer to another agent in same campaign
            user_selected_campaign = portal.selected_option
            if not user_selected_campaign:
                # this can happen if the database is deleted
                user_selected_campaign = self.config["acd.available_agents_room"]

            self.log.debug(f"Transferring to {user_selected_campaign}")

            await self.commands.handle(
                room_id=portal.room_id,
                sender=room_agent,
                command="transfer",
                args_list=[portal.room_id, user_selected_campaign],
                intent=self.intent,
                is_management=portal.room_id == room_agent.management_room,
            )

        elif action == "menu":
            self.room_manager.put_in_offline_menu(portal.room_id)
            await self.show_offline_menu(agent_displayname=agent_displayname, portal=portal)

    async def show_offline_menu(self, agent_displayname: str, portal: Portal):
        """It takes the agent's display name and returns a formatted string containing the offline menu

        Parameters
        ----------
        agent_displayname : str
            The name of the agent that the user is chatting with.
        portal: Portal
            The portal where will be send the offline menu

        Returns
        -------
            A string with the formatted offline menu.

        """

        menu = self.config["acd.offline.menu.header"].format(agentname=agent_displayname)
        menu_options = self.config["acd.offline.menu.options"]
        for key, value in menu_options.items():
            menu += f"<b>{key}</b>. "
            menu += f"{value['text']}<br>"

        await portal.send_formatted_message(text=menu)
