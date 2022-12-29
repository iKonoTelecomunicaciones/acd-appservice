from typing import Dict, List, Optional

from mautrix.types import RoomDirectoryVisibility, RoomID, UserID

from ..queue import Queue
from .handler import CommandArg, CommandEvent, command_handler

name = CommandArg(
    name="name", help_text="Queue room name", is_required=True, example='"My favourite queue"'
)

invitees = CommandArg(
    name="invitees",
    help_text="Invitees to the queue",
    is_required=True,
    example="`@user1:foo.com,@user2:foo.com,@user3:foo.com,...`",
)

description = CommandArg(
    name="description",
    help_text="Short description about the queue",
    is_required=False,
    example='"It is a queue to distribute chats"',
)


member = CommandArg(
    name="member",
    help_text="Member to be added|deleted",
    is_required=True,
    example="@user1:foo.com",
)

queue = CommandArg(
    name="queue",
    help_text=(
        "Queue where the member will be added|deleted, "
        "if no queue is provided the room_id where the command was sent will be taken."
    ),
    is_required=True,
    example="!foo:foo.com",
)

action = CommandArg(
    name="action",
    help_text="Action to be taken in the queue",
    is_required=True,
    example="`create` | `add` | `remove`",
    sub_args=[[name, member], [invitees, queue], description],
)


@command_handler(
    management_only=False,
    needs_admin=True,
    name="queue",
    help_text=(
        "Create a queue. A queue is a matrix room containing agents that will be used "
        "for chat distribution. `invitees` is a comma-separated list of user_ids."
    ),
    help_args=[action],
)
async def queue(evt: CommandEvent) -> Dict:
    """It creates a room, sets the visibility, invites the users,
    and saves the queue to the database.

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent - This is the event that is passed to the command.

    Returns
    -------
        The queue object is being returned.

    """

    json_response = {"data": None, "status": 0}

    try:
        action = evt.args_list[0]
    except IndexError:
        detail = "You have not sent the argument action"
        evt.log.error(detail)
        await evt.reply(detail)
        json_response["data"] = {"error": detail}
        json_response["status"] = 422
        return json_response

    # Creating a queue.
    if action == "create":

        # Checking if the invitees are specified.
        # If they are, it will split them by comma and strip them.
        if len(evt.args_list) < 2:
            detail = "You have not sent all arguments"
            evt.log.error(detail)
            await evt.reply(detail)
            json_response["data"] = {"error": detail}
            json_response["status"] = 422
            return json_response

        name = evt.args_list[1]
        invitees = evt.args_list[2]

        try:
            description = evt.args_list[3]
        except IndexError:
            description = ""

        return await create(evt=evt, name=name, invitees=invitees, description=description)

    elif action in ["add", "remove"]:
        try:
            member: UserID = evt.args_list[1]
        except:
            detail = "You have not sent the argument member"
            evt.log.error(detail)
            await evt.reply(detail)
            json_response["data"] = {"error": detail}
            json_response["status"] = 422
            return json_response

        try:
            queue_id = evt.args_list[2]
        except IndexError:
            queue_id = evt.room_id

        return await add_remove(evt=evt, action=action, member=member, queue_id=queue_id)


async def create(
    evt: CommandEvent, name: str, invitees: List[UserID], description: Optional[str] = None
) -> Dict:
    """It creates a new queue and saves it to the database

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent - This is the event object that is passed to the command.
    name : str
        The name of the queue.
    invitees : List[UserID]
        List[UserID]
    description : Optional[str]
        Optional[str] = None

    Returns
    -------
        A JSON response with the name and room_id of the queue.

    """
    visibility = RoomDirectoryVisibility.PRIVATE
    json_response = {}

    if isinstance(invitees, str):
        invitees: List[UserID] = [invitee.strip() for invitee in invitees.split(",")]

    # user_add_method can be 'invite' or 'join'.
    # When it's 'join' the agente will be force joined to the queue
    if evt.config["acd.queues.user_add_method"] == "invite":
        invitees = invitees + evt.config["acd.queues.invitees"]

    # Checking if the config value is set to public. If it is, it sets the visibility to public.
    if evt.config["acd.queues.visibility"] == "public":
        visibility = RoomDirectoryVisibility.PUBLIC

    try:
        topic: str = f"""
            {evt.config['acd.queues.topic']}
            {f' -> {str(description).strip()}' if description else ''}
        """

        room_id = await evt.intent.create_room(
            name=name,
            invitees=invitees
            if evt.config["acd.queues.user_add_method"] == "invite"
            else evt.config["acd.queues.invitees"],
            topic=topic.strip(),
            visibility=visibility,
        )
    except Exception as e:
        evt.log.error(e)
        await evt.reply(f"Error: {str(e)}")
        json_response["data"] = {"error": str(e)}
        json_response["status"] = 500
        return json_response

    queue: Queue = await Queue.get_by_room_id(room_id=room_id)
    queue.name = name
    queue.description = description if description else None
    await queue.save()

    for invitee in invitees:
        try:
            await queue.add_member(new_member=invitee)
        except Exception as e:
            evt.log.warning(e)

    json_response["data"] = {
        "name": queue.name,
        "room_id": queue.room_id,
    }
    json_response["status"] = 200
    return json_response


async def add_remove(
    evt: CommandEvent, action: str, member: UserID, queue_id: Optional[RoomID] = None
) -> Dict:
    """It takes in a command event, an action, a member, and an optional queue id, and returns a dictionary

    Parameters
    ----------
    evt : CommandEvent
        The event object.
    action : str
        The action to take, either add or remove
    member : UserID
        The user ID of the member to add or remove
    queue_id : Optional[RoomID]
        The room ID of the queue you want to add or remove a member from.

    Returns
    -------
        A dictionary with the status code and the data.

    """

    json_response = {}

    queue = await Queue.get_by_room_id(room_id=queue_id, create=False)

    if not queue or not member:
        json_response["data"] = {"error": "Arg queue or member not provided"}
        json_response["status"] = 422
        return json_response

    try:
        if action == "add":
            await queue.add_member(member)
        elif action == "remove":
            await queue.remove_member(member)
    except Exception as e:
        evt.log.error(e)
        await evt.reply(str(e))
        json_response["data"] = {"error": str(e)}
        json_response["status"] = 422
        return json_response

    detail = f"The member has been {'added' if action == 'add' else 'removed'} from the queue"
    json_response["data"] = (
        {
            "detail": detail,
            "member": member,
            "room_id": queue.room_id,
        },
    )
    json_response["status"] = 200

    detail = detail.replace("queue", queue.room_id).replace("member", member)
    evt.log.debug(detail)
    await evt.reply(detail)
    return json_response
