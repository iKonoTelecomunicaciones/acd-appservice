from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Optional

from mautrix.types import RoomDirectoryVisibility, RoomID, UserID
from slugify import slugify

from ..events import ACDMembershipEvents, send_membership_event
from ..queue import Queue
from ..queue_membership import QueueMembership
from ..user import User
from ..util import Util
from .handler import CommandArg, CommandEvent, command_handler

name_arg = CommandArg(
    name="--name or -n",
    help_text="Queue room name",
    is_required=True,
    example='"My favourite queue"',
)

invitees_arg = CommandArg(
    name="--invitees or -i",
    help_text="Invitees to the queue",
    is_required=True,
    example="`@user1:foo.com @user2:foo.com @user3:foo.com ...`",
)

description_arg = CommandArg(
    name="--description or -d",
    help_text="Short description about the queue",
    is_required=False,
    example='"It is a queue to distribute chats"',
)


member_arg = CommandArg(
    name="--member or -m",
    help_text="Member to be added|deleted",
    is_required=True,
    example="@user1:foo.com",
)

queue_arg = CommandArg(
    name="--queue or -q",
    help_text=(
        "Queue where the member will be added|deleted, "
        "if no queue is provided the room_id where the command was sent will be taken."
    ),
    is_required=False,
    example="!foo:foo.com",
)

force_arg = CommandArg(
    name="--force or -f",
    help_text="Do you want to force queue deleting?",
    is_required=False,
    example="`yes` | `no`",
)

action_arg = CommandArg(
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
    sub_args=[
        {"description": "Create", "args": [name_arg, invitees_arg, description_arg]},
        {"description": "Add", "args": [member_arg, queue_arg]},
        {"description": "Remove", "args": [member_arg, queue_arg]},
        {"description": "Delete", "args": [queue_arg, force_arg]},
        {"description": "Update", "args": [name_arg, queue_arg, description_arg]},
        {"description": "Info", "args": [queue_arg]},
    ],
)


def args_parser():
    parser = ArgumentParser(description="QUEUE", exit_on_error=False)
    subparsers = parser.add_subparsers(dest="action")

    # Sub command create
    parser_create: ArgumentParser = subparsers.add_parser("create")
    parser_create.add_argument("--name", "-n", dest="name", type=str, required=True)
    parser_create.add_argument(
        "--invitees", "-i", dest="invitees", action="extend", nargs="+", type=str, required=True
    )
    parser_create.add_argument("--description", "-d", dest="description", type=str, required=False)

    # Sub command add
    parser_add: ArgumentParser = subparsers.add_parser("add")
    parser_add.add_argument("--member", "-m", dest="member", type=str, required=True)
    parser_add.add_argument("--queue", "-q", dest="queue", type=str, required=False)

    # Sub command remove
    parser_remove: ArgumentParser = subparsers.add_parser("remove")
    parser_remove.add_argument("--member", "-m", dest="member", type=str, required=True)
    parser_remove.add_argument("--queue", "-q", dest="queue", type=str, required=False)

    # Sub command delete
    parser_delete: ArgumentParser = subparsers.add_parser("delete")
    parser_delete.add_argument("--queue", "-q", dest="queue", type=str, required=False)
    parser_delete.add_argument(
        "--force",
        "-f",
        dest="force",
        type=str,
        required=False,
        choices=["yes", "no"],
        default="no",
    )

    # Sub command update
    parser_update: ArgumentParser = subparsers.add_parser("update")
    parser_update.add_argument("--queue", "-q", dest="queue", type=str, required=False)
    parser_update.add_argument("--name", "-n", dest="name", type=str, required=False)
    parser_update.add_argument("--description", "-d", dest="description", type=str, required=False)

    # Sub command info
    parser_info: ArgumentParser = subparsers.add_parser("info")
    parser_info.add_argument("--queue", "-q", dest="queue", type=str, required=False)

    # Sub command list
    parser_list: ArgumentParser = subparsers.add_parser("list")

    # Sub command set
    parser_set: ArgumentParser = subparsers.add_parser("set")
    parser_set.add_argument("--queue", "-q", dest="queue", type=str, required=False)

    return parser


@command_handler(
    management_only=False,
    needs_admin=False,
    name="queue",
    help_text=(
        "Create a queue. A queue is a matrix room containing agents that will be used "
        "for chat distribution. `invitees` is a comma-separated list of user_ids."
    ),
    help_args=[action_arg],
    args_parser=args_parser(),
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

    args: Namespace = evt.cmd_args
    action = args.action

    # Creating a queue.
    if action == "create":
        name: str = args.name
        invitees: List[UserID] = args.invitees
        description: str = args.description.strip() if args.description else None

        return await create(evt=evt, name=name, invitees=invitees, description=description)

    elif action in ["add", "remove"]:
        member: UserID = args.member
        queue_room_id: RoomID = args.queue if args.queue else evt.room_id
        queue = await Queue.get_by_room_id(room_id=queue_room_id, create=False)

        if not queue:
            msg = "Incoming queue does not exist"
            evt.log.error(msg)
            await evt.reply(msg)
            return Util.create_response_data(detail=msg, room_id=queue_room_id, status=422)

        return await add_remove(evt=evt, action=action, member=member, queue_id=queue_room_id)

    elif action == "delete":
        queue_room_id = args.queue
        force = False if args.force == "no" else True

        queue = await Queue.get_by_room_id(room_id=queue_room_id, create=False)
        if not queue:
            msg = "Incoming queue does not exist"
            evt.log.error(msg)
            await evt.reply(msg)
            return Util.create_response_data(detail=msg, room_id=queue_room_id, status=422)

        return await delete(evt=evt, queue_id=queue_room_id, force=force)

    elif action == "update":
        queue_room_id = args.queue if args.queue else evt.room_id
        name = args.name
        description = args.description

        return await update(evt=evt, room_id=queue_room_id, name=name, description=description)

    elif action == "info":
        queue_room_id = args.queue if args.queue else evt.room_id

        return await info(evt=evt, room_id=queue_room_id)

    elif action == "list":
        return await _list(evt=evt)
    elif action == "set":
        queue_room_id: RoomID = args.queue if args.queue else evt.room_id
        return await _set(evt=evt, queue_room_id=queue_room_id)


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
    json_response = {"data": None, "status": 0}

    name_slugified = slugify(text=name, separator="_")
    queue_exists = await Queue.get_by_slugified_name(name_slugified=name_slugified)

    if queue_exists:
        detail = "Queue with same name already exists"
        evt.log.error(detail)
        await evt.reply(detail)
        json_response["data"] = {"error": detail}
        json_response["status"] = 409
        return json_response

    if isinstance(invitees, str):
        invitees: List[UserID] = [invitee.strip() for invitee in invitees.split(",")]

    # Checking if the config value is set to public. If it is, it sets the visibility to public.
    if evt.config["acd.queues.visibility"] == "public":
        visibility = RoomDirectoryVisibility.PUBLIC

    try:
        room_id = await evt.intent.create_room(
            name=name,
            topic=description,
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

    # Queue default invitees
    invitees += evt.config["acd.queues.invitees"]

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
            await send_membership_event(
                event_type=ACDMembershipEvents.MemberAdd,
                queue=queue,
                member=member,
                penalty=None,
                sender=evt.sender.mxid,
            )
        elif action == "remove":
            await queue.remove_member(member)
            await send_membership_event(
                event_type=ACDMembershipEvents.MemberRemove,
                queue=queue,
                member=member,
                sender=evt.sender.mxid,
            )
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
    queue: Queue = await Queue.get_by_room_id(room_id=queue_id, create=False)

    if not queue:
        detail = "The queue has not been found"
        json_response["data"] = {"error": detail}
        json_response["status"] = 422
        evt.log.error(detail)
        await evt.reply(detail)
        return json_response

    members = await queue.get_joined_users()

    async def delete_queue() -> Dict:
        for member in members:
            # Remove the room (queue) tag for the member
            user: User = await User.get_by_mxid(member.mxid)
            await user.remove_room_tag(room_id=queue_id, tag="m.queue")
        await queue.clean_up()
        detail = "The queue has been deleted"
        json_response["status"] = 200
        json_response["data"] = {"detail": detail}
        evt.log.debug(detail)
        return json_response

    if force:
        return await delete_queue()

    if len(members) == 1 and members[0].mxid == evt.intent.bot.mxid:
        return await delete_queue()

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
    json_response = {"data": None, "status": 0}
    queue = await Queue.get_by_room_id(room_id=room_id, create=False)

    name_slugified = slugify(text=name, separator="_")
    queue_exists = await Queue.get_by_slugified_name(name_slugified=name_slugified)

    if queue_exists and queue_exists.room_id != room_id:
        detail = "Queue with same name already exists"
        evt.log.error(detail)
        await evt.reply(detail)
        json_response["data"] = {"detail": detail}
        json_response["status"] = 409
        return json_response

    if not queue:
        detail = "It's not a queue"
        json_response["data"] = {"error": detail}
        json_response["status"] = 422
        evt.log.error(detail)
        await evt.reply(detail)
        return json_response

    await queue.update_name(new_name=name)
    await queue.update_description(new_description=description)

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

    memberships: List[QueueMembership] = await QueueMembership.get_by_queue(fk_queue=queue.id)
    text = f"#### Room: {await queue.get_formatted_room_id()}"

    _memberships: List[Dict[str:Any]] = []

    if memberships:
        text += "\n#### Current memberships:"
        for membership in memberships:
            user: User = await User.get_by_id(membership.fk_user)
            text += f"\n\n- {await user.get_formatted_displayname()} -> state: {membership.state.value} || paused: {membership.paused}"
            _memberships.append(
                {
                    "user_id": user.mxid,
                    "displayname": await user.get_displayname(),
                    "is_admin": user.is_admin,
                    "state": membership.state.value,
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
    queues: List[Queue] = await Queue.get_all()

    text = "#### Registered queues"

    if not queues:
        await evt.reply(text + "\nNo rooms available")
        return {
            "data": {"queues": []},
            "status": 200,
        }

    _queues = []

    for queue in queues:
        text += f"\n- {await queue.get_formatted_room_id()}" + (
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


async def _set(evt: CommandEvent, queue_room_id: RoomID) -> Dict:
    """This function will add a queue to the database and synchronize it with the room

    Parameters
    ----------
    evt : CommandEvent
        The event object that triggered the command.

    Returns
    -------
        A dictionary with a status and data.

    """

    queue = await Queue.get_by_room_id(room_id=queue_room_id)
    await queue.sync()

    detail = "The queue has been added and synchronized"
    await evt.reply(text=detail)

    return {
        "data": {"detail": detail},
        "status": 200,
    }
