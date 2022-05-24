from ..agent_manager import AgentManager
from ..puppet import Puppet
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "optionally a campaign room and a joining message can be given."
    ),
    help_args="<_customer_room_id_> <_campaign_room_id_> <_joined_message_>",
)
async def acd(evt: CommandEvent) -> str:
    """It allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    if len(evt.args) < 2:
        detail = "acd command incomplete arguments"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    customer_room_id = evt.args[1]
    campaign_room_id = evt.args[2] if len(evt.args) >= 3 else None
    room_params = f"acd {customer_room_id} {campaign_room_id}"
    joined_message = (evt.args[len(room_params) :]).strip() if len(evt.args) > 3 else None

    # Se crea el proceso de distribución dado el puppet que esté en la sala del cliente
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)
    agent_manager: AgentManager = AgentManager(
        room_manager=evt.agent_manager.room_manager,
        intent=puppet.intent,
        control_room_id=puppet.control_room_id,
    )
    try:
        await agent_manager.process_distribution(
            customer_room_id=customer_room_id,
            campaign_room_id=campaign_room_id,
            joined_message=joined_message,
        )
    except Exception as e:
        evt.log.exception(e)
