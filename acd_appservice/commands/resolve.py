from __future__ import annotations

import asyncio
import logging
from argparse import ArgumentParser, Namespace
from typing import Dict, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..events import send_resolve_event
from ..portal import Portal, PortalState
from ..puppet import Puppet
from ..signaling import Signaling
from ..user import User
from .handler import CommandArg, CommandEvent, CommandProcessor, command_handler

author_arg = CommandArg(
    name="--author or -a",
    help_text="User who is solving the room",
    is_required=True,
    example="@user_id:foo.com",
)

send_message_arg = CommandArg(
    name="--send_message or -sm",
    help_text="Should I send a resolution message?",
    is_required=False,
    example="`yes` | `y` | `1` | `no` | `n` | `0`",
)

portal_arg = CommandArg(
    name="--portal or -p",
    help_text="Room to be resolved",
    is_required=True,
    example="`!foo:foo.com`",
)


def args_parser():
    parser = ArgumentParser(description="RESOLVE", exit_on_error=False)
    parser.add_argument("--author", "-a", dest="author", type=str, required=True)
    parser.add_argument("--portal", "-p", dest="portal", type=str, required=True)
    parser.add_argument(
        "--send-message",
        "-sm",
        dest="send_message",
        type=str,
        required=False,
        choices=["yes", "y", "1", "no", "n", "0"],
        default="n",
    )

    return parser


@command_handler(
    name="resolve",
    help_text=("Command resolving a chat, ejecting the supervisor and the agent"),
    help_args=[author_arg, portal_arg, send_message_arg],
    args_parser=args_parser(),
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

    args: Namespace = evt.cmd_args
    portal_room_id: RoomID = args.portal
    author: UserID = args.author
    send_message: bool = True if args.send_message.lower() in ["yes", "y", "1"] else False

    evt.log.debug(
        (
            f"The user {author} is resolving "
            f"the room {portal_room_id}, send_message? // {send_message} "
        )
    )

    if not await Portal.is_portal(portal_room_id):
        detail = "Group queues or control rooms cannot be resolved."
        evt.log.error(detail)
        await evt.intent.send_notice(room_id=portal_room_id, text=detail)
        return

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=portal_room_id)

    portal = await Portal.get_by_room_id(
        room_id=portal_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
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

    # set chat status to resolved
    await portal.update_state(PortalState.RESOLVED)
    send_resolve_event(
        portal=portal,
        sender=evt.sender.mxid,
        reason=puppet.config["acd.resolve_chat.notice"],
        agent_removed=agent,
    )

    await puppet.agent_manager.signaling.set_chat_status(
        room_id=portal.room_id, status=Signaling.RESOLVED, agent=author
    )

    # clear campaign in the ik.chat.campaign_selection state event
    await puppet.agent_manager.signaling.set_selected_campaign(
        room_id=portal.room_id, campaign_room_id=None
    )

    resolve_chat_params = puppet.config["acd.resolve_chat"]
    if send_message:
        args = ["-p", portal.room_id, "-m", resolve_chat_params["message"]]
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

                bridge = puppet.bridge

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
