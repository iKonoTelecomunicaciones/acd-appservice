from ..puppet import Puppet
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "optionally a campaign room and a joining message can be given."
    ),
    help_args="<_customer_room_id_> [_campaign_room_id_] [_joined_message_]",
)
async def acd(evt: CommandEvent) -> str:
    """It allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    if not evt.args:
        detail = f"{evt.command} command incomplete arguments"
        evt.log.error(detail)
        await evt.reply(text=detail)
        return

    customer_room_id = evt.args[0]
    campaign_room_id = evt.args[1] if len(evt.args) >= 2 else None

    joined_message = " ".join(evt.args[2:]).strip() if len(evt.args) >= 3 else None

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)

    if not puppet:
        return

    try:
        await puppet.agent_manager.process_distribution(
            customer_room_id=customer_room_id,
            campaign_room_id=campaign_room_id,
            joined_message=joined_message,
        )
    except Exception as e:
        evt.log.exception(e)
