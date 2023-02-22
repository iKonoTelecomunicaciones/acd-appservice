from ..portal import Portal
from ..puppet import Puppet
from ..queue import Queue
from .handler import CommandArg, CommandEvent, command_handler

campaign_room_id = CommandArg(
    name="campaign_room_id",
    help_text="Campaign room_id where the customer will be distributed",
    is_required=True,
    example="`!foo:foo.com`",
)

joined_message = CommandArg(
    name="joined_message",
    help_text="Message that will be sent when the agent joins the customer room",
    is_required=False,
    example="{agentname} join to room",
)

customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be distributed",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[campaign_room_id, joined_message],
)


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "optionally a campaign room and a joining message can be given."
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
    campaign_room_id = evt.args_list[1]

    try:
        joined_message = evt.args_list[2]
    except IndexError:
        joined_message = ""

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent
    )
    queue: Queue = await Queue.get_by_room_id(room_id=campaign_room_id)

    if not puppet:
        return

    try:
        return await puppet.agent_manager.process_distribution(
            portal=portal,
            queue=queue,
            joined_message=joined_message,
        )
    except Exception as e:
        evt.log.exception(e)
