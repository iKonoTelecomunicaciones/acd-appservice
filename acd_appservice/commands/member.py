from typing import Dict

from mautrix.types import UserID

from ..queue import Queue
from ..queue_membership import QueueMembership, QueueMembershipState
from ..user import User
from .handler import CommandArg, CommandEvent, command_handler

action = CommandArg(
    name="action",
    help_text="Agent operation",
    is_required=True,
    example="`login | logout | pause | unpause`",
)

agent_id = CommandArg(
    name="agent_id",
    help_text="Agent to whom the operation applies",
    is_required=False,
    example="@agent1:foo.com",
)


@command_handler(
    name="member",
    help_text="Agent operations like login, logout, pause, unpause",
    help_args=[action, agent_id],
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

    json_response: Dict = {
        "data": {
            "detail": "",
            "room_id": evt.room_id,
        },
        "status": 0,
    }

    actions = ["login", "logout", "pause", "unpause"]
    if not evt.args.action in actions:
        msg = f"{evt.args.action} is not a valid action"
        evt.log.error(msg)
        await evt.reply(text=msg)
        return

    # Verify if user is able to do an agent operation over other agent
    agent_id: UserID = evt.args.agent_id
    if not evt.sender.is_admin and agent_id:
        msg = f"You are unable to use agent operation `{evt.args.action}` over other agents"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 403
        return json_response

    # Verify that admin do not try to do an agent operation for himself
    elif evt.sender.is_admin and not agent_id:
        msg = f"Admin user can not use agent operation `{evt.args.action}`"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 403
        return json_response

    if not agent_id:
        agent_id = evt.sender.mxid

    queue: Queue = await Queue.get_by_room_id(room_id=evt.room_id, create=False)
    user: User = await User.get_by_mxid(mxid=agent_id, create=False)
    if not queue or not user:
        msg = f"Agent {agent_id} or queue {evt.room_id} does not exists"
        await evt.reply(text=msg)
        evt.log.error(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 422
        return json_response

    membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
        fk_user=user.id, fk_queue=queue.id, create=False
    )

    if not membership:
        msg = f"User {agent_id} is not member of the room {evt.room_id}"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 422
        return json_response

    if evt.args.action == "login" or evt.args.action == "logout":
        state = (
            QueueMembershipState.Online.value
            if evt.args.action == "login"
            else QueueMembershipState.Offline.value
        )

        if membership.state == state:
            msg = f"Agent is already {state}"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 422
            return json_response

        membership.state = state
        membership.state_date = QueueMembership.now()
        await membership.save()

    msg = f"Agent operation `{evt.args.action}` was successful"
    await evt.reply(text=msg)
    json_response.get("data")["detail"] = msg
    json_response["status"] = 200
    return json_response
