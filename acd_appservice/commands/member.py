from typing import Dict

from mautrix.types import UserID

from ..queue import Queue
from ..queue_membership import QueueMembership, QueueMembershipState
from ..user import User
from ..util.util import Util
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

pause_reason = CommandArg(
    name="pause_reason",
    help_text="Why are you going to pause?",
    is_required=False,
    example="Pause to see the sky",
)


@command_handler(
    name="member",
    help_text="Agent operations like login, logout, pause, unpause",
    help_args=[action, agent_id, pause_reason],
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
        "data": {"detail": "", "room_id": evt.room_id, "room_name": ""},
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
    if not evt.sender.is_admin and Util.is_user_id(agent_id) and agent_id != evt.sender.mxid:
        msg = f"You are unable to use agent operation `{evt.args.action}` over other agents"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 403
        return json_response

    # Verify that admin do not try to do an agent operation for himself
    elif evt.sender.is_admin and not Util.is_user_id(agent_id):
        msg = f"Admin user can not use agent operation `{evt.args.action}`"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 403
        return json_response

    # Check if agent_id is empty or is something different to UserID to apply operation to sender
    if not agent_id or not Util.is_user_id(agent_id):
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

    json_response.get("data")["room_name"] = queue.name
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
            msg = f"Agent {agent_id} is already {state}"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 409
            return json_response

        membership.state = state
        membership.state_date = QueueMembership.now()
        # When action is `logout` also unpause the user and erase pause_reason
        if evt.args.action == "logout" and membership.paused:
            membership.paused = False
            membership.pause_date = QueueMembership.now()
            membership.pause_reason = None
        await membership.save()
    elif evt.args.action == "pause" or evt.args.action == "unpause":
        # An offline agent is unable to use pause or unpause operations
        if membership.state == QueueMembershipState.Offline.value:
            msg = f"You should be logged in to execute `{evt.args.action}` operation"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 422
            return json_response

        state = True if evt.args.action == "pause" else False
        if membership.paused == state:
            msg = f"Agent {agent_id} is already {evt.args.action}d"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 409
            return json_response

        membership.paused = state
        membership.pause_date = QueueMembership.now()
        # The position of the pause_reason argument is variable,
        # in some cases it can be in the position of the agent_id arg
        if evt.args.action == "pause":
            membership.pause_reason = (
                evt.args_list[2]
                if evt.sender.is_admin or evt.args.agent_id == evt.sender.mxid
                else evt.args_list[1]
            )
        else:
            membership.pause_reason = None
        await membership.save()

    msg = f"Agent operation `{evt.args.action}` was successful, {agent_id} state is `{evt.args.action}`"
    await evt.reply(text=msg)
    json_response.get("data")["detail"] = f"Agent operation `{evt.args.action}` was successful"
    json_response["status"] = 200
    return json_response
