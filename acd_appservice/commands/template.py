import json
from typing import Dict

from ..client import ProvisionBridge
from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

room_id = CommandArg(
    name="room_id",
    help_text="Room where the template will be sent",
    is_required=True,
    example="`!foo:foo.com`",
)

message = CommandArg(
    name="message",
    help_text="Message to be sent",
    is_required=True,
    example="Hello {{1}} your ticket {{2}} has been resolved",
)


@command_handler(
    name="template",
    help_text=("This command is used to send templates"),
    help_args=[room_id, message],
)
async def template(evt: CommandEvent):
    """This function is used to send a template to a room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent
    """

    puppet: Puppet = await Puppet.get_customer_room_puppet(evt.args.room_id)

    if not puppet:
        return

    if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
        bridge_connector = ProvisionBridge(
            session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
        )

        # If another bridge must send templates, make this method (gupshup_template) generic.
        await bridge_connector.gupshup_template(
            room_id=evt.args.room_id, user_id=evt.intent.mxid, template=evt.args.message
        )
    else:
        # If there's no send_template_command the message send directly to client
        await puppet.room_manager.send_formatted_message(
            room_id=evt.args.room_id, msg=evt.args.message
        )
