from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..puppet import Puppet
from ..signaling import Signaling
from ..user import User
from .handler import command_handler
from .template import template
from .typehint import CommandEvent


@command_handler(
    name="resolve",
    help_text=("Command resolving a chat, ejecting the supervisor and the agent"),
    help_args="<_room_id_> <_user_id_> <_send_message_> [_bridge_]",
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
    # Checking if the command has arguments.
    if len(evt.args_list) < 3:
        detail = "Incomplete arguments for <code>resolve_chat</code> command"
        evt.log.error(detail)
        await evt.reply(text=detail)
        return

    room_id = evt.args_list[0]
    user_id = evt.args_list[1]
    send_message = evt.args_list[2] if len(evt.args_list) > 2 else None
    bridge = evt.args_list[3] if len(evt.args_list) > 3 else None

    evt.log.debug(
        f"The user {user_id} is resolving the room {room_id}, send_message? // {send_message} "
    )

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)

    if room_id == puppet.control_room_id or (
        not await puppet.room_manager.is_customer_room(room_id=room_id)
        and not await puppet.room_manager.is_guest_room(room_id=room_id)
    ):

        detail = "Group rooms or control rooms cannot be resolved."
        evt.log.error(detail)
        await puppet.intent.send_notice(room_id=room_id, text=detail)
        return

    if send_message is not None:
        send_message = True if send_message == "yes" else False

    agent_id = await puppet.agent_manager.get_room_agent(room_id=room_id)

    try:
        if agent_id:
            await puppet.room_manager.remove_user_from_room(
                room_id=room_id, user_id=agent_id, reason=puppet.config["acd.resolve_chat.notice"]
            )
        supervisors = puppet.config["acd.supervisors_to_invite.invitees"]
        if supervisors:
            for supervisor_id in supervisors:
                await puppet.room_manager.remove_user_from_room(
                    room_id=room_id,
                    user_id=supervisor_id,
                    reason=puppet.config["acd.resolve_chat.notice"],
                )
    except Exception as e:
        evt.log.warning(e)

    # When the supervisor resolves an open chat, menubot is still in the chat
    await puppet.room_manager.menubot_leaves(
        room_id=room_id,
        reason=puppet.config["acd.resolve_chat.notice"],
    )

    await puppet.agent_manager.signaling.set_chat_status(
        room_id=room_id, status=Signaling.RESOLVED, agent=user_id
    )

    # clear campaign in the ik.chat.campaign_selection state event
    await puppet.agent_manager.signaling.set_selected_campaign(
        room_id=room_id, campaign_room_id=None
    )

    if send_message is not None:
        resolve_chat_params = puppet.config["acd.resolve_chat"]
        if send_message and bridge is not None:
            data = {
                "room_id": room_id,
                "template_message": resolve_chat_params["message"],
                "template_name": resolve_chat_params["template_name"],
                "template_data": resolve_chat_params["template_data"],
                "language": resolve_chat_params["language"],
                "bridge": bridge,
            }
            template_data = f"{json.dumps(data)}"

            cmd_evt = CommandEvent(
                intent=puppet.intent,
                config=puppet.config,
                command="template",
                sender=evt.sender,
                room_id=room_id,
                is_management=room_id == evt.sender.management_room,
                text=template_data,
                args_list=template_data.split(),
            )
            await template(cmd_evt)

        await puppet.intent.send_notice(room_id=room_id, text=resolve_chat_params["notice"])


class BulkResolve:

    loop: asyncio.AbstractEventLoop
    log: TraceLogger = logging.getLogger("acd.bulk_resolve")

    room_ids = set()

    active_resolve = False

    def __init__(self, loop: asyncio.AbstractEventLoop, config: Config) -> None:

        self.loop = loop
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
                puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
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

                fake_cmd_event = CommandEvent(
                    sender=user,
                    config=self.config,
                    command="resolve",
                    is_management=False,
                    intent=puppet.intent,
                    args=args,
                )

                tasks.append(resolve(fake_cmd_event))

            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                self.log.error(e)
                continue

        self.active_resolve = False
