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
    """
    Command that allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given.
    """

    evt.log.debug(f"Incoming command is :: {evt.args}")

    if len(evt.args) < 2:
        detail = "acd command incomplete arguments"
        evt.log.error(detail)
        return detail

    customer_room_id = evt.args[1]
    campaign_room_id = evt.args[2] if len(evt.args) >= 3 else None
    room_params = f"acd {customer_room_id} {campaign_room_id}"
    joined_message = (evt.args[len(room_params) :]).strip() if len(evt.args) > 3 else None

    # Si el ususiario es un puppet entonces ejecutamos el proceso de distribución con el
    # Sino entonces con el bot del appservice
    if evt.sender_user_id != evt.acd_appservice.az.bot_mxid:
        puppet: Puppet = await Puppet.get_puppet_by_mxid(evt.sender_user_id)
        agent_manager: AgentManager = AgentManager(
            acd_appservice=evt.acd_appservice,
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
            evt.log.error(f"### process_distribution Error: {e}")
    else:
        try:
            await evt.acd_appservice.matrix.agent_manager.process_distribution(
                customer_room_id=customer_room_id,
                campaign_room_id=campaign_room_id,
                joined_message=joined_message,
            )
        except Exception as e:
            evt.log.error(f"### process_distribution Error: {e}")
