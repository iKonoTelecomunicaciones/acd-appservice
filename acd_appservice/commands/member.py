from typing import Dict

from mautrix.types import UserID

from ..queue import Queue
from ..queue_membership import QueueMembership, QueueMembershipState
from ..user import User
from ..util.util import Util
from .handler import CommandArg, CommandEvent, command_handler

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

action = CommandArg(
    name="action",
    help_text="Agent operation",
    is_required=True,
    example="`login | logout | pause | unpause`",
    sub_args=[agent_id, pause_reason],
)


@command_handler(
    name="member",
    help_text="Agent operations like login, logout, pause, unpause",
    help_args=[action],
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

    try:
        action = evt.args_list[0]
    except IndexError:
        detail = "You have not sent the argument action"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    try:
        agent_id: UserID = evt.args_list[1]
    except IndexError:
        agent_id = ""

    if not action in ["login", "logout", "pause", "unpause"]:
        msg = f"{action} is not a valid action"
        evt.log.error(msg)
        await evt.reply(text=msg)
        return

    # Verify if user is able to do an agent operation over other agent
    if not evt.sender.is_admin and Util.is_user_id(agent_id) and agent_id != evt.sender.mxid:
        msg = f"You are unable to use agent operation `{action}` over other agents"
        await evt.reply(text=msg)
        evt.log.warning(msg)
        json_response.get("data")["detail"] = msg
        json_response["status"] = 403
        return json_response

    # Verify that admin do not try to do an agent operation for himself
    elif evt.sender.is_admin and not Util.is_user_id(agent_id):
        msg = f"Admin user can not use agent operation `{action}`"
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

    if action in ["login", "logout"]:
        state = QueueMembershipState.ONLINE if action == "login" else QueueMembershipState.OFFLINE

        if membership.state == state:
            msg = f"Agent {agent_id} is already {state.value}"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 409
            return json_response

        membership.state = state
        membership.state_date = QueueMembership.now()
        # When action is `logout` also unpause the user and erase pause_reason
        if action == "logout" and membership.paused:
            membership.paused = False
            membership.pause_date = QueueMembership.now()
            membership.pause_reason = None
        await membership.save()

    elif action in ["pause", "unpause"]:
        # An offline agent is unable to use pause or unpause operations
        if membership.state == QueueMembershipState.OFFLINE:
            msg = f"You should be logged in to execute `{action}` operation"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 422
            return json_response

        state = True if action == "pause" else False
        if membership.paused == state:
            msg = f"Agent {agent_id} is already {action}d"
            await evt.reply(text=msg)
            evt.log.warning(msg)
            json_response.get("data")["detail"] = msg
            json_response["status"] = 409
            return json_response

        membership.paused = state
        membership.pause_date = QueueMembership.now()
        # The position of the pause_reason argument is variable,
        # in some cases it can be in the position of the agent_id arg
        if action == "pause":
            membership.pause_reason = (
                evt.args_list[2]
                if evt.sender.is_admin or evt.args_list[1] == evt.sender.mxid
                else evt.args_list[1]
            )
        else:
            membership.pause_reason = None
        await membership.save()

    msg = f"Agent operation `{action}` was successful, {agent_id} state is `{action}`"
    await evt.reply(text=msg)
    json_response.get("data")["detail"] = f"Agent operation `{action}` was successful"
    json_response["status"] = 200
    return json_response
