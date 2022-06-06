import json
from typing import Dict

from mautrix.types import EventType

from ..puppet import Puppet
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="state_event",
    help_text=("Command that sends a status event to matrix"),
    help_args="<_dict_>",
)
async def state_event(evt: CommandEvent) -> Dict:
    if len(evt.args) <= 1:
        detail = "state_event command incomplete arguments"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    prefix_and_command_length = len(f"{evt.cmd}")

    incoming_message = (evt.text[prefix_and_command_length:]).strip()

    try:
        incoming_params = json.loads(incoming_message)
    except Exception as e:
        evt.log.exception(f"Error processing incoming params, skipping message - {e}")
        return

    room_id = incoming_params.get("room_id")
    event_type = incoming_params.get("event_type")

    # Validating incoming params
    if not room_id:
        evt.log.error(f"You must specify a room ID to process_state_event")
        return

    if not event_type:
        evt.log.error(
            f"You must specify a type event for the room: {room_id} - process_state_event"
        )
        return

    if event_type == "ik.chat.tag":
        event_type = EventType.find("ik.chat.tag", EventType.Class.STATE)
        content = {"tags": incoming_params.get("tags")}

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
    if puppet:
        evt.agent_manager.signaling.intent = puppet.intent
        await evt.agent_manager.signaling.send_state_event(
            room_id=room_id, event_type=event_type, content=content
        )
    else:
        evt.log.error(f"No puppet found to create the tag {content}")
