from __future__ import annotations

import asyncio
from argparse import ArgumentParser, Namespace
from typing import Any, Dict

from mautrix.types import RoomID, UserID

from ..events import ACDEventTypes, ACDPortalEvents, TransferEvent
from ..portal import Portal, PortalState
from ..puppet import Puppet
from ..queue import Queue
from ..user import User
from ..util import Util
from .handler import CommandArg, CommandEvent, command_handler

agent_arg = CommandArg(
    name="--agent or -a",
    help_text="Agent to which the chat is distributed",
    is_required=True,
    example="@agent1:foo.com",
)

force_arg = CommandArg(
    name="--force or -f",
    help_text="It's a flag that is used to decide if check the agent presence or join directly to room",
    is_required=False,
    example="`yes` | `no`",
)

queue_arg = CommandArg(
    name="--queue-room-id or -q",
    help_text="Campaign room_id  where the customer will be transferred",
    is_required=True,
    example="`!foo:foo.com`",
)

portal_arg = CommandArg(
    name="--portal or -p",
    help_text="Customer room_id to be transferred",
    is_required=True,
    example="`!foo:foo.com`",
)


def args_parser():
    parser = ArgumentParser(description="TRANSFER", exit_on_error=False)
    parser.add_argument("--portal", "-p", dest="portal", type=str, required=True)
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--queue-room-id",
        "-q",
        dest="queue",
        type=str,
        required=False,
    )
    group.add_argument(
        "--agent",
        "-a",
        dest="agent",
        type=str,
        required=False,
    )
    parser.add_argument(
        "--force",
        "-f",
        dest="force",
        required=False,
        type=str,
        choices=["yes", "no"],
        default="no",
    )

    return parser


@command_handler(
    name="transfer",
    help_text=("Command that transfers a client to an campaign_room."),
    help_args=[portal_arg, queue_arg],
    args_parser=args_parser(),
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
    args: Namespace = evt.cmd_args
    customer_room_id: RoomID = args.portal
    campaign_room_id: RoomID = args.queue

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    if not puppet:
        return

    # Checking if the room is locked, if it is, it returns.
    if portal.is_locked:
        evt.log.debug(f"Room: {portal.room_id} LOCKED by Transfer room")
        return Util.create_response_data(
            detail="Current portal is locked by transfer", room_id=portal.room_id, status=423
        )

    evt.log.debug(f"INIT TRANSFER for {portal.room_id} to ROOM {campaign_room_id}")

    # Locking the room so that no other transfer can be made to the room.
    portal.lock(transfer=True)

    # Getting the current agent in the room, if the sender is an agent,
    # it sets the transfer author to the sender,
    # if not, it sets the transfer author to the agent in the room,
    # if there is no agent in the room, it sets the transfer author to the sender.
    agent_in_portal: User = await portal.get_current_agent()

    if evt.sender.is_agent:
        transfer_author = evt.sender
    elif agent_in_portal:
        transfer_author = agent_in_portal
    else:
        transfer_author = evt.sender

    queue: Queue = await Queue.get_by_room_id(room_id=campaign_room_id)

    await send_transfer_event(
        portal=portal, puppet=puppet, sender=transfer_author.mxid, destination=queue.room_id
    )

    # Changing portal state to ENQUEUED by transfer command
    await portal.update_state(PortalState.ENQUEUED)

    # Creating a task that will be executed in the background.
    asyncio.create_task(
        puppet.agent_manager.loop_agents(
            portal=portal,
            queue=queue,
            agent_id=puppet.agent_manager.CURRENT_AGENT.get(campaign_room_id),
            transfer_author=transfer_author,
        )
    )

    return Util.create_response_data(
        detail="Transfer action in process", room_id=evt.room_id, status=200
    )


@command_handler(
    name="transfer_user",
    help_text=(
        "Command that transfers a user from one agent to another, "
        "if you send `force` in `yes`, "
        "the agent is always going to be assigned to the chat no matter the agent presence."
    ),
    help_args=[portal_arg, agent_arg, force_arg],
    args_parser=args_parser(),
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
    args: NameError = evt.cmd_args
    customer_room_id: RoomID = args.portal
    agent_id: UserID = args.agent
    force: bool = True if args.force == "yes" else False

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    agent: User = await User.get_by_mxid(agent_id, create=False)
    if not agent:
        return Util.create_response_data(
            detail="Agent with given user id does not exist", room_id=portal.room_id, status=404
        )

    if not puppet:
        return

    # Checking if the room is locked, if it is, it returns.
    if portal.is_locked:
        evt.log.debug(f"Room: {portal.room_id} LOCKED by Transfer user")
        return Util.create_response_data(
            detail="Current portal is locked by transfer", room_id=portal.room_id, status=423
        )

    evt.log.debug(f"INIT TRANSFER for {portal.room_id} to AGENT {agent.mxid}")

    # Locking the room so that no other transfer can be made to the room.
    portal.lock(transfer=True)

    # Checking if the sender is an agent, if not, it gets the agent id from the room.
    if evt.sender.is_agent:
        transfer_author = evt.sender
    else:
        _agent: User = await portal.get_current_agent()

        transfer_author: User = _agent or evt.sender

    agent_displayname: str = await agent.get_displayname()
    json_response: Dict(str, Any) = {}

    try:
        # Checking if the agent is already in the room, if so, it sends a message to the room.
        if transfer_author.mxid == agent.mxid:
            msg = (
                f"The agent [{agent_displayname}][{agent.mxid}] "
                f"is already in the room {portal.room_id}"
            )
            await portal.send_notice(text=msg)
            json_response = Util.create_response_data(detail=msg, room_id=evt.room_id, status=409)
        else:
            agent_is_online = await agent.is_online()
            if agent_is_online or force:
                await send_transfer_event(
                    portal=portal,
                    puppet=puppet,
                    sender=transfer_author.mxid,
                    destination=agent.mxid,
                )

                await puppet.agent_manager.force_invite_agent(
                    portal=portal,
                    agent_id=agent.mxid,
                    transfer_author=transfer_author or evt.sender,
                )

                if not agent_is_online:
                    json_response = Util.create_response_data(
                        detail=(
                            f"The agent {agent_displayname} has been assigned, "
                            "but they are not available to attend the chat."
                        ),
                        room_id=evt.room_id,
                        status=202,
                    )

                    if evt.config["acd.unavailable_agent_in_transfer"]:
                        msg = evt.config["acd.unavailable_agent_in_transfer"].format(
                            agentname=agent_displayname
                        )
                        await portal.send_formatted_message(msg)
                else:
                    msg = evt.config["acd.transfer_message"].format(agentname=agent_displayname)
                    json_response = Util.create_response_data(
                        detail=msg, room_id=evt.room_id, status=200
                    )
            else:
                msg = f"Agent [{agent_displayname}][{agent.mxid}] is not available"
                await portal.send_notice(text=msg)
                json_response = Util.create_response_data(
                    detail=msg, room_id=evt.room_id, status=404
                )
    except Exception as e:
        evt.log.exception(e)

    future_key = Util.get_future_key(room_id=portal.room_id, agent_id=agent.mxid, transfer=True)
    if future_key not in puppet.agent_manager.PENDING_INVITES:
        portal.unlock(transfer=True)

    return json_response


async def send_transfer_event(
    portal: Portal, puppet: Puppet, sender: UserID, destination: UserID | RoomID
):
    """It sends a transfer event

    Parameters
    ----------
    portal : Portal
        The Portal object that is being transferred
    puppet : Puppet
        The puppet that is sending the event
    sender : UserID
        The user who initiated the transfer.
    destination : UserID | RoomID
        The user ID or room ID of the destination.

    """

    transfer_event = TransferEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.Transfer,
        state=PortalState.PENDING,
        prev_state=portal.state,
        sender=sender,
        room_id=portal.room_id,
        acd=puppet.mxid,
        customer_mxid=portal.creator,
        destination=destination,
    )
    await transfer_event.send()
