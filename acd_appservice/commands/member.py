from argparse import ArgumentParser, Namespace
from typing import Dict

from mautrix.types import UserID

from ..events import ACDMemberEvents, send_member_event
from ..queue import Queue
from ..queue_membership import QueueMembership, QueueMembershipState
from ..user import User
from ..util.util import Util
from .handler import CommandArg, CommandEvent, command_handler

agent_arg = CommandArg(
    name="--agent or -g",
    help_text="Agent to whom the operation applies",
    is_required=False,
    example="@agent1:foo.com",
)

pause_reason_arg = CommandArg(
    name="--pause_reason or -p",
    help_text="Why are you going to pause?",
    is_required=False,
    example="Pause to see the sky",
)

action_arg = CommandArg(
    name="--action or -a",
    help_text="Agent operation",
    is_required=True,
    example="`login | logout | pause | unpause`",
)


def args_parser():
    parser = ArgumentParser(description="MEMBER", exit_on_error=False)

    parser.add_argument(
        "--action",
        "-a",
        dest="action",
        type=str,
        required=True,
        choices=["login", "logout", "pause", "unpause"],
    )
    parser.add_argument("--agent", "-g", dest="agent", type=str, required=False)
    parser.add_argument(
        "--pause_reason", "-p", dest="pause_reason", type=str, required=False, default=None
    )

    return parser


@command_handler(
    name="member",
    help_text="Agent operations like login, logout, pause, unpause",
    help_args=[action_arg, agent_arg, pause_reason_arg],
    args_parser=args_parser(),
)
async def member(evt: CommandEvent) -> Dict:
    """Agent operations like login, logout, pause, unpause

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        {
            data: {
                detail: str,
                room_id: RoomID,
            },
            status: int
        }

    """

    args: Namespace = evt.cmd_args
    action: str = args.action
    agent_id: UserID = args.agent
    pause_reason: str = args.pause_reason

    # Verify if user is able to do an agent operation over other agent
    if not evt.sender.is_admin and Util.is_user_id(agent_id) and agent_id != evt.sender.mxid:
        msg = f"You are unable to use agent operation `{action}` over other agents"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        return Util.create_response_data(room_id=evt.room_id, detail=msg, status=403)

    # Verify that admin do not try to do an agent operation for himself
    elif evt.sender.is_admin and not Util.is_user_id(agent_id):
        msg = f"Admin user can not use agent operation `{action}`"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        return Util.create_response_data(room_id=evt.room_id, detail=msg, status=403)

    # Check if agent_id is empty or is something different to UserID to apply operation to sender
    if not agent_id or not Util.is_user_id(agent_id):
        agent_id = evt.sender.mxid

    queue: Queue = await Queue.get_by_room_id(room_id=evt.room_id, create=False)
    user: User = await User.get_by_mxid(mxid=agent_id, create=False)
    if not queue or not user:
        msg = f"Agent {agent_id} or queue {evt.room_id} does not exists"
        await evt.reply(text=msg)
        evt.log.error(msg)
        return Util.create_response_data(room_id=evt.room_id, detail=msg, status=422)

    membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
        fk_user=user.id, fk_queue=queue.id, create=False
    )

    if not membership:
        msg = f"User {agent_id} is not member of the room {evt.room_id}"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        return Util.create_response_data(
            room_id=evt.room_id, detail=msg, status=422, additional_info={"room_name": queue.name}
        )

    if action in ["login", "logout"]:
        state = QueueMembershipState.ONLINE if action == "login" else QueueMembershipState.OFFLINE

        if membership.state == state:
            msg = f"Agent {agent_id} is already {state.value}"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            return Util.create_response_data(
                room_id=evt.room_id,
                detail=msg,
                status=409,
                additional_info={"room_name": queue.name},
            )

        membership.state = state
        membership.state_date = QueueMembership.now()
        # When action is `logout` also unpause the user and erase pause_reason
        if action == "logout" and membership.paused:
            membership.paused = False
            membership.pause_date = QueueMembership.now()
            membership.pause_reason = None
        await membership.save()

        if action == "login":
            await send_member_event(
                event_type=ACDMemberEvents.MemberLogin,
                sender=evt.sender.mxid,
                queue=evt.room_id,
                member=agent_id,
                penalty=None,
            )
        else:
            await send_member_event(
                event_type=ACDMemberEvents.MemberLogout,
                sender=evt.sender.mxid,
                queue=evt.room_id,
                member=agent_id,
            )
            if membership.paused:
                await send_member_event(
                    event_type=ACDMemberEvents.MemberPause,
                    sender=evt.sender.mxid,
                    queue=evt.room_id,
                    member=agent_id,
                    paused=False,
                )

    elif action in ["pause", "unpause"]:
        # An offline agent is unable to use pause or unpause operations
        if membership.state == QueueMembershipState.OFFLINE:
            msg = f"You should be logged in to execute `{action}` operation"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            return Util.create_response_data(
                room_id=evt.room_id,
                detail=msg,
                status=422,
                additional_info={"room_name": queue.name},
            )

        state = True if action == "pause" else False
        if membership.paused == state:
            msg = f"Agent {agent_id} is already {action}d"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            return Util.create_response_data(
                room_id=evt.room_id,
                detail=msg,
                status=409,
                additional_info={"room_name": queue.name},
            )

        membership.paused = state
        membership.pause_date = QueueMembership.now()
        membership.pause_reason = None

        if action == "pause":
            membership.pause_reason = pause_reason

        await membership.save()

        await send_member_event(
            event_type=ACDMemberEvents.MemberPause,
            sender=evt.sender.mxid,
            queue=evt.room_id,
            member=agent_id,
            paused=state,
            pause_reason=pause_reason,
        )

    msg = f"Agent operation `{action}` was successful, {agent_id} state is `{action}`"
    await evt.reply(text=msg)
    return Util.create_response_data(
        room_id=evt.room_id,
        detail=f"Agent operation `{action}` was successful",
        status=200,
        additional_info={"room_name": queue.name},
    )
