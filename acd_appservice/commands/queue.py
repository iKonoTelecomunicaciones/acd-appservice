from typing import Dict, List

from mautrix.types import RoomDirectoryVisibility, UserID

from ..queue import Queue
from .handler import CommandArg, CommandEvent, command_handler

action = CommandArg(
    name="action",
    help_text="Action to be taken in the queue",
    is_required=True,
    example="`create`",
)

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
    default="",
)


@command_handler(
    management_only=True,
    needs_admin=True,
    name="queue",
    help_text=(
        "Create a queue. A queue is a matrix room containing agents that will be used "
        "for chat distribution. `invitees` is a comma-separated list of user_ids."
    ),
    help_args=[action],
    help_sub_args=[name, invitees, description],
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

    invitees = []
    visibility = RoomDirectoryVisibility.PRIVATE
    queue = None

    json_response = {"data": None, "status": 0}

    # Creating a queue.
    if evt.args.action == "create":

        # Checking if the invitees are specified.
        # If they are, it will split them by comma and strip them.
        if evt.args.invitees:
            invitees: List[UserID] = [invitee.strip() for invitee in evt.args.invitees.split(",")]

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
                {f' -> {str(evt.args.description).strip()}' if evt.args.description else ''}
            """

            room_id = await evt.intent.create_room(
                name=evt.args.name,
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

        # Creating a new queue object and saving it to the database.
        queue: Queue = await Queue.get_by_room_id(room_id=room_id)
        queue.name = evt.args.name
        queue.description = evt.args.description if evt.args.description else None
        await queue.save()

        # Forcing the invitees to join the room.
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