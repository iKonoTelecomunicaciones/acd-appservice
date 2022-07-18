import asyncio

from mautrix.types import PresenceState

from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="transfer",
    help_text=("Command that transfers a client to an campaign_room."),
    help_args="<_customer_room_id_> <_campaign_room_id_>",
)
async def transfer(evt: CommandEvent) -> str:
    """The function is called when the `transfer` command is called.
    It checks if the command has the correct number of arguments,
    then it checks if the room is locked,
    if it is not,
    it locks the room and starts the transfer process

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent
    """

    if len(evt.args) < 2:
        detail = f"{evt.cmd} command incomplete arguments"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    customer_room_id = evt.args[1]
    campaign_room_id = evt.args[2]

    # Checking if the room is locked, if it is, it returns.
    if evt.agent_manager.room_manager.is_room_locked(room_id=customer_room_id, transfer=True):
        evt.log.debug(f"Room: {customer_room_id} LOCKED by Transfer room")
        return

    evt.log.debug(f"INIT TRANSFER to ROOM {campaign_room_id}")

    # Locking the room so that no other transfer can be made to the room.
    evt.agent_manager.room_manager.lock_room(room_id=customer_room_id, transfer=True)
    is_agent = evt.agent_manager.is_agent(agent_id=evt.sender)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if is_agent:
        transfer_author = evt.sender
    else:
        agent_id = await evt.agent_manager.get_room_agent(room_id=customer_room_id)
        transfer_author = agent_id

    # Creating a task that will be executed in the background.
    asyncio.create_task(
        evt.agent_manager.loop_agents(
            customer_room_id=customer_room_id,
            campaign_room_id=campaign_room_id,
            agent_id=evt.agent_manager.CURRENT_AGENT.get(campaign_room_id),
            transfer_author=transfer_author,
        )
    )


@command_handler(
    name="transfer_user",
    help_text=("Command that transfers a client from one agent to another."),
    help_args="<_customer_room_id_> <_agent_id_>",
)
async def transfer_user(evt: CommandEvent) -> str:
    """It checks if the room is locked,if not, it locks it, checks if the sender is an agent,
    if not, it gets the agent id from the room,
    checks if the target agent is the same as the agent in the room,
    if not, it checks if the target agent is online,
    if so, it forces the agent to join the room,
    if not, it sends a message to the room saying the agent is not available,
    and finally, it unlocks the room

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    if len(evt.args) < 2:
        detail = f"{evt.cmd} command incomplete arguments"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    customer_room_id = evt.args[1]
    target_agent_id = evt.args[2]

    # Checking if the room is locked, if it is, it returns.
    if evt.agent_manager.room_manager.is_room_locked(room_id=customer_room_id, transfer=True):
        evt.log.debug(f"Room: {customer_room_id} LOCKED by Transfer user")
        return

    evt.log.debug(f"INIT TRANSFER to AGENT {target_agent_id}")

    # Locking the room so that no other transfer can be made to the room.
    evt.agent_manager.room_manager.lock_room(room_id=customer_room_id, transfer=True)
    is_agent = evt.agent_manager.is_agent(agent_id=evt.sender)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if is_agent:
        transfer_author = evt.sender
    else:
        agent_id = await evt.agent_manager.get_room_agent(room_id=customer_room_id)
        transfer_author = agent_id

    # Checking if the agent is already in the room, if so, it sends a message to the room.
    if transfer_author == target_agent_id:
        msg = f"El agente {target_agent_id} ya está en la sala."
        await evt.intent.send_notice(room_id=customer_room_id, text=msg)
    else:
        presence_response = await evt.agent_manager.room_manager.get_user_presence(
            user_id=target_agent_id
        )
        evt.log.debug(
            f"PRESENCE RESPONSE: "
            f"[{target_agent_id}] -> [{presence_response.presence if presence_response else None}]"
        )
        if presence_response and presence_response.presence == PresenceState.ONLINE:
            await evt.agent_manager.force_invite_agent(
                room_id=customer_room_id, agent_id=target_agent_id, transfer_author=transfer_author
            )
        else:
            msg = f"El agente {target_agent_id} no está disponible."
            await evt.intent.send_notice(room_id=customer_room_id, text=msg)

    evt.agent_manager.room_manager.unlock_room(room_id=customer_room_id, transfer=True)
