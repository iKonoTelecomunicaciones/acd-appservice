from __future__ import annotations

import json
from typing import Dict

from mautrix.types import EventType

from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

room_id = CommandArg(
    name="room_id",
    help_text="Room where the status event is to be sent",
    is_required=True,
    example="`!foo:foo.com`",
)

event_type = CommandArg(
    name="event_type",
    help_text="Event_type you want to send",
    is_required=True,
    example="`m.room.name` | `m.custom.event`",
)

content = CommandArg(
    name="content",
    help_text="Message to be sent to the customer",
    is_required=True,
    example=(
        """

        {
            "tags": ["tag1", "tag2", "tag3"]
        }
        """
    ),
)


@command_handler(
    name="state_event",
    help_text=("Command that sends a state event to matrix"),
    help_args=[room_id, event_type, content],
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

    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)

    if not puppet:
        return

    event_type = EventType.find(evt.args.event_type, EventType.Class.STATE)

    try:
        content = json.loads(evt.args.content)
    except Exception as e:
        detail = f"Error processing content - {e}"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 500}

    await puppet.agent_manager.signaling.send_state_event(
        room_id=evt.args.room_id, event_type=event_type, content=content
    )
