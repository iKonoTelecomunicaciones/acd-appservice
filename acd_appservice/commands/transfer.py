import asyncio

from mautrix.types import PresenceState

from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="transfer",
    help_text=("Command that transfers a client to an room."),
    help_args="<_customer_room_id_> <_campaign_room_id|agent_id_>",
)
async def transfer(evt: CommandEvent) -> str:

    if len(evt.args) < 2:
        detail = f"{evt.cmd} command incomplete arguments"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    customer_room_id = evt.args[1]
    target_agent_id, campaign_room_id = (
        evt.args[2],
        None if evt.agent_manager.is_agent(agent_id=evt.args[2]) else None,
        evt.args[2],
    )

    transfer_author = evt.sender
    if evt.agent_manager.room_manager.is_room_locked(room_id=customer_room_id, transfer="ok"):
        evt.log.debug(f"Room: {customer_room_id} LOCKED by Transfer")
        return

    evt.agent_manager.room_manager.lock_room(room_id=customer_room_id, transfer="ok")

    is_agent = evt.agent_manager.is_agent(agent_id=evt.sender)

    agent_id = await evt.agent_manager.get_room_agent(room_id=customer_room_id)
    if not is_agent:
        transfer_author = agent_id

    if target_agent_id:
        presence_response = await evt.intent.get_presence(user_id=target_agent_id)
        if presence_response.presence == PresenceState.ONLINE:
            if agent_id == target_agent_id:
                msg = f"El agente {target_agent_id} ya está en la sala."
                evt.intent.send_text(room_id=customer_room_id, text=msg)
                evt.agent_manager.room_manager.unlock_room(room_id=customer_room_id, transfer="ok")
                return

            evt.agent_manager.force_join_agent(room_id=customer_room_id, agent_id=target_agent_id)
        else:
            msg = f"El agente {target_agent_id} no está disponible."
            evt.intent.send_text(room_id=customer_room_id, text=msg)
            evt.agent_manager.room_manager.unlock_room(room_id=customer_room_id, transfer="ok")
            return

        return

    if not campaign_room_id:
        return

    asyncio.create_task(
        await evt.agent_manager.loop_agents(
            customer_room_id=customer_room_id,
            campaign_room_id=campaign_room_id,
            agent_id=evt.agent_manager.CURRENT_AGENT,
            transfer_author=transfer_author,
        )
    )


@command_handler(
    name="transfer-user",
    help_text=("Command that transfers a client to an room."),
    help_args="<_customer_room_id_> <_agent_id_>",
)
async def transfer_user(evt: CommandEvent) -> str:
    await transfer(evt)
