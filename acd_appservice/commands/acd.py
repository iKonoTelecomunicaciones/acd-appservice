from re import match

from ..portal import Portal
from ..puppet import Puppet
from ..util import Util
from .handler import CommandArg, CommandEvent, command_handler

destination = CommandArg(
    name="destination",
    help_text="Queue room_id or agent mxid where the customer will be distributed",
    is_required=True,
    example="`!foo:foo.com`",
)

joined_message = CommandArg(
    name="joined_message",
    help_text="Message that will be sent when the agent joins the customer room",
    is_required=False,
    example='"{agentname} join to room"',
)

put_enqueued_portal = CommandArg(
    name="put_enqueued_portal",
    help_text=(
        "If the chat was not distributed, should the portal be enqueued?\n"
        "Note: This parameter is only using when destination is a queue"
    ),
    is_required=False,
    example="`yes` | `no`",
)

force_distribution = CommandArg(
    name="force_distribution",
    help_text=(
        "You want to force the agent distribution?\n"
        "Note: This parameter is only using when destination is an agent"
    ),
    is_required=False,
    example="`yes` | `no`",
)

customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be distributed",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[destination, joined_message, put_enqueued_portal, force_distribution],
)


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "a queue or agent and an optionally joining message can be given."
    ),
    help_args=[customer_room_id],
)
async def acd(evt: CommandEvent) -> str:
    """It allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    if len(evt.args_list) < 2:
        detail = "You have not all arguments"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    customer_room_id = evt.args_list[0]
    destination = evt.args_list[1]
    joined_message = ""
    put_enqueued_portal = True
    force_distribution = False

    if len(evt.args_list) > 2:
        try:
            if Util.is_room_id(destination):
                put_enqueued_portal = False if evt.args_list[3] == "no" else True
            elif Util.is_user_id(destination):
                force_distribution = False if evt.args_list[3] == "no" else True
            joined_message = evt.args_list[2]
        except IndexError:
            if match("no|yes", evt.args_list[2]):
                if Util.is_room_id(destination):
                    put_enqueued_portal = False if evt.args_list[2] == "no" else True
                elif Util.is_user_id(destination):
                    force_distribution = False if evt.args_list[2] == "no" else True
            else:
                joined_message = evt.args_list[2]

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    if not puppet:
        return

    portal: Portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    try:
        return await puppet.agent_manager.process_distribution(
            portal=portal,
            destination=destination,
            joined_message=joined_message,
            put_enqueued_portal=put_enqueued_portal,
            force_distribution=force_distribution,
        )
    except Exception as e:
        evt.log.exception(e)
