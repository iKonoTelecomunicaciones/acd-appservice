import datetime
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
    example="`login | logout | pause | despause`",
)

agent = CommandArg(
    name="agent",
    help_text="Agent to whom the operation applies",
    is_required=False,
    example="@agent1:foo.com",
)


@command_handler(name="member", help_text="Make agent operations", help_args=[action, agent])
async def member(evt: CommandEvent) -> Dict:

    agent: UserID = evt.args.agent
    if not agent:
        agent = evt.sender

    queue: Queue = await Queue.get_by_room_id(room_id=evt.room_id)
    user: User = await User.get_by_mxid(mxid=agent, create=False)

    membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
        fk_user=user.id, fk_queue=queue.id, create=False
    )

    if not membership:
        return

    if evt.args.action == "login" or evt.args.action == "logout":
        membership.state = (
            QueueMembershipState.Online
            if evt.args.action == "login"
            else QueueMembershipState.Offline
        )
        membership.state_ts = datetime.timestamp(datetime.utcnow())
        membership.save()
