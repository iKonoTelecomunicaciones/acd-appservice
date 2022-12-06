import asyncio

from mautrix.types import PresenceState

from ..puppet import Puppet
from ..queue_membership import QueueMembershipState
from .handler import CommandArg, CommandEvent, command_handler

customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be transferred",
    is_required=True,
    example="`!foo:foo.com`",
)

campaign_room_id = CommandArg(
    name="campaign_room_id",
    help_text="Campaign room_id  where the customer will be transferred",
    is_required=True,
    example="`!foo:foo.com`",
)


@command_handler(
    name="transfer",
    help_text=("Command that transfers a client to an campaign_room."),
    help_args=[customer_room_id, campaign_room_id],
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

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=evt.args.customer_room_id)

    if not puppet:
        return

    # Checking if the room is locked, if it is, it returns.
    if puppet.room_manager.is_room_locked(room_id=evt.args.customer_room_id, transfer=True):
        evt.log.debug(f"Room: {evt.args.customer_room_id} LOCKED by Transfer room")
        return

    evt.log.debug(
        f"INIT TRANSFER for {evt.args.customer_room_id} to ROOM {evt.args.campaign_room_id}"
    )

    # Locking the room so that no other transfer can be made to the room.
    puppet.room_manager.lock_room(room_id=evt.args.customer_room_id, transfer=True)
    is_agent = puppet.agent_manager.is_agent(agent_id=evt.sender.mxid)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if is_agent:
        transfer_author = evt.sender.mxid
    else:
        agent_id = await puppet.agent_manager.get_room_agent(room_id=evt.args.customer_room_id)
        transfer_author = agent_id

    # Creating a task that will be executed in the background.
    asyncio.create_task(
        puppet.agent_manager.loop_agents(
            customer_room_id=evt.args.customer_room_id,
            campaign_room_id=evt.args.campaign_room_id,
            agent_id=puppet.agent_manager.CURRENT_AGENT.get(evt.args.campaign_room_id),
            transfer_author=transfer_author or evt.sender.mxid,
        )
    )


agent_id = CommandArg(
    name="agent_id",
    help_text="Agent to which the chat is distributed",
    is_required=True,
    example="@agent1:foo.com",
)

force = CommandArg(
    name="force",
    help_text="It's a flag that is used to decide if check the agent presence or join directly to room",
    is_required=False,
    example="`yes` | `no`",
)


@command_handler(
    name="transfer_user",
    help_text=(
        "Command that transfers a user from one agent to another, "
        "if you send `force` in `yes`, "
        "the agent is always going to be assigned to the chat no matter the agent presence."
    ),
    help_args=[customer_room_id, agent_id, force],
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

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=evt.args.customer_room_id)
    evt.args.force = evt.args.force or "no"

    if not puppet:
        return

    # Checking if the room is locked, if it is, it returns.
    if puppet.room_manager.is_room_locked(room_id=evt.args.customer_room_id, transfer=True):
        evt.log.debug(f"Room: {evt.args.customer_room_id} LOCKED by Transfer user")
        return

    evt.log.debug(f"INIT TRANSFER for {evt.args.customer_room_id} to AGENT {evt.args.agent_id}")

    # Locking the room so that no other transfer can be made to the room.
    puppet.room_manager.lock_room(room_id=evt.args.customer_room_id, transfer=True)
    is_agent = puppet.agent_manager.is_agent(agent_id=evt.sender.mxid)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if is_agent:
        transfer_author = evt.sender.mxid
    else:
        agent_id = await puppet.agent_manager.get_room_agent(room_id=evt.args.customer_room_id)
        transfer_author = agent_id

    # Checking if the agent is already in the room, if so, it sends a message to the room.
    if transfer_author == evt.args.agent_id:
        msg = f"The {evt.args.agent_id} agent is already in the room {evt.args.customer_room_id}"
        await evt.intent.send_notice(room_id=evt.args.customer_room_id, text=msg)
    else:
        # Switch between presence and agent operation login using config parameter
        # to verify if agent is available to be assigned to the chat
        if evt.config["acd.use_presence"]:
            presence_response = await puppet.agent_manager.get_agent_presence(
                agent_id=evt.args.agent_id
            )
            is_agent_online = (
                presence_response and presence_response.presence == PresenceState.ONLINE
            )
        else:
            presence_response = await puppet.agent_manager.get_agent_status(
                agent_id=evt.args.agent_id
            )
            is_agent_online = (
                presence_response
                and presence_response.get("presence") == QueueMembershipState.Online.value
            )

        evt.log.debug(
            f"PRESENCE RESPONSE: "
            f"[{evt.args.agent_id}] -> "
            f"""[{presence_response.get('presence') or presence_response.presence
            if presence_response else None}]"""
        )

        if is_agent_online or evt.args.force == "yes":
            await puppet.agent_manager.force_invite_agent(
                room_id=evt.args.customer_room_id,
                agent_id=evt.args.agent_id,
                transfer_author=transfer_author or evt.sender.mxid,
            )
        else:
            msg = f"Agent {evt.args.agent_id} is not available"
            await evt.intent.send_notice(room_id=evt.args.customer_room_id, text=msg)

    puppet.room_manager.unlock_room(room_id=evt.args.customer_room_id, transfer=True)
