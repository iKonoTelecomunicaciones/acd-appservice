import json
from typing import Dict

from ..puppet import Puppet
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="template",
    help_text=("This command is used to send templates"),
    help_args="<_room_id_> <_template_name_> <_template_message_> <_bridge_>",
)
async def template(evt: CommandEvent) -> Dict:
    """It receives a JSON string, parses it, and sends a message to a room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dictionary with the following keys:

    """
    # Checking if the command has arguments.
    if len(evt.args) <= 1:
        detail = "Incomplete arguments for <code>template</code> command"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    # Remove 'template' word and unify json template_data
    template_data = " ".join(evt.args[1:])
    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)
    try:
        incoming_params = json.loads(template_data)
    except Exception:
        msg = "Error processing incoming params, skipping message"
        return await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)

    room_id = incoming_params.get("room_id")
    template_name = incoming_params.get("template_name")
    template_message = incoming_params.get("template_message")
    bridge = incoming_params.get("bridge")

    send_template_command = None
    whatsapp_command_prefix = None
    for config_bridge in evt.config["bridges"]:
        if evt.config[f"bridges.{config_bridge}.prefix"] == bridge:
            whatsapp_command_prefix = bridge
            send_template_command = evt.config[f"bridges.{config_bridge}.send_template_command"]
            break

    # Validate bridge used
    # If there's no whatsapp_command_prefix means the received bridge isn't valid
    if not whatsapp_command_prefix:
        msg = "Bridge doesn't found, skipping message"
        return await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)

    # Validating incoming params
    if not room_id:
        msg = "You must specify a room ID"
        return await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)

    if not template_name or not template_message:
        msg = "You must specify a template name and message"
        return await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)

    if send_template_command:
        del incoming_params["bridge"]
        msg = f"{whatsapp_command_prefix} {send_template_command} {template_data}"
        await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)
    else:
        # If there's no send_template_command the message send directly to client
        await evt.intent.send_text(room_id=room_id, text=template_message)
