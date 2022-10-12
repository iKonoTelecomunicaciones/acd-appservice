import json
from typing import Dict

from ..http_client import ProvisionBridge
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
    if not evt.args:
        detail = "Incomplete arguments for <code>template</code> command"
        await evt.reply(text=detail)
        evt.log.error(detail)
        return

    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)

    if not puppet:
        return

    try:
        evt.log.debug(evt.text)
        incoming_params = json.loads(evt.text)
    except Exception as e:
        await evt.reply(text=e)
        evt.log.trace(e)
        return

    room_id = incoming_params.get("room_id")
    template_name = incoming_params.get("template_name")
    template_message = incoming_params.get("template_message")

    # Validating incoming params
    if not room_id:
        msg = "You must specify a room ID"
        await evt.reply(text=msg)
        evt.log.error(msg)
        return

    if not template_name or not template_message:
        msg = "You must specify a template name and message"
        await evt.reply(text=msg)
        evt.log.error(msg)
        return

    if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
        bridge_connector = ProvisionBridge(
            session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
        )

        # TODO Si otro bridge debe enviar templates, hacer generico este metodo (gupshup_template)
        await bridge_connector.gupshup_template(
            room_id=room_id, user_id=evt.intent.mxid, template=template_message
        )
    else:
        # If there's no send_template_command the message send directly to client
        await evt.intent.send_text(room_id=room_id, text=template_message)
