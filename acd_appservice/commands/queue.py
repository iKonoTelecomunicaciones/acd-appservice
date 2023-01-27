from typing import Any, Dict, List, Optional

from mautrix.types import RoomDirectoryVisibility, RoomID, UserID

from ..queue import Queue
from ..queue_membership import QueueMembership
from ..user import User
from ..util import Util
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
    help_text=(
        "Action to be taken in the queue.\n\n"
        "\t`create`: Creates a new queue.\n\n"
        "\t`add`: Adds a member to a specific queue.\n\n"
        "\t`remove`: Removes a member from a specific queue.\n\n"
        "\t`info`: Shows detailed information about a specific queue.\n\n"
        "\t`list`: Shows a list of all existing queues.\n\n"
        "\t`update`: Updates the information of a specific queue.\n\n"
        "\t`delete`: Deletes a specific queue.\n\n"
        "\t`set`: Sets a specific room as a queue.\n\n"
    ),
    is_required=True,
    example="`create` | `add` | `remove` | `info` | `list` | `update` | `delete` | `set`",
    sub_args=[[name, member], [invitees, queue], description],
)


@command_handler(
    management_only=False,
    needs_admin=False,
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
        if len(evt.args_list) < 3:
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

        if isinstance(invitees, str):
            invitees: List[UserID] = [invitee.strip() for invitee in invitees.split(",")]

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

        queue = await Queue.get_by_room_id(room_id=queue_id, create=False)

        if not queue or not member:
            detail = "Arg queue or member not provided"
            json_response["data"] = {"error": detail}
            json_response["status"] = 422
            evt.log.error(detail)
            await evt.reply(detail)
            return json_response

        return await add_remove(evt=evt, action=action, member=member, queue_id=queue_id)

    elif action == "delete":

        # Checking if the second argument is a room id. If it is,
        # it sets the queue_id to the second argument and the force to the third argument.
        # If it is not, it sets the queue_id to the room id and the force to the second argument.
        try:
            queue_id_or_force = evt.args_list[1]

            if Util.is_room_id(queue_id_or_force):
                queue_id = queue_id_or_force
                try:
                    force = evt.args_list[2]
                except IndexError:
                    force = "n"
            else:
                queue_id = evt.room_id
                force = queue_id_or_force
        except IndexError:
            force = "n"
            queue_id = evt.room_id

        force = (
            (True if force.lower() in ["yes", "y", "1"] else False)
            if isinstance(force, str)
            else force
        )

        return await delete(evt=evt, queue_id=queue_id, force=force)

    elif action == "update":

        try:
            # Checking if the room_id is valid.
            # If it is, it will set the room_id to the first argument,
            # and the name to the second argument.
            # If it is not, it will set the room_id to the current room_id,
            # and the name to the first argument.
            if Util.is_room_id(evt.args_list[1]):
                room_id = evt.args_list[1]
                try:
                    name = evt.args_list[2]
                except IndexError:
                    detail = "Arg name not provided"
                    json_response["data"] = {"error": detail}
                    json_response["status"] = 422
                    evt.log.error(detail)
                    await evt.reply(detail)
                    return json_response
                try:
                    description = evt.args_list[3]
                except IndexError:
                    description = ""
            else:
                room_id = evt.room_id
                name = evt.args_list[1]
                description = evt.args_list[2]

        except IndexError:
            # Checking if the name is provided or not.
            room_id = evt.room_id
            try:
                name = evt.args_list[1]
            except IndexError:
                detail = "Arg name not provided"
                json_response["data"] = {"error": detail}
                json_response["status"] = 422
                evt.log.error(detail)
                await evt.reply(detail)
                return json_response

            try:
                description = evt.args_list[2]
            except IndexError:
                description = ""

        return await update(evt=evt, room_id=room_id, name=name, description=description)

    elif action == "info":
        try:
            room_id = evt.args_list[1]
        except IndexError:
            room_id = evt.room_id

        return await info(evt=evt, room_id=room_id)

    elif action == "list":
        return await _list(evt=evt)
    elif action == "set":
        return await _set(evt=evt)


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

        room_id = await evt.intent.create_room(
            name=name,
            invitees=invitees
            if evt.config["acd.queues.user_add_method"] == "invite"
            else evt.config["acd.queues.invitees"],
            topic=description.strip(),
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
    json_response["data"] = {"detail": detail, "member": member, "room_id": queue.room_id}

    json_response["status"] = 200

    detail = detail.replace("queue", queue.room_id).replace("member", member)
    evt.log.debug(detail)
    await evt.reply(detail)
    return json_response


async def delete(evt: CommandEvent, queue_id: RoomID, force: Optional[bool] = False) -> Dict:
    """It deletes a queue if the user is alone in the room or
    if the user sends the argument `force` in `yes`

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent
    queue_id : RoomID
        The room ID of the queue to delete.
    force : Optional[bool], optional
        Optional[bool] = False

    Returns
    -------
        A JSON response

    """
    json_response = {}
    queue = await Queue.get_by_room_id(room_id=queue_id, create=False)

    if not queue:
        detail = "The queue has not been found"
        json_response["data"] = {"error": detail}
        json_response["status"] = 422
        evt.log.error(detail)
        await evt.reply(detail)
        return json_response

    members = await evt.intent.get_joined_members(room_id=queue_id)

    if len(members) > 1:
        if force:
            await queue.clean_up()
            detail = "The queue has been deleted"
            json_response["status"] = 200
            json_response["data"] = {"detail": detail}
            evt.log.debug(detail)
            return json_response
        else:
            detail = (
                "You can only delete the queues in which you are alone "
                "or send the argument force in `yes`"
            )
            json_response["data"] = {"error": detail}
            json_response["status"] = 422
            evt.log.error(detail)
            await evt.reply(detail)
            return json_response


async def update(
    evt: CommandEvent, room_id: RoomID, name: str, description: Optional[str]
) -> Dict:
    """It updates the name and description of a queue

    Parameters
    ----------
    evt : CommandEvent
        The event object.
    room_id : RoomID
        The room ID of the room where the queue is.
    name : str
        The name of the queue.
    description : Optional[str]
        The description of the queue.

    Returns
    -------
        A dictionary with the status code and the data.

    """
    json_response = {}
    queue = await Queue.get_by_room_id(room_id=room_id, create=False)

    if not queue:
        detail = "It's not a queue"
        json_response["data"] = {"error": detail}
        json_response["status"] = 422
        evt.log.error(detail)
        await evt.reply(detail)
        return json_response

    await queue.update_name(new_name=name)
    await queue.update_description(new_description=description.strip())

    detail = "The queue has been updated"
    json_response["status"] = 200
    json_response["data"] = {"detail": detail}
    evt.log.debug(detail)
    await evt.reply(detail)
    return json_response


async def info(evt: CommandEvent, room_id: RoomID) -> Dict:
    """It returns a JSON response with the queue information

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent - This is the event that triggered the command.
    room_id : RoomID
        The room ID of the queue you want to get information about.

    Returns
    -------
        A dictionary with the data and status.

    """

    json_response = {}
    queue = await Queue.get_by_room_id(room_id=room_id, create=False)

    if not queue:
        detail = f"It's not a queue"
        json_response["data"] = {"error": detail}
        json_response["status"] = 422
        evt.log.error(detail)
        await evt.reply(detail)
        return json_response

    memberships = await QueueMembership.get_by_queue(fk_queue=queue.id)
    text = f"#### Room: {await queue.formatted_room_id()}"

    _memberships: List[Dict[str:Any]] = []

    if memberships:
        text += "\n#### Current memberships:"
        for membership in memberships:
            user: User = await User.get_by_id(membership.fk_user)
            text += f"\n\n- {await user.formatted_displayname()} -> state: {membership.state} || paused: {membership.paused}"
            _memberships.append(
                {
                    "user_id": user.mxid,
                    "displayname": await user.get_displayname(),
                    "is_admin": user.is_admin,
                    "state": membership.state,
                    "paused": membership.paused,
                    "creation_date": membership.creation_date.strftime("%Y-%m-%d %H:%M:%S%z")
                    if membership.creation_date
                    else None,
                    "state_date": membership.state_date.strftime("%Y-%m-%d %H:%M:%S%z")
                    if membership.state_date
                    else None,
                    "pause_date": membership.pause_date.strftime("%Y-%m-%d %H:%M:%S%z")
                    if membership.pause_date
                    else None,
                    "pause_reason": membership.pause_reason,
                }
            )
    await evt.reply(text=text)

    return {
        "data": {
            "queue": {
                "name": queue.name,
                "room_id": queue.room_id,
                "description": queue.description,
                "memberships": _memberships,
            }
        },
        "status": 200,
    }


async def _list(evt: CommandEvent) -> Dict:
    """`list` returns a list of all registered queues

    Parameters
    ----------
    evt : CommandEvent
        The event object.

    Returns
    -------
        A dictionary with a status code and a data key.

    """
    queues = await Queue.get_all()

    text = "#### Registered queues"

    if not queues:
        await evt.reply(text + "\nNo rooms available")
        return {
            "data": {"queues": []},
            "status": 200,
        }

    _queues = []

    for queue in queues:
        text += f"\n- {await queue.formatted_room_id()}" + (
            f"-> `{queue.description}`" if queue.description else ""
        )
        _queues.append(
            {
                "room_id": queue.room_id,
                "name": queue.name or None,
                "description": queue.description or None,
            }
        )

    await evt.reply(text)

    return {
        "data": {"queues": _queues},
        "status": 200,
    }


async def _set(evt: CommandEvent) -> Dict:
    """This function will add a queue to the database and synchronize it with the room

    Parameters
    ----------
    evt : CommandEvent
        The event object that triggered the command.

    Returns
    -------
        A dictionary with a status and data.

    """

    try:
        queue_id = evt.args_list[1]
    except IndexError:
        queue_id = evt.room_id

    queue = await Queue.get_by_room_id(room_id=queue_id, create=False)
    if queue:
        detail = "The queue already exists"
        await evt.reply(text=detail)
        return {
            "data": {"detail": detail},
            "status": 422,
        }

    queue = await Queue.get_by_room_id(room_id=queue_id)
    await queue.sync()

    detail = "The queue has been added and synchronized"
    await evt.reply(text=detail)

    return {
        "data": {"detail": detail},
        "status": 200,
    }
