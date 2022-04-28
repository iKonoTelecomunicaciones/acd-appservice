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


log: TraceLogger = logging.getLogger("mau.matrix")


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


async def command_processor(command_event: CommandEvent):
    command_event.args = command_event.text.split()
    if command_event.args[0] == "help":
        return make_help_text(
            command_prefix=command_event.acd_appservice.config["bridge.command_prefix"]
        )
    elif command_event.args[0] in command_handlers:
        return await command_handlers[command_event.args[0]]._handler(command_event)
    else:
        return "Unrecognized command"


def make_help_text(command_prefix: str) -> str:
    text = "# Description of commands \n"
    for cmd in command_handlers:
        text = f"{text} * **{command_prefix}** {command_handlers[cmd].help} \n"

    return markdown(text)
