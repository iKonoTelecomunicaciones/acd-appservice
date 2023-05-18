from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from typing import Any, Dict

from mautrix.types import EventType, StateEvent

from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

event_type_arg = CommandArg(
    name="--event-type or -e",
    help_text="Event_type you want to send",
    is_required=True,
    example="`m.room.name` | `m.custom.event`",
)

content_arg = CommandArg(
    name="--content or -c",
    help_text="The content to send",
    is_required=True,
    example=(
        """

        {
            "tags": ["tag1", "tag2", "tag3"]
        }
        """
    ),
)

room_id_arg = CommandArg(
    name="--room-id or -r",
    help_text="Room where the status event is to be sent",
    is_required=True,
    example="`!foo:foo.com`",
)


def args_parser():
    parser = ArgumentParser(description="STATE EVENT", exit_on_error=False)
    parser.add_argument("--event-type", "-e", dest="event_type", type=str, required=True)
    parser.add_argument("--content", "-c", dest="content", type=str, required=True)
    parser.add_argument(
        "--room-id",
        "-r",
        dest="room_id",
        type=str,
    )

    return parser


@command_handler(
    name="state_event",
    help_text=("Command that sends a state event to matrix"),
    help_args=[room_id_arg, event_type_arg, content_arg],
    args_parser=args_parser(),
)
async def state_event(evt: CommandEvent) -> Dict | None:
    """It receives a message from the client, parses it, and sends a state event to the room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dictionary

    """

    puppet: Puppet = await Puppet.get_by_portal(evt.cmd_args.room_id)

    if not puppet:
        return

    args: Namespace = evt.cmd_args
    room_id: str = args.room_id
    event_type: StateEvent = args.event_type
    content: Dict(str, Any) = args.content

    event_type = EventType.find(event_type, EventType.Class.STATE)

    try:
        content = json.loads(content)
    except Exception as e:
        detail = f"Error processing content - {e}"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 500}

    await puppet.agent_manager.signaling.send_state_event(
        room_id=room_id, event_type=event_type, content=content
    )
