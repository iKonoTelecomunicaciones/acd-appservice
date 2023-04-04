from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..portal import Portal, PortalState
from ..puppet import Puppet
from ..signaling import Signaling
from ..user import User
from ..util import ACDEventsType, ACDPortalEvents, ResolveEvent
from .handler import CommandArg, CommandEvent, CommandProcessor, command_handler

user_id = CommandArg(
    name="user_id",
    help_text="User who is solving the room",
    is_required=True,
    example="@user_id:foo.com",
)

send_message = CommandArg(
    name="send_message",
    help_text="Should I send a resolution message?",
    is_required=False,
    example="`yes` | `y` | `1` | `no` | `n` | `0`",
)

room_id = CommandArg(
    name="room_id",
    help_text="Room to be resolved",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[user_id, send_message],
)


@command_handler(
    name="resolve",
    help_text=("Command resolving a chat, ejecting the supervisor and the agent"),
    help_args=[room_id],
)
async def resolve(evt: CommandEvent) -> Dict:
    """It kicks the agent and menubot from the chat,
    sets the chat status to resolved, and sends a notice to the user

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dictionary with the following keys:

    """

    try:
        customer_room_id = evt.args_list[0]
        user_id = evt.args_list[1]
    except IndexError:
        detail = "You have not all arguments"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    try:
        send_message = evt.args_list[2]
    except IndexError:
        send_message = "n"

    if send_message.lower() in ["yes", "y", "1"]:
        send_message = True
    else:
        send_message = False

    evt.log.debug(
        (
            f"The user {user_id} is resolving "
            f"the room {customer_room_id}, send_message? // {send_message} "
        )
    )

    if not await Portal.is_portal(customer_room_id):
        detail = "Group queues or control rooms cannot be resolved."
        evt.log.error(detail)
        await evt.intent.send_notice(room_id=customer_room_id, text=detail)
        return

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)

    portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )
    agent = await portal.get_current_agent()

    try:
        if agent:
            await portal.remove_member(
                member=agent.mxid, reason=puppet.config["acd.resolve_chat.notice"]
            )
        supervisors = puppet.config["acd.supervisors_to_invite.invitees"]
        if supervisors:
            for supervisor_id in supervisors:
                await portal.remove_member(
                    member=supervisor_id, reason=puppet.config["acd.resolve_chat.notice"]
                )
    except Exception as e:
        evt.log.warning(e)

    # TODO Remove when all clients have menuflow
    menubot = await portal.get_current_menubot()
    if menubot:
        await puppet.room_manager.send_menubot_command(menubot.mxid, "cancel_task", portal.room_id)
        # -------- end remove -------
        # When the supervisor resolves an open chat, menubot is still in the chat
        await portal.remove_menubot(reason=puppet.config["acd.resolve_chat.notice"])

    resolve_event = ResolveEvent(
        event_type=ACDEventsType.PORTAL,
        event=ACDPortalEvents.Resolve,
        state=PortalState.RESOLVED,
        prev_state=portal.state,
        sender=evt.sender.mxid,
        room_id=portal.room_id,
        acd=puppet.mxid,
        customer_mxid=portal.creator,
        agent_mxid=user_id,
        reason=None,
    )
    await resolve_event.send()

    # set chat status to resolved
    await portal.update_state(PortalState.RESOLVED)

    await puppet.agent_manager.signaling.set_chat_status(
        room_id=portal.room_id, status=Signaling.RESOLVED, agent=user_id
    )

    # clear campaign in the ik.chat.campaign_selection state event
    await puppet.agent_manager.signaling.set_selected_campaign(
        room_id=portal.room_id, campaign_room_id=None
    )

    if send_message is not None:
        resolve_chat_params = puppet.config["acd.resolve_chat"]
        if send_message:
            args = [portal.room_id, resolve_chat_params["message"]]
            await evt.processor.handle(
                sender=evt.sender,
                command="template",
                args_list=args,
                is_management=portal.room_id == evt.sender.management_room,
                intent=puppet.intent,
                room_id=evt.room_id,
            )

        await portal.send_notice(text=resolve_chat_params["notice"])


class BulkResolve:
    log: TraceLogger = logging.getLogger("acd.bulk_resolve")
    room_ids = set()
    active_resolve = False

    def __init__(self, config: Config, commands: CommandProcessor) -> None:
        self.commands = commands
        self.config = config
        self.block_size = self.config["acd.bulk_resolve.block_size"]

    async def resolve(
        self, new_room_ids: List[RoomID], user: User, user_id: UserID, send_message: str
    ):
        """It resolves all the rooms in the `room_ids` set, in blocks of `block_size` rooms

        Parameters
        ----------
        new_room_ids : List[RoomID]
            List[RoomID]
        user : User
            The user that will be used to send the message.
        user_id : UserID
            The user ID of the user who will send the message.
        send_message : str
            The message to be sent to the room.

        Returns
        -------
            A list of rooms to be resolved.

        """

        # Adding the new rooms to the set of rooms to be resolved.
        self.room_ids |= set(new_room_ids)

        self.log.info(
            f"Starting bulk resolve of {len(new_room_ids)} rooms, "
            f"current rooms {len(self.room_ids)}"
        )

        if self.active_resolve:
            self.log.debug(
                f"Rooms have been enqueued {len(new_room_ids)}, "
                "as there is an active bulk resolution"
            )
            return

        self.active_resolve = True

        # Resolving the rooms in bulk.
        while len(self.room_ids) > 0:
            tasks = []

            rooms_to_resolve = list(self.room_ids)[0 : self.block_size]
            self.log.info(
                f"Rooms to be resolved: {len(rooms_to_resolve)}, current rooms {len(self.room_ids)}"
            )

            for room_id in rooms_to_resolve:
                self.room_ids.remove(room_id)
                puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
                if not puppet:
                    self.log.warning(
                        f"The room {room_id} has not been resolved because the puppet was not found"
                    )
                    continue

                bridge = await puppet.room_manager.get_room_bridge(room_id=room_id)

                if not bridge:
                    self.log.warning(
                        f"The room {room_id} has not been resolved because I didn't found the bridge"
                    )
                    continue

                bridge_prefix = puppet.config[f"bridges.{bridge}.prefix"]

                args = [room_id, user_id, send_message, bridge_prefix]

                tasks.append(
                    self.commands.handle(
                        sender=user,
                        command="resolve",
                        args_list=args,
                        intent=puppet.intent,
                        is_management=False,
                    )
                )

            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                self.log.error(e)
                continue

        self.active_resolve = False
