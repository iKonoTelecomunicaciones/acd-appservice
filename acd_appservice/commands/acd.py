from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be distributed",
    is_required=True,
    example="`!foo:foo.com`",
)

campaign_room_id = CommandArg(
    name="campaign_room_id",
    help_text="Campaign room_id where the customer will be distributed",
    is_required=False,
    example="`!foo:foo.com`",
)

joined_message = CommandArg(
    name="joined_message",
    help_text="Message that will be sent when the agent joins the customer room",
    is_required=False,
    example="{agentname} join to room",
)


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "optionally a campaign room and a joining message can be given."
    ),
    help_args=[customer_room_id, campaign_room_id, joined_message],
)
async def acd(evt: CommandEvent) -> str:
    """It allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=evt.args.customer_room_id)

    if not puppet:
        return

    try:
        await puppet.agent_manager.process_distribution(
            customer_room_id=evt.args.customer_room_id,
            campaign_room_id=evt.args.campaign_room_id,
            joined_message=evt.args.joined_message,
        )
    except Exception as e:
        evt.log.exception(e)
