from argparse import ArgumentParser
from typing import Dict

from .handler import CommandArg, CommandEvent, command_handler

cmd_arg = CommandArg(
    name="command",
    help_text="Command that will be forwarded for the acd[n] that listens to it.",
    is_required=True,
    example="!wa help",
)


def args_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Bridge command", exit_on_error=False)
    parser.add_argument("command", type=str, help="Command that will be relayed")
    return parser


@command_handler(
    name="br_cmd",
    help_text=("This command works as an echo"),
    help_args=[cmd_arg],
    args_parser=args_parser(),
)
async def br_cmd(evt: CommandEvent) -> Dict:
    """It takes the command arguments, joins them together, and sends them to the room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dictionary

    """

    if not evt.cmd_args:
        detail = "You have not sent the argument command"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    await evt.intent.send_text(room_id=evt.room_id, text=evt.cmd_args.command)
