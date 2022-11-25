from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..puppet import Puppet
from ..signaling import Signaling
from ..user import User
from .handler import CommandArg, CommandEvent, CommandProcessor, command_handler

room_id = CommandArg(
    name="room_id",
    help_text="Room to be resolved",
    is_required=True,
    example="`!foo:foo.com`",
)

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
    default="",
)


@command_handler(
    name="resolve",
    help_text=("Command resolving a chat, ejecting the supervisor and the agent"),
    help_args=[room_id, user_id, send_message],
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

    if evt.args.send_message.lower() in ["yes", "y", "1"]:
        send_message = True

    if evt.args.send_message.lower() in ["no", "n", "0"] or not evt.args.send_message:
        send_message = False

    evt.log.debug(
        (
            f"The user {evt.args.user_id} is resolving "
            f"the room {evt.args.room_id}, send_message? // {send_message} "
        )
    )

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=evt.args.room_id)

    if evt.args.room_id == puppet.control_room_id or (
        not await puppet.room_manager.is_customer_room(room_id=evt.args.room_id)
        and not await puppet.room_manager.is_guest_room(room_id=evt.args.room_id)
    ):

        detail = "Group rooms or control rooms cannot be resolved."
        evt.log.error(detail)
        await puppet.intent.send_notice(room_id=evt.args.room_id, text=detail)
        return

    agent_id = await puppet.agent_manager.get_room_agent(room_id=evt.args.room_id)

    try:
        if agent_id:
            await puppet.room_manager.remove_user_from_room(
                room_id=evt.args.room_id,
                user_id=agent_id,
                reason=puppet.config["acd.resolve_chat.notice"],
            )
        supervisors = puppet.config["acd.supervisors_to_invite.invitees"]
        if supervisors:
            for supervisor_id in supervisors:
                await puppet.room_manager.remove_user_from_room(
                    room_id=evt.args.room_id,
                    user_id=supervisor_id,
                    reason=puppet.config["acd.resolve_chat.notice"],
                )
    except Exception as e:
        evt.log.warning(e)

    # When the supervisor resolves an open chat, menubot is still in the chat
    await puppet.room_manager.menubot_leaves(
        room_id=evt.args.room_id,
        reason=puppet.config["acd.resolve_chat.notice"],
    )

    await puppet.agent_manager.signaling.set_chat_status(
        room_id=evt.args.room_id, status=Signaling.RESOLVED, agent=evt.args.user_id
    )

    # clear campaign in the ik.chat.campaign_selection state event
    await puppet.agent_manager.signaling.set_selected_campaign(
        room_id=evt.args.room_id, campaign_room_id=None
    )

    if send_message is not None:
        resolve_chat_params = puppet.config["acd.resolve_chat"]
        if send_message:

            args = [evt.args.room_id, resolve_chat_params["message"]]
            await evt.processor.handle(
                sender=evt.sender,
                command="template",
                args_list=args,
                is_management=evt.args.room_id == evt.sender.management_room,
                intent=puppet.intent,
                room_id=evt.room_id,
            )

        await puppet.intent.send_notice(
            room_id=evt.args.room_id, text=resolve_chat_params["notice"]
        )


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
