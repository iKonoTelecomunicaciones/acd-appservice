from argparse import ArgumentParser

from ..portal import Portal
from ..puppet import Puppet
from .handler import CommandArg, CommandEvent, command_handler

agent = CommandArg(
    name="--agent or -a",
    help_text="Agent mxid where the customer will be distributed",
    is_required=True,
    example="`@agent1:foo.com`",
)

queue = CommandArg(
    name="--queue-room-id or -q",
    help_text="Queue room_id where the customer will be distributed",
    is_required=True,
    example="`!foo:foo.com`",
)

joined_message = CommandArg(
    name="--join-message or -j",
    help_text="Message that will be sent when the agent joins the customer room",
    is_required=False,
    example='"{agentname} join to room"',
)

enqueued_chat = CommandArg(
    name="--enqueue-chat or -e",
    help_text=(
        "If the chat was not distributed, should the portal be enqueued?\n"
        "Note: This parameter is only used when destination is a queue"
    ),
    is_required=False,
    example="`yes` | `no`",
)

force_distribution = CommandArg(
    name="--force-distribution or -f",
    help_text=(
        "You want to force the agent distribution?\n"
        "Note: This parameter is only used when destination is an agent"
    ),
    is_required=False,
    example="`yes` | `no`",
)

customer_room = CommandArg(
    name="--customer-room or -c",
    help_text="Customer room_id to be distributed",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[
        {"description": "Distribute to queue", "args": [queue, enqueued_chat]},
        {"description": "Distribute to agent", "args": [agent, force_distribution]},
    ],
)


def args_parser():
    parser = ArgumentParser(description="ACD", exit_on_error=False)

    parser.add_argument("--customer-room", "-c", dest="customer_room", type=str, required=True)
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
        "--enqueue-chat",
        "-e",
        dest="enqueue_chat",
        required=False,
        type=str,
        choices=["yes", "no"],
        default="yes",
    )
    parser.add_argument(
        "--force-distribution",
        "-f",
        dest="force_distribution",
        required=False,
        type=str,
        choices=["yes", "no"],
        default="no",
    )
    parser.add_argument(
        "--join-message",
        "-j",
        dest="join_message",
        type=str,
        required=False,
    )

    return parser


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "a queue or agent and an optionally joining message can be given."
    ),
    help_args=[customer_room, joined_message],
    args_parser=args_parser(),
)
async def acd(evt: CommandEvent) -> str:
    """It allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    args = evt.cmd_args

    customer_room_id = args.customer_room
    destination = args.queue if args.queue else args.agent
    joined_message = ""
    put_enqueued_portal = False if args.enqueue_chat == "no" else True
    force_distribution = False if args.force_distribution == "no" else True

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    if not puppet:
        return

    portal: Portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    try:
        return await puppet.agent_manager.process_distribution(
            portal=portal,
            destination=destination,
            joined_message=joined_message,
            put_enqueued_portal=put_enqueued_portal,
            force_distribution=force_distribution,
        )
    except Exception as e:
        evt.log.exception(e)
