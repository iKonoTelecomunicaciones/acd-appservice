import json
from typing import Dict

from ..http_client import ProvisionBridge, client
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
        await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)
        return

    room_id = incoming_params.get("room_id")
    template_name = incoming_params.get("template_name")
    template_message = incoming_params.get("template_message")

    # Validating incoming params
    if not room_id:
        msg = "You must specify a room ID"
        await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)
        return

    bridge = await evt.room_manager.get_room_bridge(room_id=room_id)

    if not template_name or not template_message:
        msg = "You must specify a template name and message"
        await evt.intent.send_text(room_id=puppet.control_room_id, text=msg)
        return

    if evt.config[f"bridges.{bridge}.send_template_command"]:
        bridge_connector = ProvisionBridge(
            session=client.session, config=evt.config, bridge=bridge
        )

        # TODO Si otro bridge debe enviar templates, hacer generico este metodo (gupshup_template)
        await bridge_connector.gupshup_template(
            room_id=room_id, user_id=evt.intent.mxid, template=template_message
        )
    else:
        # If there's no send_template_command the message send directly to client
        await evt.intent.send_text(room_id=room_id, text=template_message)
