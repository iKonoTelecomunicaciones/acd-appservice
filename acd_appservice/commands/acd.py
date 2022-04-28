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

    evt.log.debug(f"{evt.args}")

    if len(evt.args) < 2:
        detail = "acd command incomplete arguments"
        evt.log.error(detail)
        return detail

    customer_room_id = evt.args[1]
    campaign_room_id = evt.args[2] if len(evt.args) >= 3 else None
    room_params = f"acd {customer_room_id} {campaign_room_id}"
    joined_message = (evt.args[len(room_params) :]).strip() if len(evt.args) > 3 else None

    if evt.sender_user_id != evt.acd_appservice.az.bot_mxid:
        puppet: Puppet = await Puppet.get_puppet_by_mxid(evt.sender_user_id)
        agent_manager: AgentManager = AgentManager(
            room_manager=evt.acd_appservice.matrix.room_manager,
            intent=puppet.intent,
            control_room_id=puppet.control_room_id,
        )
    else:
        agent_manager: AgentManager = AgentManager(
            room_manager=evt.acd_appservice.matrix.room_manager,
            intent=evt.acd_appservice.az.intent,
            control_room_id=evt.acd_appservice.config["acd.control_room_id"],
        )

    await agent_manager.process_distribution(
        customer_room_id=customer_room_id,
        campaign_room_id=campaign_room_id,
        joined_message=joined_message,
    )
