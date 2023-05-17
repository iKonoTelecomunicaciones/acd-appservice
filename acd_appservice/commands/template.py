from argparse import ArgumentParser, Namespace

from ..client import ProvisionBridge
from ..portal import Portal
from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

message = CommandArg(
    name="--message or -m",
    help_text="Message to be sent",
    is_required=True,
    example="Hello {{1}} your ticket {{2}} has been resolved",
)

portal = CommandArg(
    name="--portal or -p",
    help_text="Room where the template will be sent",
    is_required=True,
    example="`!foo:foo.com`",
)


def args_parser():
    parser = ArgumentParser(description="TEMPLATE", exit_on_error=False)
    parser.add_argument("--message", "-m", dest="message", type=str, required=True)
    parser.add_argument("--portal", "-p", dest="portal", type=str, required=True)

    return parser


@command_handler(
    name="template",
    help_text=("This command is used to send templates"),
    help_args=[portal, message],
    args_parser=args_parser(),
)
async def template(evt: CommandEvent):
    """This function is used to send a template to a room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent
    """
    args: Namespace = evt.cmd_args
    portal_room_id = args.portal
    message = args.message

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id)
    portal: Portal = await Portal.get_by_room_id(
        portal_room_id,
        create=False,
        fk_puppet=puppet.pk,
        intent=puppet.intent,
        bridge=puppet.bridge,
    )

    if not puppet or not portal:
        return

    if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
        bridge_connector = ProvisionBridge(
            session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
        )

        # If another bridge must send templates, make this method (gupshup_template) generic.
        await bridge_connector.gupshup_template(
            room_id=portal_room_id, user_id=evt.intent.mxid, template=message
        )
    else:
        # If there's no send_template_command the message send directly to client
        await portal.send_formatted_message(text=message)
