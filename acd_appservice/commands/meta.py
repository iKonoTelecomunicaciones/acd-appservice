from __future__ import annotations

from mautrix.types import EventID

from .. import VERSION
from .handler import CommandEvent, command_handler, command_handlers


def make_help_text(command_prefix: str) -> str:
    """It takes a command prefix and returns a string containing a markdown formatted help message

    Parameters
    ----------
    command_prefix : str
        The prefix that the bot will look for when it's trying to find a command.

    Returns
    -------
        A string with the help text for all the commands.

    """
    text = (
        "# Description of commands\n"
        "If you want to know more information about each command, "
        f"send **{command_prefix}** _cmd_ help"
    )

    text += 2 * "\n"

    for cmd in command_handlers:
        if cmd == "unknown_command":
            continue

        text += f"- **{command_prefix}** {cmd} {command_handlers[cmd].help}"

    return text


@command_handler()
async def unknown_command(evt: CommandEvent) -> EventID:
    return await evt.reply(f"Unknown command. Try **`{evt.command_prefix} help`** for help.")


@command_handler(
    name="help",
    help_text="Show this help message.",
)
async def help_cmd(evt: CommandEvent) -> EventID:
    return await evt.reply(make_help_text(evt.config["bridge.command_prefix"]))


@command_handler(
    name="version",
    help_text="Show this help message.",
)
async def version(evt: CommandEvent) -> EventID:
    return await evt.reply(VERSION)
