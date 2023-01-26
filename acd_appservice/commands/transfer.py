import asyncio

from mautrix.types import PresenceState

from ..portal import Portal
from ..puppet import Puppet
from ..queue import Queue
from ..queue_membership import QueueMembershipState
from .handler import CommandArg, CommandEvent, command_handler

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

campaign_room_id = CommandArg(
    name="campaign_room_id",
    help_text="Campaign room_id  where the customer will be transferred",
    is_required=True,
    example="`!foo:foo.com`",
)

customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be transferred",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[campaign_room_id],
)

_customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be transferred",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[agent_id, force],
)


@command_handler(
    name="transfer",
    help_text=("Command that transfers a client to an campaign_room."),
    help_args=[customer_room_id],
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
    try:
        customer_room_id = evt.args_list[0]
        campaign_room_id = evt.args_list[1]
    except IndexError:
        detail = "You have not sent the argument customer_room_id"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)

    if not puppet:
        return

    # Checking if the room is locked, if it is, it returns.
    if puppet.room_manager.is_room_locked(room_id=customer_room_id, transfer=True):
        evt.log.debug(f"Room: {customer_room_id} LOCKED by Transfer room")
        return

    evt.log.debug(f"INIT TRANSFER for {customer_room_id} to ROOM {campaign_room_id}")

    # Locking the room so that no other transfer can be made to the room.
    puppet.room_manager.lock_room(room_id=customer_room_id, transfer=True)
    is_agent = puppet.agent_manager.is_agent(agent_id=evt.sender.mxid)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if is_agent:
        transfer_author = evt.sender.mxid
    else:
        agent_id = await puppet.agent_manager.get_room_agent(room_id=customer_room_id)
        transfer_author = agent_id

    portal: Portal = await Portal.get_by_room_id(room_id=customer_room_id)
    queue: Queue = await Queue.get_by_room_id(room_id=campaign_room_id)
    # Creating a task that will be executed in the background.
    asyncio.create_task(
        puppet.agent_manager.loop_agents(
            portal=portal,
            queue=queue,
            agent_id=puppet.agent_manager.CURRENT_AGENT.get(campaign_room_id),
            transfer_author=transfer_author or evt.sender.mxid,
        )
    )


@command_handler(
    name="transfer_user",
    help_text=(
        "Command that transfers a user from one agent to another, "
        "if you send `force` in `yes`, "
        "the agent is always going to be assigned to the chat no matter the agent presence."
    ),
    help_args=[_customer_room_id],
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

    try:
        customer_room_id = evt.args_list[0]
        agent_id = evt.args_list[1]
    except IndexError:
        detail = "You have not sent the all arguments"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    portal: Portal = await Portal.get_by_room_id(room_id=customer_room_id)
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=portal.room_id)

    try:
        force = evt.args_list[2]
    except IndexError:
        force = "no"

    if not puppet:
        return

    # Checking if the room is locked, if it is, it returns.
    if puppet.room_manager.is_room_locked(room_id=portal.room_id, transfer=True):
        evt.log.debug(f"Room: {portal.room_id} LOCKED by Transfer user")
        return

    evt.log.debug(f"INIT TRANSFER for {portal.room_id} to AGENT {agent_id}")

    # Locking the room so that no other transfer can be made to the room.
    puppet.room_manager.lock_room(room_id=portal.room_id, transfer=True)
    is_agent = puppet.agent_manager.is_agent(agent_id=evt.sender.mxid)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if is_agent:
        transfer_author = evt.sender.mxid
    else:
        _agent_id = await puppet.agent_manager.get_room_agent(room_id=portal.room_id)
        transfer_author = _agent_id

    # Checking if the agent is already in the room, if so, it sends a message to the room.
    if transfer_author == agent_id:
        msg = f"The {agent_id} agent is already in the room {portal.room_id}"
        await evt.intent.send_notice(room_id=portal.room_id, text=msg)
    else:
        # Switch between presence and agent operation login using config parameter
        # to verify if agent is available to be assigned to the chat
        if evt.config["acd.use_presence"]:
            presence_response = await puppet.agent_manager.get_agent_presence(agent_id=agent_id)
            is_agent_online = (
                presence_response and presence_response.presence == PresenceState.ONLINE
            )
        else:
            presence_response = await puppet.agent_manager.get_agent_status(agent_id=agent_id)
            is_agent_online = (
                presence_response
                and presence_response.get("presence") == QueueMembershipState.Online.value
            )

        evt.log.debug(
            f"PRESENCE RESPONSE: "
            f"[{agent_id}] -> "
            f"""[{presence_response.get('presence') or presence_response.presence
            if presence_response else None}]"""
        )

        if is_agent_online or force == "yes":
            await puppet.agent_manager.force_invite_agent(
                portal=portal,
                agent_id=agent_id,
                transfer_author=transfer_author or evt.sender.mxid,
            )
        else:
            msg = f"Agent {agent_id} is not available"
            await evt.intent.send_notice(room_id=portal.room_id, text=msg)

    puppet.room_manager.unlock_room(room_id=portal.room_id, transfer=True)
