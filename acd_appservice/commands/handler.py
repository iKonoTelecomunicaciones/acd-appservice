from __future__ import annotations

import logging
from typing import Type

from markdown import markdown
from mautrix.util.logging import TraceLogger

from ..commands.typehint import CommandEvent

command_handlers: dict[str, CommandHandler] = {}


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
        actual_name = name or func.__name__.replace("_", "-")
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
    cmd_evt.args = cmd_evt.text.split()
    if cmd_evt.args[0] == "help":
        await cmd_evt.reply(
            make_help_text(command_prefix=cmd_evt.acd_appservice.config["bridge.command_prefix"])
        )
    elif cmd_evt.args[0] in command_handlers:
        await cmd_evt.reply(await command_handlers[cmd_evt.args[0]]._handler(cmd_evt))
    else:
        await cmd_evt.reply("Unrecognized command")


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
    for cmd in command_handlers:
        text = f"{text} * **{command_prefix}** {command_handlers[cmd].help} \n"

    return markdown(text)