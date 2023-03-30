from ..client import ProvisionBridge
from ..portal import Portal
from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

message = CommandArg(
    name="message",
    help_text="Message to be sent",
    is_required=True,
    example="Hello {{1}} your ticket {{2}} has been resolved",
)

room_id = CommandArg(
    name="room_id",
    help_text="Room where the template will be sent",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[message],
)


@command_handler(
    name="template",
    help_text=("This command is used to send templates"),
    help_args=[room_id],
)
async def template(evt: CommandEvent):
    """This function is used to send a template to a room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent
    """

    try:
        room_id = evt.args_list[0]
        message = evt.args_list[1]
    except IndexError:
        detail = "You have not all arguments"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    puppet: Puppet = await Puppet.get_by_portal(room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id, create=False, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    if not puppet or not portal:
        return

    if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
        bridge_connector = ProvisionBridge(
            session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
        )

        # If another bridge must send templates, make this method (gupshup_template) generic.
        await bridge_connector.gupshup_template(
            room_id=room_id, user_id=evt.intent.mxid, template=message
        )
    else:
        # If there's no send_template_command the message send directly to client
        await portal.send_formatted_message(text=message)
