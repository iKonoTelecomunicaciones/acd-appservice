from __future__ import annotations

from typing import Type

from .. import VERSION
from ..commands.typehint import CommandEvent

command_handlers: dict[str, CommandHandler] = {}

helpers = {
    "help": "Prints this help.",
    "version": "View the software version.",
}


class CommandHandler:
    name: str
    _help_text: str
    _help_args: str

    def __init__(
        self,
        handler: function,
        name: str,
        help_text: str,
        help_args: str,
    ) -> None:
        self._handler = handler
        self.name = name
        self._help_text = help_text
        self._help_args = help_args

    @property
    def help(self) -> str:
        """Returns the help text to this command."""
        return f"{self.name} {self._help_args} - {self._help_text}"


def command_handler(
    _func: function | None = None,
    *,
    name: str | None = None,
    help_text: str = "",
    help_args: str = "",
    _handler_class: Type[CommandHandler] = CommandHandler,
):
    """Decorator to create CommandHandlers"""

    def decorator(func: function) -> CommandHandler:
        actual_name = name or func.__name__
        handler = _handler_class(
            func,
            name=actual_name,
            help_text=help_text,
            help_args=help_args,
        )
        command_handlers[handler.name] = handler
        return handler

    return decorator if _func is None else decorator(_func)


async def command_processor(cmd_evt: CommandEvent):
    """It takes a command event, splits the text into arguments,
    and then calls the appropriate handler function

    Parameters
    ----------
    cmd_evt : CommandEvent
        The CommandEvent object.

    """

    if not cmd_evt.args:
        cmd_evt.args = cmd_evt.text.split()

    cmd_evt.log.debug(f"Incoming command is :: {cmd_evt.args}")

    if cmd_evt.cmd == "help":
        await cmd_evt.reply(make_help_text(command_prefix=cmd_evt.config["bridge.command_prefix"]))
    elif cmd_evt.cmd == "version":
        await cmd_evt.reply(text=f"ACD AS :: v{VERSION}")
    elif cmd_evt.cmd in command_handlers:
        result = await command_handlers[cmd_evt.cmd]._handler(cmd_evt)
        if result:
            return result
    else:
        await cmd_evt.reply(
            text=f"Unrecognized command - Use **`{cmd_evt.command_prefix} help`** for more information"
        )


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
    text = "# Description of commands \n"

    for helper in helpers:
        text = f"{text} * **{command_prefix}** {helper} - {helpers[helper]} \n"

    for cmd in command_handlers:
        text = f"{text} * **{command_prefix}** {command_handlers[cmd].help} \n"

    return text
