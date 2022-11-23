from datetime import datetime
from typing import Dict

from mautrix.types import UserID

from ..queue import Queue
from ..queue_membership import QueueMembership, QueueMembershipState
from ..user import User
from .handler import CommandArg, command_handler
from .typehint import CommandEvent

action = CommandArg(
    name="action",
    help_text="Operation taken by the agent",
    is_required=True,
    example="`login | logout | pause | unpause`",
)

agent = CommandArg(
    name="agent",
    help_text="Agent to whom the operation applies",
    is_required=False,
    example="@agent1:foo.com",
)


@command_handler(name="member", help_text="Make agent operations", help_args=[action, agent])
async def member(evt: CommandEvent) -> Dict:

    actions = ["login", "logout", "pause", "unpause"]
    if not evt.args.action in actions:
        msg = f"{evt.args.action} is not a valid action"
        await evt.intent.send_notice(room_id=evt.room_id, text=msg)
        return

    agent_id: UserID = evt.args.agent
    if not agent_id:
        agent_id = evt.sender.mxid

    queue: Queue = await Queue.get_by_room_id(room_id=evt.room_id, create=False)
    user: User = await User.get_by_mxid(mxid=agent_id, create=False)
    if not queue or not user:
        msg = f"Agent {agent_id} or queue {evt.room_id} does not exists"
        await evt.intent.send_notice(room_id=evt.room_id, text=msg)
        evt.log.debug(msg)
        return {
            "detail": msg,
            "room_id": evt.room_id,
            "error_code": 422,
        }

    membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
        fk_user=user.id, fk_queue=queue.id, create=False
    )

    if not membership:
        msg = f"User {agent_id} is not member of the room {evt.room_id}"
        await evt.intent.send_notice(room_id=evt.room_id, text=msg)
        evt.log.debug(msg)
        return {
            "detail": msg,
            "room_id": evt.room_id,
            "error_code": 422,
        }

    if evt.args.action == "login" or evt.args.action == "logout":
        membership.state = (
            QueueMembershipState.Online.value
            if evt.args.action == "login"
            else QueueMembershipState.Offline.value
        )
        membership.state_ts = datetime.timestamp(datetime.utcnow())
        await membership.save()

    msg = f"Agent operation `{evt.args.action}` was successfully"
    await evt.intent.send_notice(room_id=evt.room_id, text=msg)
    return {
        "detail": msg,
        "room_id": evt.room_id,
        "error_code": 200,
    }
